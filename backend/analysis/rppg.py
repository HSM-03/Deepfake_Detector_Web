"""
rPPG 신호 추출 (상세제안서 기능 2·4) — 얼굴 ROI 추적 → ROI별 평균 RGB → POS/CHROM → 대역통과 → Welch → 심박.

  1. MediaPipe Face Mesh(468점)로 프레임마다 이마·왼볼·오른볼 영역을 잡아 영역 안의 평균 RGB를 기록한다(extract_traces)
  2. 세 색 신호를 POS(Wang 2017) 또는 CHROM(de Haan 2013)으로 맥박 신호 하나로 합친다
  3. Butterworth 대역통과(dsp.py) → Welch 스펙트럼 → 심박 대역 안 가장 큰 피크 = 심박 (포물선 보간)
  4. 윈도우(RPPG_WINDOW_SEC)마다 심박을 다시 재서 시간에 따른 변동을 본다

'왼볼·오른볼'은 영상 속 사람 기준이다(화면에서는 왼볼이 오른쪽에 보인다). MediaPipe 랜드마크 번호도 사람 기준이다.
"""
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import dsp, settings
from .video_meta import VideoMeta, read_video_meta

# ROI 다각형의 꼭짓점이 될 Face Mesh 랜드마크 번호 (이 점들의 볼록 껍질을 ROI로 쓴다)
ROI_LANDMARKS: dict[str, tuple[int, ...]] = {
    # 이마: 눈썹 위부터 이마 위쪽까지
    'forehead': (10, 109, 67, 103, 104, 69, 108, 151, 337, 299, 333, 332, 297, 338),
    # 볼: 광대 아래, 코 옆~턱선 위. 왼볼과 오른볼은 서로 좌우 대칭인 번호
    'left_cheek': (280, 330, 347, 346, 352, 376, 411, 425, 266, 371),
    'right_cheek': (50, 101, 118, 117, 123, 147, 187, 205, 36, 142),
}
ROI_KEYS = tuple(ROI_LANDMARKS)

# 얼굴 피부 전체 ROI(4단계 A 시험): 얼굴 윤곽 안에서 눈·눈썹·입술을 뺀 영역. 평균에 쓰는 픽셀이 세 ROI보다 훨씬 많다.
#   'face'      윤곽 − (눈·눈썹, 입술)
#   'face_skin' 위 영역 중 피부색(YCrCb 범위)인 픽셀만 — 머리카락(앞머리)·그림자·배경을 더 뺀다
#   (코 아래 입·턱을 뺀 영역도 시험했지만 말할 때의 심박 오차가 줄지 않아 넣지 않았다 — 계획서 4단계)
FACE_KEYS = ('face', 'face_skin')
_FACE_OVAL = (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
              176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109)
_FACE_EXCLUDE = (
    # 왼눈+왼눈썹 (사람 기준)
    (263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466,
     276, 283, 282, 295, 285, 300, 293, 334, 296, 336),
    # 오른눈+오른눈썹
    (33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246,
     46, 53, 52, 65, 55, 70, 63, 105, 66, 107),
    # 입술 바깥선
    (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185),
)
# 입 벌림을 잴 윗입술 안쪽(13)·아랫입술 안쪽(14)
_LIP_INNER = (13, 14)
# 피부색 범위 (YCrCb의 Cr·Cb, Chai & Ngan 1999에서 흔히 쓰는 값). 예시값
_SKIN_CR = (133, 173)
_SKIN_CB = (77, 127)

# Face Mesh는 내부에서 얼굴을 작게 줄여 보므로, 큰 프레임은 이 크기로 줄여 넣는다(좌표는 0~1 비율이라 원본에 그대로 쓴다)
_MESH_MAX_SIDE = 640


@dataclass
class RoiTraces:
    """프레임별 ROI 평균 RGB. 얼굴을 놓친 프레임은 앞뒤 값으로 선형 보간했고 tracked가 False다"""

    fps: float
    rgb: dict[str, np.ndarray]  # ROI 이름(+ 'all') → (프레임 수, 3) R·G·B 평균
    pixels: dict[str, np.ndarray]  # ROI 이름 → (프레임 수,) 영역 픽셀 수 (SQI의 얼굴 픽셀 수에 쓴다)
    tracked: np.ndarray  # (프레임 수,) 얼굴을 잡았는지
    # 프레임별 얼굴 위치·크기·입 벌림(px, 못 잡은 프레임은 NaN): 'cx', 'cy', 'width', 'height', 'mouth' — SQI 움직임 항목에 쓴다
    geometry: dict[str, np.ndarray] = field(default_factory=dict)
    # 프레임별 배경 평균 밝기(0~255): 얼굴 상자를 1.6배 넓힌 영역 바깥. 얼굴을 못 잡으면 프레임 전체 — SQI 조명 항목에 쓴다
    background: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def tracked_rate(self) -> float:
        return float(self.tracked.mean()) if len(self.tracked) else 0.0


