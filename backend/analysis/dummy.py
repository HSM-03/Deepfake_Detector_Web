"""
더미 분석 값 — 실제 분석을 붙이기 전에 대신 쓴다. settings.USE_DUMMY_MAIN_MODEL / USE_DUMMY_RPPG가 켜져 있을 때만 쓴다.

프론트엔드 목(frontend/src/mocks/scenarios.ts, evidence.ts)과 같은 시나리오 5종을 파이썬으로 옮겼다.
파일명에 fake / hold / fail(noface) / lowsqi가 있으면 그 시나리오, 아니면 '진짜'.
점수·BPM·특징 기준값은 전부 화면 확인용 예시이며, 판정은 실제 규칙(fusion.py)으로 낸다.
"""
import hashlib
from dataclasses import dataclass, field

import numpy as np

DUMMY_PREFIX = '[더미] '

ROI_KEYS = ('forehead', 'left_cheek', 'right_cheek')
HR_BAND = (0.7, 4.0)  # 심박 대역 Hz (42~240 BPM)


@dataclass
class ScoredScenario:
    p_model: float
    p_model_std: float
    p_rppg: float
    sqi: float
    sqi_components: dict
    roi_bpm: dict  # 추정 실패는 None
    interpretation: str
    periodicity: float  # 근거 파형의 주기성 0~1 (차트 모양용)
    noise: float  # 근거 파형의 잡음 크기
    features: list[dict] = field(default_factory=list)


def _feature(key, label, value, display, reference, judgement, conflict_source=False) -> dict:
    return dict(key=key, label=label, value=value, display=display, reference=reference,
                judgement=judgement, conflict_source=conflict_source)


def _features(hr: str, rows: list[tuple]) -> list[dict]:
    """특징 6개. rows: (값, 표시, 판단, 상충 요인) × 5 — 심박 범위 다음 순서대로"""
    labels = [
        ('snr', '주 피크 SNR', '≥ 3 dB'),
        ('spectral_entropy', '스펙트럼 엔트로피', '≤ 0.60'),
        ('roi_bpm_std', 'ROI 간 심박수 일치도', 'σ ≤ 5 BPM'),
        ('phase_consistency', 'ROI 간 신호 일치도(위상 일관성)', '≥ 0.70'),
        ('window_bpm_var', '윈도우별 BPM 변동성', 'σ ≤ 6 BPM'),
    ]
    out = [_feature('hr_in_range', '심박수 생리학적 범위', 1, hr, '45~180 BPM', 'ok')]
    for (key, label, reference), (value, display, judgement, *conflict) in zip(labels, rows):
        out.append(_feature(key, label, value, display, reference, judgement, bool(conflict and conflict[0])))
    return out


