"""
rPPG 분류기 개선 작업 1 — 판정 기준선 재결정 (docs/rppg-region-preregistration.md 5절). 새 분석 없이 저장된 값으로 다시 계산한다.

  python -m scripts.rederive_baseline            (backend/ 에서, Windows 파이썬 또는 컨테이너)

- 데이터: 5-5 Celeb-DF 검증 세트(backend/out/stage5/celebdf_val.jsonl, 평가 세트 밖). 얼굴 미검출은 빼고 개수만 적는다.
  P_rppg는 서비스와 같은 분류기(analysis/p_rppg_model.json)로 특징 6개에서 계산한다.
- 메인 모델 판정은 P_model로만 낸다(S 가중 평균은 판정에서 뺀다, 사전 등록 3절).
  (A) P_model ≤ 0.4 진짜 / ≥ 0.6 가짜, 그 사이는 진짜·가짜·보류 중 하나  (B) 기준선 하나 t: P_model ≥ t 가짜, 그 아래 진짜
- rPPG 비대칭 규칙(3절): τ는 ②로 정하기 전이므로 '메인 모델 가짜 + SQI ≥ 하한 + |P_model − P_rppg| ≥ 상충 임계 → 보류'만 적용한다.
  메인 모델 진짜 줄(P_rppg ≥ τ → 보류)은 τ가 정해지면 같은 표로 다시 계산한다(2026-10-31 결정).
- 지표(1·2절): 진짜 오판율 = 진짜 중 가짜·보류 / 진짜, 가짜 놓침률 = 가짜 중 진짜 / 가짜, 보류 비율 = 보류 / 전체. 윌슨 95% 신뢰구간.
- 선택(2절): 진짜 오판율 ≤ 10% 이고 보류 ≤ 20%인 후보 중 가짜 놓침률 최소. 없으면 진짜 오판율 최소 → 가짜 놓침률 → 보류 순, '상한 미충족'.
  상한을 만족하는 후보끼리 가짜 놓침률이 같으면 진짜 오판율이 낮은 후보, 그래도 같으면 보류가 적은 후보(사전 등록에 없어 이 스크립트에서 정함).
"""
import json
from pathlib import Path

import numpy as np

from analysis import p_rppg as p_rppg_model
from analysis import settings

OUT_DIR = Path(__file__).resolve().parents[1] / 'out'
VAL_PATH = OUT_DIR / 'stage5' / 'celebdf_val.jsonl'
RESULT_PATH = OUT_DIR / 'rppg_region' / 'work1_baseline.json'

REAL_MISJUDGE_CAP = 0.10  # 사전 등록 2절 (2026-10-28 확정)
HOLD_CAP = 0.20  # 5단계 사전 등록 5절, 그대로 유지
A_LOW, A_HIGH = 0.4, 0.6
B_THRESHOLDS = (0.4, 0.5, 0.6, 0.7)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(centre - half, 4), round(centre + half, 4))


def main_verdict(pm: float, candidate: tuple) -> str:
    kind, value = candidate
    if kind == 'A':
        if pm <= A_LOW:
            return 'real'
        if pm >= A_HIGH:
            return 'fake'
        return value  # 경계 구간 판정
    return 'fake' if pm >= value else 'real'


def final_verdict(main: str, pm: float, pr: float, sqi: float, use_rppg: bool) -> str:
    if use_rppg and main == 'fake' and sqi >= settings.SQI_MIN and abs(pm - pr) >= settings.CONFLICT_GAP:
        return 'hold'
    return main


def metrics(v: np.ndarray, labels: np.ndarray) -> dict:
    real, fake = labels == 'real', labels == 'fake'
    k_rm = int((real & (v != 'real')).sum())
    k_fm = int((fake & (v == 'real')).sum())
    k_hold = int((v == 'hold').sum())
    n_real, n_fake, n = int(real.sum()), int(fake.sum()), len(v)
    return {
        'real_misjudge': {'k': k_rm, 'n': n_real, 'rate': round(k_rm / n_real, 4), 'ci95': wilson(k_rm, n_real)},
        'fake_miss': {'k': k_fm, 'n': n_fake, 'rate': round(k_fm / n_fake, 4), 'ci95': wilson(k_fm, n_fake)},
        'hold': {'k': k_hold, 'n': n, 'rate': round(k_hold / n, 4), 'ci95': wilson(k_hold, n)},
        'real_as_fake': int((real & (v == 'fake')).sum()),
        'real_as_hold': int((real & (v == 'hold')).sum()),
        'fake_as_hold': int((fake & (v == 'hold')).sum()),
    }


