"""
rPPG 압축 강도별 시험 (docs/backend-plan.md 4단계) — UBFC-rPPG를 비트레이트 단계별로 다시 압축해 심박 오차가 어떻게 무너지는지 본다.
SQI의 '압축 정도' 항목 기준을 잡는 근거로 쓴다.

ffmpeg가 필요하다. 분석 이미지에는 넣지 않으므로 일회용 컨테이너에서 설치해 실행한다:
  docker run --rm -v (backend):/app -v (데이터셋):/data:ro -w /app deepfake-backend bash -c \\
    "apt-get update -qq && apt-get install -y -qq --no-install-recommends ffmpeg && python -m scripts.rppg_bitrate_sweep"

코덱: H.264, MPEG-4 Part 2(= Celeb-DF와 같은 코덱), HEVC(libx265, 휴대폰 영상),
      'h264>hevc' = H.264 2000k로 한 번 압축한 뒤 HEVC로 다시 압축(카톡처럼 이중 압축)
  --codecs로 일부만 고를 수 있다. 20초 조각마다 CHROM·POS 심박과 정답을 함께 저장한다(두 방식 차이 분석용).

결과: 코덱 × 비트레이트별
  20초 조각 심박 오차(MAE), SNR(추정 기준), ROI 간 σ, 픽셀당 비트(bpp). 설정의 방식·영역(RPPG_METHOD, RPPG_PRIMARY_ROI)을 쓴다.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from analysis import rppg, settings
from analysis.video_meta import read_video_meta
from scripts.run_rppg import load_ubfc_truth

CODECS = {
    'h264': ['-c:v', 'libx264', '-preset', 'medium'],
    'mpeg4': ['-c:v', 'mpeg4'],
    'hevc': ['-c:v', 'libx265', '-preset', 'medium', '-x265-params', 'log-level=error'],
}
DOUBLE_FIRST_KBPS = 2000  # 이중 압축의 첫 단계(H.264) 비트레이트
BITRATES_KBPS = (8000, 4000, 2000, 1000, 500, 250)
CLIP_SEC = 20.0


def encode(src: Path, dst: Path, codec: str, kbps: int) -> float:
    """src를 codec·목표 비트레이트로 다시 압축하고 실제 비트레이트(kbps)를 돌려준다. 'h264>hevc'는 두 번 압축한다"""
    if codec == 'h264>hevc':
        first = dst.with_name(dst.stem + '_first.mp4')
        encode(src, first, 'h264', DOUBLE_FIRST_KBPS)
        real = encode(first, dst, 'hevc', kbps)
        first.unlink()
        return real
    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src), *CODECS[codec],
           '-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{2 * kbps}k', '-an', str(dst)]
    subprocess.run(cmd, check=True)
    meta = read_video_meta(dst)
    return dst.stat().st_size * 8 / 1000 / meta.duration_sec


def evaluate(video: Path, hr: np.ndarray) -> dict:
    meta = read_video_meta(video)
    traces = rppg.extract_traces(video, meta)
    n = min(len(hr), len(traces.tracked))
    fs, clip = meta.fps, int(round(CLIP_SEC * meta.fps))
    roi = settings.RPPG_PRIMARY_ROI
    err, snr, roi_std, clips = [], [], [], []
    for a in range(0, n - clip + 1, clip):
        est = {k: rppg.estimate_pulse(traces.rgb[k][a:a + clip], fs) for k in rppg.ROI_KEYS + (roi,)}
        main = est[roi]
        other = rppg.estimate_pulse(traces.rgb[roi][a:a + clip], fs, 'pos' if settings.RPPG_METHOD == 'chrom' else 'chrom')
        truth = float(hr[a:a + clip].mean())
        if main.bpm is not None:
            err.append(abs(main.bpm - truth))
            snr.append(main.snr_db)
        bpms = [est[k].bpm for k in rppg.ROI_KEYS if est[k].bpm is not None]
        roi_std.append(float(np.std(bpms)) if len(bpms) >= 2 else np.nan)
        clips.append({'truth': truth, settings.RPPG_METHOD: main.bpm,
                      'pos' if settings.RPPG_METHOD == 'chrom' else 'chrom': other.bpm})
    bpp = video.stat().st_size * 8 / meta.duration_sec / (meta.width * meta.height * meta.fps)
    return {'mae': float(np.mean(err)), 'snr_db': float(np.mean(snr)), 'roi_std': float(np.nanmean(roi_std)), 'bpp': bpp,
            'clips': clips}


def main() -> int:
    parser = argparse.ArgumentParser(description='rPPG 압축 강도별 시험 (UBFC-rPPG)')
    parser.add_argument('--root', type=Path, default=settings.DATASET_DIR / 'UBFC-rPPG' / 'DATASET_2')
    parser.add_argument('--tmp', type=Path, default=Path('/tmp/sweep'))
    parser.add_argument('--codecs', nargs='+', default=list(CODECS) + ['h264>hevc'],
                        choices=list(CODECS) + ['h264>hevc'])
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    args.tmp.mkdir(parents=True, exist_ok=True)

    print(f'방식 {settings.RPPG_METHOD}, 영역 {settings.RPPG_PRIMARY_ROI}, 20초 조각 기준\n')
    records = []
    for folder in sorted(p for p in args.root.iterdir() if (p / 'vid.avi').exists()):
        _, hr, _ = load_ubfc_truth(folder)
        r = evaluate(folder / 'vid.avi', hr)
        records.append({'subject': folder.name, 'codec': '원본', 'target_kbps': None, 'kbps': None, **r})
        print(f'{folder.name} 원본(비압축)            bpp {r["bpp"]:7.3f} | MAE {r["mae"]:5.1f} | SNR {r["snr_db"]:5.1f} | ROI σ {r["roi_std"]:5.1f}', flush=True)
        for codec in args.codecs:
            for kbps in BITRATES_KBPS:
                dst = args.tmp / f'{folder.name}_{codec.replace(">", "-")}_{kbps}.mp4'
                real = encode(folder / 'vid.avi', dst, codec, kbps)
                r = evaluate(dst, hr)
                dst.unlink()
                records.append({'subject': folder.name, 'codec': codec, 'target_kbps': kbps, 'kbps': real, **r})
                print(f'{folder.name} {codec:<9} {kbps:>5}k (실제 {real:5.0f}k) bpp {r["bpp"]:7.3f} | MAE {r["mae"]:5.1f}'
                      f' | SNR {r["snr_db"]:5.1f} | ROI σ {r["roi_std"]:5.1f}', flush=True)

    print('\n요약 (세 사람 평균)')
    print(f'  {"코덱":<6} {"목표":>6} {"bpp":>6} {"MAE":>6} {"SNR":>6} {"ROI σ":>6}')
    for codec in ['원본'] + args.codecs:
        for kbps in (None,) if codec == '원본' else BITRATES_KBPS:
            g = [r for r in records if r['codec'] == codec and r['target_kbps'] == kbps]
            m = {k: np.mean([r[k] for r in g]) for k in ('bpp', 'mae', 'snr_db', 'roi_std')}
            print(f'  {codec:<9} {"-" if kbps is None else f"{kbps}k":>6} {m["bpp"]:6.3f} {m["mae"]:6.1f} {m["snr_db"]:6.1f} {m["roi_std"]:6.1f}')
    if args.json:
        args.json.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
