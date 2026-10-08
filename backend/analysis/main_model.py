"""
메인 모델 판별 (상세제안서 기능 3): 영상 1편 → P_model, 분산, 구간별 점수 프로파일.

  1. 영상 전체에서 프레임을 고르게 MAIN_MODEL_NUM_FRAMES장 뽑는다 (DeepfakeBench와 같은 방식)
  2. 프레임마다 얼굴을 검출·정렬해 256×256으로 자른다 (face_align.py)
  3. EfficientNet-B4로 프레임별 조작 확률을 낸다 (effnb4.py)
  4. 위·아래 이상치를 버린 평균 = P_model, 같은 범위의 표준편차·분산
  5. MAIN_MODEL_SEGMENT_SEC초 구간마다 평균 확률 = 구간별 프로파일
"""
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch

from . import settings
from .effnb4 import EfficientNetB4, load_model, predict_fake_prob, to_input_tensor
from .face_align import FaceAligner


@dataclass
class FrameScore:
    index: int
    t: float  # 초
    p: float  # 조작 확률


@dataclass
class Segment:
    """API ModelSegment와 같은 모양 (frontend/src/types/api.ts)"""

    t_start: float
    t_end: float
    p: float


@dataclass
class MainModelResult:
    p_model: float | None  # 얼굴이 한 장도 없으면 None
    p_model_std: float | None
    p_model_var: float | None
    frames: list[FrameScore]
    profile: list[Segment]
    # 진단용
    fps: float
    duration_sec: float
    frames_sampled: int
    frames_with_face: int
    trimmed_each_side: int
    timing_sec: dict[str, float] = field(default_factory=dict)

    @property
    def face_rate(self) -> float:
        return self.frames_with_face / self.frames_sampled if self.frames_sampled else 0.0


class MainModel:
    """모델과 얼굴 검출기를 한 번만 불러 두고 영상 여러 편에 쓴다 (불러오는 데 몇 초 걸린다)"""

    def __init__(self, weights_path=settings.EFFNB4_WEIGHTS, landmarks_path=settings.DLIB_LANDMARKS):
        torch.set_grad_enabled(False)
        self.model: EfficientNetB4 = load_model(weights_path)
        self.aligner = FaceAligner.load(landmarks_path)

    def analyze(self, video_path, num_frames: int = settings.MAIN_MODEL_NUM_FRAMES) -> MainModelResult:
        timing: dict[str, float] = {}

        started = time.perf_counter()
        sampled, fps, total = _sample_frames(Path(video_path), num_frames)
        timing['decode'] = time.perf_counter() - started

        started = time.perf_counter()
        faces, kept = [], []
        for index, frame in sampled:
            face = self.aligner.align(frame, settings.MAIN_MODEL_FACE_SIZE)
            if face is not None:
                faces.append(face)
                kept.append(index)
        timing['face'] = time.perf_counter() - started

        started = time.perf_counter()
        probs: list[float] = []
        size = settings.MAIN_MODEL_BATCH_SIZE
        for i in range(0, len(faces), size):
            probs.extend(predict_fake_prob(self.model, to_input_tensor(faces[i : i + size])).tolist())
        timing['model'] = time.perf_counter() - started
        timing['total'] = sum(timing.values())

        duration = total / fps if fps else 0.0
        frames = [FrameScore(index=i, t=round(i / fps, 3) if fps else 0.0, p=p) for i, p in zip(kept, probs)]
        mean, std, var, trimmed = _trimmed_stats(probs, settings.MAIN_MODEL_TRIM_RATIO)

        return MainModelResult(
            p_model=mean,
            p_model_std=std,
            p_model_var=var,
            frames=frames,
            profile=_segment_profile(frames, duration, settings.MAIN_MODEL_SEGMENT_SEC),
            fps=fps,
            duration_sec=round(duration, 3),
            frames_sampled=len(sampled),
            frames_with_face=len(faces),
            trimmed_each_side=trimmed,
            timing_sec={k: round(v, 2) for k, v in timing.items()},
        )


def _sample_frames(path: Path, num_frames: int) -> tuple[list[tuple[int, np.ndarray]], float, int]:
    """
    영상 처음부터 끝까지 고른 간격으로 num_frames장을 뽑는다(DeepfakeBench의 np.linspace 방식).
    프레임 위치로 바로 건너뛰는(seek) 방식은 코덱에 따라 엉뚱한 프레임이 나올 수 있어서,
    처음부터 차례로 읽되 고를 프레임만 실제로 디코딩한다(grab → retrieve).
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f'영상을 열 수 없습니다: {path}')
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    wanted = set(np.linspace(0, max(total - 1, 0), num_frames, endpoint=True, dtype=int).tolist())

    frames: list[tuple[int, np.ndarray]] = []
    index = 0
    while index < total and len(frames) < len(wanted):
        if not cap.grab():
            break
        if index in wanted:
            ok, frame = cap.retrieve()
            if ok:
                frames.append((index, frame))
        index += 1
    cap.release()
    return frames, fps, total


def _trimmed_stats(values: list[float], ratio: float) -> tuple[float | None, float | None, float | None, int]:
    """위·아래에서 각각 ratio만큼 버린 뒤의 평균·표준편차·분산, 그리고 한쪽에서 버린 개수"""
    if not values:
        return None, None, None, 0
    ordered = np.sort(np.asarray(values, dtype=np.float64))
    cut = int(len(ordered) * ratio)
    kept = ordered[cut : len(ordered) - cut] if len(ordered) - 2 * cut > 0 else ordered
    return float(kept.mean()), float(kept.std()), float(kept.var()), cut


def _segment_profile(frames: list[FrameScore], duration: float, segment_sec: float) -> list[Segment]:
    """segment_sec초 구간마다 그 안의 프레임 확률 평균. 얼굴이 하나도 없는 구간은 뺀다"""
    if not frames or duration <= 0:
        return []
    segments: list[Segment] = []
    start = 0.0
    while start < duration:
        end = min(start + segment_sec, duration)
        inside = [f.p for f in frames if start <= f.t < end or (end == duration and f.t == end)]
        if inside:
            segments.append(Segment(t_start=round(start, 2), t_end=round(end, 2), p=round(float(np.mean(inside)), 4)))
        start = end
    return segments
