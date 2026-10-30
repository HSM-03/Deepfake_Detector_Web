"""
작업 2 확인 (개발 중 확인용, 설정을 고르는 데 쓰지 않음) — UBFC 3명으로 부위별 신호가 쓸 만한지 본다. 컨테이너에서 실행한다.

  python -m scripts.check_region_ubfc        (먼저 python -m scripts.extract_region_signals ubfc)

1. 서비스와 같은 값인지: index.jsonl의 특징 6개를 5-4에 서비스 코드로 뽑은 out/stage5/ubfc_features.json과 비교한다(같아야 한다).
2. 부위별 심박 오차: 4단계와 같은 방식 — CHROM, 20초 조각마다 영상 단위 심박(Welch 10초) − 정답(맥박 측정기) 평균.
   사전 등록 4절: "부위를 나눠도 심박 오차가 1.5BPM 수준인지". 목 부위를 쓸지(6절)의 근거 중 하나다. 배경은 대조군(맞으면 안 된다).
"""
import json
from pathlib import Path

import numpy as np

from analysis import rppg, settings
from rppg_region import regions
from scripts.run_rppg import CLIP_SEC, load_ubfc_truth

OUT = Path('/app/out/rppg_region')
KEYS = ('face_skin', 'forehead', 'left_cheek', 'right_cheek') + regions.REGION_KEYS


def main() -> int:
    rows = [json.loads(l) for l in (OUT / 'index.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if r['source'] == 'ubfc']
    ref = {r['video']: r['features'] for r in json.loads(Path('/app/out/stage5/ubfc_features.json').read_text(encoding='utf-8'))}

    print('1. 특징 6개 — 5-4 서비스 값과 비교')
    for r in rows:
        if r['video_id'] not in ref:
            print(f'  {r["video_id"]}: 비교 대상 없음')
            continue
        diff = max(abs((r['features'][k] or 0) - (v or 0)) for k, v in ref[r['video_id']].items())
        print(f'  {r["video_id"]}: 최대 차이 {diff:.2e} → {"같음" if diff < 1e-9 else "다름"}')

    print(f'\n2. 부위별 심박 오차 (CHROM, {CLIP_SEC:g}초 조각, |추정 − 정답| BPM)')
    errors = {k: [] for k in KEYS}
    per_subject = {}
    for r in rows:
        data = regions.load_npz(OUT / r['npz'])
        fs = float(data['fps'])
        _, hr, _ = load_ubfc_truth(settings.DATASET_DIR / 'UBFC-rPPG' / 'DATASET_2' / r['video_id'])
        n = min(len(hr), len(data['tracked']))
        clip = int(round(CLIP_SEC * fs))
        per_subject[r['video_id']] = {}
        for key in KEYS:
            rgb = data[f'rgb_{key}'][:n].astype(np.float64)
            errs = []
            for a in range(0, n - clip + 1, clip):
                est = rppg.estimate_pulse(rgb[a:a + clip], fs)
                errs.append(abs(est.bpm - hr[a:a + clip].mean()) if est.bpm is not None else np.nan)
            errors[key] += errs
            per_subject[r['video_id']][key] = errs

    subjects = list(per_subject)
    print('  조각 수: ' + ', '.join(f'{s} {len(per_subject[s][KEYS[0]])}' for s in subjects))
    print(f'  {"부위":<16} {"MAE":>6} {"최대":>6}   ' + ' | '.join(subjects))
    for key in KEYS:
        e = np.array(errors[key], dtype=np.float64)
        cells = ' | '.join(' '.join(f'{x:5.1f}' for x in per_subject[s][key]) for s in subjects)
        print(f'  {key:<16} {np.nanmean(e):6.2f} {np.nanmax(e):6.1f}   {cells}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
