"""
메인 모델 판별 (상세제안서 기능 3): 영상 1편 → P_model, 분산, 구간별 점수 프로파일.

  1. 영상 전체에서 프레임을 고르게 MAIN_MODEL_NUM_FRAMES장 뽑는다 (DeepfakeBench와 같은 방식)
  2. 프레임마다 얼굴을 검출·정렬해 256×256으로 자른다 (face_align.py)
  3. EfficientNet-B4로 프레임별 조작 확률을 낸다 (effnb4.py)
  4. 위·아래 이상치를 버린 평균 = P_model, 같은 범위의 표준편차·분산
  5. MAIN_MODEL_SEGMENT_SEC초 구간마다 평균 확률 = 구간별 프로파일

진행률: on_progress(단계, 0~100)로 알린다. 'preprocess'(프레임 추출·얼굴 정렬)는 실제 처리량,
'model'(EfficientNet-B4)은 얼굴을 한 번에 계산해 중간을 알 수 없으므로 경과 시간으로 추정한다.
"""
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import torch

from . import settings
from .effnb4 import EfficientNetB4, load_model, predict_fake_prob, to_input_tensor
from .face_align import FaceAligner
from .video_meta import VideoMeta, read_video_meta

# on_progress(단계, 진행률): 단계는 'preprocess' 또는 'model', 진행률은 0~100.
# 예외를 내면(예: 사용자가 취소함) 분석을 멈춘다. 단, 모델 계산 중에는 다른 스레드에서 불리므로
# 그때 낸 예외는 계산이 끝난 뒤에 다시 낸다(계산 자체는 도중에 끊을 수 없다)
ProgressCallback = Callable[[str, int], None]


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
class FaceStats:
    """얼굴 검출 통계: 뽑은 프레임 = 잡힌 프레임 + 얼굴 없음 + 재검출 탈락"""

    frames_sampled: int
    frames_with_face: int
    frames_no_face: int  # 프레임에서 얼굴을 못 찾음 (화면에 없음, 너무 작음 등)
    frames_recheck_failed: int  # 찾았지만 정렬 후 다시 검출되지 않아 버림 (옆얼굴·가림 등, DeepfakeBench 규칙)
    face_box_mean: tuple[int, int] | None  # 검출된 얼굴 상자의 평균 크기 (가로, 세로 px). 하나도 못 찾으면 None
    frames_retried_full_res: int  # 줄인 사본에서 못 찾아 원본 해상도로 다시 찾은 프레임 수 (그중 찾은 것도, 못 찾은 것도 포함)
    brightness_mean: float  # 뽑은 프레임의 평균 밝기 (흑백 0~255). 분석 불가 안내에서 '어둡다'를 판단할 때 쓴다

    @property
    def face_rate(self) -> float:
        return self.frames_with_face / self.frames_sampled if self.frames_sampled else 0.0


@dataclass
class PreparedFaces:
    """전처리(prepare) 결과 — 모델 계산(score)에 넘긴다. 얼굴 검출률이 기준에 못 미치면 score를 부르지 않고 멈출 수 있다"""

    meta: VideoMeta
    faces: list[np.ndarray]  # 정렬해 자른 RGB 얼굴
    kept: list[int]  # 얼굴마다 원래 프레임 번호
    stats: FaceStats
    timing_sec: dict[str, float]


@dataclass
class MainModelResult:
    p_model: float | None  # 얼굴이 한 장도 없으면 None
    p_model_std: float | None
    p_model_var: float | None
    frames: list[FrameScore]
    profile: list[Segment]
    stats: FaceStats
    # 진단용
    fps: float
    duration_sec: float
    frame_count: int
    trimmed_each_side: int
    timing_sec: dict[str, float] = field(default_factory=dict)

    # 1단계 스크립트가 쓰던 이름
    @property
    def face_rate(self) -> float:
        return self.stats.face_rate

    @property
    def frames_sampled(self) -> int:
        return self.stats.frames_sampled

    @property
    def frames_with_face(self) -> int:
        return self.stats.frames_with_face


