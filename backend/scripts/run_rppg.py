"""
rPPG 소규모 검증 (docs/backend-plan.md 4단계) — 파이프라인을 웹에 연결하기 전에 신호가 제대로 잡히는지 본다.

  # (a) UBFC-rPPG: 정답 심박(손가락 맥박 측정기) 대비 오차. 원본과 압축 사본(MPEG-4)을 함께, POS·CHROM × 윈도우 6·8초
  python -m scripts.run_rppg ubfc

  # (b) Celeb-real: 평가 세트(List_of_testing_videos.txt)를 뺀 N편 — 정답이 없으므로 신호가 깨끗한 정도(SNR·ROI 간 차이)만
  python -m scripts.run_rppg videos --celebdf-real 25

  # (c) 직접 찍은 영상
  python -m scripts.run_rppg videos /app/out/01_selfie_front.mp4 ...

정답이 없는 영상의 SNR·ROI 간 차이는 '심박을 정확히 뽑았는지'가 아니라 '신호가 깨끗한지'를 보여 줄 뿐이다.
얼굴 이미지는 저장하지 않는다.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from analysis import rppg, settings
from analysis.video_meta import read_video_meta

METHODS = ('pos', 'chrom')
WINDOWS = (6.0, 8.0)
CLIP_SEC = 20.0  # UBFC 영상(약 68초)을 실제 업로드 길이와 비슷한 20초 조각으로 나눠 영상 단위 심박도 본다


# ── (a) UBFC ──

def load_ubfc_truth(folder: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ground_truth.txt: 1줄 PPG 파형, 2줄 심박수(BPM), 3줄 시각(초). 세 줄 모두 영상 프레임마다 값 하나"""
    ppg, hr, t = (np.array(line.split(), dtype=np.float64) for line in (folder / 'ground_truth.txt').read_text().splitlines()[:3])
    return ppg, hr, t


def compress_copy(src: Path, dst: Path) -> float:
    """MPEG-4 Part 2(Celeb-DF와 같은 코덱)로 다시 저장한 사본을 만들고 비트레이트(kbps)를 돌려준다"""
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS)
    size = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*'mp4v'), fps, size)
    frames = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        writer.write(frame)
        frames += 1
    cap.release()
    writer.release()
    return dst.stat().st_size * 8 / 1000 / (frames / fps)


def evaluate_ubfc(traces: rppg.RoiTraces, hr_true: np.ndarray) -> dict:
    """방식(POS·CHROM) × 윈도우(6·8초)별 윈도우 단위 오차, 20초 조각 단위 오차·SNR·ROI 간 차이"""
    fs = traces.fps
    out = {}
    for method in METHODS:
        for win in WINDOWS:
            est = rppg.estimate_pulse(traces.rgb['all'], fs, method, win)
            errors = []
            for start, bpm in est.window_bpm:
                a, b = int(round(start * fs)), int(round((start + win) * fs))
                if bpm is not None:
                    errors.append(bpm - hr_true[a:b].mean())
            out[f'{method}/윈도우{win:g}초'] = _error_stats(errors)
        # 20초 조각: 영상 단위 심박(Welch 10초) — 실제 업로드 영상 길이에 가까운 조건
        clip = int(round(CLIP_SEC * fs))
        clip_err, snr_true, snr_est, roi_std = [], [], [], []
        for a in range(0, len(hr_true) - clip + 1, clip):
            truth = hr_true[a:a + clip].mean()
            per_roi = {}
            for key in rppg.ROI_KEYS + ('all',):
                e = rppg.estimate_pulse(traces.rgb[key][a:a + clip], fs, method)
                per_roi[key] = e
            e_all = per_roi['all']
            if e_all.bpm is not None:
                clip_err.append(e_all.bpm - truth)
                snr_est.append(e_all.snr_db)
            snr_true.append(rppg.snr_at(e_all.freqs, e_all.psd, truth / 60))
            bpms = [per_roi[k].bpm for k in rppg.ROI_KEYS if per_roi[k].bpm is not None]
            roi_std.append(float(np.std(bpms)) if len(bpms) >= 2 else np.nan)
        out[f'{method}/20초조각'] = {**_error_stats(clip_err), 'snr_true_db': _mean(snr_true),
                                   'snr_est_db': _mean(snr_est), 'roi_std_bpm': _mean(roi_std)}
    return out


