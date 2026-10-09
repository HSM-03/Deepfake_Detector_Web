"""
융합 판정 (상세제안서 기능 6) — 두 축의 점수와 신호 품질로 최종 판정을 낸다.

  w = α·SQI,  S = (1 − w)·P_model + w·P_rppg
  - SQI ≥ 하한 이고 |P_model − P_rppg| ≥ 상충 임계 → 판단 보류 (S는 내지 않는다)
  - 그 외: S ≥ 가짜 기준 → 가짜, S ≤ 진짜 기준 → 진짜, 그 사이 → BOUNDARY_VERDICT (미결정, 예시값)
  - SQI < 하한 → 'rPPG 기여도 낮음' 표시

임계값은 모두 settings.py에 있다(예시값). 판정에 쓴 임계값은 결과와 함께 저장한다(thresholds()).
"""
from dataclasses import dataclass

from . import settings


@dataclass
class FusionOutcome:
    verdict: str  # 'real' | 'fake' | 'hold'
    score: float | None  # S. 판단 보류면 None
    w: float
    axis_gap: float
    rppg_low_contribution: bool
    sqi_grade: str  # 'good' | 'fair' | 'poor'


def thresholds() -> dict:
    """API 응답의 Thresholds 형식 (frontend/src/types/api.ts)"""
    return {
        'score_real_max': settings.SCORE_REAL_MAX,
        'score_fake_min': settings.SCORE_FAKE_MIN,
        'conflict_gap': settings.CONFLICT_GAP,
        'sqi_min': settings.SQI_MIN,
        'alpha': settings.ALPHA,
    }


def sqi_grade(sqi: float) -> str:
    if sqi >= settings.SQI_GOOD_MIN:
        return 'good'
    if sqi >= settings.SQI_MIN:
        return 'fair'
    return 'poor'


def fuse(p_model: float, p_rppg: float, sqi: float) -> FusionOutcome:
    w = settings.ALPHA * sqi
    gap = abs(p_model - p_rppg)
    common = dict(
        w=round(w, 3),
        axis_gap=round(gap, 3),
        rppg_low_contribution=sqi < settings.SQI_MIN,
        sqi_grade=sqi_grade(sqi),
    )

    # 신호를 믿을 만한데 두 축이 크게 엇갈리면, 한쪽을 임의로 택하지 않고 보류한다
    if sqi >= settings.SQI_MIN and gap >= settings.CONFLICT_GAP:
        return FusionOutcome(verdict='hold', score=None, **common)

    score = (1 - w) * p_model + w * p_rppg
    if score >= settings.SCORE_FAKE_MIN:
        verdict = 'fake'
    elif score <= settings.SCORE_REAL_MAX:
        verdict = 'real'
    else:
        verdict = settings.BOUNDARY_VERDICT  # 미결정 구간 (예시값)
    return FusionOutcome(verdict=verdict, score=round(score, 3), **common)