def extract_traces(video_path, meta: VideoMeta | None = None, on_progress: Callable[[float], None] | None = None,
                   frame_hook: Callable[[int, np.ndarray, dict], None] | None = None) -> RoiTraces:
    """
    영상의 모든 프레임에서 ROI 평균 RGB를 뽑는다 (rPPG는 프레임을 건너뛰면 안 된다).
    frame_hook(프레임 번호, BGR 프레임, ROI 다각형 dict): 확인용(ROI 그림 저장 등)
    """
    import mediapipe as mp  # 무거워서 쓸 때만 불러온다

    path = Path(video_path)
    meta = meta or read_video_meta(path)
    if meta is None:
        raise ValueError(f'영상을 열 수 없습니다: {path}')
    total = meta.frame_count

    sums = {k: [] for k in ROI_KEYS + FACE_KEYS}
    counts = {k: [] for k in ROI_KEYS + FACE_KEYS}
    tracked: list[bool] = []
    geometry: dict[str, list[float]] = {k: [] for k in ('cx', 'cy', 'width', 'height', 'mouth')}
    background: list[float] = []
    cap = cv2.VideoCapture(str(path))
    mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=False,
                                           min_detection_confidence=0.5, min_tracking_confidence=0.5)
    try:
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            height, width = frame.shape[:2]
            scale = min(1.0, _MESH_MAX_SIDE / max(height, width))
            small = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else frame
            found = mesh.process(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)).multi_face_landmarks
            polygons = {}
            face = None
            if found:
                lm = found[0].landmark

                def points(ids):
                    return np.array([[lm[i].x * width, lm[i].y * height] for i in ids], dtype=np.float32)

                for key, ids in ROI_LANDMARKS.items():
                    polygons[key] = cv2.convexHull(points(ids)).astype(np.int32)
                oval = points(_FACE_OVAL)
                face = (oval.astype(np.int32),
                        [cv2.convexHull(points(ids)).astype(np.int32) for ids in _FACE_EXCLUDE])
                polygons['face'] = face  # 확인용(frame_hook): (윤곽, [뺄 영역…])
                (x0, y0), (x1, y1) = oval.min(axis=0), oval.max(axis=0)
                upper_lip, lower_lip = points(_LIP_INNER)
                for key, value in (('cx', (x0 + x1) / 2), ('cy', (y0 + y1) / 2), ('width', x1 - x0), ('height', y1 - y0),
                                   ('mouth', float(np.linalg.norm(lower_lip - upper_lip)))):
                    geometry[key].append(float(value))
            else:
                for values in geometry.values():
                    values.append(np.nan)
            background.append(_background_luma(small, scale, geometry, bool(found)))
            for key in ROI_KEYS:
                total_bgr, n = _polygon_sum(frame, polygons.get(key))
                sums[key].append(total_bgr)
                counts[key].append(n)
            for key, (total_bgr, n) in zip(FACE_KEYS, _face_sums(frame, face)):
                sums[key].append(total_bgr)
                counts[key].append(n)
            tracked.append(bool(found))
            if frame_hook:
                frame_hook(index, frame, polygons)
            index += 1
            if on_progress and total:
                on_progress(min(index / total, 1.0))
    finally:
        cap.release()
        mesh.close()

    tracked_arr = np.array(tracked, dtype=bool)
    rgb, pixels = {}, {}
    for key in ROI_KEYS + FACE_KEYS:
        s = np.array(sums[key], dtype=np.float64)  # (n, 3) BGR 합
        c = np.array(counts[key], dtype=np.float64)
        pixels[key] = c
        rgb[key] = _fill_gaps(s[:, ::-1] / np.maximum(c, 1)[:, None], c > 0)
    # 'all': 세 ROI를 픽셀 수만큼 가중해 합친 평균
    s_all = sum(np.array(sums[k], dtype=np.float64) for k in ROI_KEYS)
    c_all = sum(np.array(counts[k], dtype=np.float64) for k in ROI_KEYS)
    rgb['all'] = _fill_gaps(s_all[:, ::-1] / np.maximum(c_all, 1)[:, None], c_all > 0)
    pixels['all'] = c_all
    return RoiTraces(fps=meta.fps, rgb=rgb, pixels=pixels, tracked=tracked_arr,
                     geometry={k: np.array(v, dtype=np.float64) for k, v in geometry.items()},
                     background=np.array(background, dtype=np.float64))


