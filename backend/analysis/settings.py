"""
분석 설정 — 바뀔 수 있는 값은 이 파일 한 곳에서 관리한다.

경로는 환경변수로 받는다(컨테이너 안 기본값: /models, /data).
"예시"라고 적은 값은 아직 근거가 없는 시작값이며, Celeb-DF 학습·검증 세트 실험으로 확정한다(docs/backend-plan.md 5단계).
"""
import os
from pathlib import Path

# ── 경로 ──
MODEL_DIR = Path(os.environ.get('MODEL_DIR', '/models'))
DATASET_DIR = Path(os.environ.get('DATASET_DIR', '/data'))

EFFNB4_WEIGHTS = MODEL_DIR / 'effnb4_best.pth'
DLIB_LANDMARKS = MODEL_DIR / 'shape_predictor_81_face_landmarks.dat'
CELEBDF_DIR = DATASET_DIR / 'Celeb-DF-v2'

# ── 메인 모델 (기능 3) ──
# 영상에서 고르게 뽑을 프레임 수. DeepfakeBench 전처리 기본값(32)과 같게 둔다
MAIN_MODEL_NUM_FRAMES = 32
# 얼굴 정렬 후 크기. DeepfakeBench EfficientNet-B4 설정(resolution: 256)과 같아야 한다
MAIN_MODEL_FACE_SIZE = 256
# 한 번에 모델에 넣는 얼굴 수. 32장을 한 번에 넣는 것이 8장씩 넣는 것보다 약 20% 빨랐다(1단계 속도 실험)
MAIN_MODEL_BATCH_SIZE = 32
# P_model을 낼 때 위·아래에서 각각 버리는 비율 (예시). 0.1이면 32장 중 위 3장·아래 3장을 뺀다
MAIN_MODEL_TRIM_RATIO = 0.1
# 구간별 점수 프로파일의 구간 길이(초) (예시)
MAIN_MODEL_SEGMENT_SEC = 2.0