SCENARIOS: dict[str, ScoredScenario] = {
    'real': ScoredScenario(
        p_model=0.22, p_model_std=0.05, p_rppg=0.12, sqi=0.82,
        sqi_components={'face_pixels': 0.91, 'compression': 0.78, 'illumination': 0.84, 'motion': 0.75},
        roi_bpm={'forehead': 72, 'left_cheek': 73, 'right_cheek': 71},
        interpretation='시각 아티팩트가 거의 없고, 세 ROI에서 일관된 심박 신호(약 72 BPM)가 검출되었습니다. 실제 촬영 영상일 가능성이 높습니다.',
        periodicity=1.0, noise=0.25,
        features=_features('72 BPM', [
            (8.4, '8.4 dB', 'ok'), (0.41, '0.41', 'ok'), (0.8, 'σ = 0.8 BPM', 'ok'),
            (0.88, '0.88', 'ok'), (1.6, 'σ = 1.6 BPM', 'ok'),
        ]),
    ),
    'fake': ScoredScenario(
        p_model=0.71, p_model_std=0.11, p_rppg=0.88, sqi=0.76,
        sqi_components={'face_pixels': 0.88, 'compression': 0.71, 'illumination': 0.79, 'motion': 0.66},
        roi_bpm={'forehead': 64, 'left_cheek': 97, 'right_cheek': 118},
        interpretation='얼굴 경계에서 합성 흔적이 관찰되고, 세 ROI의 추정 심박이 서로 크게 다릅니다(64 / 97 / 118 BPM). 합성 영상일 가능성이 높습니다.',
        periodicity=0.12, noise=0.9,
        features=_features('93 BPM', [
            (0.9, '0.9 dB', 'bad'), (0.87, '0.87', 'bad'), (22.2, 'σ = 22.2 BPM', 'bad'),
            (0.31, '0.31', 'bad'), (19.5, 'σ = 19.5 BPM', 'bad'),
        ]),
    ),
    'hold': ScoredScenario(
        p_model=0.21, p_model_std=0.06, p_rppg=0.83, sqi=0.79,
        sqi_components={'face_pixels': 0.9, 'compression': 0.74, 'illumination': 0.81, 'motion': 0.72},
        roi_bpm={'forehead': 58, 'left_cheek': 104, 'right_cheek': 131},
        interpretation='신호 품질은 충분하지만 메인 모델은 진짜 쪽, rPPG 축은 가짜 쪽으로 판단해 두 축이 크게 상충합니다. 임의로 한쪽을 택하지 않고 판단을 보류합니다.',
        periodicity=0.18, noise=0.8,
        features=_features('98 BPM', [
            (1.4, '1.4 dB', 'bad', True), (0.79, '0.79', 'warn'), (30.1, 'σ = 30.1 BPM', 'bad', True),
            (0.36, '0.36', 'bad', True), (12.8, 'σ = 12.8 BPM', 'warn'),
        ]),
    ),
    'low_sqi': ScoredScenario(
        p_model=0.68, p_model_std=0.14, p_rppg=0.35, sqi=0.18,
        sqi_components={'face_pixels': 0.12, 'compression': 0.15, 'illumination': 0.31, 'motion': 0.22},
        roi_bpm={'forehead': 88, 'left_cheek': None, 'right_cheek': 141},
        interpretation='화질이 낮아 생체신호 축의 신뢰도가 떨어집니다. rPPG 기여도 낮음 — 메인 모델 중심 판정입니다.',
        periodicity=0.25, noise=1.4,
        features=_features('88 BPM', [
            (1.1, '1.1 dB', 'bad'), (0.91, '0.91', 'bad'), (26.5, 'σ = 26.5 BPM', 'bad'),
            (0.44, '0.44', 'warn'), (15.2, 'σ = 15.2 BPM', 'bad'),
        ]),
    ),
}

# '분석 불가' 시나리오: 전처리(2/5단계)에서 얼굴 미검출로 중단
FAILED_FACE = {
    'code': 'FACE_NOT_DETECTED',
    'title': DUMMY_PREFIX + '영상에서 얼굴을 충분히 검출하지 못했습니다',
    'stopped_stage': 'preprocess',
    'stopped_stage_index': 2,
    'checks': [
        {'label': '얼굴 검출 프레임 비율', 'measured': '5.3%', 'criterion': '80% 이상', 'passed': False},
        {'label': '평균 얼굴 크기', 'measured': '42×48px', 'criterion': '80×80px 이상', 'passed': False},
    ],
    'suggestions': [
        '정면 얼굴이 10초 이상 연속으로 나오는 구간을 사용해 주세요.',
        '720p 이상 해상도의 영상을 권장합니다.',
        '얼굴이 화면에서 충분히 크게 보이도록 잘라낸 뒤 다시 업로드해 주세요.',
    ],
}


def scenario_from_filename(filename: str) -> str:
    """프론트엔드 목과 같은 규칙. 'real' | 'fake' | 'hold' | 'failed' | 'low_sqi'"""
    name = filename.lower()
    if 'lowsqi' in name or 'low_sqi' in name:
        return 'low_sqi'
    if 'fake' in name:
        return 'fake'
    if 'hold' in name:
        return 'hold'
    if 'fail' in name or 'noface' in name:
        return 'failed'
    return 'real'


