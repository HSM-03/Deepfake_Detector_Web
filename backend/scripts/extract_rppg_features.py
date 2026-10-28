"""
5단계 P_rppg 분류기용 특징 추출 — FaceForensics++ original ↔ Deepfakes 쌍 (rPPG 분석·분류기 학습 한정)

  python -m scripts.extract_rppg_features --batch /app/out/stage5/batch_01.json
  python -m scripts.extract_rppg_features --batch …/batch_00_old25.json --compression raw

- 묶음 파일: {"pairs": ["000_003", ...]} — "a_b"는 original a와 Deepfakes a_b 한 쌍.
- 서비스와 같은 계산: 앞 RPPG_MAX_ANALYSIS_SEC초만 추적(rppg.extract_traces) → 특징 6개(rppg_features.compute) → SQI(sqi.compute).
- 결과는 영상 하나당 한 줄(JSON Lines)로 --out에 덧붙인다. 이미 있는 영상(같은 id·압축 단계)은 건너뛰므로 끊겨도 이어서 돌리면 된다.
  기록: 영상 id·쌍·진짜/가짜·조작 방식·압축 단계·길이·추적률·심박·특징 6개·SQI(값·등급·구성 4개)·추출 시각.
- 데이터셋은 읽기 전용으로 연결한다. 영상 삭제는 이 스크립트가 하지 않는다(결과를 확인한 뒤 따로 지운다).
- 메인 모델은 FF++에 돌리지 않는다. 얼굴 이미지는 저장하지 않는다.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from analysis import rppg, rppg_features, settings, sqi
from analysis.stream_info import stream_info
from analysis.video_meta import read_video_meta

MANIPULATION = 'Deepfakes'  # 4-1과 같은 조작 방식으로 통일
DEFAULT_OUT = Path('/app/out/stage5/ffpp_features.jsonl')


def video_paths(root: Path, pair: str, compression: str) -> dict[str, Path]:
    real_id = pair.split('_')[0]
    return {
        'real': root / 'original_sequences' / 'youtube' / compression / 'videos' / f'{real_id}.mp4',
        'fake': root / 'manipulated_sequences' / MANIPULATION / compression / 'videos' / f'{pair}.mp4',
    }


def _clean(value):
    """NaN은 JSON에 null로"""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def extract(path: Path) -> dict:
    meta = read_video_meta(path)
    if meta is None:
        return {'error': '영상을 열 수 없음'}
    max_frames = int(round(settings.RPPG_MAX_ANALYSIS_SEC * meta.fps)) if meta.fps else None
    traces = rppg.extract_traces(path, meta, max_frames=max_frames)
    features = rppg_features.compute(traces)
    quality = sqi.compute(traces, meta.codec, stream_info(path, meta))
    return {
        'codec': meta.codec,
        'width': meta.width,
        'height': meta.height,
        'fps': round(meta.fps, 3),
        'duration_sec': round(meta.duration_sec, 2),
        'analyzed_sec': round(min(meta.duration_sec, settings.RPPG_MAX_ANALYSIS_SEC), 2),
        'tracked_rate': round(traces.tracked_rate, 4),
        'hr_bpm': None if features.hr_bpm is None else round(features.hr_bpm, 2),
        'features': {k: _clean(float(v)) for k, v in features.values.items()},
        'sqi': {'value': round(quality.value, 4), 'grade': quality.grade,
                'components': {k: round(v, 4) for k, v in quality.components.items()}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='FF++ 쌍의 rPPG 특징 추출 (5단계 분류기용)')
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--compression', default='raw', choices=('raw', 'c23', 'c40'))
    parser.add_argument('--root', type=Path, default=settings.DATASET_DIR / 'FaceForensics++')
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    pairs = json.loads(args.batch.read_text(encoding='utf-8'))['pairs']
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        for line in args.out.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            done.add((row['video_id'], row['compression']))

    missing, written = [], 0
    for pair in pairs:
        for role, path in video_paths(args.root, pair, args.compression).items():
            video_id = path.stem
            if (video_id, args.compression) in done:
                continue
            if not path.exists():
                missing.append(path.name)
                continue
            row = {'video_id': video_id, 'pair': pair, 'role': role, 'manipulation': MANIPULATION,
                   'compression': args.compression, **extract(path),
                   'extracted_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
            with args.out.open('a', encoding='utf-8') as f:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            done.add((video_id, args.compression))
            written += 1
            sqi_text = f'SQI {row["sqi"]["value"]:.2f}' if 'sqi' in row else row.get('error')
            print(f'  {pair:<9} {role:<4} {video_id:<9} {row.get("duration_sec", 0):5.1f}초 '
                  f'추적 {row.get("tracked_rate", 0):.0%} 심박 {row.get("hr_bpm")} {sqi_text}', flush=True)

    print(f'\n{args.batch.name}: 쌍 {len(pairs)}개, 새로 기록 {written}편, 없는 영상 {len(missing)}편 → {args.out}')
    if missing:
        print('  없는 영상:', ' '.join(missing))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
