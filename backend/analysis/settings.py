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

# ── 더미 분석 ──
# 켜져 있으면 워커가 실제 모델 대신 미리 정한 예시 값을 돌려주고, 해석 문장·단계 로그 앞에 '[더미]'를 붙인다.
# 백엔드 골격(2단계)용이다. 실제 메인 모델을 붙이는 3단계에서 끈다: 환경변수 USE_DUMMY_ANALYSIS=false
USE_DUMMY_ANALYSIS = os.environ.get('USE_DUMMY_ANALYSIS', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
# 더미 모드에서 단계마다 걸리는 시간(초). 진행 화면을 확인할 수 있을 만큼만 기다린다 (합계 약 12초)
DUMMY_STAGE_SECONDS = {'preprocess': 4.0, 'model': 5.0, 'rppg': 6.0, 'fusion': 2.0}

# ── 분석 불가 조건 (상세제안서 기능 6) ──
# 영상 길이가 이보다 짧으면 분석하지 않는다 (30fps 기준 300프레임)
MIN_DURATION_SEC = 10.0

# ── 융합 판정 (상세제안서 기능 6) ──
# S = (1 − w)·P_model + w·P_rppg,  w = α·SQI
# 아래 값은 전부 예시다. 5단계에서 Celeb-DF 검증 세트로 확정한다. 프론트엔드 목(frontend/src/mocks/scenarios.ts)과 같은 값이다
ALPHA = 0.5  # w = α·SQI
SCORE_REAL_MAX = 0.4  # S가 이 값 이하면 진짜
SCORE_FAKE_MIN = 0.6  # S가 이 값 이상이면 가짜
CONFLICT_GAP = 0.4  # |P_model − P_rppg|가 이 값 이상이면 두 축이 상충
SQI_MIN = 0.5  # SQI 하한. 미만이면 'rPPG 기여도 낮음'
SQI_GOOD_MIN = 0.7  # SQI 등급: 이 값 이상 '양호', SQI_MIN 이상 '보통', 그 아래 '낮음'
# 미결정: S가 경계 구간(SCORE_REAL_MAX < S < SCORE_FAKE_MIN)인데 두 축이 상충하지 않을 때의 판정.
# 문서에 정의가 없어 프론트엔드 목과 같게 '진짜'로 둔 예시값이다. 'real' 또는 'fake'
BOUNDARY_VERDICT = 'real'

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
