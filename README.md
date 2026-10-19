# 딥페이크 탐지기 — rPPG 생체신호 교차검증 기반 영상 진위 판별

2026년도 심화응용프로젝트 (인하공업전문대학 컴퓨터시스템공학과, 지능·응용 S/W 분야)

> **진행 중인 프로젝트입니다.** 지금은 4단계(rPPG 파이프라인)까지 끝났습니다. rPPG 신호·SQI·근거는 실제로 분석하고, rPPG 진짜/가짜 점수(P_rppg)는 5단계 분류기 전까지 메인 모델 값을 임시로 씁니다.
> 이 문서는 단계가 끝날 때마다 갱신합니다.

## 무엇을 하나

영상을 올리면 서로 다른 두 가지 근거로 진위를 판별하고, 판정과 그 근거를 웹 대시보드로 보여 줍니다.

| 판별 축 | 보는 것 | 점수 |
|---|---|---|
| 메인 모델 | 얼굴 이미지의 합성 흔적 (DeepfakeBench EfficientNet-B4) | `P_model` |
| rPPG | 얼굴 피부의 미세한 색 변화로 읽은 맥박 신호가 실제 사람처럼 일관된지 | `P_rppg` |

두 점수는 rPPG 신호 품질(SQI)에 따라 가중치를 달리해 합칩니다.

```
S = (1 − w)·P_model + w·P_rppg,   w = α·SQI
```

- 신호 품질이 낮으면 w가 작아져 메인 모델 중심으로 판정합니다.
- 신호 품질이 충분한데 두 축이 크게 엇갈리면, 한쪽을 임의로 고르지 않고 **판단 보류**로 두어 검토자에게 넘깁니다.
- 임계값과 α는 아직 예시값이며, 5단계에서 Celeb-DF 검증 세트로 정합니다.

## 진행 상황

| 단계 | 내용 | 상태 |
|---|---|---|
| 프론트엔드 | React 대시보드 화면 7개 (업로드·진행·결과·근거·분석 불가·판단 보류·이력) | 완료 |
| 0 | 메인 모델 학습 데이터 확인(Celeb-DF 미포함), 데이터셋 확인 | 완료 |
| 1 | 메인 모델 단독 추론 스크립트 | 완료 |
| 2 | 백엔드 골격 (FastAPI·Celery·Redis·SQLite, API 7개) | 완료 |
| 3 | 실제 메인 모델을 웹 분석에 연결 | 완료 |
| 4 | rPPG 파이프라인 (ROI 추적, CHROM/POS, 대역통과, Welch, 특징 6개, SQI) | 완료 (P_rppg는 5단계까지 임시) |
| 5 | rPPG 분류기 학습, 융합 가중치·임계값 결정, 평가 세트 비교 | 예정 |

단계별 상세 기록은 [`docs/backend-plan.md`](docs/backend-plan.md)에 있습니다.

## 지금까지의 결과

**메인 모델, Celeb-DF 40편** (최종 평가 세트 518개와 겹치지 않는 영상, 진짜·가짜 각 20편)

| | P_model 평균 | 0.5 기준 정답 |
|---|---|---|
| 진짜 | 0.311 | 17/20 |
| 가짜 | 0.726 | 17/20 |

- 영상 단위 AUC는 0.907입니다. 표본이 작아 성능 수치로는 쓰지 않습니다.

**직접 촬영한 휴대폰 셀카 (진짜 영상)**

- 메인 모델이 0.53~0.94로 가짜 쪽으로 평가했습니다.
- 해상도·코덱·HDR·얼굴 정렬 문제는 아닌 것을 확인했습니다.
- 셀카 보정, 메신저 재압축, 학습 데이터와의 차이를 원인 후보로 보고 있습니다.
- 한 사람·한 기기로 찍은 소수 표본이라 일반화하지 않습니다.
- 메인 모델 단독의 한계를 보여 주는 사례입니다. 같은 조건의 웹캠 영상에서 rPPG 심박은 정답과 3BPM 차이로 맞았지만, 판정을 바로잡으려면 5단계의 P_rppg 분류기가 필요합니다.

**처리 시간**: 노트북 CPU에서 영상 1편당 약 25~30초 (Intel Core Ultra 5 228V)

## 저장소 구조

```
frontend/            React 18 + Vite + TypeScript 대시보드 (목 API 내장)
backend/
  app/               FastAPI(API 7개) + Celery 워커 + SQLite·Redis
  analysis/          분석 파이프라인 — 메인 모델, 얼굴 정렬, 융합 판정, 해석 문장. 설정은 settings.py 한 곳
  scripts/           웹 없이 실행하는 분석 스크립트
docs/
  screen-spec.md     화면설계서 요약 (화면·API 기준)
  backend-plan.md    백엔드·분석 진행 계획과 단계별 결과
  SETUP.md           새 PC 개발 환경 준비 안내
docker-compose.yml   Redis + API 서버 + 분석 워커
```

## 실행

처음이라면 [`docs/SETUP.md`](docs/SETUP.md)의 순서를 따라 주세요.

**프론트엔드만 (목 API, 백엔드 없이 화면 확인)**

```bash
cd frontend
npm install
npm run dev
```

http://localhost:5173 에서 확인합니다.

**백엔드까지 (WSL2 Ubuntu의 Docker, 저장소 루트에서)**

```bash
docker compose up --build
```

- API 문서는 http://localhost:8000/docs 에 있습니다.
- 프론트엔드를 실제 백엔드에 붙이려면 `frontend/.env.development.local`에 `VITE_USE_MOCK=false`를 적고 `npm run dev`를 다시 시작합니다.
- 모델 가중치와 데이터셋은 저장소에 없습니다. 기본 경로는 `D:\Deepfake_Models`, `D:\Deepfake_Datasets`이고, 다른 경로를 쓰려면 저장소 루트 `.env`에 `MODEL_HOST_DIR`, `DATASET_HOST_DIR`를 적습니다.

## 기술 스택

- **프론트엔드**: React 18, TypeScript, Vite, Axios, Recharts, MSW(목 API)
- **백엔드**: Python 3.10, FastAPI, Celery + Redis, SQLite(SQLAlchemy), Docker Compose
- **분석**: PyTorch(CPU), efficientnet_pytorch, OpenCV, dlib, NumPy
  - 4단계부터 MediaPipe를 씁니다. SciPy·scikit-learn은 설치 시점을 아직 정하지 않았습니다.

## 데이터·모델·라이선스

- **Celeb-DF v2**로 실험·평가합니다. 데이터셋은 이용 약관에 따라 저장소에 포함하지 않으며, 데이터셋 인물 얼굴 이미지도 올리지 않습니다.
  - `List_of_testing_videos.txt`의 518개는 최종 평가에만 씁니다.
- **FaceForensics++**는 rPPG 특징 분석(압축 강도별 비교)에만 씁니다. 메인 모델의 학습 데이터라서 메인 모델·융합·최종 평가에는 쓰지 않습니다.
- **UBFC-rPPG**(Bobbia et al., 2017)는 정답 심박이 있어 rPPG 정확도 확인에만 씁니다.
- 메인 모델 가중치와 얼굴 정렬 방식은 [DeepfakeBench](https://github.com/SCLBD/DeepfakeBench)(© 2023 CUHK(SZ), CC BY-NC 4.0)를 따릅니다.
  - `backend/analysis/face_align.py`는 DeepfakeBench 전처리를 옮긴 코드입니다(출처는 파일 머리말에 표기).
  - 가중치 파일은 저장소에 포함하지 않습니다.
- 학습 목적의 비상업적 프로젝트입니다.
