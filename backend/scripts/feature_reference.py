"""
5-4 특징 기준값 재산출 — 근거 화면 특징 표의 ○/△/× 기준(settings.RPPG_FEATURE_JUDGE)을 실제 얼굴 영상 분포로 다시 잡는다.

  python -m scripts.feature_reference

- 기준 영상: FF++ c0 **학습 쌍의 진짜 영상만**(시험 쌍 영상은 넣지 않음, 사전 등록 6절) + UBFC-rPPG 원본 3명.
  학습 쌍 제외 규칙(10초 미만, 추적률 70% 미만)은 분류기와 같게 적용한다.
- 규칙(값을 보기 전에 정함, docs/backend-plan.md 5-4): ○ = 기준 영상의 75%가 들어가는 범위, △ = 95%가 들어가는 범위, 그 밖은 ×.
  '좋은 방향'이 큰 쪽인 특징(min: SNR, ROI 간 신호 일치도)은 25%·5% 분위가 경계, 작은 쪽인 특징(max)은 75%·95% 분위가 경계다.
- 심박 범위(45~180BPM)는 생리학적 범위라 그대로 둔다.
"""
import json
from pathlib import Path

import numpy as np

from analysis import rppg, rppg_features, settings
from analysis.video_meta import read_video_meta
from scripts.train_p_rppg import FEATURES_PATH, SPLIT_PATH, exclusion_reason, load_rows

UBFC_CACHE = Path('/app/out/stage5/ubfc_features.json')


def ubfc_features() -> list[dict]:
    if UBFC_CACHE.exists():
        return json.loads(UBFC_CACHE.read_text(encoding='utf-8'))
    rows = []
    for folder in sorted((settings.DATASET_DIR / 'UBFC-rPPG' / 'DATASET_2').glob('subject*')):
        path = folder / 'vid.avi'
        meta = read_video_meta(path)
        max_frames = int(round(settings.RPPG_MAX_ANALYSIS_SEC * meta.fps)) if meta.fps else None
        values = rppg_features.compute(rppg.extract_traces(path, meta, max_frames=max_frames)).values
        rows.append({'video': folder.name, 'features': {k: (None if v != v else float(v)) for k, v in values.items()}})
    UBFC_CACHE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    return rows


def main() -> int:
    split = json.loads(SPLIT_PATH.read_text(encoding='utf-8'))
    rows = load_rows()
    reals = []
    for pair in split['train_old25'] + split['train_new']:
        real, fake = rows.get(pair.split('_')[0]), rows.get(pair)
        if exclusion_reason(real) or exclusion_reason(fake):
            continue
        reals.append(real)
    ubfc = ubfc_features()
    print(f'기준 영상: FF++ 학습 쌍 진짜 {len(reals)}편 + UBFC {len(ubfc)}편 (특징: {FEATURES_PATH.name})\n')

    judge = {}
    for key, (direction, ok_old, warn_old) in settings.RPPG_FEATURE_JUDGE.items():
        values = np.array([r['features'][key] for r in reals + ubfc if r['features'].get(key) is not None], float)
        if direction == 'min':
            ok, warn = np.percentile(values, 25), np.percentile(values, 5)
        else:
            ok, warn = np.percentile(values, 75), np.percentile(values, 95)
        judge[key] = (direction, round(float(ok), 2), round(float(warn), 2))
        print(f'  {key:<18} {direction}  ○ {judge[key][1]:>7}  △ {judge[key][2]:>7}   (이전 ○ {ok_old} △ {warn_old}, 영상 {len(values)}편,'
              f' 중앙값 {np.median(values):.2f})')
    print('\nsettings.RPPG_FEATURE_JUDGE에 넣을 값:')
    for key, value in judge.items():
        print(f"    '{key}': {value},")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
