"""
rPPG 특징 6개 (상세제안서 기능 5, API FeatureKey) — 서비스와 검증 스크립트가 **같은 함수**를 쓴다.

FF++ 25쌍 구분력 검증(scripts/check_rppg_separability.py)과 5단계 P_rppg 분류기가 같은 정의로 이어지도록,
특징 계산은 이 파일 한 곳에만 둔다. 정의를 바꾸면 검증 결과와 분류기가 끊기므로 docs/backend-plan.md의 정의도 함께 고친다.

  API 키              계산 (방식·영역·윈도우는 settings: CHROM, 얼굴 피부 ROI, 8초)
  hr_in_range         영상 전체 심박이 RPPG_HR_RANGE_BPM 안이면 1, 아니면 0 (심박을 못 찾으면 0)
  snr                 주 영역(얼굴 피부)의 SNR, dB (de Haan 2013 방식, dsp.snr_db)
  spectral_entropy    주 영역 스펙트럼을 심박 대역 안에서 합이 1이 되게 나눈 뒤의 엔트로피 ÷ log(칸 수) (0~1, 클수록 평평)
  roi_bpm_std         이마·왼볼·오른볼 세 영역 심박의 표준편차 (BPM, 모집단 표준편차)
  phase_consistency   세 영역 필터 신호끼리의 피어슨 상관계수 3개의 평균 ("ROI 간 상관", 위상 일관성의 대용)
  window_bpm_var      주 영역 윈도우별 심박의 **표준편차** (BPM). 이름은 API 호환 때문에 'var'지만 값은 분산이 아니라 표준편차다
"""
from dataclasses import dataclass

import numpy as np

from . import rppg, settings

FEATURE_KEYS = ('hr_in_range', 'snr', 'spectral_entropy', 'roi_bpm_std', 'phase_consistency', 'window_bpm_var')


@dataclass
class RppgFeatures:
    values: dict[str, float]  # FEATURE_KEYS → 값 (계산할 수 없으면 NaN)
    hr_bpm: float | None  # 주 영역 영상 전체 심박
    roi_bpm: dict[str, float | None]  # 세 영역 심박
    window_bpm: list[tuple[float, float | None]]
    estimates: dict[str, rppg.PulseEstimate]  # 주 영역 + 세 영역 (근거 화면의 파형·스펙트럼에 쓴다)


def compute(traces: rppg.RoiTraces, method: str = settings.RPPG_METHOD,
            roi: str = settings.RPPG_PRIMARY_ROI) -> RppgFeatures:
    est = {k: rppg.estimate_pulse(traces.rgb[k], traces.fps, method) for k in rppg.ROI_KEYS + (roi,)}
    main = est[roi]
    band = (main.freqs >= settings.RPPG_BAND_HZ[0]) & (main.freqs <= settings.RPPG_BAND_HZ[1])
    p = main.psd[band] / main.psd[band].sum()
    entropy = float(-(p * np.log(p + 1e-20)).sum() / np.log(len(p)))
    roi_bpm = {k: est[k].bpm for k in rppg.ROI_KEYS}
    bpms = [b for b in roi_bpm.values() if b is not None]
    signals = [est[k].filtered for k in rppg.ROI_KEYS]
    corr = [np.corrcoef(signals[i], signals[j])[0, 1] for i in range(3) for j in range(i + 1, 3)]
    wins = [b for _, b in main.window_bpm if b is not None]
    low, high = settings.RPPG_HR_RANGE_BPM
    values = {
        'hr_in_range': float(main.bpm is not None and low <= main.bpm <= high),
        'snr': main.snr_db if main.snr_db is not None else np.nan,
        'spectral_entropy': entropy,
        'roi_bpm_std': float(np.std(bpms)) if len(bpms) >= 2 else np.nan,
        'phase_consistency': float(np.mean(corr)),
        'window_bpm_var': float(np.std(wins)) if len(wins) >= 2 else np.nan,
    }
    return RppgFeatures(values=values, hr_bpm=main.bpm, roi_bpm=roi_bpm, window_bpm=main.window_bpm, estimates=est)
