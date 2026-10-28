"""
5-5 융합 판정 확인 — Celeb-DF 검증 세트(scripts/run_validation.py 결과)에서 메인 모델 단독과 융합을 같은 기준으로 비교하고,
경계 구간 판정을 사전 등록(docs/stage5-preregistration.md 5절) 규칙대로 고른다.

  python -m scripts.evaluate_fusion --mode classifier   P_rppg 분류기(analysis/p_rppg_model.json)를 쓴 융합
  python -m scripts.evaluate_fusion --mode fallback     분류기 실패 시 대안: P_rppg는 판정에 쓰지 않고,
                                                        SQI 양호 + 심박 정상 범위 + 메인 모델 가짜 확신이면 판단 보류

- 판정 규칙은 서비스(analysis/fusion.py)와 같다. 경계 구간(S가 진짜·가짜 기준 사이, 두 축 비상충)만 후보(진짜/가짜/보류)를 바꿔 본다.
- 지표: AUC(점수 기준, 보류와 무관), 확신 오류율 = 진짜/가짜로 판정했는데 틀린 수 ÷ 전체, 보류 비율 = 보류 ÷ 전체, 정확도(보류 제외).
  메인 모델 단독 = S 대신 P_model, 상충 보류 없음, 같은 경계 후보.
- 얼굴 미검출(서비스에서 분석 불가)인 영상은 비교에서 빼고 개수만 적는다.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from analysis import p_rppg as p_rppg_model
from analysis import settings
from scripts.check_rppg_separability import auc

VAL_PATH = Path('/app/out/stage5/celebdf_val.jsonl')
CANDIDATES = ('real', 'fake', 'hold')
HOLD_CAP = 0.20  # 사전 등록 5절 (2026-10-25 확정)


def verdicts(p_model, p_rppg, sqi, hr_ok, boundary, mode, fused):
    """영상별 판정 'real' | 'fake' | 'hold'. fused=False면 메인 모델 단독"""
    out, scores = [], []
    for pm, pr, q, ok in zip(p_model, p_rppg, sqi, hr_ok):
        if not fused:
            s = pm
        elif mode == 'fallback':
            s = pm  # P_rppg는 판정에 쓰지 않는다
            if q >= settings.SQI_GOOD_MIN and ok and pm >= settings.SCORE_FAKE_MIN:
                out.append('hold'); scores.append(s); continue
        else:
            w = settings.ALPHA * q
            if q >= settings.SQI_MIN and abs(pm - pr) >= settings.CONFLICT_GAP:
                out.append('hold'); scores.append((1 - w) * pm + w * pr); continue
            s = (1 - w) * pm + w * pr
        scores.append(s)
        if s >= settings.SCORE_FAKE_MIN:
            out.append('fake')
        elif s <= settings.SCORE_REAL_MAX:
            out.append('real')
        else:
            out.append(boundary)
    return np.array(out), np.array(scores)


def metrics(v, scores, labels) -> dict:
    n = len(v)
    decided = v != 'hold'
    wrong = decided & (v != labels)
    return {
        'auc': round(auc(scores[labels == 'real'], scores[labels == 'fake']), 4),
        'confident_error': round(wrong.sum() / n, 4),
        'hold_rate': round((~decided).sum() / n, 4),
        'accuracy_decided': round(1 - wrong.sum() / max(decided.sum(), 1), 4),
        'n': n,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('classifier', 'fallback'), required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in VAL_PATH.read_text(encoding='utf-8').splitlines()]
    failed = [r for r in rows if 'failed' in r]
    rows = [r for r in rows if 'failed' not in r]
    labels = np.array([r['label'] for r in rows])
    p_model = np.array([r['p_model'] for r in rows])
    sqi = np.array([r['sqi']['value'] for r in rows])
    hr_ok = np.array([bool(r['features'].get('hr_in_range')) for r in rows])
    if args.mode == 'classifier':
        model = p_rppg_model.load_model()
        p_rppg = np.array([p_rppg_model.p_rppg(r['features'], model) for r in rows])
    else:
        p_rppg = p_model.copy()

    print(f'검증 세트: 분석 {len(rows)}편(진짜 {(labels == "real").sum()}, 가짜 {(labels == "fake").sum()}), 얼굴 미검출 제외 {len(failed)}편')
    print(f'SQI 하한({settings.SQI_MIN}) 이상 {int((sqi >= settings.SQI_MIN).sum())}편, 양호({settings.SQI_GOOD_MIN}) 이상 {int((sqi >= settings.SQI_GOOD_MIN).sum())}편,'
          f' w 평균 {np.mean(settings.ALPHA * sqi):.3f}\n')

    result = {'mode': args.mode, 'failed': len(failed), 'candidates': {}}
    print(f'{"경계 후보":<8} {"방식":<6} {"AUC":>6} {"확신 오류":>9} {"보류":>6} {"정확도(보류 제외)":>16}')
    for boundary in CANDIDATES:
        main_m = metrics(*verdicts(p_model, p_rppg, sqi, hr_ok, boundary, args.mode, fused=False), labels)
        fuse_m = metrics(*verdicts(p_model, p_rppg, sqi, hr_ok, boundary, args.mode, fused=True), labels)
        result['candidates'][boundary] = {'main_only': main_m, 'fusion': fuse_m}
        for name, m in (('단독', main_m), ('융합', fuse_m)):
            print(f'{boundary:<8} {name:<6} {m["auc"]:>6.3f} {m["confident_error"]:>9.3f} {m["hold_rate"]:>6.3f} {m["accuracy_decided"]:>16.3f}')

    # 사전 등록 5절: 융합 기준으로 보류 상한 이하 후보 중 확신 오류율 최소, 같으면 보류가 적은 후보
    allowed = [b for b in CANDIDATES if result['candidates'][b]['fusion']['hold_rate'] <= HOLD_CAP]
    chosen = min(allowed, key=lambda b: (result['candidates'][b]['fusion']['confident_error'],
                                        result['candidates'][b]['fusion']['hold_rate'])) if allowed else None
    result['chosen_boundary'] = chosen
    if chosen:
        f, m = result['candidates'][chosen]['fusion'], result['candidates'][chosen]['main_only']
        result['not_worse'] = bool(f['confident_error'] <= m['confident_error'] and f['auc'] >= m['auc'] - 1e-9)
        print(f'\n경계 구간 판정: {chosen} (보류 상한 {HOLD_CAP:.0%} 이하 후보 중 확신 오류율 최소)')
        print(f'융합이 메인 모델 단독보다 나빠지지 않음: {result["not_worse"]} '
              f'(확신 오류 {f["confident_error"]:.3f} vs {m["confident_error"]:.3f}, AUC {f["auc"]:.3f} vs {m["auc"]:.3f})')
    else:
        print('\n보류 상한을 넘지 않는 후보가 없음')
    out = VAL_PATH.with_name(f'fusion_{args.mode}.json')
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'저장: {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