@dataclass
class MainModelValues:
    """메인 모델 축의 값. 더미(dummy_main_model)와 실제(3단계, main_model.py) 모두 이 모양으로 넘긴다"""

    p_model: float
    p_model_std: float
    # 구간별 점수 [{t_start, t_end, p}]. None이면 build_evidence가 p_model 둘레로 그림용 값을 만든다(더미)
    profile: list[dict] | None = None


@dataclass
class RppgValues:
    """rPPG 축의 값 (4단계 전까지는 더미)"""

    p_rppg: float
    sqi: float
    sqi_components: dict
    roi_bpm: dict  # 추정 실패는 None
    features: list[dict]
    periodicity: float  # 근거 파형의 주기성 0~1 (차트 모양용)
    noise: float  # 근거 파형의 잡음 크기


# rPPG 값을 바꾸는 키워드 시나리오. 'failed'(얼굴 미검출)는 메인 모델 쪽 실패라 여기서는 쓰지 않는다
_RPPG_KEYWORD_SCENARIOS = ('fake', 'hold', 'low_sqi')


def dummy_main_model(filename: str) -> MainModelValues:
    """더미 메인 모델 값: 파일 이름 키워드로 고른 시나리오의 P_model ('failed'는 호출하는 쪽에서 먼저 걸러야 한다)"""
    s = SCENARIOS[scenario_from_filename(filename)]
    return MainModelValues(p_model=s.p_model, p_model_std=s.p_model_std)


def rppg_follows_model(filename: str) -> bool:
    """키워드가 없어 더미 P_rppg가 P_model을 그대로 따라가는지 (해석 문장에서 그렇게 밝힌다)"""
    return scenario_from_filename(filename) not in _RPPG_KEYWORD_SCENARIOS


def dummy_rppg(filename: str, p_model: float) -> RppgValues:
    """
    더미 rPPG 값.
    - 파일 이름에 키워드(fake / hold / lowsqi)가 있으면 그 시나리오의 rPPG 값 — 판단 보류·신호 품질 낮음 화면 확인용
    - 키워드가 없으면 P_rppg = P_model로 둔다. 그러면 S = P_model이고 두 축 차이가 0이라 판정이 메인 모델과 같다
      (더미 rPPG가 실제 메인 모델의 판정을 바꾸지 않게). SQI·심박·특징·파형은 '진짜' 시나리오 값을 쓴다
    """
    key = scenario_from_filename(filename)
    s = SCENARIOS[key if key in _RPPG_KEYWORD_SCENARIOS else 'real']
    return RppgValues(
        p_rppg=s.p_rppg if key in _RPPG_KEYWORD_SCENARIOS else p_model,
        sqi=s.sqi,
        sqi_components=s.sqi_components,
        roi_bpm=s.roi_bpm,
        features=s.features,
        periodicity=s.periodicity,
        noise=s.noise,
    )