def _background_luma(small: np.ndarray, scale: float, geometry: dict, found: bool) -> float:
    """얼굴 상자(1.6배로 넓힘) 바깥의 평균 밝기. 줄인 프레임에서 계산한다(밝기 평균이라 해상도 영향이 작다)"""
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    if not found:
        return float(gray.mean())
    cx, cy = geometry['cx'][-1] * scale, geometry['cy'][-1] * scale
    hw, hh = geometry['width'][-1] * scale * 0.8, geometry['height'][-1] * scale * 0.8
    mask = np.ones(gray.shape, dtype=bool)
    mask[max(int(cy - hh), 0):max(int(cy + hh), 0), max(int(cx - hw), 0):max(int(cx + hw), 0)] = False
    return float(gray[mask].mean()) if mask.any() else float(gray.mean())


def _polygon_sum(frame: np.ndarray, polygon: np.ndarray | None) -> tuple[np.ndarray, int]:
    """다각형 안 픽셀의 BGR 합과 픽셀 수. 다각형의 경계 사각형만 잘라 계산한다"""
    if polygon is None or len(polygon) < 3:
        return np.zeros(3), 0
    x, y, w, h = cv2.boundingRect(polygon)
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, frame.shape[1]), min(y + h, frame.shape[0])
    if x1 <= x0 or y1 <= y0:
        return np.zeros(3), 0
    crop = frame[y0:y1, x0:x1]
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillConvexPoly(mask, polygon - [x0, y0], 255)
    n = int(np.count_nonzero(mask))
    if n == 0:
        return np.zeros(3), 0
    return crop[mask > 0].sum(axis=0).astype(np.float64), n


def _face_sums(frame: np.ndarray, face) -> list[tuple[np.ndarray, int]]:
    """얼굴 피부 전체 ROI 세 가지(FACE_KEYS 순서)의 BGR 합과 픽셀 수"""
    empty = [(np.zeros(3), 0)] * len(FACE_KEYS)
    if face is None:
        return empty
    oval, excludes = face
    x, y, w, h = cv2.boundingRect(oval)
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, frame.shape[1]), min(y + h, frame.shape[0])
    if x1 <= x0 or y1 <= y0:
        return empty
    crop = frame[y0:y1, x0:x1]
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [oval - [x0, y0]], 255)
    for poly in excludes:
        cv2.fillConvexPoly(mask, poly - [x0, y0], 0)
    ycrcb = cv2.cvtColor(crop, cv2.COLOR_BGR2YCrCb)
    skin = cv2.inRange(ycrcb, (0, _SKIN_CR[0], _SKIN_CB[0]), (255, _SKIN_CR[1], _SKIN_CB[1]))
    out = []
    for m in (mask, cv2.bitwise_and(mask, skin)):
        n = int(np.count_nonzero(m))
        out.append((crop[m > 0].sum(axis=0).astype(np.float64), n) if n else (np.zeros(3), 0))
    return out


