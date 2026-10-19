"""
결과 화면의 설명 문장 — 실제 점수와 판정 규칙으로 만든다.

  interpretation: 판정 카드의 해석 문장 (api.ts ResultBase.interpretation). 메인 모델 → rPPG → 결론, 2~3문장
  axis_summary:   판정 근거 상세의 두 축 대조 문장 (api.ts EvidenceResponse.axis_summary.text)
임계값은 settings.py 값을 그대로 읽어 넣는다(예시값이 바뀌면 문장도 따라 바뀐다).
"""
from . import settings
from .fusion import FusionOutcome

DUMMY_PREFIX = '[더미] '

def _ro(value: float) -> str:
    """소수 둘째 자리 숫자 + 조사 '로/으로'. 끝자리 소리에 받침이 있으면 '으로'(0 영·3 삼·6 육), ㄹ받침이나 받침이 없으면 '로'"""
    number = f'{value:.2f}'
    return number + ('으로' if number[-1] in '036' else '로')


# 구간별 점수가 이만큼 벌어지면 가장 높은 구간을 짚어 준다 (문장용 기준, 판정에는 쓰지 않는다)
_PROFILE_SPREAD_NOTE = 0.3

# SQI 항목 이름 (화면 SqiCard의 이름과 같게)
SQI_COMPONENT_LABELS = {'face_pixels': '얼굴 크기', 'compression': '압축 상태', 'illumination': '조명', 'motion': '움직임'}


def interpretation(
    outcome: FusionOutcome,
    p_model: float,
    p_rppg: float,
    sqi: float,
    *,
    face_count: int | None = None,
    profile: list[dict] | None = None,
    rppg_is_dummy: bool = False,
    rppg_mirrors_model: bool = False,
    rppg_measured: dict | None = None,
) -> str:
    """
    face_count: P_model을 낸 얼굴 프레임 수 (없으면 생략)
    profile: 구간별 점수 [{t_start, t_end, p}] (없으면 구간 언급 생략)
    rppg_is_dummy: rPPG 값이 더미면 rPPG 문장 앞에 [더미]
    rppg_mirrors_model: P_rppg가 P_model을 그대로 따라간 경우(더미 키워드 없음, 또는 5단계 분류기 전)
    rppg_measured: 실제 rPPG 신호 분석 결과 {'hr': 심박 또는 None, 'weakest': 가장 낮은 SQI 항목 키} — 4-3부터
    """
    sentences = [_model_sentence(p_model, face_count, profile)]
    if rppg_measured is not None:
        sentences.append(_measured_sentence(outcome, sqi, rppg_measured))
        sentences.append(_conclusion(outcome, mention_low=False))  # 신호 품질 문장을 앞에서 이미 말했다
    else:
        rppg = _rppg_sentence(p_rppg, sqi, rppg_mirrors_model)
        sentences.append((DUMMY_PREFIX if rppg_is_dummy else '') + rppg)
        sentences.append(_conclusion(outcome))
    return ' '.join(sentences)


def _measured_sentence(outcome: FusionOutcome, sqi: float, measured: dict) -> str:
    """실제 rPPG 신호 + 임시 P_rppg(= P_model, 5단계 분류기 전)"""
    weakest = SQI_COMPONENT_LABELS.get(measured.get('weakest'), measured.get('weakest'))
    if outcome.rppg_low_contribution:
        return (f'rPPG 신호 품질이 낮아(SQI {sqi:.2f}, 가장 약한 항목: {weakest}) rPPG는 판정에 반영되지 않았습니다.')
    hr = measured.get('hr')
    found = f'rPPG 신호에서 심박 약 {hr:.0f}BPM을 측정했습니다' if hr is not None else 'rPPG 신호에서 심박을 찾지 못했습니다'
    return (f'{found}(신호 품질 SQI {sqi:.2f}). rPPG의 진짜/가짜 점수는 분류기(5단계)를 붙이기 전이라 '
            '메인 모델 값으로 두어 판정에 영향을 주지 않습니다.')


def _model_sentence(p_model: float, face_count: int | None, profile: list[dict] | None) -> str:
    where = f'얼굴 프레임 {face_count}장에서 ' if face_count else ''
    text = f'메인 모델은 {where}조작 확률을 평균 {_ro(p_model)} 평가했습니다'
    # 영상 끝에 남는 짧은 조각(예: 10~10.07초)은 프레임이 한두 장뿐이라 짚지 않는다
    full = [s for s in profile or [] if s['t_end'] - s['t_start'] >= settings.MAIN_MODEL_SEGMENT_SEC / 2]
    if len(full) >= 2:
        top = max(full, key=lambda s: s['p'])
        low = min(full, key=lambda s: s['p'])
        if top['p'] - low['p'] >= _PROFILE_SPREAD_NOTE:
            return text + f'. 구간별 차이가 커서 {top["t_start"]:g}~{top["t_end"]:g}초 구간이 {_ro(top["p"])} 가장 높았습니다.'
    return text + '.'


