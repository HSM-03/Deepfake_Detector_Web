"""
5-5 Celeb-DF 검증 세트 — 서비스와 같은 분석(메인 모델 + rPPG 특징·SQI)을 영상마다 돌려 기록한다.

  python -m scripts.run_validation pick --per-class 100      검증 세트 고르기 → /app/out/stage5/celebdf_val_list.json
  python -m scripts.run_validation run                       고른 영상 분석 → /app/out/stage5/celebdf_val.jsonl (끊겨도 이어서)

- 평가 세트(List_of_testing_videos.txt 518개)는 넣지 않는다. Celeb-DF 평가 세트에 거의 모든 인물이 들어 있어(평가 세트 밖이면서
  평가 세트 인물이 아닌 영상은 진짜 30편·가짜 45편뿐) 인물 단위로 완전히 나눌 수는 없다 — 평가 세트 영상만 뺀다.
- 진짜 = Celeb-real + YouTube-real(평가 세트 밖), 가짜 = Celeb-synthesis(평가 세트 밖). 10초 미만은 서비스가 분석하지 않아 뺀다. 시드 0.
- 여기서는 P_model·특징·SQI만 기록한다. P_rppg와 융합 판정은 확정된 분류기와 규칙으로 따로 계산한다(같은 값으로 여러 규칙을 비교하기 위해).
- 검증 세트는 "융합해도 메인 모델 단독보다 나빠지지 않는가"와 경계 구간 판정 고르기(docs/stage5-preregistration.md 5절)에만 쓴다.
"""
import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from analysis import rppg, rppg_features, settings, sqi
from analysis.stream_info import stream_info
from analysis.video_meta import read_video_meta

OUT_DIR = Path('/app/out/stage5')
LIST_PATH = OUT_DIR / 'celebdf_val_list.json'
RESULT_PATH = OUT_DIR / 'celebdf_val.jsonl'
SEED = 0


def pick(per_class: int) -> int:
    root = settings.CELEBDF_DIR
    test = {line.split()[1] for line in (root / 'List_of_testing_videos.txt').read_text().splitlines() if line.strip()}
    pools = {'real': [], 'fake': []}
    for folder, label in (('Celeb-real', 'real'), ('YouTube-real', 'real'), ('Celeb-synthesis', 'fake')):
        for path in sorted((root / folder).glob('*.mp4')):
            if f'{folder}/{path.name}' not in test:
                pools[label].append(f'{folder}/{path.name}')
    rng = random.Random(SEED)
    chosen = {}
    for label, pool in pools.items():
        rng.shuffle(pool)
        picked = []
        for rel in pool:
            meta = read_video_meta(root / rel)
            if meta is None or meta.duration_sec < settings.MIN_DURATION_SEC:
                continue
            picked.append(rel)
            if len(picked) == per_class:
                break
        chosen[label] = picked
    LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIST_PATH.write_text(json.dumps({'seed': SEED, 'rule': __doc__.strip().splitlines()[0], **chosen}, ensure_ascii=False, indent=1) + '\n',
                         encoding='utf-8')
    print(f'진짜 {len(chosen["real"])}편 (Celeb-real {sum(r.startswith("Celeb-real") for r in chosen["real"])}, '
          f'YouTube-real {sum(r.startswith("YouTube") for r in chosen["real"])}), 가짜 {len(chosen["fake"])}편 → {LIST_PATH}')
    return 0


def analyze(model, path: Path) -> dict:
    meta = read_video_meta(path)
    prepared = model.prepare(str(path), meta=meta)
    stats = prepared.stats
    row = {'duration_sec': round(meta.duration_sec, 2), 'codec': meta.codec, 'width': meta.width, 'height': meta.height,
           'face_rate': round(stats.face_rate, 4)}
    if stats.face_rate < settings.MAIN_MODEL_MIN_FACE_RATE:
        return {**row, 'failed': '얼굴 미검출'}  # 서비스에서는 분석 불가
    result = model.score(prepared)
    max_frames = int(round(settings.RPPG_MAX_ANALYSIS_SEC * meta.fps)) if meta.fps else None
    traces = rppg.extract_traces(path, meta, max_frames=max_frames)
    features = rppg_features.compute(traces)
    quality = sqi.compute(traces, meta.codec, stream_info(path, meta))
    return {**row, 'p_model': round(result.p_model, 4), 'p_model_std': round(result.p_model_std, 4),
            'tracked_rate': round(traces.tracked_rate, 4),
            'hr_bpm': None if features.hr_bpm is None else round(features.hr_bpm, 2),
            'features': {k: (None if v != v else float(v)) for k, v in features.values.items()},
            'sqi': {'value': round(quality.value, 4), 'grade': quality.grade,
                    'components': {k: round(v, 4) for k, v in quality.components.items()}}}


def run() -> int:
    from analysis.main_model import MainModel

    chosen = json.loads(LIST_PATH.read_text(encoding='utf-8'))
    done = set()
    if RESULT_PATH.exists():
        done = {json.loads(line)['video'] for line in RESULT_PATH.read_text(encoding='utf-8').splitlines()}
    model = MainModel()
    items = [(rel, label) for label in ('real', 'fake') for rel in chosen[label]]
    for i, (rel, label) in enumerate(items, 1):
        if rel in done:
            continue
        row = {'video': rel, 'label': label, **analyze(model, settings.CELEBDF_DIR / rel),
               'analyzed_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
        with RESULT_PATH.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(f'  [{i}/{len(items)}] {rel}', flush=True)  # 값은 찍지 않는다(규칙을 정하기 전에 결과를 보지 않도록)
    print(f'완료 → {RESULT_PATH}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('pick', 'run'))
    parser.add_argument('--per-class', type=int, default=100)
    args = parser.parse_args()
    return pick(args.per_class) if args.command == 'pick' else run()


if __name__ == '__main__':
    raise SystemExit(main())
