"""
작업 3 준비 확인 — 저장된 부위별 신호(index.jsonl의 영상)로 부위 간 비교 특징 2개(rppg_region.compare)를 계산해 출력한다.

  python -m scripts.check_region_compare              전부
  python -m scripts.check_region_compare --source ubfc

- 지금은 UBFC 진짜 3편만 있다(개발 중 확인용, 설정을 고르는 데 쓰지 않음). 진짜 영상이면 위상 차이가 작고(0에 가까움) 일치도가 높아야 한다.
- 결과 파일은 만들지 않는다(화면 출력만). 학습용 특징 표는 FF++ 신호가 모인 뒤 따로 만든다.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from rppg_region import compare, regions

OUT = Path('/app/out/rppg_region')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source')
    args = parser.parse_args()
    rows = [json.loads(l) for l in (OUT / 'index.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    rows = [r for r in rows if 'npz' in r and (args.source is None or r['source'] == args.source)]

    print(f'{"출처":<6} {"영상":<12} {"역할":<5} {"위상 차이(rad)":>14} {"일치도":>7}   심박(주 / 안쪽 / 바깥쪽 BPM)')
    for r in rows:
        f = compare.compute(regions.load_npz(OUT / r['npz']))
        hr = ' / '.join('-' if f[k] is None else f'{f[k]:.1f}' for k in ('hr_main_bpm', 'hr_inner_bpm', 'hr_outer_bpm'))
        phase = 'NaN' if np.isnan(f['inner_outer_phase']) else f'{f["inner_outer_phase"]:.3f}'
        print(f'{r["source"]:<6} {r["video_id"]:<12} {r["role"]:<5} {phase:>14} {f["inner_outer_corr"]:>7.3f}   {hr}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
