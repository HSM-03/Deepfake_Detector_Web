"""
rPPG 신호 처리 (상세제안서 기능 4) — Butterworth 대역통과, Welch 파워 스펙트럼, 피크 보간, SNR.

프로젝트의 차별점이라 SciPy를 쓰지 않고 NumPy로 직접 구현한다. 결과가 맞는지는 scipy.signal과 비교하는 시험으로
확인한다(scripts/check_dsp.py).
  - Butterworth는 2차 구간(SOS, second-order sections)으로 설계·적용한다. 저역 차단이 0.7Hz처럼 낮으면
    계수 하나짜리(b, a) 방식은 반올림 오차가 커져 불안정해질 수 있기 때문이다.
  - filtfilt(앞뒤로 한 번씩 적용, 위상 지연 없음)는 scipy.signal.sosfiltfilt와 같은 방식으로 양 끝을 처리한다:
    신호를 양쪽으로 홀수 대칭 연장하고, 필터 초기 상태를 연장한 첫 값에 맞춘다.
"""
import numpy as np


# ── Butterworth 대역통과 (SOS) ──

def butter_bandpass_sos(order: int, low_hz: float, high_hz: float, fs: float) -> np.ndarray:
    """
    order차 Butterworth 대역통과 필터의 SOS 계수 (order×2차 구간이 아니라, 대역통과라 2차 구간 order개).
    scipy.signal.butter(order, [low, high], 'bandpass', fs=fs, output='sos')와 같은 설계 절차:
    아날로그 저역통과 원형 → 주파수 사전 왜곡 → 대역통과 변환 → 쌍선형 변환 → 2차 구간으로 묶기.
    """
    if not 0 < low_hz < high_hz < fs / 2:
        raise ValueError(f'대역({low_hz}~{high_hz}Hz)이 0과 나이퀴스트 주파수({fs / 2}Hz) 사이에 있어야 합니다')
    # 1. 아날로그 저역통과 원형(차단 1rad/s): 왼쪽 반평면 단위원 위의 극점 order개, 영점 없음
    k = np.arange(1, order + 1)
    poles = np.exp(1j * np.pi * (2 * k + order - 1) / (2 * order))

    # 2. 쌍선형 변환이 주파수 축을 휘게 하므로 차단 주파수를 미리 왜곡해 둔다 (표본화 주파수를 2로 정규화한 scipy 방식)
    fs_norm = 2.0
    low, high = (4.0 * np.tan(np.pi * (f / (fs / 2)) / fs_norm) for f in (low_hz, high_hz))

    # 3. 저역통과 → 대역통과: s → (s² + w0²) / (s·bw). 극점 하나가 둘로, 원점에 영점 order개
    bw, w0 = high - low, np.sqrt(low * high)
    half = poles * bw / 2
    root = np.sqrt(half**2 - w0**2)
    poles_bp = np.concatenate([half + root, half - root])
    gain_bp = bw**order

    # 4. 쌍선형 변환: s → 2·fs·(z − 1)/(z + 1). 원점 영점은 z = 1로, 남는 차수만큼 z = −1에 영점
    c = 2.0 * fs_norm
    poles_z = (c + poles_bp) / (c - poles_bp)
    gain_z = gain_bp * np.real(c**order / np.prod(c - poles_bp))

    # 5. 2차 구간으로 묶기: 켤레 극점 한 쌍 + 영점 (z = 1, z = −1) → 분자 (1, 0, −1).
    #    단위원에서 먼 극점부터 앞에 둔다(scipy와 같은 순서, 앞 구간에서 신호가 크게 부풀지 않게)
    upper = poles_z[np.imag(poles_z) > 0]
    upper = upper[np.argsort(np.abs(upper))]
    sos = np.zeros((order, 6))
    for i, p in enumerate(upper):
        sos[i] = [1.0, 0.0, -1.0, 1.0, -2.0 * p.real, abs(p) ** 2]
    sos[0, :3] *= gain_z  # 전체 이득은 첫 구간에 싣는다
    return sos