def _error_stats(errors: list[float]) -> dict:
    e = np.abs(np.array(errors, dtype=np.float64))
    if e.size == 0:
        return {'n': 0}
    return {'n': int(e.size), 'mae': float(e.mean()), 'rmse': float(np.sqrt((e**2).mean())),
            'within5': float((e <= 5).mean())}


def _mean(values) -> float:
    v = np.array([x for x in values if x is not None], dtype=np.float64)
    return float(np.nanmean(v)) if v.size and not np.all(np.isnan(v)) else float('nan')


def run_ubfc(root: Path, tmp: Path) -> list[dict]:
    records = []
    for folder in sorted(p for p in root.iterdir() if (p / 'vid.avi').exists()):
        _, hr, _ = load_ubfc_truth(folder)
        for variant in ('원본', '압축'):
            video = folder / 'vid.avi'
            kbps = None
            if variant == '압축':
                video = tmp / f'{folder.name}_mpeg4.mp4'
                kbps = compress_copy(folder / 'vid.avi', video)
            started = time.perf_counter()
            meta = read_video_meta(video)
            traces = rppg.extract_traces(video, meta)
            n = min(len(hr), len(traces.tracked))
            for key in traces.rgb:
                traces.rgb[key] = traces.rgb[key][:n]
            result = evaluate_ubfc(traces, hr[:n])
            records.append({'subject': folder.name, 'variant': variant, 'kbps': kbps, 'fps': meta.fps,
                            'hr_true_range': [float(hr.min()), float(hr.max())], 'tracked': traces.tracked_rate,
                            'seconds': time.perf_counter() - started, 'result': result})
            line = f'{folder.name} {variant}' + (f'({kbps:.0f}kbps)' if kbps else '') + f' 추적 {traces.tracked_rate:.0%}'
            print(line)
            for name, r in result.items():
                extra = f' SNR(정답기준) {r["snr_true_db"]:.1f}dB, ROI 간 σ {r["roi_std_bpm"]:.1f}' if 'snr_true_db' in r else ''
                print(f'    {name:<16} n={r["n"]:<3} MAE {r.get("mae", float("nan")):5.2f} RMSE {r.get("rmse", float("nan")):5.2f}'
                      f' ±5BPM {r.get("within5", float("nan")):.0%}{extra}')
    _print_ubfc_summary(records)
    return records


def _print_ubfc_summary(records: list[dict]) -> None:
    print('\n요약 (세 사람 평균 MAE, BPM)')
    names = list(records[0]['result']) if records else []
    print(f'  {"":<16} {"원본":>8} {"압축":>8}')
    for name in names:
        row = []
        for variant in ('원본', '압축'):
            v = [r['result'][name].get('mae', np.nan) for r in records if r['variant'] == variant]
            row.append(f'{np.nanmean(v):8.2f}')
        print(f'  {name:<16} ' + ' '.join(row))


# ── (b)(c) 정답 없는 영상 ──

def celebdf_real(root: Path, n: int, seed: int) -> list[Path]:
    """평가 세트를 뺀 Celeb-real을 고정 시드로 섞어, 웹 분석과 같은 조건(MIN_DURATION_SEC 이상)인 영상 n편을 고른다"""
    lines = (root / 'List_of_testing_videos.txt').read_text().splitlines()
    excluded = {line.split()[1] for line in lines if line.strip()}
    candidates = sorted(p for p in (root / 'Celeb-real').glob('*.mp4') if f'Celeb-real/{p.name}' not in excluded)
    random.Random(seed).shuffle(candidates)
    picked = []
    for path in candidates:
        meta = read_video_meta(path)
        if meta and meta.duration_sec >= settings.MIN_DURATION_SEC:
            picked.append(path)
        if len(picked) == n:
            break
    return picked


