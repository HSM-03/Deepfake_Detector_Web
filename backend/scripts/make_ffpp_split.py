"""
5단계 FF++ 학습·시험 쌍 나누기 (docs/stage5-preregistration.md 1절 규칙). 표준 라이브러리만 써서 Windows 파이썬으로도 돈다.

  python backend/scripts/make_ffpp_split.py --filelist D:/Deepfake_Datasets/FaceForensics++/filelist.json \
      --old backend/out/stage5/batch_00_old25.json --out docs/stage5/ffpp_split.json --batches backend/out/stage5

- filelist.json: FF++ 서버의 쌍 목록 [[a, b], ...] (ffpp_pick.py list로 받음). 한 줄 [a, b]에서 쌍 (a, a_b)·(b, b_a)가 나온다.
- 4-1 25쌍의 번호가 든 묶음은 고르지 않는다. 나머지 묶음을 목록 순서대로 놓고 시드 0으로 섞어 앞 50묶음 = 학습, 다음 50묶음 = 시험.
- 받기용 묶음 파일(50쌍씩)을 --batches에 쓴다: batch_01_train.json, batch_02_train.json, batch_03_test.json, batch_04_test.json.
"""
import argparse
import json
import random
from pathlib import Path

SEED = 0
GROUPS_PER_SIDE = 50
GROUPS_PER_BATCH = 25  # 50쌍


def pairs_of(group: list[str]) -> list[str]:
    a, b = group
    return [f'{a}_{b}', f'{b}_{a}']


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--filelist', type=Path, required=True)
    parser.add_argument('--old', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--batches', type=Path, required=True)
    args = parser.parse_args()

    groups = json.loads(args.filelist.read_text(encoding='utf-8'))
    ids = [i for g in groups for i in g]
    assert all(len(g) == 2 for g in groups), '쌍 목록 형식이 다름'
    assert len(ids) == len(set(ids)), '같은 번호가 두 묶음에 나옴 — 묶음 단위 나누기 가정이 깨짐'

    old_pairs = json.loads(args.old.read_text(encoding='utf-8'))['pairs']
    old_ids = {i for p in old_pairs for i in p.split('_')}
    candidates = [g for g in groups if not (set(g) & old_ids)]
    rng = random.Random(SEED)
    rng.shuffle(candidates)
    train, test = candidates[:GROUPS_PER_SIDE], candidates[GROUPS_PER_SIDE:2 * GROUPS_PER_SIDE]

    train_ids = {i for g in train for i in g} | old_ids
    test_ids = {i for g in test for i in g}
    assert not (train_ids & test_ids), '학습·시험 번호가 겹침'

    split = {
        'rule': 'docs/stage5-preregistration.md 1절',
        'manipulation': 'Deepfakes', 'compression': 'raw', 'seed': SEED,
        'groups_total': len(groups), 'groups_excluded_old': len(groups) - len(candidates),
        'train_old25': sorted(old_pairs),
        'train_new': [p for g in train for p in pairs_of(g)],
        'test': [p for g in test for p in pairs_of(g)],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(split, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')

    args.batches.mkdir(parents=True, exist_ok=True)
    names = ['batch_01_train', 'batch_02_train', 'batch_03_test', 'batch_04_test']
    chunks = [train[:GROUPS_PER_BATCH], train[GROUPS_PER_BATCH:], test[:GROUPS_PER_BATCH], test[GROUPS_PER_BATCH:]]
    for name, chunk in zip(names, chunks):
        (args.batches / f'{name}.json').write_text(json.dumps({'pairs': [p for g in chunk for p in pairs_of(g)]}) + '\n',
                                                   encoding='utf-8')
    print(f'묶음 {len(groups)}개 중 4-1 번호가 든 {len(groups) - len(candidates)}개 제외 → 학습 새 {len(split["train_new"])}쌍'
          f' + 4-1 {len(old_pairs)}쌍, 시험 {len(split["test"])}쌍 → {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
