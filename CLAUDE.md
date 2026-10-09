# 딥페이크 탐지기 — rPPG 생체신호 교차검증 기반 영상 진위 판별 시스템

2026년도 심화응용프로젝트(인하공업전문대학 컴퓨터시스템공학과, 지능·응용S/W 분야).
영상을 올리면 두 판별 축 — 메인 모델 `P_model`(DeepfakeBench EfficientNet-B4)과 rPPG `P_rppg` — 을 돌려
`S = (1 − w)·P_model + w·P_rppg` (w = α·SQI)로 융합 판정하고, 웹 대시보드에 판정과 근거를 보여 준다.

## 저장소 구조

```
docs/
  screen-spec.md      화면설계서 v1.3 요약 — 화면과 API 7개의 기준
  backend-plan.md     백엔드·분석 파이프라인 진행 계획 — 확정 결정, 미결정 사항, 0~5단계, 완료 기준
frontend/             React 대시보드 (완성). 세부 규칙은 frontend/CLAUDE.md
backend/
  app/                FastAPI(API 7개) + Celery 워커 + SQLite·Redis — 웹 백엔드
  analysis/           분석 파이프라인(메인 모델, 얼굴 정렬, 융합 판정, 더미 값). 설정은 analysis/settings.py 한 곳
  scripts/            웹 없이 실행하는 분석 스크립트(1단계 메인 모델 단독 실행 등)
docker-compose.yml    Redis + API 서버 + 워커
```

진행 상황은 `docs/backend-plan.md`의 각 단계 아래 "결과"에 기록한다. 지금은 2단계(백엔드 골격, 더미 분석)까지 끝났다.

- **API 형식의 기준은 `frontend/src/types/api.ts`다.** 백엔드 응답은 이 타입과 정확히 맞아야 한다.
  형식을 바꿔야 하면 바꾸기 전에 사용자에게 알리고, 타입 → 목(`frontend/src/mocks/`) → 백엔드를 함께 고친다.
- 백엔드 작업은 `docs/backend-plan.md`의 단계 순서를 따른다. 각 단계는 완료 기준을 채우고 보고한 뒤 다음으로 넘어간다.

## 데이터셋·모델 가중치

저장소 밖에 둔다. Git에 올리지 않는다(`.gitignore`가 영상·가중치·ZIP 확장자를 막는다).

| 용도 | Windows 경로 | WSL·컨테이너에서 |
|---|---|---|
| 데이터셋 (Celeb-DF v2 등) | `D:\Deepfake_Datasets` | `/mnt/d/Deepfake_Datasets` |
| 모델 가중치 (`effnb4_best.pth`, dlib 랜드마크) | `D:\Deepfake_Models` | `/mnt/d/Deepfake_Models` |

코드에서는 경로를 환경변수(`DATASET_DIR`, `MODEL_DIR`)로 받는다.
**FaceForensics++는 쓰지 않는다**(메인 모델의 학습 데이터). Celeb-DF의 `List_of_testing_videos.txt` 518개는 최종 평가 전용이다.

## 개발 환경