def run_videos(videos: list[Path], method: str) -> list[dict]:
    records = []
    print(f'방식 {method}, 윈도우 {settings.RPPG_WINDOW_SEC:g}초. 신호 기준(예시): SNR ≥ {settings.RPPG_SIGNAL_SNR_MIN_DB:g}dB'
          f' 그리고 ROI 간 σ ≤ {settings.RPPG_SIGNAL_ROI_STD_MAX_BPM:g}BPM. 피부: ROI 피부의 평균 밝기(0~255)\n')
    print(f'{"영상":<34} {"추적":>5} {"피부":>4} {"심박(all)":>9} {"SNR":>6} {"이마":>6} {"왼볼":>6} {"오른볼":>6} {"ROI σ":>6} {"윈도우 σ":>7}  판정')
    for path in videos:
        meta = read_video_meta(path)
        if meta is None or meta.duration_sec < settings.MIN_DURATION_SEC:
            print(f'{path.name:<34} 제외 — ' + ('열 수 없음' if meta is None else f'{meta.duration_sec:.1f}초로 너무 짧음'))
            continue
        traces = rppg.extract_traces(path, meta)
        est = {key: rppg.estimate_pulse(traces.rgb[key], meta.fps, method) for key in rppg.ROI_KEYS + ('all',)}
        a = est['all']
        roi_bpm = {k: est[k].bpm for k in rppg.ROI_KEYS}
        valid = [b for b in roi_bpm.values() if b is not None]
        roi_std = float(np.std(valid)) if len(valid) >= 2 else float('nan')
        wins = [b for _, b in a.window_bpm if b is not None]
        win_std = float(np.std(wins)) if len(wins) >= 2 else float('nan')
        brightness = float(traces.rgb['all'].mean())
        captured = (a.snr_db is not None and a.snr_db >= settings.RPPG_SIGNAL_SNR_MIN_DB
                    and roi_std <= settings.RPPG_SIGNAL_ROI_STD_MAX_BPM)
        name = f'{path.parent.name}/{path.name}'
        records.append({'video': name, 'tracked': traces.tracked_rate, 'bpm': a.bpm, 'snr_db': a.snr_db,
                        'roi_bpm': roi_bpm, 'roi_std': roi_std, 'window_std': win_std, 'skin_mean': brightness,
                        'captured': captured, 'duration': meta.duration_sec})
        fmt = lambda v: '-' if v is None or (isinstance(v, float) and np.isnan(v)) else f'{v:.1f}'  # noqa: E731
        print(f'{name[-34:]:<34} {traces.tracked_rate:>5.0%} {brightness:>4.0f} {fmt(a.bpm):>9} {fmt(a.snr_db):>6}'
              f' {fmt(roi_bpm["forehead"]):>6} {fmt(roi_bpm["left_cheek"]):>6} {fmt(roi_bpm["right_cheek"]):>6}'
              f' {fmt(roi_std):>6} {fmt(win_std):>7}  {"잡힘" if captured else "-"}')
    _print_video_summary(records)
    return records


def _print_video_summary(records: list[dict]) -> None:
    if not records:
        return
    snr = np.array([r['snr_db'] if r['snr_db'] is not None else np.nan for r in records])
    std = np.array([r['roi_std'] for r in records])
    q = lambda v: '중앙값 {:.1f} (사분위 {:.1f}~{:.1f})'.format(*np.nanpercentile(v, [50, 25, 75]))  # noqa: E731
    print(f'\n요약 {len(records)}편: 신호 기준을 넘은 영상 {sum(r["captured"] for r in records)}편'
          f'\n  SNR(dB) {q(snr)}\n  ROI 간 σ(BPM) {q(std)}')


def main() -> int:
    parser = argparse.ArgumentParser(description='rPPG 소규모 검증')
    sub = parser.add_subparsers(dest='mode', required=True)
    u = sub.add_parser('ubfc', help='UBFC-rPPG 정답 대비 오차')
    u.add_argument('--root', type=Path, default=settings.DATASET_DIR / 'UBFC-rPPG' / 'DATASET_2')
    u.add_argument('--tmp', type=Path, default=Path('/tmp/rppg'), help='압축 사본을 둘 임시 폴더')
    v = sub.add_parser('videos', help='정답 없는 영상의 신호 상태')
    v.add_argument('videos', nargs='*', type=Path)
    v.add_argument('--celebdf-real', type=int, metavar='N', help='평가 세트를 뺀 Celeb-real에서 N편')
    v.add_argument('--seed', type=int, default=0)
    v.add_argument('--method', choices=METHODS, default=settings.RPPG_METHOD)
    for p in (u, v):
        p.add_argument('--json', type=Path, help='결과 JSON 저장 경로')
    args = parser.parse_args()

    if args.mode == 'ubfc':
        args.tmp.mkdir(parents=True, exist_ok=True)
        records = run_ubfc(args.root, args.tmp)
    else:
        videos = list(args.videos)
        if args.celebdf_real:
            videos += celebdf_real(settings.CELEBDF_DIR, args.celebdf_real, args.seed)
        if not videos:
            parser.error('영상 경로나 --celebdf-real 중 하나는 필요합니다')
        records = run_videos(videos, args.method)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=float))
    return 0


if __name__ == '__main__':
    sys.exit(main())