class MainModel:
    """
    모델과 얼굴 검출기를 한 번만 불러 두고 영상 여러 편에 쓴다 (불러오는 데 몇 초 걸린다).
    analyze = prepare(프레임 추출·얼굴 정렬) + score(EfficientNet-B4). 워커는 둘 사이에서 얼굴 검출률을 확인한다.
    """

    def __init__(self, weights_path=settings.EFFNB4_WEIGHTS, landmarks_path=settings.DLIB_LANDMARKS):
        torch.set_grad_enabled(False)
        self.model: EfficientNetB4 = load_model(weights_path)
        self.aligner = FaceAligner.load(landmarks_path)

    def analyze(
        self,
        video_path,
        num_frames: int = settings.MAIN_MODEL_NUM_FRAMES,
        meta: VideoMeta | None = None,
        on_progress: ProgressCallback | None = None,
        detect_max_side: int | None = settings.MAIN_MODEL_DETECT_MAX_SIDE,
    ) -> MainModelResult:
        return self.score(self.prepare(video_path, num_frames, meta, on_progress, detect_max_side), on_progress)

    def prepare(
        self,
        video_path,
        num_frames: int = settings.MAIN_MODEL_NUM_FRAMES,
        meta: VideoMeta | None = None,
        on_progress: ProgressCallback | None = None,
        detect_max_side: int | None = settings.MAIN_MODEL_DETECT_MAX_SIDE,
    ) -> PreparedFaces:
        """
        프레임을 고르게 뽑아 얼굴을 정렬한다. 진행률은 'preprocess'로 알린다(추출 0~30%, 얼굴 정렬 30~100%).
        meta: 업로드·검증 단계에서 읽은 영상 정보. 없으면 여기서 읽는다. fps·프레임 수는 반드시 video_meta 방식으로 읽는다
              (브라우저로 녹화한 WebM은 OpenCV가 fps를 1000처럼 엉뚱하게 알려 준다).
        detect_max_side: 얼굴 찾기를 할 때 프레임 긴 변의 최대 크기 (face_align.FaceAligner.align_detail). None이면 원본 그대로
        """
        path = Path(video_path)
        report = _ProgressReporter(on_progress)
        if meta is None:
            meta = read_video_meta(path)
            if meta is None:
                raise ValueError(f'영상을 열 수 없습니다: {path}')
        timing: dict[str, float] = {}

        report('preprocess', 0)
        started = time.perf_counter()
        sampled = _sample_frames(path, num_frames, meta.frame_count, lambda ratio: report('preprocess', 30 * ratio))
        timing['decode'] = time.perf_counter() - started

        started = time.perf_counter()
        faces, kept, boxes, brightness = [], [], [], []
        no_face = recheck_failed = retried = 0
        for n, (index, frame) in enumerate(sampled, start=1):
            brightness.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
            aligned = self.aligner.align_detail(frame, settings.MAIN_MODEL_FACE_SIZE, detect_max_side)
            retried += aligned.retried_full_res
            if aligned.box is not None:
                boxes.append(aligned.box)
            if aligned.status == 'ok':
                faces.append(aligned.face)
                kept.append(index)
            elif aligned.status == 'no_face':
                no_face += 1
            else:
                recheck_failed += 1
            report('preprocess', 30 + 70 * n / len(sampled))
        timing['face'] = time.perf_counter() - started
        report('preprocess', 100)

        stats = FaceStats(
            frames_sampled=len(sampled),
            frames_with_face=len(faces),
            frames_no_face=no_face,
            frames_recheck_failed=recheck_failed,
            face_box_mean=tuple(int(round(v)) for v in np.mean(boxes, axis=0)) if boxes else None,
            frames_retried_full_res=retried,
            brightness_mean=round(float(np.mean(brightness)), 1) if brightness else 0.0,
        )
        return PreparedFaces(meta=meta, faces=faces, kept=kept, stats=stats, timing_sec=timing)

    def score(self, prepared: PreparedFaces, on_progress: ProgressCallback | None = None) -> MainModelResult:
        """정렬된 얼굴로 프레임별 조작 확률을 내고 P_model·분산·구간 프로파일을 만든다. 진행률은 'model'로 알린다"""
        timing = dict(prepared.timing_sec)
        started = time.perf_counter()
        probs = self._predict(prepared.faces, _ProgressReporter(on_progress)) if prepared.faces else []
        timing['model'] = time.perf_counter() - started
        timing['total'] = sum(timing.values())

        meta = prepared.meta
        fps, duration = meta.fps, meta.duration_sec
        frames = [FrameScore(index=i, t=round(i / fps, 3) if fps else 0.0, p=p) for i, p in zip(prepared.kept, probs)]
        mean, std, var, trimmed = _trimmed_stats(probs, settings.MAIN_MODEL_TRIM_RATIO)

        return MainModelResult(
            p_model=mean,
            p_model_std=std,
            p_model_var=var,
            frames=frames,
            profile=_segment_profile(frames, duration, settings.MAIN_MODEL_SEGMENT_SEC),
            stats=prepared.stats,
            fps=fps,
            duration_sec=round(duration, 3),
            frame_count=meta.frame_count,
            trimmed_each_side=trimmed,
            timing_sec={k: round(v, 2) for k, v in timing.items()},
        )

    def _predict(self, faces: list[np.ndarray], report: '_ProgressReporter') -> list[float]:
        """
        얼굴들의 조작 확률. 계산하는 동안 별도 스레드가 0.5초마다 '경과 시간 ÷ 예상 시간'으로 진행률을 알린다(최대 95%).
        진행률 알림이 예외를 내면(취소) 계산이 끝난 뒤 그 예외를 다시 낸다.
        """
        expected = max(settings.MAIN_MODEL_SEC_PER_FACE * len(faces), 0.1)
        stop = threading.Event()
        errors: list[BaseException] = []
        started = time.perf_counter()

        def tick() -> None:
            while not stop.wait(0.5):
                try:
                    report('model', min(95, 100 * (time.perf_counter() - started) / expected))
                except BaseException as error:  # 메인 스레드에서 다시 낸다
                    errors.append(error)
                    return

        report('model', 0)
        ticker = threading.Thread(target=tick, name='main-model-progress', daemon=True)
        ticker.start()
        try:
            probs: list[float] = []
            size = settings.MAIN_MODEL_BATCH_SIZE
            for i in range(0, len(faces), size):
                probs.extend(predict_fake_prob(self.model, to_input_tensor(faces[i : i + size])).tolist())
        finally:
            stop.set()
            ticker.join()
        if errors:
            raise errors[0]
        report('model', 100)
        return probs


