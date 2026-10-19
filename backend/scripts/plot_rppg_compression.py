"""
압축 강도(bpp)에 따른 rPPG 성능 그림 (docs/backend-plan.md 4단계) — 얼굴 이미지는 없다.

  위: UBFC-rPPG 심박 오차(MAE) — rppg_bitrate_sweep.py 결과
  아래: 진짜/가짜 구분력(AUC + 95% 신뢰구간), 특징마다 작은 그림 — check_rppg_separability.py 결과
        (Celeb-DF 25쌍, FaceForensics++ c0/c23/c40 각 10쌍. FF++는 rPPG 분석 한정)
  세로 점선: Celeb-DF bpp 중앙값

  python -m scripts.plot_rppg_compression --sweep s.json --celebdf c.json --ffpp raw.json c23.json c40.json \\
      --out ../docs/figures/rppg_compression.png --font /fonts/malgun.ttf --data ../docs/figures/rppg_compression_data.json
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

FEATURES = {
    'window_bpm_std': '윈도우별 심박 변동',
    'snr_db': 'SNR',
    'roi_corr': 'ROI 간 상관',
    'roi_bpm_std': 'ROI 간 심박 차이',
    'spectral_entropy': '스펙트럼 엔트로피',
}
# 참고 팔레트(dataviz) 1·2번 — 검증 통과(CVD ΔE 24.7)
BLUE, ORANGE = '#2a78d6', '#eb6834'
INK, MUTED, GRID, SURFACE = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'


def load(args) -> dict:
    sweep = json.loads(Path(args.sweep).read_text(encoding='utf-8'))
    curves = {}
    for codec in ('h264', 'mpeg4'):
        points = {}
        for r in sweep:
            if r['codec'] == codec:
                points.setdefault(r['target_kbps'], []).append(r)
        # 목표 비트레이트별 세 사람 평균. MPEG-4는 높은 목표(2000k 이상)에서 실제 비트레이트가 같아 같은 점이 겹치므로 하나만 남긴다
        means = {(round(float(np.mean([r['bpp'] for r in g])), 4), round(float(np.mean([r['mae'] for r in g])), 2))
                 for g in points.values()}
        curves[codec] = sorted(means)
    original = [r for r in sweep if r['codec'] == '원본']
    data = {'ubfc': {'h264': curves['h264'], 'mpeg4': curves['mpeg4'],
                     'original': [float(np.mean([r['bpp'] for r in original])), float(np.mean([r['mae'] for r in original]))]},
            'separability': []}
    sources = [('Celeb-DF (25쌍)', args.celebdf)] + [(f'FF++ {c} (10쌍)', p) for c, p in zip(('c0', 'c23', 'c40'), args.ffpp)]
    for label, path in sources:
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        bpp = float(np.median([p['bpp_real'] for p in d['pairs']]))
        feats = {f: d['summary'][f'chrom/{f}'] for f in FEATURES}
        data['separability'].append({'source': label, 'bpp': bpp, 'features': feats})
    return data


def plot(data: dict, out: Path, celebdf_bpp: float) -> None:
    fig = plt.figure(figsize=(13, 8.6), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 5, height_ratios=[1.25, 1], hspace=0.42, wspace=0.28)
    top = fig.add_subplot(grid[0, :])
    xlim = (0.002, 40)

    def style(ax):
        ax.set_facecolor(SURFACE)
        ax.set_xscale('log')
        ax.set_xlim(*xlim)
        ax.set_xticks([0.01, 0.1, 1, 10])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
        ax.grid(True, which='major', color=GRID, linewidth=0.8)
        for side in ('top', 'right'):
            ax.spines[side].set_visible(False)
        for side in ('left', 'bottom'):
            ax.spines[side].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.axvline(celebdf_bpp, color=MUTED, linestyle='--', linewidth=1.2, zorder=1)

    style(top)
    top.axvspan(0.05, 0.10, color='#efeee9', zorder=0)
    u = data['ubfc']
    for codec, color, name in (('h264', BLUE, 'H.264'), ('mpeg4', ORANGE, 'MPEG-4 Part 2 (Celeb-DF와 같은 코덱)')):
        xs, ys = zip(*u[codec])
        top.plot(xs, ys, color=color, linewidth=2, marker='o', markersize=8, markeredgecolor=SURFACE,
                 markeredgewidth=2, label=name, zorder=3)
        top.annotate(name.split(' ')[0], (xs[0], ys[0]), textcoords='offset points', xytext=(-6, 8),
                     ha='right', color=INK, fontsize=10)
    top.plot(*u['original'], marker='D', markersize=8, color=MUTED, markeredgecolor=SURFACE, markeredgewidth=2,
             linestyle='none', label='원본(비압축)', zorder=3)
    top.annotate('원본(비압축)', tuple(u['original']), textcoords='offset points', xytext=(0, 10), ha='center',
                 color=INK, fontsize=10)
    top.text(celebdf_bpp * 1.05, 28.5, f'Celeb-DF 중앙값 {celebdf_bpp:.3f}', color=MUTED, fontsize=9, va='top')
    top.text(0.0705, 28.5, '경계 부근\n0.05~0.10', color=MUTED, fontsize=8.5, ha='right', va='top',
             bbox={'facecolor': '#efeee9', 'edgecolor': 'none', 'pad': 1})
    top.set_ylim(0, 29)
    top.set_ylabel('심박 오차 MAE (BPM)', color=INK, fontsize=10)
    top.set_title('UBFC-rPPG 3명: 압축할수록 심박 오차 (CHROM, 얼굴 피부 ROI, 20초 조각)', loc='left', color=INK, fontsize=12)
    top.legend(loc='upper right', frameon=False, fontsize=9, labelcolor=INK)

    markers = {'Celeb': 's', 'FF++': 'o'}
    for i, (key, title) in enumerate(FEATURES.items()):
        ax = fig.add_subplot(grid[1, i], sharex=top)
        style(ax)
        ax.axhline(0.5, color=MUTED, linewidth=1, zorder=1)
        for s in data['separability']:
            f = s['features'][key]
            lo, hi = f['ci']
            excluded = lo > 0.5 or hi < 0.5
            marker = markers['Celeb' if s['source'].startswith('Celeb') else 'FF++']
            ax.errorbar(s['bpp'], f['auc'], yerr=[[f['auc'] - lo], [hi - f['auc']]], color=BLUE, elinewidth=1.5,
                        capsize=3, linestyle='none', zorder=2)
            ax.plot(s['bpp'], f['auc'], marker=marker, markersize=8, color=BLUE if excluded else SURFACE,
                    markeredgecolor=BLUE, markeredgewidth=2, linestyle='none', zorder=3)
        ax.set_ylim(0, 1)
        ax.set_title(title, color=INK, fontsize=10)
        ax.set_xlabel('bpp (로그)', color=MUTED, fontsize=9)
        if i == 0:
            ax.set_ylabel('AUC (가짜 쪽 값이 클 확률)', color=INK, fontsize=9.5)
            for s in data['separability']:
                short = s['source'].split(' (')[0].replace('FF++ ', '')
                align = {'c23': 'right', 'Celeb-DF': 'left'}.get(short, 'center')
                ax.annotate(short, (s['bpp'], 0.04), ha=align, color=MUTED, fontsize=8)
        else:
            ax.tick_params(labelleft=False)
    fig.text(0.125, 0.455, '진짜/가짜 구분력 — 0.5 = 구분 못 함. 채운 점 = 95% 신뢰구간이 0.5를 벗어남, 빈 점 = 0.5 포함.'
             '  ■ Celeb-DF 25쌍  ● FaceForensics++ 10쌍 (rPPG 분석 한정)', color=INK, fontsize=10.5)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches='tight', facecolor=SURFACE)


def main() -> int:
    parser = argparse.ArgumentParser(description='압축 강도별 rPPG 성능 그림')
    parser.add_argument('--sweep', required=True)
    parser.add_argument('--celebdf', required=True)
    parser.add_argument('--ffpp', nargs=3, required=True, metavar=('RAW', 'C23', 'C40'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--data', type=Path, help='그림에 쓴 숫자를 JSON으로 저장 (다시 그릴 때 확인용)')
    parser.add_argument('--font', help='한글 글꼴 파일(.ttf)')
    args = parser.parse_args()
    if args.font:
        font_manager.fontManager.addfont(args.font)
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=args.font).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    data = load(args)
    celeb = next(s['bpp'] for s in data['separability'] if s['source'].startswith('Celeb'))
    plot(data, args.out, celeb)
    if args.data:
        args.data.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f'저장: {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