def _fill_gaps(values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """얼굴을 놓친 프레임의 값을 앞뒤 잡힌 프레임으로 선형 보간한다. 하나도 없으면 그대로(0)"""
    if valid.all() or not valid.any():
        return values
    idx = np.arange(len(values))
    return np.stack([np.interp(idx, idx[valid], values[valid, c]) for c in range(values.shape[1])], axis=1)


# ── 색 신호 → 맥박 신호 ──

def pos(rgb: np.ndarray, fs: float, window_sec: float = settings.RPPG_COMBINE_WINDOW_SEC) -> np.ndarray:
    """
    POS (Plane-Orthogonal-to-Skin, Wang et al. 2017, 논문의 Algorithm 1).
    짧은 창마다 색을 창 평균으로 나눠 정규화하고, 피부색 방향에 수직인 평면에 투영한 두 신호를 크기를 맞춰 더한 뒤 겹쳐 더한다.
    """
    n = len(rgb)
    length = int(np.ceil(window_sec * fs))
    projection = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    out = np.zeros(n)
    for start in range(0, n - length + 1):
        c = rgb[start:start + length].T  # (3, length)
        mean = c.mean(axis=1, keepdims=True)
        if np.any(mean == 0):
            continue
        s = projection @ (c / mean)
        std1 = s[1].std()
        h = s[0] + (s[0].std() / std1 if std1 > 0 else 0.0) * s[1]
        out[start:start + length] += h - h.mean()
    return out


def chrom(rgb: np.ndarray, fs: float, window_sec: float = settings.RPPG_COMBINE_WINDOW_SEC) -> np.ndarray:
    """
    CHROM (de Haan & Jeanne 2013). 짧은 창(절반씩 겹침)마다 색을 정규화해 색차 신호 X = 3R − 2G, Y = 1.5R + G − 1.5B를 만들고,
    각각 대역통과한 뒤 S = X − (σX/σY)·Y로 합쳐 Hann 창을 씌워 겹쳐 더한다.
    """
    n = len(rgb)
    length = int(np.ceil(window_sec * fs))
    length += length % 2  # 절반씩 겹치려고 짝수로
    half = length // 2
    sos = dsp.butter_bandpass_sos(settings.RPPG_FILTER_ORDER, *settings.RPPG_BAND_HZ, fs)
    window = dsp.hann(length)
    out = np.zeros(n)
    for start in range(0, n - length + 1, half):
        c = rgb[start:start + length]
        mean = c.mean(axis=0)
        if np.any(mean == 0):
            continue
        r, g, b = (c / mean).T
        x = dsp.sosfiltfilt(sos, 3 * r - 2 * g)
        y = dsp.sosfiltfilt(sos, 1.5 * r + g - 1.5 * b)
        sy = y.std()
        s = x - (x.std() / sy if sy > 0 else 0.0) * y
        out[start:start + length] += window * (s - s.mean())
    return out


COMBINERS = {'pos': pos, 'chrom': chrom}


# ── 맥박 신호 → 심박 ──

@dataclass
class PulseEstimate:
    raw: np.ndarray  # POS/CHROM 결과 (필터 전)
    filtered: np.ndarray  # 대역통과 후
    freqs: np.ndarray  # Welch 스펙트럼
    psd: np.ndarray
    bpm: float | None  # 영상 전체 심박 (피크를 못 찾으면 None)
    peak_power: float | None
    snr_db: float | None  # 추정 심박 기준 SNR
    window_bpm: list[tuple[float, float | None]] = field(default_factory=list)  # (윈도우 시작 초, 심박)


def estimate_pulse(rgb: np.ndarray, fs: float, method: str = settings.RPPG_METHOD,
                   window_sec: float = settings.RPPG_WINDOW_SEC) -> PulseEstimate:
    band = settings.RPPG_BAND_HZ
    raw = COMBINERS[method](rgb, fs)
    sos = dsp.butter_bandpass_sos(settings.RPPG_FILTER_ORDER, *band, fs)
    filtered = dsp.sosfiltfilt(sos, raw)
    freqs, psd = spectrum(filtered, fs, settings.RPPG_PSD_SEGMENT_SEC)
    peak = dsp.peak_frequency(freqs, psd, band)
    snr = snr_at(freqs, psd, peak[0]) if peak else None
    return PulseEstimate(
        raw=raw, filtered=filtered, freqs=freqs, psd=psd,
        bpm=peak[0] * 60 if peak else None, peak_power=peak[1] if peak else None, snr_db=snr,
        window_bpm=window_bpms(filtered, fs, window_sec),
    )


def spectrum(signal: np.ndarray, fs: float, segment_sec: float) -> tuple[np.ndarray, np.ndarray]:
    """Welch 스펙트럼: 구간 segment_sec초(신호가 더 짧으면 전체), 50% 겹침, RPPG_PSD_GRID_HZ 간격으로 계산"""
    nperseg = min(int(round(segment_sec * fs)), len(signal))
    nfft = max(int(round(fs / settings.RPPG_PSD_GRID_HZ)), nperseg)
    return dsp.welch(signal, fs, nperseg, nfft=nfft)


def snr_at(freqs: np.ndarray, psd: np.ndarray, f0_hz: float) -> float:
    return dsp.snr_db(freqs, psd, f0_hz, settings.RPPG_BAND_HZ,
                      settings.RPPG_SNR_HALF_WIDTH_HZ, settings.RPPG_SNR_HARMONIC_HALF_WIDTH_HZ)


def window_bpms(filtered: np.ndarray, fs: float, window_sec: float,
                step_sec: float = settings.RPPG_WINDOW_STEP_SEC) -> list[tuple[float, float | None]]:
    """window_sec초 윈도우를 step_sec초씩 옮기며 윈도우마다 심박을 잰다 (윈도우 하나 = Welch 구간 하나)"""
    length, step = int(round(window_sec * fs)), max(1, int(round(step_sec * fs)))
    out = []
    for start in range(0, len(filtered) - length + 1, step):
        freqs, psd = spectrum(filtered[start:start + length], fs, window_sec)
        peak = dsp.peak_frequency(freqs, psd, settings.RPPG_BAND_HZ)
        out.append((round(start / fs, 3), peak[0] * 60 if peak else None))
    return out
