"""
5단계 P_rppg 분류기 학습·평가 — docs/stage5-preregistration.md 2·3절을 그대로 따른다.

  python -m scripts.train_p_rppg train            학습 쌍 교차검증(C 고르기, SVM 비교) → 최종 모델을 analysis/p_rppg_model.json에 저장
  python -m scripts.train_p_rppg test             시험 쌍을 최종 모델로 **한 번만** 평가(결과 파일이 있으면 다시 하지 않음)
  python -m scripts.train_p_rppg own /own/…mp4    직접 찍은 영상의 P_rppg (참고 확인, 기준과 별개)

- 특징: backend/out/stage5/ffpp_features.jsonl (scripts/extract_rppg_features.py). 쌍 목록: split 파일(docs/stage5/ffpp_split.json 사본).
- 특징 6개 고정, NaN은 학습 쌍 중앙값으로 채우고 학습 쌍 기준 표준화, 로지스틱 회귀(가짜 = 1). P_rppg = 가짜일 확률.
- 제외 규칙: 쌍의 두 영상 중 하나라도 기록이 없거나 열 수 없거나, 10초 미만이거나, 얼굴 추적률 70% 미만이면 뺀다.
- 모델 파일에는 숫자(중앙값·평균·표준편차·계수)만 담는다(pickle 안 씀). P_rppg 계산식은 analysis/p_rppg.py 한 곳(서비스와 같음).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from analysis import rppg_features, settings
from analysis.p_rppg import MODEL_PATH, predict

FEATURES = rppg_features.FEATURE_KEYS  # 6개, 순서 고정
C_GRID = (0.01, 0.03, 0.1, 0.3, 1, 3, 10)
CV_FOLDS = 5
SEED = 0
BOOTSTRAP = 2000
MIN_TRACKED = 0.7

OUT_DIR = Path('/app/out/stage5')
FEATURES_PATH = OUT_DIR / 'ffpp_features.jsonl'
SPLIT_PATH = OUT_DIR / 'ffpp_split.json'
TEST_RESULT_PATH = OUT_DIR / 'test_result.json'


def load_rows() -> dict[str, dict]:
    rows = {}
    for line in FEATURES_PATH.read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['compression'] == 'raw':
            rows[row['video_id']] = row
    return rows


def exclusion_reason(row: dict | None) -> str | None:
    if row is None:
        return '기록 없음'
    if 'error' in row:
        return row['error']
    if row['duration_sec'] < settings.MIN_DURATION_SEC:
        return f'{settings.MIN_DURATION_SEC:g}초 미만'
    if row['tracked_rate'] < MIN_TRACKED:
        return f'추적률 {MIN_TRACKED:.0%} 미만'
    return None


def build(pairs: list[str], rows: dict[str, dict]):
    """쌍 목록 → X(영상별 특징), y(가짜 1), 묶음 번호, 쌍 이름, 뺀 쌍"""
    X, y, groups, names, excluded = [], [], [], [], []
    for pair in pairs:
        real, fake = rows.get(pair.split('_')[0]), rows.get(pair)
        reason = exclusion_reason(real) or exclusion_reason(fake)
        if reason:
            excluded.append((pair, reason))
            continue
        group = '_'.join(sorted(pair.split('_')))
        for row, label in ((real, 0), (fake, 1)):
            X.append([np.nan if row['features'][k] is None else row['features'][k] for k in FEATURES])
            y.append(label)
            groups.append(group)
            names.append(pair)
    return np.array(X, float), np.array(y), np.array(groups), np.array(names), excluded


def make_pipeline(model):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline as mp
    from sklearn.preprocessing import StandardScaler
    return mp(SimpleImputer(strategy='median'), StandardScaler(), model)


def cv_auc(X, y, groups, model) -> float:
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedGroupKFold
    scores = []
    for tr, va in StratifiedGroupKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED).split(X, y, groups):
        pipe = make_pipeline(model).fit(X[tr], y[tr])
        scores.append(roc_auc_score(y[va], pipe.predict_proba(X[va])[:, 1]))
    return float(np.mean(scores))


def train(split: dict) -> int:
    from sklearn import __version__ as sk_version
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC

    rows = load_rows()
    pairs = split['train_old25'] + split['train_new']
    X, y, groups, _names, excluded = build(pairs, rows)
    print(f'학습 쌍: {len(pairs)}개 중 {len(pairs) - len(excluded)}개 사용, 제외 {len(excluded)}개')
    for pair, reason in excluded:
        print(f'  제외 {pair}: {reason}')

    print(f'\n교차검증 {CV_FOLDS}겹(묶음 단위, 시드 {SEED}) AUC 평균')
    lr_scores = {c: cv_auc(X, y, groups, LogisticRegression(C=c, max_iter=5000)) for c in C_GRID}
    svm_scores = {c: cv_auc(X, y, groups, SVC(C=c, kernel='rbf', probability=True, random_state=SEED)) for c in C_GRID}
    for c in C_GRID:
        print(f'  C={c:<5}  로지스틱 회귀 {lr_scores[c]:.3f}   SVM(비교) {svm_scores[c]:.3f}')
    best_c = max(C_GRID, key=lambda c: (lr_scores[c], -c))  # 같으면 더 강한 정규화(작은 C)
    print(f'→ 고른 C = {best_c} (교차검증 AUC {lr_scores[best_c]:.3f}). 최종 모델은 로지스틱 회귀(사전 등록)')

    pipe = make_pipeline(LogisticRegression(C=best_c, max_iter=5000)).fit(X, y)
    imputer, scaler, lr = pipe.steps[0][1], pipe.steps[1][1], pipe.steps[2][1]
    model = {
        'kind': 'logistic_regression',
        'features': list(FEATURES),
        'impute_median': [float(v) for v in imputer.statistics_],
        'scale_mean': [float(v) for v in scaler.mean_],
        'scale_std': [float(v) for v in scaler.scale_],
        'coef': [float(v) for v in lr.coef_[0]],
        'intercept': float(lr.intercept_[0]),
        'C': best_c,
        'cv_auc': round(lr_scores[best_c], 4),
        'cv_auc_svm_best': round(max(svm_scores.values()), 4),
        'trained_pairs': len(pairs) - len(excluded),
        'data': 'FaceForensics++ Deepfakes raw(c0), docs/stage5/ffpp_split.json 학습 쌍',
        'sklearn': sk_version,
        'trained_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    # 모델 파일의 숫자만으로 계산한 값(서비스가 쓰는 식)이 scikit-learn 결과와 같아야 한다
    gap = float(np.max(np.abs(predict(model, X) - pipe.predict_proba(X)[:, 1])))
    assert gap < 1e-9, f'모델 파일 계산과 scikit-learn 결과가 다름 ({gap:.1e})'
    MODEL_PATH.write_text(json.dumps(model, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'모델 파일 계산 = scikit-learn 결과 (최대 차이 {gap:.1e})')
    print('\n계수(표준화된 특징 기준, + 쪽이 가짜):')
    for k, c in zip(FEATURES, model['coef']):
        print(f'  {k:<18} {c:+.3f}')
    print(f'저장: {MODEL_PATH}')
    return 0


def test(split: dict) -> int:
    from scripts.check_rppg_separability import auc, bootstrap_ci

    if TEST_RESULT_PATH.exists():
        print(f'시험 쌍은 이미 평가했습니다({TEST_RESULT_PATH}). 사전 등록에 따라 다시 평가하지 않습니다.')
        print(TEST_RESULT_PATH.read_text(encoding='utf-8'))
        return 1
    model = json.loads(MODEL_PATH.read_text(encoding='utf-8'))
    rows = load_rows()
    X, y, _groups, names, excluded = build(split['test'], rows)
    p = predict(model, X)
    real, fake = p[y == 0], p[y == 1]  # build가 쌍마다 진짜·가짜 순서로 넣으므로 같은 위치가 같은 쌍
    value = auc(real, fake)
    lo, hi = bootstrap_ci(real, fake, BOOTSTRAP, SEED)
    result = {
        'auc': round(value, 4), 'ci95': [round(lo, 4), round(hi, 4)],
        'success': bool(lo > 0.5), 'criterion': '시험 쌍 AUC 95% 신뢰구간 하한 > 0.5 (쌍 단위 부트스트랩 2000회, 시드 0)',
        'pairs_used': len(real), 'pairs_listed': len(split['test']), 'excluded': excluded,
        'p_rppg_real_median': round(float(np.median(real)), 4), 'p_rppg_fake_median': round(float(np.median(fake)), 4),
        'model_C': model['C'], 'model_cv_auc': model['cv_auc'],
        'evaluated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    TEST_RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=1))
    print('\n판정:', '성공 — 분류기를 서비스에 연결한다(5-3)' if result['success'] else '실패 — 사전 등록의 대안 규칙으로 간다')
    return 0


def own(paths: list[Path]) -> int:
    from analysis import rppg
    from analysis.video_meta import read_video_meta

    model = json.loads(MODEL_PATH.read_text(encoding='utf-8'))
    print('직접 찍은 영상의 P_rppg (참고 확인 — 진짜 쪽 = 0.5 미만)')
    for path in paths:
        meta = read_video_meta(path)
        max_frames = int(round(settings.RPPG_MAX_ANALYSIS_SEC * meta.fps)) if meta.fps else None
        values = rppg_features.compute(rppg.extract_traces(path, meta, max_frames=max_frames)).values
        x = np.array([[values[k] for k in FEATURES]], float)
        value = float(predict(model, x)[0])
        print(f'  {path.name:<28} P_rppg {value:.3f} {"진짜 쪽" if value < 0.5 else "가짜 쪽"}', flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('train', 'test', 'own'))
    parser.add_argument('paths', nargs='*', type=Path)
    args = parser.parse_args()
    if args.command == 'own':
        return own(args.paths)
    split = json.loads(SPLIT_PATH.read_text(encoding='utf-8'))
    return train(split) if args.command == 'train' else test(split)


if __name__ == '__main__':
    sys.exit(main())