def name_of(candidate: tuple) -> str:
    kind, value = candidate
    return f'A 경계={value}' if kind == 'A' else f'B t={value}'


def main() -> int:
    rows = [json.loads(line) for line in VAL_PATH.read_text(encoding='utf-8').splitlines() if line.strip()]
    failed = [r for r in rows if 'failed' in r]
    rows = [r for r in rows if 'failed' not in r]
    labels = np.array([r['label'] for r in rows])
    p_model = np.array([r['p_model'] for r in rows])
    sqi = np.array([r['sqi']['value'] for r in rows])
    model = p_rppg_model.load_model()
    p_rppg = np.array([p_rppg_model.p_rppg(r['features'], model) for r in rows])

    print(f'검증 세트: 분석 {len(rows)}편(진짜 {(labels == "real").sum()}, 가짜 {(labels == "fake").sum()}), 얼굴 미검출 제외 {len(failed)}편')
    print(f'SQI 하한({settings.SQI_MIN}) 이상 {int((sqi >= settings.SQI_MIN).sum())}편, 상충 임계 {settings.CONFLICT_GAP}\n')

    candidates = [('A', b) for b in ('real', 'fake', 'hold')] + [('B', t) for t in B_THRESHOLDS]
    table = []
    for c in candidates:
        mains = [main_verdict(pm, c) for pm in p_model]
        entry = {'candidate': name_of(c)}
        for key, use in (('main_only', False), ('with_rppg', True)):
            v = np.array([final_verdict(m, pm, pr, q, use) for m, pm, pr, q in zip(mains, p_model, p_rppg, sqi)])
            entry[key] = metrics(v, labels)
        table.append(entry)

    def fmt(m: dict, key: str) -> str:
        x = m[key]
        return f'{x["k"]:>3}/{x["n"]:<3} {x["rate"]:6.1%} [{x["ci95"][0]:.1%}, {x["ci95"][1]:.1%}]'

    print(f'{"후보":<12} {"방식":<8} {"진짜 오판율":<26} {"가짜 놓침률":<26} {"보류 비율":<26}')
    for e in table:
        for key, label in (('main_only', '메인단독'), ('with_rppg', 'rPPG규칙')):
            m = e[key]
            print(f'{e["candidate"]:<12} {label:<8} {fmt(m, "real_misjudge"):<26} {fmt(m, "fake_miss"):<26} {fmt(m, "hold"):<26}')

    def r(e, k):
        return e['with_rppg'][k]['rate']

    allowed = [e for e in table if r(e, 'real_misjudge') <= REAL_MISJUDGE_CAP and r(e, 'hold') <= HOLD_CAP]
    if allowed:
        chosen = min(allowed, key=lambda e: (r(e, 'fake_miss'), r(e, 'real_misjudge'), r(e, 'hold')))
        caps_met = True
    else:
        chosen = min(table, key=lambda e: (r(e, 'real_misjudge'), r(e, 'fake_miss'), r(e, 'hold')))
        caps_met = False
    print(f'\n상한(진짜 오판율 ≤ {REAL_MISJUDGE_CAP:.0%}, 보류 ≤ {HOLD_CAP:.0%}) 만족 후보: {[e["candidate"] for e in allowed] or "없음"}')
    print(f'선택: {chosen["candidate"]}' + ('' if caps_met else ' (상한 미충족 — 진짜 오판율이 가장 낮은 후보)'))

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps({
        'rule': 'docs/rppg-region-preregistration.md 5절, τ 전(메인 가짜 + 상충 → 보류만)',
        'n_analyzed': len(rows), 'n_failed': len(failed),
        'n_sqi_above_min': int((sqi >= settings.SQI_MIN).sum()),
        'settings': {'sqi_min': settings.SQI_MIN, 'conflict_gap': settings.CONFLICT_GAP,
                     'real_misjudge_cap': REAL_MISJUDGE_CAP, 'hold_cap': HOLD_CAP},
        'candidates': table, 'allowed': [e['candidate'] for e in allowed],
        'chosen': chosen['candidate'], 'caps_met': caps_met,
    }, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'저장: {RESULT_PATH}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
