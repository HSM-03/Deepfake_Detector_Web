"""
부위 간 비교 특징 2개 (사전 등록 7절) — 작업 2가 저장한 부위별 신호(npz)에서 계산한다. 서비스는 이 파일을 쓰지 않는다.

  inner_outer_phase   안쪽–바깥쪽 맥박 위상 차이 크기 (라디안, 0~π). 클수록 타이밍이 어긋남
  inner_outer_corr    안쪽–바깥쪽 신호 일치도 (피어슨 상관, −1~1). 서비스 phase_consistency와 같은 방식을 안쪽–바깥쪽 한 쌍에 적용

세부 계산 (사전 등록에 없는 세부를 값을 보기 전에 정함, 2026-11-10. 이후 UBFC 결과를 보고 바꾸는 것은 계산 오류 수정뿐):
- 맥박 신호: 서비스와 같은 rppg.estimate_pulse(CHROM → Butterworth 대역통과 0.7~4Hz)의 필터 신호
- 안쪽 = 'inner'. 바깥쪽 = 'upper_forehead'와 'edge'를 프레임별 픽셀 수로 가중한 평균 RGB(서비스 'all'과 같은 합치는 방식).
  목은 사전 등록 6절의 사용 여부 결정 전이라 넣지 않는다(결정되면 넣을지를 ③을 열기 전에 정한다)
- 위상 차이: 두 필터 신호의 교차 스펙트럼(Welch와 같은 구간 나누기 — RPPG_PSD_SEGMENT_SEC초, 50% 겹침, Hann 창, RPPG_PSD_GRID_HZ 간격)을
  심박 주파수 f0 ± RPPG_SNR_HALF_WIDTH_HZ 안에서 복소수로 더한 값의 각도 크기. f0 = 서비스 심박(주 영역 face_skin의 스펙트럼 피크).
  심박을 못 찾으면 NaN
- 일치도: 분석 구간 전체의 두 필터 신호의 피어슨 상관계수
"""
import numpy as np

from analysis import dsp, rppg, settings

FEATURE_KEYS = ('inner_outer_phase', 'inner_outer_corr')
OUTER_KEYS = ('upper_forehead', 'edge')


def outer_rgb(data: dict[str, np.ndarray]) -> np.ndarray:
    """바깥쪽 부위들을 프레임별 픽셀 수로 가중해 합친 평균 RGB. 두 부위 모두 0픽셀인 프레임(보간된 프레임)은 단순 평균"""
    rgb = np.stack([data[f'rgb_{k}'].astype(np.float64) for k in OUTER_KEYS])  # (부위, 프레임, 3)
    px = np.stack([data[f'pixels_{k}'].astype(np.float64) for k in OUTER_KEYS])  # (부위, 프레임)
    total = px.sum(axis=0)
    weights = np.where(total > 0, px / np.maximum(total, 1), 1.0 / len(OUTER_KEYS))
    return (rgb * weights[:, :, None]).sum(axis=0)


def cross_spectrum(x: np.ndarray, y: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """dsp.welch와 같은 구간 나누기로 평균한 교차 스펙트럼 X·conj(Y) (복소수, 크기 단위는 위상만 쓰므로 맞추지 않는다)"""
    nperseg = min(int(round(settings.RPPG_PSD_SEGMENT_SEC * fs)), len(x))
    nfft = max(int(round(fs / settings.RPPG_PSD_GRID_HZ)), nperseg)
    window = dsp.hann(nperseg)
    step = nperseg - nperseg // 2
    total = np.zeros(nfft // 2 + 1, dtype=np.complex128)
    for start in range(0, len(x) - nperseg + 1, step):
        a, b = x[start:start + nperseg], y[start:start + nperseg]
        fa = np.fft.rfft((a - a.mean()) * window, n=nfft)
        fb = np.fft.rfft((b - b.mean()) * window, n=nfft)
        total += fa * np.conj(fb)
    return np.fft.rfftfreq(nfft, 1.0 / fs), total


def compute(data: dict[str, np.ndarray]) -> dict:
    """npz 하나(rppg_region.regions.load_npz) → 특징 2개와 확인용 값"""
    fs = float(data['fps'])
    main = rppg.estimate_pulse(data[f'rgb_{settings.RPPG_PRIMARY_ROI}'].astype(np.float64), fs)
    inner = rppg.estimate_pulse(data['rgb_inner'].astype(np.float64), fs)
    outer = rppg.estimate_pulse(outer_rgb(data), fs)
    corr = float(np.corrcoef(inner.filtered, outer.filtered)[0, 1])
    phase = np.nan
    if main.bpm is not None:
        f0 = main.bpm / 60
        freqs, pxy = cross_spectrum(inner.filtered, outer.filtered, fs)
        near = np.abs(freqs - f0) <= settings.RPPG_SNR_HALF_WIDTH_HZ
        phase = float(abs(np.angle(pxy[near].sum())))
    return {
        'inner_outer_phase': phase,
        'inner_outer_corr': corr,
        # 확인용: 각 신호의 심박
        'hr_main_bpm': main.bpm, 'hr_inner_bpm': inner.bpm, 'hr_outer_bpm': outer.bpm,
    }
