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
# 켜져 있으면 실제 분석 대신 미리 정한 예시 값(dummy.py)을 쓰고, 해당 문구 앞에 '[더미]'를 붙인다. 환경변수로 켜고 끈다.
def _env_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


# 메인 모델 점수(P_model, 구간 프로파일). 3단계에서 실제 EfficientNet-B4를 붙여 기본으로 끈다.
# 켜면(USE_DUMMY_MAIN_MODEL=true) 모델 없이 화면만 확인할 수 있다(파일 이름 키워드 fail·noface도 이때만 동작)
USE_DUMMY_MAIN_MODEL = _env_flag('USE_DUMMY_MAIN_MODEL', False)
# rPPG 신호 분석(SQI·ROI 심박·특징·근거 차트). 4단계에서 실제 계산을 붙여 기본으로 끈다.
# 켜면(USE_DUMMY_RPPG=true) 예전처럼 더미 시나리오로 동작한다 — 파일 이름 키워드(hold, lowsqi, fake)로 판단 보류 등 화면을 확인할 때 쓴다
USE_DUMMY_RPPG = _env_flag('USE_DUMMY_RPPG', False)
# P_rppg(rPPG 축의 진짜/가짜 점수): 기본은 5단계 분류기(analysis/p_rppg.py, FF++ c0 학습). 켜면(true) 예전처럼 P_model 값을 임시로 쓴다
USE_DUMMY_P_RPPG = _env_flag('USE_DUMMY_P_RPPG', False)
# 더미 모드에서 단계마다 걸리는 시간(초). 진행 화면을 확인할 수 있을 만큼만 기다린다 (합계 약 12초)
# rppg_after_main: 메인 모델이 실제일 때, 메인 모델이 끝난 뒤 더미 rPPG를 채우는 시간
DUMMY_STAGE_SECONDS = {'preprocess': 4.0, 'model': 5.0, 'rppg': 6.0, 'fusion': 2.0, 'rppg_after_main': 2.0}

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
# S가 경계 구간(SCORE_REAL_MAX < S < SCORE_FAKE_MIN)인데 두 축이 상충하지 않을 때의 판정 — 5-5에서 정함(2026-10-26).
# 사전 등록(docs/stage5-preregistration.md 5절) 규칙: Celeb-DF 검증 세트에서 보류 비율 20% 이하 후보 중 확신 오류율 최소.
# 'hold'는 확신 오류가 가장 낮았지만(8.6%) 보류 22.8%로 상한을 넘었고, 'fake' 16.2% < 'real' 18.8%. 'real' | 'fake'
BOUNDARY_VERDICT = 'fake'

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
# 메인 모델 분석 불가 기준: 뽑은 프레임 중 얼굴이 잡힌 비율이 이보다 낮으면 '얼굴 미검출'로 분석을 멈춘다 (예시).
# 80%로 시작했다가 고개를 돌리는 셀카 영상(78.1%)이 탈락해 70%로 낮췄다(3-6). 검출률은 작업마다 DB에 남기므로
# 분포를 보고 다시 정한다. 메인 모델용 기준이다. rPPG에 필요한 얼굴 기준(연속 추적 등)은 4단계에서 따로 정한다
MAIN_MODEL_MIN_FACE_RATE = 0.7
# 얼굴 '찾기'를 할 때 프레임 긴 변의 최대 크기(px). 더 크면 줄인 사본에서 찾고, 못 찾으면 원본에서 다시 찾는다.
# 1080×1920 휴대폰 영상은 원본에서 찾으면 32장에 약 20초가 걸린다. None이면 줄이지 않는다
MAIN_MODEL_DETECT_MAX_SIDE = 960

# ── 분석 불가 안내 문구 (판정에는 쓰지 않는다, 예시) ──
# 찾은 얼굴의 평균 크기가 이보다 작을 때만 '얼굴을 더 크게' 안내를 넣는다(px)
FACE_SMALL_PX = 100
# 뽑은 프레임의 평균 밝기(흑백 0~255)가 이보다 낮으면 '영상이 어둡다' 안내를 넣는다
DARK_BRIGHTNESS = 60
# 진행률 추정용: 얼굴 한 장을 모델에 넣는 데 걸리는 시간(초). 노트북 CPU 측정값(1단계, 32장 약 18초).
# 32장을 한 번에 계산해 중간 진행을 알 수 없어서, 경과 시간 ÷ (이 값 × 얼굴 수)로 진행률을 추정한다
MAIN_MODEL_SEC_PER_FACE = 0.6

