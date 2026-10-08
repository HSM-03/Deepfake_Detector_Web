# 딥페이크 탐지기 — rPPG 생체신호 교차검증 기반 영상 진위 판별 시스템

2026년도 심화응용프로젝트(인하공업전문대학 컴퓨터시스템공학과, 지능·응용S/W 분야).
영상을 올리면 두 판별 축 — 메인 모델 `P_model`(DeepfakeBench EfficientNet-B4)과 rPPG `P_rppg` — 을 돌려
`S = (1 − w)·P_model + w·P_rppg` (w = α·SQI)로 융합 판정하고, 웹 대시보드에 판정과 근거를 보여 준다.

## 저장소 구조

```
docs/
  screen-spec.md      화면설계서 v1.3 요약 — 화면과 API 7개의 기준
  backend-plan.md     백엔드·분석 파이프라인 진행 계획 — 확정 결정, 미결정 사항, 0~5단계, 완료 기준
frontend/             React 대시보드 (완성, 목 API로 동작). 세부 규칙은 frontend/CLAUDE.md
backend/              FastAPI + Celery/Redis + SQLite + 분석 파이프라인 (docs/backend-plan.md 2단계부터 만든다)
```

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
- **프론트엔드**: Windows에서 `frontend/` 폴더로 들어가 `npm run dev` (http://localhost:5173)
- **백엔드**: WSL2 Ubuntu 안에 직접 설치한 Docker로 실행한다(Docker Desktop은 쓰지 않는다).
  - API 서버·Celery 워커·Redis는 docker compose 하나로 띄운다. Redis와 Celery가 Windows를 공식 지원하지 않기 때문이다.
  - Windows 쪽에서 실행할 때는 `wsl docker compose ...`처럼 WSL을 거친다.
  - WSL을 재시작한 뒤 Docker 데몬에 연결되지 않으면 WSL에서 `sudo service docker start`가 필요할 수 있다.
  - dlib(얼굴 정렬)처럼 Windows 설치가 까다로운 분석 코드도 처음부터 Docker(리눅스) 안에서 실행한다.
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