def build_evidence(job_id: str, roi: str, fps: float, duration: float, main: MainModelValues, rppg: RppgValues,
                   w: float, axis_text: str, low_contribution: bool, axis_text_prefix: str = DUMMY_PREFIX) -> dict:
    """
    판정 근거 상세(SCR-04) 응답 하나 (api.ts EvidenceResponse).
    rPPG 부분(파형·스펙트럼·윈도우 BPM)은 주기성·잡음 값으로 합성한 그림용 값이다(4단계 전까지).
    메인 모델 구간 프로파일은 main.profile이 있으면 그대로(실제), 없으면 합성한다(더미).
    같은 작업·부위면 항상 같은 값이 나오도록 작업 ID로 난수 시드를 정한다.
    """
    seed = int(hashlib.sha256(f'{job_id}:{roi}'.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    fs = round(fps) or 30
    duration = min(duration or 20.0, 20.0)

    valid = [b for b in rppg.roi_bpm.values() if b is not None]
    bpm = float(np.mean(valid)) if roi == 'all' else rppg.roi_bpm.get(roi)
    hz = (bpm or 0) / 60
    amp = 0.0 if bpm is None else rppg.periodicity

    # 원신호: 느린 밝기 변동 + 맥파 + 잡음 / 필터 후: 느린 변동 제거
    t = np.arange(int(duration * fs)) / fs
    pulse = amp * np.sin(2 * np.pi * hz * t)
    drift = 0.8 * np.sin(2 * np.pi * 0.08 * t) + 0.3 * np.sin(2 * np.pi * 0.21 * t)
    raw = pulse + drift + rppg.noise * 0.5 * rng.uniform(-1, 1, t.size)
    filtered = pulse + rppg.noise * 0.22 * rng.uniform(-1, 1, t.size)

    # 파워 스펙트럼: 바닥 잡음 + 심박 피크 (주기성이 약하면 여러 개의 작은 봉우리)
    freqs = np.round(np.arange(0, 5.0001, 0.05), 2)
    power = 0.04 + 0.03 * rng.random(freqs.size) + 0.12 * rppg.noise * np.exp(-freqs / 1.5) * rng.random(freqs.size)
    power += amp**2 * np.exp(-((freqs - hz) ** 2) / (2 * 0.06**2))
    if rppg.periodicity < 0.5:
        for lump_hz, lump_power in zip(0.8 + rng.random(4) * 3, 0.1 + rng.random(4) * 0.25):
            power += lump_power * rppg.noise * np.exp(-((freqs - lump_hz) ** 2) / (2 * 0.12**2))
    band = (freqs >= HR_BAND[0]) & (freqs <= HR_BAND[1])
    top = int(np.flatnonzero(band)[np.argmax(power[band])])
    peak = None if bpm is None else {'hz': float(freqs[top]), 'bpm': round(float(freqs[top]) * 60), 'power': round(float(power[top]), 4)}

    # 3초 윈도우 BPM (1초 간격)
    spread = 1.5 if rppg.periodicity >= 0.5 else 22
    window_bpm = [
        {'t_start': start, 'bpm': None if bpm is None else round(bpm + spread * rng.uniform(-1, 1))}
        for start in range(0, int(duration - 3) + 1)
    ]

    # 메인 모델 구간별 프로파일: 실제 값이 있으면 그대로, 없으면 2초 구간으로 합성
    model_profile = main.profile
    if model_profile is None:
        model_profile = []
        start = 0.0
        while start < duration:
            end = min(start + 2, duration)
            p = float(np.clip(main.p_model + main.p_model_std * 1.2 * rng.uniform(-1, 1), 0, 1))
            model_profile.append({'t_start': round(start, 2), 't_end': round(end, 2), 'p': round(p, 3)})
            start = end

    return {
        'job_id': job_id,
        'roi': roi,
        'fs': fs,
        'raw_signal': [{'t': round(float(a), 3), 'v': round(float(b), 4)} for a, b in zip(t, raw)],
        'filtered_signal': [{'t': round(float(a), 3), 'v': round(float(b), 4)} for a, b in zip(t, filtered)],
        'psd': [{'hz': float(f), 'power': round(float(p), 4)} for f, p in zip(freqs, power)],
        'hr_band': list(HR_BAND),
        'peak': peak,
        'roi_bpm': rppg.roi_bpm,
        'roi_bpm_std': round(float(np.std(valid)), 1) if len(valid) >= 2 else None,
        'window_bpm': window_bpm,
        'model_profile': model_profile,
        'features': rppg.features,
        'axis_summary': {
            'p_model': round(main.p_model, 3), 'p_rppg': round(rppg.p_rppg, 3), 'w': w, 'sqi': rppg.sqi,
            'text': axis_text_prefix + axis_text,
        },
        'rppg_low_contribution': low_contribution,
    }