# ── rPPG (기능 2·4) — 4단계. 전부 예시값이며 UBFC-rPPG·Celeb-DF 학습/검증 세트로 확정한다 ──
# 심박 대역 (Hz). 0.7~4Hz = 42~240 BPM. 대역통과 필터와 피크 탐색에 함께 쓴다
RPPG_BAND_HZ = (0.7, 4.0)
# Butterworth 차수. 2차 구간(SOS)으로 구현하고 앞뒤로 한 번씩 적용한다(filtfilt — 실제 감쇠는 두 배)
RPPG_FILTER_ORDER = 4
# 원신호를 만드는 방식: 'pos'(Wang 2017) 또는 'chrom'(de Haan 2013).
# UBFC 원본에서는 둘이 같고(영상 단위 오차 약 1.5BPM), 압축 사본에서 CHROM이 덜 나빠 CHROM으로 정했다(4단계, 2026-10-19)
RPPG_METHOD = 'chrom'
# 심박·SNR·윈도우 심박을 재는 영역. 'all'(이마·양 볼 세 영역 합) / 'face'(얼굴 윤곽 − 눈·입) / 'face_skin'(+ 피부색 필터).
# 압축 사본에서 face_skin이 가장 나았고(CHROM 23.6 → 8.7BPM) 원본에서는 차이가 없었다. ROI 간 일치도는 항상 세 영역으로 잰다
RPPG_PRIMARY_ROI = 'face_skin'
# POS·CHROM이 피부색 정규화에 쓰는 짧은 창 길이(초). 두 논문의 값(약 1.6초)
RPPG_COMBINE_WINDOW_SEC = 1.6
# 영상 전체 심박: Welch 구간 길이(초), 50% 겹침. 실제 주파수 해상도 = 1/구간 길이 (10초 → 0.1Hz = 6BPM)
RPPG_PSD_SEGMENT_SEC = 10.0
# 스펙트럼 계산 간격(Hz). 0을 덧붙여(zero-padding) 촘촘히 계산하고 피크는 포물선 보간한다. 0.01Hz = 0.6BPM
RPPG_PSD_GRID_HZ = 0.01
# 윈도우별 심박: 윈도우 길이와 간격(초). 화면설계서의 3초(해상도 20BPM)에서 바꿨다(설계 변경).
# UBFC 원본에서 8초가 6초보다 조금 나아(윈도우 오차 2.6 vs 3.0BPM) 8초로 정했다
RPPG_WINDOW_SEC = 8.0
RPPG_WINDOW_STEP_SEC = 1.0
# SNR(de Haan 2013 방식): 심박 f0 ± 이 폭(Hz) + 2배 주파수 2·f0 ± 아래 폭 안의 파워 ÷ 대역 안 나머지 파워
RPPG_SNR_HALF_WIDTH_HZ = 0.1
RPPG_SNR_HARMONIC_HALF_WIDTH_HZ = 0.2
# '신호가 잡혔다'고 보는 기준(예시). 정확도가 아니라 신호가 깨끗한 정도다.
# UBFC 원본(SNR +2.5~+3.7dB, ROI 간 σ 0.2~0.4)과 압축 사본(−2~−4dB, 6.5~12) 사이의 빈 구간에서 잡았다.
# 이 기준이면 휴대폰·웹캠 원본(SNR 대부분 0dB 미만)에서도 rPPG가 꺼진다 — 휴대폰이 통과하도록 낮추지는 않는다
RPPG_SIGNAL_SNR_MIN_DB = 0.0
RPPG_SIGNAL_ROI_STD_MAX_BPM = 3.0
# 특징 'hr_in_range'의 생리학적 심박 범위(BPM). 예시
RPPG_HR_RANGE_BPM = (45.0, 180.0)

# ── SQI(신호품질지수, 기능 6) — 4단계. 네 항목(각 0~1) 중 가장 낮은 값이 SQI다(가장 약한 고리). 기준값은 전부 예시 ──
# 압축: 영상 스트림 bpp(픽셀당 비트, analysis/stream_info.py)를 코덱별 (0점 bpp, 1점 bpp) 사이에서 로그 눈금으로 0~1.
# 근거는 UBFC 비트레이트 단계별 시험(H.264·MPEG-4만). 나머지 코덱은 시험하지 않았다 — 근거 없음, 보수적 기본값
SQI_COMPRESSION_BPP = {
    'h264': (0.02, 0.10),  # 0.016 → 오차 15BPM, 0.053 → 4.1, 0.11 → 2.0
    'mpeg4': (0.06, 0.13),  # 0.056 → 21, 0.10 → 4.2, 0.13 → 2.0
    # HEVC(libx265): 시험한 가장 낮은 bpp 0.028까지 오차 1.7BPM(원본 수준)이라 1점 지점은 0.028(실측).
    # 0점 지점 0.008은 시험 범위 밖 추정(H.264가 0.016에서 무너지고 HEVC는 같은 화질에 약 절반 용량) — 근거 약함
    'hevc': (0.008, 0.028),
}
# 코덱 → 적용할 기준. HEVC는 2026-10-20 시험으로 따로 정했다. VP9·AV1은 시험하지 않았고(근거 없음, 보수적 기본값)
# 같은 bpp에서 H.264보다 효율이 좋아 H.264 기준을 쓴다.
# 주의: 파일 정보로는 이중 압축(예: H.264 → HEVC, 카카오톡 재전송)을 알아낼 수 없다 — 최종 bpp가 높아도 신호가 망가질 수 있다.
# VP8과 목록에 없는 코덱은 가장 엄격한 MPEG-4 기준. 무압축은 항상 1점
SQI_CODEC_RULE = {'h264': 'h264', 'h265': 'hevc', 'hevc': 'hevc', 'vp9': 'h264', 'av1': 'h264', 'av01': 'h264',
                  'mpeg4': 'mpeg4', 'vp8': 'mpeg4'}
