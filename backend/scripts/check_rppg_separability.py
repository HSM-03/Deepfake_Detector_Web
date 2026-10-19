"""
rPPG 특징이 진짜와 가짜를 가를 가능성이 있는지 확인 (docs/backend-plan.md 4단계 B, "가능성 확인"용).

  python -m scripts.check_rppg_separability --pairs 25

- Celeb-DF에서 같은 원본에서 나온 진짜-가짜 쌍을 뽑는다. 가짜 'idX_idY_NNNN'은 진짜 'idX_NNNN' 영상에 idY의 얼굴을
  합성한 것이라(프레임 수가 같음) 배경·조명·움직임이 같고 얼굴만 다르다. 둘 다 평가 세트(518개) 밖, 10초 이상, 진짜 원본은 겹치지 않게.
- --roi: SNR·엔트로피·윈도우 변동을 잴 영역 ('all' 세 영역 합 / 'face' / 'face_skin'). ROI 간 특징은 항상 이마·양 볼 세 영역.
- 특징(임시 정의 — 4단계 본 구현에서 확정):
    snr_db            추정 심박 기준 SNR (de Haan 방식)
    spectral_entropy  심박 대역 안 스펙트럼을 확률처럼 정규화한 엔트로피 (0~1, 클수록 평평 = 주기성 약함)
    roi_bpm_std       이마·왼볼·오른볼 심박의 표준편차
    roi_corr          세 ROI 필터 신호의 쌍별 상관계수 평균 (위상 일관성의 대용)
    window_bpm_std    윈도우별 심박의 표준편차
- AUC는 "가짜 쪽 값이 클 확률"이다. 0.5면 구분 못 함, 0.5에서 멀수록(0에 가까워도) 구분된다.
  신뢰구간은 쌍 단위 부트스트랩(같은 쌍의 진짜·가짜를 함께 뽑음).
- 가짜는 다시 인코딩된 영상이라 압축 상태가 다를 수 있어, 픽셀당 비트(bpp = 비트레이트 / (가로×세로×fps))도 비교한다.
얼굴 이미지는 저장하지 않는다.
"""
import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

from analysis import rppg, settings
from analysis.video_meta import read_video_meta

FEATURES = ('snr_db', 'spectral_entropy', 'roi_bpm_std', 'roi_corr', 'window_bpm_std')


def pick_pairs(root: Path, n: int, seed: int) -> list[tuple[Path, Path]]:
    test = {line.split()[1] for line in (root / 'List_of_testing_videos.txt').read_text().splitlines() if line.strip()}
    by_real: dict[Path, list[Path]] = {}
    for fake in sorted((root / 'Celeb-synthesis').glob('*.mp4')):
        if f'Celeb-synthesis/{fake.name}' in test:
            continue
        target, _source, number = fake.stem.split('_')
        real = root / 'Celeb-real' / f'{target}_{number}.mp4'
        if real.exists() and f'Celeb-real/{real.name}' not in test:
            by_real.setdefault(real, []).append(fake)
    rng = random.Random(seed)
    reals = sorted(by_real)
    rng.shuffle(reals)
    pairs = []
    for real in reals:
        meta = read_video_meta(real)
        if meta is None or meta.duration_sec < settings.MIN_DURATION_SEC:
            continue
        pairs.append((real, rng.choice(by_real[real])))
        if len(pairs) == n:
            break
    return pairs


def bpp(path: Path) -> float:
    meta = read_video_meta(path)
    return path.stat().st_size * 8 / meta.duration_sec / (meta.width * meta.height * meta.fps)


def features(traces: rppg.RoiTraces, method: str, roi: str) -> dict:
    est = {k: rppg.estimate_pulse(traces.rgb[k], traces.fps, method) for k in rppg.ROI_KEYS + (roi,)}
    a = est[roi]
    band = (a.freqs >= settings.RPPG_BAND_HZ[0]) & (a.freqs <= settings.RPPG_BAND_HZ[1])
    p = a.psd[band] / a.psd[band].sum()
    entropy = float(-(p * np.log(p + 1e-20)).sum() / np.log(len(p)))
    bpms = [est[k].bpm for k in rppg.ROI_KEYS if est[k].bpm is not None]
    sig = [est[k].filtered for k in rppg.ROI_KEYS]
    corr = [np.corrcoef(sig[i], sig[j])[0, 1] for i in range(3) for j in range(i + 1, 3)]
    wins = [b for _, b in a.window_bpm if b is not None]
    return {
        'snr_db': a.snr_db if a.snr_db is not None else np.nan,
        'spectral_entropy': entropy,
        'roi_bpm_std': float(np.std(bpms)) if len(bpms) >= 2 else np.nan,
        'roi_corr': float(np.mean(corr)),
        'window_bpm_std': float(np.std(wins)) if len(wins) >= 2 else np.nan,
    }


