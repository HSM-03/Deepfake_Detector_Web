"""
판정 근거 상세(SCR-04) 응답을 실제 rPPG 신호로 만든다 (api.ts EvidenceResponse) — 4-3.

ROI 선택 'all'은 주 영역(settings.RPPG_PRIMARY_ROI, 얼굴 피부)의 신호, 'forehead'·'left_cheek'·'right_cheek'는 각 영역의 신호다.
특징 표(features)는 영상 전체 값이라 어느 ROI를 골라도 같다.
화면용으로 파형은 표준편차 1로 맞추고(모양만 보면 되므로), 스펙트럼은 0~5Hz를 0.02Hz 간격으로 줄여 최댓값 1로 맞춘다.
"""
import numpy as np

from . import rppg, settings
from .rppg_features import RppgFeatures

HR_BAND = list(settings.RPPG_BAND_HZ)
_PSD_STEP_HZ = 0.02
_PSD_MAX_HZ = 5.0

# 화면 이름·기준값 표시 (api.ts FeatureRow.label·reference). 기준값은 settings.RPPG_FEATURE_JUDGE의 예시값
_LABELS = {
    'hr_in_range': '심박수 생리학적 범위',
    'snr': '주 피크 SNR',
    'spectral_entropy': '스펙트럼 엔트로피',
    'roi_bpm_std': 'ROI 간 심박수 일치도',
    'phase_consistency': 'ROI 간 신호 일치도(위상 일관성)',
    'window_bpm_var': '윈도우별 BPM 변동성',
}


def feature_rows(features: RppgFeatures) -> list[dict]:
    """특징 6개 → 화면 표의 행. 판단은 settings.RPPG_FEATURE_JUDGE(예시) 기준 ○(ok)/△(warn)/×(bad)"""
    v = features.values
    low, high = settings.RPPG_HR_RANGE_BPM
    hr = features.hr_bpm
    rows = [{
        'key': 'hr_in_range', 'label': _LABELS['hr_in_range'], 'value': v['hr_in_range'],
        'display': '측정 실패' if hr is None else f'{hr:.0f} BPM', 'reference': f'{low:.0f}~{high:.0f} BPM',
        'judgement': 'ok' if v['hr_in_range'] == 1 else 'bad', 'conflict_source': False,
    }]
    for key in ('snr', 'spectral_entropy', 'roi_bpm_std', 'phase_consistency', 'window_bpm_var'):
        value = v[key]
        direction, ok_at, warn_at = settings.RPPG_FEATURE_JUDGE[key]
        if value is None or not np.isfinite(value):
            judgement, display = 'bad', '측정 실패'
        else:
            better = (lambda a, b: a >= b) if direction == 'min' else (lambda a, b: a <= b)
            judgement = 'ok' if better(value, ok_at) else 'warn' if better(value, warn_at) else 'bad'
            display = _display(key, value)
        measured = value is not None and np.isfinite(value)
        # API FeatureRow.value는 숫자여야 해서, 측정 실패면 0을 넣고 display로 실패를 알린다
        rows.append({'key': key, 'label': _LABELS[key], 'value': round(float(value), 4) if measured else 0.0,
                     'display': display, 'reference': _reference(key, direction, ok_at), 'judgement': judgement,
                     'conflict_source': False})
    return rows


def _reference(key: str, direction: str, value: float) -> str:
    """기준값 표시. 예: 'σ ≤ 3.0 BPM', '≥ -1.5 dB', '≤ 0.88'"""
    sign = '≥' if direction == 'min' else '≤'
    if key in ('roi_bpm_std', 'window_bpm_var'):
        return f'σ {sign} {value:.1f} BPM'
    if key == 'snr':
        return f'{sign} {value:.1f} dB'
    return f'{sign} {value:.2f}'


def _display(key: str, value: float) -> str:
    if key == 'snr':
        return f'{value:.1f} dB'
    if key in ('roi_bpm_std', 'window_bpm_var'):
        return f'σ = {value:.1f} BPM'
    return f'{value:.2f}'


def build(job_id: str, roi: str, traces: rppg.RoiTraces, features: RppgFeatures, model_profile: list[dict],
          axis_summary: dict, low_contribution: bool) -> dict:
    """ROI 하나의 근거 응답. roi는 API 선택지('all', 'forehead', 'left_cheek', 'right_cheek')"""
    key = settings.RPPG_PRIMARY_ROI if roi == 'all' else roi
    est = features.estimates[key]
    fs = traces.fps
    n = min(len(est.raw), int(settings.RPPG_EVIDENCE_MAX_SEC * fs))
    t = np.arange(n) / fs

    def wave(x):
        x = np.asarray(x[:n], dtype=np.float64)
        x = x - x.mean()
        scale = x.std() or 1.0
        return [{'t': round(float(a), 3), 'v': round(float(b / scale), 4)} for a, b in zip(t, x)]

    grid = np.round(np.arange(0, _PSD_MAX_HZ + 1e-9, _PSD_STEP_HZ), 2)
    power = np.interp(grid, est.freqs, est.psd)
    top = max(float(power.max()), float(est.psd.max())) or 1.0  # 피크 값이 1을 넘지 않게 원래 스펙트럼의 최댓값도 본다
    roi_bpm = {k: None if b is None else round(float(b), 1) for k, b in features.roi_bpm.items()}
    valid = [b for b in roi_bpm.values() if b is not None]
    peak = None
    if est.bpm is not None:
        hz = est.bpm / 60
        peak = {'hz': round(float(hz), 3), 'bpm': round(float(est.bpm)),
                'power': round(float(np.interp(hz, est.freqs, est.psd) / top), 4)}
    return {
        'job_id': job_id,
        'roi': roi,
        'fs': round(float(fs), 3),
        'raw_signal': wave(est.raw),
        'filtered_signal': wave(est.filtered),
        'psd': [{'hz': float(f), 'power': round(float(p / top), 4)} for f, p in zip(grid, power)],
        'hr_band': HR_BAND,
        'peak': peak,
        'roi_bpm': roi_bpm,
        'roi_bpm_std': round(float(np.std(valid)), 1) if len(valid) >= 2 else None,
        'window_bpm': [{'t_start': s, 'bpm': None if b is None else round(float(b))} for s, b in est.window_bpm],
        'model_profile': model_profile,
        'features': feature_rows(features),
        'axis_summary': axis_summary,
        'rppg_low_contribution': low_contribution,
    }
