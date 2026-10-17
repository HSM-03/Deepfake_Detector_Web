"""
메인 모델 단독 실행 (docs/backend-plan.md 1단계) — 웹 없이 영상의 P_model·분산·구간 프로파일을 출력한다.

사용 예 (컨테이너 안, /app 기준):
  # 영상 직접 지정 (DATASET_DIR 기준 상대 경로 또는 절대 경로)
  python -m scripts.run_main_model Celeb-DF-v2/Celeb-real/id0_0000.mp4

  # Celeb-DF에서 평가 세트(List_of_testing_videos.txt)를 뺀 영상 중 진짜 N개·가짜 N개를 골라 실행
  python -m scripts.run_main_model --celebdf-sample 5

  # 직접 찍은 영상 확인 (얼굴 검출률이 MAIN_MODEL_MIN_FACE_RATE보다 낮으면 '기준 미달'로 표시), 진행률 알림도 출력
  python -m scripts.run_main_model /app/out/my_webcam.webm --progress

  # 결과를 JSON으로도 저장 (얼굴 이미지는 저장하지 않는다)
  python -m scripts.run_main_model --celebdf-sample 5 --json /app/out/main_model.json
"""
import argparse
import json
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

from analysis import settings
from analysis.main_model import MainModel

# Celeb-DF 폴더 → 정답 (진짜 / 가짜)
CELEBDF_LABELS = {'Celeb-real': '진짜', 'YouTube-real': '진짜', 'Celeb-synthesis': '가짜'}


def celebdf_test_set(root: Path) -> set[str]:
    """최종 평가 전용 518개. 어떤 실험에도 쓰지 않도록 고를 때 뺀다 (줄 형식: '1 YouTube-real/00170.mp4')"""
    lines = (root / 'List_of_testing_videos.txt').read_text().splitlines()
    return {line.split()[1] for line in lines if line.strip()}


def celebdf_sample(root: Path, per_class: int, seed: int) -> list[Path]:
    """평가 세트를 뺀 Celeb-real에서 per_class개, Celeb-synthesis에서 per_class개를 고정 시드로 고른다"""
    excluded = celebdf_test_set(root)
    rng = random.Random(seed)
    picked: list[Path] = []
    for folder in ('Celeb-real', 'Celeb-synthesis'):
        candidates = sorted(p for p in (root / folder).glob('*.mp4') if f'{folder}/{p.name}' not in excluded)
        picked += rng.sample(candidates, per_class)
    return picked


def label_of(path: Path) -> str:
    return CELEBDF_LABELS.get(path.parent.name, '-')


def resolve(video: str) -> Path:
    path = Path(video)
    return path if path.is_absolute() else settings.DATASET_DIR / path


def fmt(value: float | None, digits: int = 3) -> str:
    return '-' if value is None else f'{value:.{digits}f}'