SQI_CODEC_DEFAULT_RULE = 'mpeg4'
SQI_LOSSLESS_CODECS = ('rawvideo', 'raw', 'ffv1', 'huffyuv', '')  # ''는 FourCC가 비어 있는 비압축 AVI(UBFC 원본 등)
# 얼굴 크기: 얼굴 피부 ROI의 프레임당 평균 픽셀 수 (0점, 1점), 로그 눈금.
# UBFC 원본 4,436px에서도 심박이 정확해(오차 0.35BPM) 2,500→40,000에서 낮췄다. 비압축 기준이라 '작은 얼굴 + 압축'은 시험하지 않았다
SQI_FACE_PIXELS = (1_500, 6_000)
# 조명: 피부 평균 밝기(0~255) (0점, 1점)과 포화(이 값 이상이면 감점 시작, 255에서 0),
# 배경의 빠른 밝기 변화 = 배경 밝기(상대값)를 rPPG와 같은 대역통과(0.7~4Hz)에 통과시킨 표준편차 (0점, 1점), 로그 눈금.
# 정상 그룹(UBFC·웹캠·휴대폰 원본) 최대 0.30%, 카톡본 셀카 01~03번 약 2.3%. UBFC 압축 사본(H.264·HEVC·이중 압축 전 단계)은
# 원본 값 그대로(최대 0.15%)라 압축 잡음에는 반응하지 않는다 — 이중 압축은 이 항목으로도 막히지 않는다
SQI_BRIGHTNESS = (40.0, 100.0)
SQI_BRIGHTNESS_SATURATION = 230.0
SQI_BACKGROUND_INBAND = (0.015, 0.004)
# 움직임: 프레임당 얼굴 중심 이동(얼굴 폭 대비), 프레임당 입 벌림 변화(얼굴 높이 대비) (0점, 1점). 둘 중 낮은 쪽
SQI_HEAD_MOTION = (0.03, 0.005)
SQI_MOUTH_MOTION = (0.008, 0.001)  # 영상 3편(웹캠 09·11·13번, 말하기) 기준 예시값

# ── rPPG 특징 표의 기준값(화면의 ○△× 판단) — 5-4 (2026-10-26) ──
# 실제 얼굴 영상(FF++ c0 학습 쌍의 진짜 118편 + UBFC 원본 3편)의 분포: ○ = 75%가 들어가는 범위, △ = 95%가 들어가는 범위.
# 규칙은 값을 계산하기 전에 정했다(scripts/feature_reference.py). FF++ 진짜 영상은 말하는 영상이 많아 맥박 신호가 깨끗하지 않아
# 4-3의 임시 기준(신호 좋은 10편: ROI 간 σ ≤ 3, 일치도 ≥ 0.40 등)보다 훨씬 느슨하다 — '맥박이 깨끗한가'가 아니라 '실제 얼굴 영상의 흔한 범위인가'다.
# (방향, ○ 경계, △ 경계): 'min'이면 값이 클수록 좋음(○ ≥ 첫 값, △ ≥ 둘째 값), 'max'면 작을수록 좋음
RPPG_FEATURE_JUDGE = {
    'snr': ('min', -4.57, -6.12),  # 기준 영상 중앙값 −3.50dB (4-3 임시: −1.5 / −3.5)
    'spectral_entropy': ('max', 0.93, 0.95),  # 중앙값 0.91 (4-3 임시: 0.88 / 0.91)
    'roi_bpm_std': ('max', 22.48, 33.57),  # 중앙값 14.5BPM (4-3 임시: 3 / 8)
    'phase_consistency': ('min', 0.06, -0.06),  # 중앙값 0.14 (4-3 임시: 0.40 / 0.20)
    'window_bpm_var': ('max', 23.67, 38.47),  # 중앙값 16.3BPM (4-3 임시: 8 / 12)
}
# rPPG는 모든 프레임을 처리해 영상 길이에 비례해 오래 걸리므로(1080p 30초에 약 17초) 앞 이 길이만 분석한다.
# 업로드 길이 제한은 없다(용량 500MB만). 메인 모델은 영상 전체에서 32프레임을 그대로 뽑는다
RPPG_MAX_ANALYSIS_SEC = 60.0
# 근거 화면 파형 차트에 보낼 최대 길이(초). 길면 응답이 커진다
RPPG_EVIDENCE_MAX_SEC = 60.0