class _ProgressReporter:
    """on_progress를 감싼다: 정수로 바꾸고, 같은 값이 거듭되면 다시 알리지 않는다 (Redis 쓰기를 줄인다)"""

    def __init__(self, callback: ProgressCallback | None):
        self.callback = callback
        self.last: dict[str, int] = {}

    def __call__(self, stage: str, percent: float) -> None:
        if self.callback is None:
            return
        value = max(0, min(100, int(percent)))
        if self.last.get(stage) == value:
            return
        self.last[stage] = value
        self.callback(stage, value)


def _sample_frames(
    path: Path, num_frames: int, total: int, on_ratio: Callable[[float], None] | None = None
) -> list[tuple[int, np.ndarray]]:
    """
    영상 처음부터 끝까지 고른 간격으로 num_frames장을 뽑는다(DeepfakeBench의 np.linspace 방식).
    total은 video_meta가 읽은 프레임 수다(OpenCV가 알려 주는 값은 WebM 등에서 틀릴 수 있다).
    프레임 위치로 바로 건너뛰는(seek) 방식은 코덱에 따라 엉뚱한 프레임이 나올 수 있어서,
    처음부터 차례로 읽되 고를 프레임만 실제로 디코딩한다(grab → retrieve). 읽은 비율(0~1)을 on_ratio로 알린다.
    """
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f'영상을 열 수 없습니다: {path}')
    wanted = set(np.linspace(0, max(total - 1, 0), num_frames, endpoint=True, dtype=int).tolist())
    last_wanted = max(wanted)

    frames: list[tuple[int, np.ndarray]] = []
    index = 0
    try:
        while index < total and len(frames) < len(wanted):
            if not cap.grab():
                break
            if index in wanted:
                ok, frame = cap.retrieve()
                if ok:
                    frames.append((index, frame))
                if on_ratio:
                    on_ratio(index / last_wanted if last_wanted else 1.0)
            index += 1
    finally:
        cap.release()
    return frames


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
