"""
P_rppg 분류기 (5단계) — 특징 6개로 "가짜일 확률"을 계산한다. 1에 가까울수록 가짜.

학습은 scripts/train_p_rppg.py(FF++ c0 Deepfakes 학습 쌍, 로지스틱 회귀)가 하고, 결과 숫자만 p_rppg_model.json에 저장한다.
여기서는 그 숫자로 같은 식을 계산한다: 빈 값은 학습 중앙값으로 채움 → 표준화 → 로지스틱 함수. scikit-learn 없이 NumPy만 쓴다.
"""
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).with_name('p_rppg_model.json')


@lru_cache(maxsize=1)
def load_model(path: Path = MODEL_PATH) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def predict(model: dict, X: np.ndarray) -> np.ndarray:
    """X: (영상 수, 특징 6개 — model['features'] 순서). NaN은 학습 중앙값으로 채운다"""
    X = np.asarray(X, float)
    X = np.where(np.isnan(X), np.array(model['impute_median']), X)
    z = (X - np.array(model['scale_mean'])) / np.array(model['scale_std'])
    return 1 / (1 + np.exp(-(z @ np.array(model['coef']) + model['intercept'])))


def p_rppg(features: dict[str, float], model: dict | None = None) -> float:
    """특징 6개(rppg_features.compute(...).values) → P_rppg"""
    model = model or load_model()
    x = np.array([[features.get(k, np.nan) for k in model['features']]], float)
    return float(predict(model, x)[0])