def _rppg_sentence(p_rppg: float, sqi: float, mirrors_model: bool) -> str:
    if mirrors_model:
        return 'rPPG 축은 아직 연결 전이라 메인 모델과 같은 값으로 두어 판정에 영향을 주지 않습니다.'
    side = '가짜' if p_rppg >= 0.5 else '진짜'
    return f'rPPG 축은 {_ro(p_rppg)} {side} 쪽이며, 신호 품질(SQI)은 {sqi:.2f}입니다.'


def _conclusion(outcome: FusionOutcome, mention_low: bool = True) -> str:
    real_max, fake_min = settings.SCORE_REAL_MAX, settings.SCORE_FAKE_MIN

    if outcome.verdict == 'hold':
        return (f'두 축의 차이({outcome.axis_gap:.2f})가 상충 기준({settings.CONFLICT_GAP:.2f}) 이상이고 신호 품질도 충분해, '
                '한쪽을 임의로 택하지 않고 판단을 보류합니다. 검토자의 확인이 필요합니다.')

    s = outcome.score
    low = ''
    if outcome.rppg_low_contribution and mention_low:
        low = (f' 신호 품질이 하한({settings.SQI_MIN:.2f})보다 낮아 rPPG 반영 비중이 작으므로(w = {outcome.w:.2f}) '
               '메인 모델 중심의 판정입니다.')

    if s >= fake_min:
        return f'종합 점수 S = {_ro(s)} 가짜 기준({fake_min:.2f}) 이상이라 합성 영상일 가능성이 높습니다.' + low
    if s <= real_max:
        return f'종합 점수 S = {_ro(s)} 진짜 기준({real_max:.2f}) 이하라 실제 촬영 영상일 가능성이 높습니다.' + low
    label = '진짜' if outcome.verdict == 'real' else '가짜'
    return (f'종합 점수 S = {_ro(s)} 진짜·가짜 기준 사이({real_max:.2f}~{fake_min:.2f})의 경계 구간이라, '
            f'현재 규칙(예시값)에 따라 {label}로 판정했습니다. 확신하기 어려운 결과이니 판정 근거를 함께 확인해 주세요.' + low)


def axis_summary(outcome: FusionOutcome, p_model: float, p_rppg: float, sqi: float, *, rppg_mirrors_model: bool = False,
                 rppg_measured: dict | None = None) -> str:
    """두 축 대조 요약. 판정이 아니라 두 점수 값을 기준으로 쓴다(경계 구간 점수를 '낮다'고 쓰지 않도록)"""
    gap = f'축 간 차이 {_ro(outcome.axis_gap)}'
    if rppg_measured is not None:
        if outcome.rppg_low_contribution:
            weakest = SQI_COMPONENT_LABELS.get(rppg_measured.get('weakest'), rppg_measured.get('weakest'))
            return (f'rPPG 미반영(신호 품질 낮음): SQI가 {_ro(sqi)} 하한({settings.SQI_MIN:.2f}) 미만이고 가장 약한 항목은 {weakest}입니다'
                    f'(w = {outcome.w:.2f}). 본 판정은 메인 모델 결과입니다.')
        return (f'rPPG 신호는 측정했지만(SQI {sqi:.2f}) 진짜/가짜 점수는 분류기(5단계) 전이라 메인 모델과 같은 값({p_model:.2f})으로 두었습니다. '
                f'{gap}, 판정은 메인 모델 단독 결과와 같습니다.')
    if rppg_mirrors_model:
        return f'rPPG 축은 아직 연결 전이라 메인 모델과 같은 값({p_model:.2f})으로 두었습니다. {gap}, 판정은 메인 모델 단독 결과와 같습니다.'
    if outcome.rppg_low_contribution:
        return (f'SQI({sqi:.2f})가 하한({settings.SQI_MIN:.2f}) 미만이라 rPPG 축의 반영 비중이 작습니다(w = {outcome.w:.2f}). '
                '본 판정은 메인 모델 중심의 결과입니다.')
    sides = f'메인 모델은 {_side(p_model)} 쪽({p_model:.2f}), rPPG 축은 {_side(p_rppg)} 쪽({p_rppg:.2f})으로 평가했습니다.'
    if outcome.verdict == 'hold':
        return (f'{sides} {gap} 상충 기준({settings.CONFLICT_GAP:.2f}) 이상이며 '
                f'SQI({sqi:.2f})는 하한({settings.SQI_MIN:.2f})을 넘습니다.')
    return f'{sides} {gap} 상충 기준({settings.CONFLICT_GAP:.2f}) 미만이라 두 축의 평가가 크게 어긋나지 않습니다.'


def _side(p: float) -> str:
    return '가짜' if p >= 0.5 else '진짜'