def auc(real: np.ndarray, fake: np.ndarray) -> float:
    """가짜 값이 진짜 값보다 클 확률 (같으면 0.5)"""
    real, fake = real[~np.isnan(real)], fake[~np.isnan(fake)]
    if not len(real) or not len(fake):
        return np.nan
    diff = fake[:, None] - real[None, :]
    return float(((diff > 0) + 0.5 * (diff == 0)).mean())


def bootstrap_ci(real: np.ndarray, fake: np.ndarray, iters: int, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(real)
    values = [auc(real[idx], fake[idx]) for idx in (rng.integers(0, n, n) for _ in range(iters))]
    return tuple(np.nanpercentile(values, [2.5, 97.5]))


def main() -> int:
    parser = argparse.ArgumentParser(description='rPPG 특징의 진짜/가짜 구분 가능성 (쌍 비교)')
    parser.add_argument('--pairs', type=int, default=25)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--bootstrap', type=int, default=2000)
    parser.add_argument('--roi', choices=('all',) + rppg.FACE_KEYS, default=settings.RPPG_PRIMARY_ROI)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()

    pairs = pick_pairs(settings.CELEBDF_DIR, args.pairs, args.seed)
    print(f'쌍 {len(pairs)}개 (시드 {args.seed}), ROI {args.roi}, 윈도우 {settings.RPPG_WINDOW_SEC:g}초, 부트스트랩 {args.bootstrap}회\n')

    records = []
    for real, fake in pairs:
        row = {'real': real.name, 'fake': fake.name, 'bpp_real': bpp(real), 'bpp_fake': bpp(fake)}
        traces = {'real': rppg.extract_traces(real), 'fake': rppg.extract_traces(fake)}
        for method in ('pos', 'chrom'):
            for side in ('real', 'fake'):
                row[f'{method}_{side}'] = {**features(traces[side], method, args.roi), 'tracked': traces[side].tracked_rate}
        records.append(row)
        print(f'  {real.name:<14} ↔ {fake.name:<20} bpp {row["bpp_real"]:.3f} / {row["bpp_fake"]:.3f}', flush=True)

    b_real = np.array([r['bpp_real'] for r in records])
    b_fake = np.array([r['bpp_fake'] for r in records])
    print(f'\n픽셀당 비트(bpp): 진짜 중앙값 {np.median(b_real):.3f}, 가짜 중앙값 {np.median(b_fake):.3f},'
          f' 쌍별 (가짜 − 진짜) 중앙값 {np.median(b_fake - b_real):+.3f} (가짜가 더 작은 쌍 {int((b_fake < b_real).sum())}/{len(records)})'
          f' | bpp만으로 AUC {auc(b_real, b_fake):.2f}')

    print(f'\n{"방식":<6} {"특징":<17} {"진짜 중앙값":>10} {"가짜 중앙값":>10} {"AUC":>6}  95% 신뢰구간')
    summary = {}
    for method in ('pos', 'chrom'):
        for f in FEATURES:
            real = np.array([r[f'{method}_real'][f] for r in records], dtype=float)
            fake = np.array([r[f'{method}_fake'][f] for r in records], dtype=float)
            value = auc(real, fake)
            lo, hi = bootstrap_ci(real, fake, args.bootstrap, args.seed)
            summary[f'{method}/{f}'] = {'auc': value, 'ci': [lo, hi]}
            flag = '  ← 0.5를 벗어남' if (lo > 0.5 or hi < 0.5) else ''
            print(f'{method:<6} {f:<17} {np.nanmedian(real):>10.3f} {np.nanmedian(fake):>10.3f} {value:>6.2f}  [{lo:.2f}, {hi:.2f}]{flag}')

    if args.json:
        args.json.write_text(json.dumps({'pairs': records, 'summary': summary}, ensure_ascii=False, indent=2, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