def sosfilt(sos: np.ndarray, x: np.ndarray, zi: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """2차 구간을 차례로 적용한다(직접형 II 전치). zi: 구간마다 상태 2개 (구간 수 × 2). 출력과 마지막 상태를 돌려준다"""
    y = np.asarray(x, dtype=np.float64).copy()
    state = np.zeros((len(sos), 2)) if zi is None else np.array(zi, dtype=np.float64)
    for s, (b0, b1, b2, _a0, a1, a2) in enumerate(sos):
        z1, z2 = state[s]
        out = np.empty_like(y)
        for n, v in enumerate(y):
            o = b0 * v + z1
            z1 = b1 * v - a1 * o + z2
            z2 = b2 * v - a2 * o
            out[n] = o
        state[s] = z1, z2
        y = out
    return y, state


def sosfilt_zi(sos: np.ndarray) -> np.ndarray:
    """
    계단 입력(값 1이 계속)에 대해 필터가 이미 정상 상태인 것처럼 시작하는 초기 상태 (scipy.signal.sosfilt_zi와 같은 계산).
    구간마다 앞 구간을 지난 계단의 크기(누적 직류 이득)를 곱한다.
    """
    zi = np.zeros((len(sos), 2))
    scale = 1.0
    for s, (b0, b1, b2, a0, a1, a2) in enumerate(sos):
        b = np.array([b0, b1, b2]) / a0
        a = np.array([1.0, a1 / a0, a2 / a0])
        # 정상 상태 조건 (I − Aᵀ)·zi = b[1:] − a[1:]·b[0]  (A: 동반 행렬)
        companion_t = np.array([[-a[1], 1.0], [-a[2], 0.0]])
        zi[s] = np.linalg.solve(np.eye(2) - companion_t, b[1:] - a[1:] * b[0]) * scale
        scale *= b.sum() / a.sum()
    return zi


def sosfiltfilt(sos: np.ndarray, x: np.ndarray) -> np.ndarray:
    """
    앞으로 한 번, 뒤로 한 번 적용해 위상 지연을 없앤다 (scipy.signal.sosfiltfilt 기본값과 같은 양 끝 처리).
      - 연장 길이 = 3 × (2 × 구간 수 + 1 − 끝 계수가 0인 구간 수)
      - 홀수 대칭 연장: 앞쪽은 2·x[0] − x[연장길이:0:−1], 뒤쪽도 같은 방식
      - 초기 상태 = sosfilt_zi × 연장 신호의 첫 값
    """
    x = np.asarray(x, dtype=np.float64)
    trailing_zero = min(int((sos[:, 2] == 0).sum()), int((sos[:, 5] == 0).sum()))
    pad = 3 * (2 * len(sos) + 1 - trailing_zero)
    if len(x) <= pad:
        raise ValueError(f'신호가 너무 짧습니다({len(x)}개). 필터를 적용하려면 {pad}개보다 길어야 합니다')
    ext = np.concatenate([2 * x[0] - x[pad:0:-1], x, 2 * x[-1] - x[-2:-pad - 2:-1]])
    zi = sosfilt_zi(sos)
    forward, _ = sosfilt(sos, ext, zi * ext[0])
    backward, _ = sosfilt(sos, forward[::-1], zi * forward[-1])
    return backward[::-1][pad:-pad]


# ── Welch 파워 스펙트럼 ──

def hann(n: int) -> np.ndarray:
    """주기형 Hann 창 (스펙트럼 분석용. scipy.signal.get_window('hann', n)과 같음)"""
    return 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / n)


def welch(x: np.ndarray, fs: float, nperseg: int, noverlap: int | None = None,
          nfft: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """
    Welch 방법: 신호를 겹치는 구간으로 나눠 구간마다 (평균 제거 → Hann 창 → FFT 제곱)한 뒤 평균한 파워 스펙트럼 밀도.
    nfft > nperseg면 0을 덧붙여(zero-padding) 주파수 간격을 촘촘하게 계산한다 — 실제 해상도(fs/nperseg)는 그대로다.
    scipy.signal.welch(x, fs, 'hann', nperseg, noverlap, nfft, detrend='constant', scaling='density')와 같은 값.
    """
    x = np.asarray(x, dtype=np.float64)
    nperseg = min(nperseg, len(x))
    noverlap = nperseg // 2 if noverlap is None else noverlap
    nfft = max(nfft or nperseg, nperseg)
    window = hann(nperseg)
    scale = 1.0 / (fs * (window**2).sum())
    step = nperseg - noverlap
    starts = range(0, len(x) - nperseg + 1, step)
    power = np.zeros(nfft // 2 + 1)
    for start in starts:
        segment = x[start:start + nperseg]
        spectrum = np.fft.rfft((segment - segment.mean()) * window, n=nfft)
        power += np.abs(spectrum) ** 2
    power *= scale / len(starts)
    # 한쪽 스펙트럼: 음의 주파수 몫을 더한다(직류와, nfft가 짝수면 나이퀴스트 칸 제외)
    power[1:-1 if nfft % 2 == 0 else None] *= 2
    return np.fft.rfftfreq(nfft, 1.0 / fs), power


# ── 피크·SNR ──

def peak_frequency(freqs: np.ndarray, power: np.ndarray, band: tuple[float, float]) -> tuple[float, float] | None:
    """
    band 안에서 가장 큰 피크의 주파수와 파워. 이웃 두 칸과 함께 포물선을 맞춰 칸 사이의 위치를 추정한다(포물선 보간).
    band 안에 값이 없거나 피크가 band 끝에 붙어 있으면(진짜 피크가 아닐 가능성) None.
    """
    inside = np.flatnonzero((freqs >= band[0]) & (freqs <= band[1]))
    if len(inside) < 3:
        return None
    i = inside[np.argmax(power[inside])]
    if i in (inside[0], inside[-1]):
        return None
    a, b, c = power[i - 1], power[i], power[i + 1]
    denom = a - 2 * b + c
    shift = 0.5 * (a - c) / denom if denom != 0 else 0.0
    return float(freqs[i] + shift * (freqs[1] - freqs[0])), float(b - 0.25 * (a - c) * shift)


def snr_db(freqs: np.ndarray, power: np.ndarray, f0: float, band: tuple[float, float],
           half_width: float, harmonic_half_width: float) -> float:
    """
    de Haan & Jeanne(2013, CHROM 논문)의 SNR 정의를 따른다:
      심박 주파수 f0 ± half_width와 2배 주파수 2·f0 ± harmonic_half_width 안의 파워 ÷ band 안 나머지 파워 (dB).
    f0로 정답 심박을 넣으면 '정답 기준 SNR', 추정 심박을 넣으면 '신호가 깨끗한 정도'다.
    """
    in_band = (freqs >= band[0]) & (freqs <= band[1])
    signal = in_band & ((np.abs(freqs - f0) <= half_width) | (np.abs(freqs - 2 * f0) <= harmonic_half_width))
    noise = in_band & ~signal
    if not signal.any() or not noise.any() or power[noise].sum() <= 0:
        return float('nan')
    return float(10 * np.log10(power[signal].sum() / power[noise].sum()))
