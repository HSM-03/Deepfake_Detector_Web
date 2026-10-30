"""
rPPG 분류기 개선 작업 2 — 부위별 맥박 신호 저장 (docs/rppg-region-preregistration.md 6절). 컨테이너에서 실행한다(MediaPipe).

  python -m scripts.extract_region_signals ffpp --batch /app/out/rppg_region/batches/xxx.json --manipulations Deepfakes,FaceSwap
  python -m scripts.extract_region_signals ubfc                     UBFC DATASET_2의 subject 전부(개발 중 확인용)
  python -m scripts.extract_region_signals videos /app/out/06.mp4 …  직접 찍은 영상(개발 중 확인용)
  공통: --preview 3   영상마다 부위를 칠한 프레임 3장을 /app/out/rppg_region/preview/에 저장(얼굴이 담김 — 확인 뒤 지운다)

- 서비스와 같은 추적(앞 RPPG_MAX_ANALYSIS_SEC초)에서 새 부위(rppg_region.regions)를 함께 잰다. 특징 6개·SQI는 서비스와 같은 함수로 계산한다.
- 영상마다 signals/<출처>/<조작 방식>/<영상>.npz(부위별 프레임별 평균 RGB·픽셀 수·추적 여부·얼굴 위치)와 index.jsonl 한 줄.
  이미 있는 영상(같은 출처·조작 방식·영상·압축 단계)은 건너뛰므로 끊겨도 이어서 돌리면 된다.
- FF++ 묶음 파일: {"pairs": ["a_b", ...]}. 쌍마다 진짜 a(original)와 조작 방식별 가짜 a_b를 처리한다. 진짜는 조작 방식과 상관없이 한 번만.
- 데이터셋은 읽기 전용. 영상 삭제는 하지 않는다. 메인 모델은 돌리지 않는다. 얼굴 이미지는 --preview일 때만 out/에 저장한다.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from analysis import rppg_features, settings, sqi
from analysis.stream_info import stream_info
from analysis.video_meta import read_video_meta
from rppg_region import regions

OUT = Path('/app/out/rppg_region')
INDEX = OUT / 'index.jsonl'
MANIPULATIONS = ('Deepfakes', 'FaceSwap', 'FaceShifter', 'Face2Face', 'NeuralTextures')


def _clean(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _preview_saver(name: str, count: int, total_frames: int):
    if count <= 0:
        return None
    picks = {int(i) for i in np.linspace(0, max(total_frames - 1, 0), count + 2)[1:-1]}
    folder = OUT / 'preview'
    folder.mkdir(parents=True, exist_ok=True)

    def save(index, frame, polygons, masks, origin, boxes):
        if index in picks:
            cv2.imwrite(str(folder / f'{name}_{index:05d}.jpg'), regions.draw_preview(frame, polygons, masks, origin, boxes))
    return save


def process(path: Path, key: dict, npz_path: Path, preview: int) -> dict:
    meta = read_video_meta(path)
    if meta is None:
        return {**key, 'error': '영상을 열 수 없음'}
    max_frames = int(round(settings.RPPG_MAX_ANALYSIS_SEC * meta.fps)) if meta.fps else None
    total = min(meta.frame_count, max_frames) if max_frames else meta.frame_count
    traces = regions.extract(path, meta, max_frames=max_frames,
                             preview=_preview_saver(npz_path.stem if key['source'] != 'ffpp' else f'{key["manipulation"] or "original"}_{npz_path.stem}', preview, total))
    regions.save_npz(traces, npz_path)
    s = traces.service
    features = rppg_features.compute(s)
    quality = sqi.compute(s, meta.codec, stream_info(path, meta))
    tracked = s.tracked
    return {
        **key,
        'codec': meta.codec, 'width': meta.width, 'height': meta.height, 'fps': round(meta.fps, 3),
        'duration_sec': round(meta.duration_sec, 2),
        'analyzed_sec': round(min(meta.duration_sec, settings.RPPG_MAX_ANALYSIS_SEC), 2),
        'tracked_rate': round(s.tracked_rate, 4),
        'hr_bpm': None if features.hr_bpm is None else round(features.hr_bpm, 2),
        'features': {k: _clean(float(v)) for k, v in features.values.items()},
        'sqi': {'value': round(quality.value, 4), 'grade': quality.grade,
                'components': {k: round(v, 4) for k, v in quality.components.items()}},
        # 추적된 프레임의 부위별 픽셀 수 중앙값 (부위가 너무 작거나 프레임 밖으로 나간 영상 확인용)
        'region_pixels_median': {k: int(np.median(v[tracked])) if tracked.any() else 0
                                 for k, v in {**traces.pixels, 'face_skin': s.pixels['face_skin']}.items()},
        'npz': str(npz_path.relative_to(OUT)),
        'extracted_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }


def index_key(row: dict) -> tuple:
    return (row['source'], row.get('manipulation'), row['video_id'], row.get('compression'))


def jobs_ffpp(args) -> list[tuple[Path, dict, Path]]:
    pairs = json.loads(args.batch.read_text(encoding='utf-8'))['pairs']
    manipulations = [m.strip() for m in args.manipulations.split(',') if m.strip()]
    unknown = set(manipulations) - set(MANIPULATIONS)
    if unknown:
        raise SystemExit(f'모르는 조작 방식: {sorted(unknown)}')
    root = args.root / 'FaceForensics++'
    out = []
    for pair in pairs:
        real_id = pair.split('_')[0]
        base = {'source': 'ffpp', 'pair': pair, 'compression': args.compression}
        out.append((root / 'original_sequences' / 'youtube' / args.compression / 'videos' / f'{real_id}.mp4',
                    {**base, 'video_id': real_id, 'role': 'real', 'manipulation': None},
                    OUT / 'signals' / 'ffpp' / 'original' / f'{real_id}.npz'))
        for m in manipulations:
            out.append((root / 'manipulated_sequences' / m / args.compression / 'videos' / f'{pair}.mp4',
                        {**base, 'video_id': pair, 'role': 'fake', 'manipulation': m},
                        OUT / 'signals' / 'ffpp' / m / f'{pair}.npz'))
    return out


def jobs_ubfc(args) -> list[tuple[Path, dict, Path]]:
    root = args.root / 'UBFC-rPPG' / 'DATASET_2'
    return [(folder / 'vid.avi', {'source': 'ubfc', 'video_id': folder.name, 'role': 'real', 'manipulation': None, 'compression': None},
             OUT / 'signals' / 'ubfc' / f'{folder.name}.npz')
            for folder in sorted(root.iterdir()) if (folder / 'vid.avi').exists()]


def jobs_videos(args) -> list[tuple[Path, dict, Path]]:
    return [(p, {'source': 'own', 'video_id': p.stem, 'role': 'real', 'manipulation': None, 'compression': None},
             OUT / 'signals' / 'own' / f'{p.stem}.npz') for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(description='부위별 맥박 신호 저장 (작업 2)')
    parser.add_argument('--root', type=Path, default=settings.DATASET_DIR)
    parser.add_argument('--preview', type=int, default=0)
    sub = parser.add_subparsers(dest='source', required=True)
    f = sub.add_parser('ffpp')
    f.add_argument('--batch', type=Path, required=True)
    f.add_argument('--manipulations', required=True, help='쉼표로 구분: ' + ','.join(MANIPULATIONS))
    f.add_argument('--compression', default='raw', choices=('raw',))  # 이번 작업은 c0만
    sub.add_parser('ubfc')
    v = sub.add_parser('videos')
    v.add_argument('paths', type=Path, nargs='+')
    args = parser.parse_args()

    jobs = {'ffpp': jobs_ffpp, 'ubfc': jobs_ubfc, 'videos': jobs_videos}[args.source](args)
    OUT.mkdir(parents=True, exist_ok=True)
    done = set()
    if INDEX.exists():
        done = {index_key(json.loads(line)) for line in INDEX.read_text(encoding='utf-8').splitlines() if line.strip()}

    missing, written, seen = [], 0, set()
    for path, key, npz_path in jobs:
        k = index_key(key)
        if k in done or k in seen:
            continue
        seen.add(k)
        if not path.exists():
            missing.append(str(path))
            continue
        row = process(path, key, npz_path, args.preview)
        with INDEX.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
        written += 1
        px = row.get('region_pixels_median', {})
        print(f'  {key.get("manipulation") or key["role"]:<14} {key["video_id"]:<10} {row.get("analyzed_sec", 0):5.1f}초 '
              f'추적 {row.get("tracked_rate", 0):.0%} SQI {row.get("sqi", {}).get("value")} '
              f'픽셀(안쪽 {px.get("inner")}, 이마위 {px.get("upper_forehead")}, 가장자리 {px.get("edge")}, 목 {px.get("neck")})', flush=True)

    print(f'\n새로 기록 {written}편, 없는 영상 {len(missing)}편 → {INDEX}')
    for m in missing:
        print('  없음:', m)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