def main() -> int:
    parser = argparse.ArgumentParser(description='메인 모델(EfficientNet-B4) 단독 실행')
    parser.add_argument('videos', nargs='*', help='영상 경로 (DATASET_DIR 기준 상대 경로 또는 절대 경로)')
    parser.add_argument('--celebdf-sample', type=int, metavar='N', help='평가 세트를 뺀 Celeb-DF에서 진짜·가짜 각 N개')
    parser.add_argument('--seed', type=int, default=0, help='--celebdf-sample 고를 때 시드 (기본 0)')
    parser.add_argument('--frames', type=int, default=settings.MAIN_MODEL_NUM_FRAMES, help='영상당 뽑을 프레임 수')
    parser.add_argument('--json', type=Path, help='결과를 저장할 JSON 경로')
    parser.add_argument('--profile', action='store_true', help='영상마다 구간별 프로파일도 출력')
    parser.add_argument('--progress', action='store_true', help='진행률 알림(전처리·메인 모델)을 받는 대로 출력')
    parser.add_argument('--detect-max-side', type=int, default=settings.MAIN_MODEL_DETECT_MAX_SIDE, metavar='PX',
                        help=f'얼굴 찾기 때 프레임 긴 변 최대 크기 (기본 {settings.MAIN_MODEL_DETECT_MAX_SIDE}, 0이면 원본 그대로)')
    args = parser.parse_args()

    videos = [resolve(v) for v in args.videos]
    if args.celebdf_sample:
        videos += celebdf_sample(settings.CELEBDF_DIR, args.celebdf_sample, args.seed)
    if not videos:
        parser.error('영상 경로나 --celebdf-sample 중 하나는 필요합니다')

    started = time.perf_counter()
    model = MainModel()
    print(f'모델·얼굴 검출기 불러오기: {time.perf_counter() - started:.1f}초')
    print(f'영상 {len(videos)}개, 영상당 프레임 {args.frames}장, 이상치 제거 위·아래 각 {settings.MAIN_MODEL_TRIM_RATIO:.0%},'
          f' 얼굴 검출률 기준 {settings.MAIN_MODEL_MIN_FACE_RATE:.0%}(예시),'
          f' 얼굴 찾기 최대 크기 {args.detect_max_side or "원본"}\n')

    # 얼굴: 잡힌 수/뽑은 수. 없음/탈락: 얼굴을 못 찾은 수/찾았지만 재검출에서 버린 수. 크기: 검출된 얼굴 상자 평균(px)
    # 재시도: 줄인 사본에서 못 찾아 원본에서 다시 찾은 프레임 수. 밝기: 뽑은 프레임 평균 (0~255)
    header = (f'{"영상":<36} {"정답":<3} {"P_model":>7} {"표준편차":>7} {"얼굴":>6} {"없음/탈락":>9} {"크기":>9}'
              f' {"재시도":>4} {"밝기":>4} {"길이":>6}  시간(디코딩/얼굴/모델/합계 초)')
    print(header)
    print('-' * len(header.encode('utf-8')))

    records = []
    for path in videos:
        name = f'{path.parent.name}/{path.name}'
        try:
            result = model.analyze(path, args.frames, on_progress=_print_progress if args.progress else None,
                                   detect_max_side=args.detect_max_side or None)
        except Exception as error:  # 영상 하나가 실패해도 나머지는 계속한다
            print(f'{name:<36} 실패: {error}')
            records.append({'video': name, 'label': label_of(path), 'error': str(error)})
            continue
        t = result.timing_sec
        print(
            f'{name:<36} {label_of(path):<3} {fmt(result.p_model):>7} {fmt(result.p_model_std):>7}'
            f' {result.frames_with_face:>3}/{result.frames_sampled:<2}'
            f' {f"{result.stats.frames_no_face}/{result.stats.frames_recheck_failed}":>9}'
            f' {"×".join(map(str, result.stats.face_box_mean)) if result.stats.face_box_mean else "-":>9}'
            f' {result.stats.frames_retried_full_res:>5} {result.stats.brightness_mean:>5.0f}'
            f' {result.duration_sec:>5.1f}s'
            f'  {t["decode"]:.1f} / {t["face"]:.1f} / {t["model"]:.1f} / {t["total"]:.1f}'
            + ('  ← 얼굴 검출률 기준 미달' if result.face_rate < settings.MAIN_MODEL_MIN_FACE_RATE else '')
        )
        if args.profile:
            print('    구간: ' + ', '.join(f'{s.t_start:g}~{s.t_end:g}s {s.p:.2f}' for s in result.profile))
        records.append({'video': name, 'label': label_of(path), **asdict(result)})

    _print_summary(records)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print(f'\nJSON 저장: {args.json}')
    return 0


def _print_progress(stage: str, percent: int) -> None:
    print(f'    진행률 {stage}: {percent}%', flush=True)


def _print_summary(records: list[dict]) -> None:
    done = [r for r in records if 'error' not in r and r['p_model'] is not None]
    if not done:
        return
    print('\n요약 (P_model 0.5 기준 — 임계값 확정 전 참고용)')
    for label in ('진짜', '가짜'):
        group = [r['p_model'] for r in done if r['label'] == label]
        if not group:
            continue
        correct = sum((p >= 0.5) == (label == '가짜') for p in group)
        print(f'  {label}: {len(group)}개, P_model 평균 {sum(group) / len(group):.3f}, 0.5 기준으로 맞힌 수 {correct}/{len(group)}')
    totals = [r['timing_sec']['total'] for r in done]
    print(f'  영상 1편 처리 시간: 평균 {sum(totals) / len(totals):.1f}초 (최소 {min(totals):.1f} / 최대 {max(totals):.1f})')


if __name__ == '__main__':
    sys.exit(main())
