"""
직접 구현한 신호 처리(analysis/dsp.py)를 scipy.signal과 비교하는 시험 (docs/backend-plan.md 4단계).

  python -m scripts.check_dsp

비교 항목
  1. Butterworth 대역통과(SOS): 주파수 응답, 초기 상태(sosfilt_zi), sosfiltfilt 출력 — 전체와 양 끝 1초를 따로
  2. Welch 파워 스펙트럼 (zero-padding 포함)
  3. 피크 보간: 주파수를 아는 사인파에서 추정 오차 (SciPy와 무관한 정확도 시험)
  4. 참고: 같은 필터를 계수 하나짜리(b, a) 방식으로 적용했을 때 SOS와의 차이
차이는 신호 표준편차 대비 최대 절대 오차로 적는다. 1e-9 이하면 '같음'으로 본다.
"""
import sys

import numpy as np
from scipy import signal as sp

from analysis import dsp, settings

TOLERANCE = 1e-9


def rel_err(a: np.ndarray, b: np.ndarray, ref: np.ndarray) -> float:
    return float(np.max(np.abs(a - b)) / (np.std(ref) or 1.0))


def test_signal(n: int, fs: float, seed: int) -> np.ndarray:
    """rPPG 원신호와 비슷한 시험 신호: 맥박(1.2Hz) + 느린 밝기 변화 + 큰 직류 + 잡음"""
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    return 120 + 3 * t / t[-1] + 0.8 * np.sin(2 * np.pi * 0.1 * t) + 0.3 * np.sin(2 * np.pi * 1.2 * t) + 0.2 * rng.standard_normal(n)


def main() -> int:
    low, high = settings.RPPG_BAND_HZ
    order = settings.RPPG_FILTER_ORDER
    failures = 0

    def report(name: str, err: float) -> None:
        nonlocal failures
        ok = err <= TOLERANCE
        failures += not ok
        print(f'  {"같음" if ok else "다름"}  {name}: {err:.1e}')

    print(f'1. Butterworth {order}차 대역통과 {low}~{high}Hz (SOS)')
    for fs in (30.0, 29.79, 25.0, 60.0):
        mine = dsp.butter_bandpass_sos(order, low, high, fs)
        ref = sp.butter(order, [low, high], 'bandpass', fs=fs, output='sos')
        w, h_mine = sp.sosfreqz(mine, worN=2048, fs=fs)
        _, h_ref = sp.sosfreqz(ref, worN=2048, fs=fs)
        report(f'fs={fs:g} 주파수 응답(크기·위상)', float(np.max(np.abs(h_mine - h_ref))))
        report(f'fs={fs:g} 초기 상태 sosfilt_zi', float(np.max(np.abs(dsp.sosfilt_zi(mine) - sp.sosfilt_zi(mine)))))
        for n in (300, 600, 2000):
            x = test_signal(n, fs, seed=n)
            y_mine = dsp.sosfiltfilt(mine, x)
            y_ref = sp.sosfiltfilt(ref, x)
            edge = int(round(fs))  # 양 끝 1초. 오차는 필터 후 신호 전체의 표준편차 대비로 잰다
            report(f'fs={fs:g} n={n} sosfiltfilt 전체', rel_err(y_mine, y_ref, y_ref))
            report(f'fs={fs:g} n={n} sosfiltfilt 앞 1초', rel_err(y_mine[:edge], y_ref[:edge], y_ref))
            report(f'fs={fs:g} n={n} sosfiltfilt 뒤 1초', rel_err(y_mine[-edge:], y_ref[-edge:], y_ref))

    print('\n2. Welch 파워 스펙트럼 (Hann, 50% 겹침, zero-padding)')
    for fs in (30.0, 29.79):
        for n, seg_sec in ((300, 10.0), (600, 10.0), (2000, 10.0), (180, 6.0)):
            x = test_signal(n, fs, seed=n + 1)
            nperseg = min(int(round(seg_sec * fs)), n)
            nfft = max(int(round(fs / settings.RPPG_PSD_GRID_HZ)), nperseg)
            f_mine, p_mine = dsp.welch(x, fs, nperseg, nfft=nfft)
            f_ref, p_ref = sp.welch(x, fs, 'hann', nperseg, nperseg // 2, nfft, detrend='constant', scaling='density')
            report(f'fs={fs:g} n={n} 구간 {seg_sec:g}초 주파수 축', float(np.max(np.abs(f_mine - f_ref))))
            report(f'fs={fs:g} n={n} 구간 {seg_sec:g}초 파워', float(np.max(np.abs(p_mine - p_ref)) / p_ref.max()))

    print('\n3. 피크 보간 정확도 (사인파 + 잡음, 정답 주파수를 아는 경우)')
    rng = np.random.default_rng(0)
    for seconds, label in ((10.0, '영상 전체 Welch 10초'), (settings.RPPG_WINDOW_SEC, f'윈도우 {settings.RPPG_WINDOW_SEC:g}초'),
                           (8.0, '윈도우 8초')):
        fs = 30.0
        errors_raw, errors_interp = [], []
        for _ in range(200):
            true_hz = rng.uniform(0.8, 3.0)
            t = np.arange(int(seconds * fs)) / fs
            x = np.sin(2 * np.pi * true_hz * t + rng.uniform(0, 2 * np.pi)) + 0.5 * rng.standard_normal(t.size)
            nperseg = len(x)
            # 보간 없음: zero-padding 없이 가장 큰 칸
            f0, p0 = dsp.welch(x, fs, nperseg)
            band = (f0 >= low) & (f0 <= high)
            errors_raw.append(abs(f0[band][np.argmax(p0[band])] - true_hz) * 60)
            # 제안 방식: zero-padding(0.01Hz 간격) + 포물선 보간
            f1, p1 = dsp.welch(x, fs, nperseg, nfft=int(fs / settings.RPPG_PSD_GRID_HZ))
            peak = dsp.peak_frequency(f1, p1, (low, high))
            errors_interp.append(abs(peak[0] - true_hz) * 60 if peak else np.nan)
        print(f'  {label}: 실제 해상도 {60 / seconds:.1f}BPM | 보간 없음 평균 오차 {np.mean(errors_raw):.2f}BPM'
              f' (최대 {np.max(errors_raw):.2f}) | 제안 방식 평균 {np.nanmean(errors_interp):.2f}BPM (최대 {np.nanmax(errors_interp):.2f})')

    print('\n4. 참고: 계수 하나짜리(b, a) 방식과 SOS 방식의 차이 (scipy 둘 다)')
    for fs in (30.0, 60.0):
        for o in (order, 8):
            b, a = sp.butter(o, [low, high], 'bandpass', fs=fs)
            sos = sp.butter(o, [low, high], 'bandpass', fs=fs, output='sos')
            x = test_signal(2000, fs, seed=7)
            y_ba = sp.filtfilt(b, a, x)
            y_sos = sp.sosfiltfilt(sos, x)
            print(f'  fs={fs:g} {o}차: (b, a) 방식과 SOS 방식의 최대 차이 {rel_err(y_ba, y_sos, y_sos):.1e} (신호 표준편차 대비)')

    print(f'\n결과: {"모두 같음" if failures == 0 else f"{failures}개 항목이 다름"}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