- 코드는 Windows의 VS Code에서 작성한다.
- **프론트엔드**: Windows PowerShell에서 `frontend/` 폴더로 들어가 `npm run dev` (http://localhost:5173)
  - 기본은 목 API(`frontend/.env.development`의 `VITE_USE_MOCK=true`).
  - 실제 백엔드에 붙이려면 `frontend/.env.development.local`에 `VITE_USE_MOCK=false` 한 줄을 넣고 `npm run dev`를 다시 시작한다.
    이 파일은 `.local`로 끝나 git에 올라가지 않으므로 PC마다 따로 정한다. 목을 끄면 화면 아래 DEV 패널이 사라진다.
- **백엔드**: WSL2 Ubuntu 안에 직접 설치한 Docker로 실행한다(Docker Desktop은 쓰지 않는다).
  - API 서버·Celery 워커·Redis는 docker compose 하나로 띄운다. Redis와 Celery가 Windows를 공식 지원하지 않기 때문이다.
  - docker 명령은 WSL 터미널(`wsl`로 들어가 `cd /mnt/d/Deepfake_Detector_Web`)에서 실행한다.
  - WSL을 재시작한 뒤 Docker 데몬에 연결되지 않으면 WSL에서 `sudo service docker start`가 필요할 수 있다.
  - dlib(얼굴 정렬)처럼 Windows 설치가 까다로운 분석 코드도 처음부터 Docker(리눅스) 안에서 실행한다.
  - 가중치·데이터셋 경로가 다른 PC는 저장소 루트 `.env`(git 제외)에 `MODEL_HOST_DIR=…`, `DATASET_HOST_DIR=…`를 적는다.

  | 명령 (WSL, 저장소 루트) | 하는 일 |
  |---|---|
  | `docker compose up --build` | 이미지를 (다시) 빌드하고 Redis·API·워커를 띄운다. 로그가 화면에 계속 나온다(`Ctrl + C`로 끔) |
  | `docker compose up` | 이미지 변경 없이 띄운다 |
  | `docker compose down` | 컨테이너를 끈다. **볼륨(DB·업로드 영상)은 남는다** |
  | `docker compose down -v` | 볼륨까지 지운다(DB 초기화). 테이블 구조를 바꿨을 때만 |
  | `docker compose restart worker` | 워커만 다시 시작. **워커 코드(`app/tasks.py`, `analysis/` 등)를 고치면 필요하다**(API 서버는 `--reload`로 자동 반영) |
  | `docker compose logs -f worker` | 워커 로그를 계속 본다. 작업마다 단계 시작·완료·최종 상태가 한 줄씩 찍힌다 |
  | `docker compose run --rm api python -m app.db` | DB 파일 위치, WAL 모드, 테이블 목록 확인 |

  - API 문서(자동 생성): http://localhost:8000/docs, 상태 확인: http://localhost:8000/api/health
  - **더미 모드**(`USE_DUMMY_ANALYSIS`, 기본 켜짐): 점수는 파일명 키워드로 고른 예시 값이다(`fake` / `hold` / `fail`·`noface` / `lowsqi`,
    그 외 진짜). 업로드·검증(파일 손상, 10초 미만)과 융합 판정 규칙은 실제로 동작한다. 실제 모델을 붙이는 3단계에서 끈다.
- 분석용 이미지는 `backend/Dockerfile`로 만든다(Python 3.10, PyTorch CPU, efficientnet_pytorch, OpenCV, dlib + 웹 서버 라이브러리).
  라이브러리 목록은 둘로 나눴다: `requirements.txt`(분석, dlib 컴파일 10~20분)와 `requirements-api.txt`(웹 서버).
  웹 쪽만 바뀌면 dlib 단계는 캐시를 재사용해 1~2분이면 빌드된다. 코드는 볼륨으로 연결하므로 고쳐도 다시 빌드할 필요가 없다.

  메인 모델 단독 실행(1단계) — Celeb-DF에서 평가 세트를 뺀 진짜·가짜 각 5개:

  ```bash
  docker compose run --rm worker python -m scripts.run_main_model --celebdf-sample 5
  ```

  분석 설정(경로, 프레임 수, 이상치 제거 비율, 구간 길이, 판정 임계값, 더미 모드)은 `backend/analysis/settings.py` 한 곳에 있다.
- 메인 모델은 학습하지 않고 노트북 CPU로 추론만 한다. 학습은 rPPG 특징 기반 로지스틱 회귀/SVM뿐이다.
  데이터셋 전체 특징 추출처럼 분량이 많은 작업만 Colab/Kaggle 무료 GPU를 한시적으로 쓴다.

## 작업 방식

- 작업을 시작하기 전에 이해한 내용과 진행 계획을 사용자에게 확인받는다. 허락받은 범위는 끝까지 진행한 뒤 보고한다.
- 미결정 사항(P_rppg 방향, S 0.4~0.6 비상충 판정, 임계값·α, 이력 API 세부, ZIP 내보내기)은 임의로 정하지 않는다.
  확정 전까지는 설정 파일 한 곳에 예시값으로 두고, 코드에 박지 않는다.
- 상세제안서 스택에 없는 라이브러리를 추가하기 전에 사용자에게 확인한다.
- 데이터셋 인물 얼굴이 담긴 이미지를 저장소나 문서에 넣지 않는다(초상권, Celeb-DF 이용 약관).
- 화면 문구·주석·커밋 메시지는 한국어.
- 팀원 두 명이 서로의 작업을 이어받는 방식이라 담당자를 나눠 적지 않는다.
