# 개발 환경 준비 가이드

새 PC(Windows 10/11)에서 이 프로젝트를 실행할 수 있게 만드는 순서입니다. 위에서부터 차례대로 따라 하면 됩니다.
디스크 여유 공간은 **약 40 GB**가 필요합니다(데이터셋 약 20 GB + Celeb-DF ZIP 9.3 GB + Docker 이미지 등).

| 단계 | 내용 | 필수 여부 |
|---|---|---|
| 1 | 기본 프로그램 설치 (Git, VS Code, Node.js) | 필수 |
| 2 | 저장소 받기 | 필수 |
| 3 | 프론트엔드 실행 (목 API) | 필수 |
| 4 | WSL2 + Docker 설치 | 백엔드 작업 시 필수 |
| 5 | 모델 가중치 받기 | 백엔드 실행 시 필수 |
| 6 | 데이터셋 받기 (Celeb-DF, UBFC-rPPG, FaceForensics++) | 실험(특징 추출·평가) 시 필수 |
| 7 | 백엔드 실행과 화면 연결 | 필수 |
| 8 | 설치 확인 (다른 PC와 같은 결과가 나오는지) | 필수 |

---

## 1. 기본 프로그램 설치

| 프로그램 | 받는 곳 | 확인 명령 (PowerShell) |
|---|---|---|
| Git | https://git-scm.com/download/win | `git --version` |
| VS Code | https://code.visualstudio.com | — |
| Node.js **20 LTS (20.19 이상)** | https://nodejs.org | `node -v` → `v20.19` 이상 |

- Node.js는 22나 24가 아니라 **20 LTS**를 설치합니다. 프로젝트가 Node 20 기준으로 맞춰져 있습니다.
- 설치 후에는 PowerShell을 새로 열어야 명령이 인식됩니다.

## 2. 저장소 받기

```powershell
cd D:\
git clone https://github.com/HSM-03/Deepfake_Detector_Web.git
cd Deepfake_Detector_Web
```

- C 드라이브 등 다른 위치에 받아도 됩니다. 바탕화면·문서처럼 OneDrive가 동기화하는 폴더와, 띄어쓰기·한글이 든 경로는 피합니다.
  다른 위치에 받으면 WSL에서는 `/mnt/c/...`처럼 그 경로로 들어가고, 데이터셋·가중치 위치는 7-1의 `.env`로 알려 줍니다.

저장소 구조:
```
docs/       설계 문서 (screen-spec.md 화면설계서, backend-plan.md 진행 계획·결과, 이 파일)
frontend/   React 대시보드
backend/    FastAPI(API) + Celery 워커 + SQLite·Redis + 분석 파이프라인(메인 모델, rPPG, SQI, 융합 판정)
docker-compose.yml   Redis + API 서버 + 워커
CLAUDE.md   프로젝트 전체 개요와 작업 규칙
```

- 저장소는 **공개**입니다. 개인 설정(`.env`), 데이터셋, 가중치, 직접 찍은 영상(`backend/out/`)은 `.gitignore`로 막혀 있어 올라가지 않습니다.
- 진행 상황은 `docs/backend-plan.md`에 단계별로 적혀 있습니다. 지금은 **5단계 5-5까지 끝났고 5-6 최종 평가와 5-7 정리가 남았습니다.**

## 3. 프론트엔드 실행 (목 API)

```powershell
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:5173 을 열어 화면이 나오면 성공입니다.
처음에는 **목 API**(가짜 데이터)로 동작하므로 백엔드 없이도 모든 화면을 볼 수 있습니다. 화면 하단 DEV 패널에서 시나리오별 결과 화면으로 바로 이동할 수 있습니다.
실제 백엔드에 붙이는 방법은 7단계에 있습니다.

## 4. WSL2 + Docker 설치 (백엔드용)

백엔드(API 서버, Celery 워커, Redis)는 Windows가 아니라 **WSL2 우분투 안의 Docker**에서 실행합니다. Redis와 Celery가 Windows를 공식 지원하지 않고,
얼굴 정렬에 쓰는 dlib도 Windows 설치가 까다롭기 때문입니다.

### 4-1. WSL2 우분투 설치
PowerShell을 **관리자 권한**으로 열고:
```powershell
wsl --install
```
설치가 끝나면 PC를 재시작합니다. 재시작 후 우분투 창이 뜨면 사용자 이름과 비밀번호를 정합니다.

### 4-2. 우분투 안에 Docker 설치
시작 메뉴에서 "Ubuntu"를 실행하고 아래를 차례로 입력합니다.
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```
우분투 창을 닫고 PowerShell에서 `wsl --shutdown`을 실행한 뒤, 우분투를 다시 엽니다.

### 4-3. 확인
```bash
docker --version
docker compose version
docker run hello-world
```
`Hello from Docker!`가 나오면 성공입니다.

- `Cannot connect to the Docker daemon` 오류가 나면 `sudo service docker start`를 실행한 뒤 다시 해 보세요. PC나 WSL을 재시작한 뒤에 가끔 필요합니다.
- 이 프로젝트는 **Docker Desktop을 쓰지 않습니다**(팀원 PC와 환경을 같게). 이미 Docker Desktop이 깔려 있으면 우분투 Docker와 충돌할 수 있으니 둘 중 하나만 쓰세요.

### 4-4. WSL에서 Windows 폴더 보기
WSL 안에서는 Windows 드라이브가 `/mnt` 아래에 보입니다. 같은 폴더를 가리키는 다른 이름일 뿐입니다.

| Windows | WSL |
|---|---|
| `D:\Deepfake_Detector_Web` (저장소) | `/mnt/d/Deepfake_Detector_Web` |
| `D:\Deepfake_Datasets` | `/mnt/d/Deepfake_Datasets` |
| `D:\Deepfake_Models` | `/mnt/d/Deepfake_Models` |

## 5. 모델 가중치 받기

**저장소 밖**에 폴더를 만들고 아래 파일을 넣습니다. 기본 위치는 `D:\Deepfake_Models`입니다. 파일 이름을 바꾸지 않습니다.

| 파일 | 크기 | 받는 곳 |
|---|---|---|
| `effnb4_best.pth` (메인 모델) | 약 71 MB | https://github.com/SCLBD/DeepfakeBench/releases/tag/v1.0.1 → Assets |
| `shape_predictor_81_face_landmarks.dat` (얼굴 정렬용) | 약 19 MB | https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.0/shape_predictor_81_face_landmarks.dat |
| `xception_best.pth` (비교용, 선택) | 약 84 MB | v1.0.1 Assets |

- 가중치는 DeepfakeBench(CC BY-NC 4.0)의 것입니다. 비상업적 학습 목적으로만 씁니다.

## 6. 데이터셋 받기

세 데이터셋 모두 **저장소 밖** `D:\Deepfake_Datasets` 아래에 둡니다. 코드는 폴더 이름으로 찾으므로 **아래 구조와 이름을 그대로** 맞춥니다.

```
D:\Deepfake_Datasets\
  Celeb-DF-v2\
    Celeb-real\              (영상 590개)
    Celeb-synthesis\         (영상 5,639개)
    YouTube-real\            (영상 300개)
    List_of_testing_videos.txt   (518줄)
  UBFC-rPPG\
    DATASET_2\
      subject47\  vid.avi, ground_truth.txt
      subject48\  …
      subject49\  …
  FaceForensics++\
    original_sequences\youtube\{raw,c23,c40}\videos\     (033.mp4 …)
    manipulated_sequences\Deepfakes\{raw,c23,c40}\videos\ (033_097.mp4 …)
```

| 데이터셋 | 용도 | 쓰면 안 되는 곳 |
|---|---|---|
| Celeb-DF v2 | 주 데이터셋. 실험·평가 | `List_of_testing_videos.txt` 518개는 **최종 평가 전용** — 학습·기준값·α 결정에 쓰지 않음 |
| UBFC-rPPG | 정답 심박이 있어 **rPPG 심박 정확도 확인** | 딥페이크 판별 학습·평가 |
| FaceForensics++ | **rPPG 특징 분석과 P_rppg 분류기 학습에만** (압축 단계별 비교, 5단계 분류기 학습·시험) | **메인 모델·융합·최종 평가 금지** — 메인 모델의 학습 데이터라 성능이 부풀려짐. 메인 모델을 FF++에 돌리지 않음 |

### 공통: 각자 신청, 파일은 팀원에게 받기
- 데이터셋 이용 약관에 각자 동의해야 하므로 **본인 이름으로 직접 신청**합니다(아래 6-1, 6-3).
- 신청한 뒤에는 **팀원에게 USB 등으로 폴더째 받는 것을 권장**합니다(둘 다 약관에 동의한 상태). 직접 내려받는 것보다 빠르고,
  특히 UBFC·FF++는 지금 쓰는 영상이 **일부만 골라 받은 것**이라 같은 파일을 받아야 결과가 같게 나옵니다.
- **다운로드 링크와 데이터셋 파일은 팀 밖으로 공유하지 않습니다.**

### 6-1. Celeb-DF v2 — 사용 신청
제출하면 바로 다운로드 링크가 나옵니다.
- 신청서: https://github.com/yuezunli/celeb-deepfakeforensics 의 Google 폼
- 입력 예시

| 항목 | 내용 |
|---|---|
| Name | 본인 영문 이름 |
| Organization | Inha Technical College (Department of Computer Systems Engineering) |
| City / Country | Incheon / Republic of Korea |
| Version | **v2만** 선택 |
| Signature | 본인 영문 이름을 그대로 입력 |

- Purpose 예시:
  > I am an undergraduate student at Inha Technical College. I will use Celeb-DF solely for non-commercial academic research in my graduation project, which develops a deepfake video detection system that combines a visual detection model with remote photoplethysmography (rPPG) signals. The dataset will be used only to train and evaluate the detection model, and no videos or faces from the dataset will be redistributed or shown publicly.

직접 받을 때:
1. 구글 드라이브의 **Celeb-DF (v2)** 링크로 ZIP(약 9.3 GB)을 받습니다. "다운로드 할당량 초과"가 뜨면 몇 시간 뒤 다시 시도합니다.
2. **다운로드가 완전히 끝난 뒤에** 압축을 풉니다. 받는 중에 ZIP을 열면 "손상된 파일"로 보입니다.
3. Windows 기본 압축 해제 대신 **반디집**이나 **7-Zip**을 씁니다(큰 ZIP에서 오류가 날 수 있음).
4. 풀린 폴더 이름을 `Celeb-DF-v2`로 맞춥니다.

주의: `List_of_testing_videos.txt`의 라벨은 **1 = 진짜, 0 = 가짜**입니다. 우리 시스템(1에 가까울수록 가짜)과 방향이 반대입니다.

### 6-2. UBFC-rPPG
- 출처: https://sites.google.com/view/ybenezeth/ubfcrppg (페이지의 Google Drive 링크, "연구 목적으로 공유").
- 쓰는 것: **DATASET_2의 subject47·48·49 세 명만**(비압축 AVI, 편당 약 1.8 GB, 약 68초). 전체를 받을 필요가 없습니다.
- 인용: S. Bobbia et al., "Unsupervised skin tissue segmentation for remote photoplethysmography", Pattern Recognition Letters, 2017.
- 실제 사람 얼굴이므로 Celeb-DF와 같은 규칙입니다: 얼굴이 담긴 이미지를 저장소·문서·발표 자료에 넣지 않습니다.

### 6-3. FaceForensics++ — 사용 신청
- 신청서: https://github.com/ondyari/FaceForensics 의 Google 폼(약관 동의). 승인 메일로 내려받기 스크립트(`download.py`)가 옵니다.
- 쓰는 것: original(youtube)과 Deepfakes의 **25쌍**, raw(c0)·c23 각 25편, c40 10편. 4단계 분석(`check_rppg_separability --ffpp`)이 이 쌍으로 판정했습니다.
  `download.py`는 영상 번호를 골라 받을 수 없으므로 **팀원에게 폴더째 받습니다.**
- 5단계 분류기용 영상(c0, Deepfakes 200쌍)은 **50쌍씩 받아 특징만 뽑고 지웁니다.** 영상을 골라 받는 도우미 `ffpp_pick.py`를 `download.py` 옆에 둡니다(저장소 밖, 팀원에게 받음).
  뽑은 특징은 `backend/out/stage5/ffpp_features.jsonl`(깃 제외)이며, 같은 결과를 쓰려면 이 파일을 팀원에게 받으면 됩니다. 쌍 목록은 `docs/stage5-preregistration.md`에 있습니다.

### 6-4. 개수 확인
PowerShell:
```powershell
(Get-ChildItem "D:\Deepfake_Datasets\Celeb-DF-v2\Celeb-real" -Filter *.mp4).Count          # 590
(Get-ChildItem "D:\Deepfake_Datasets\Celeb-DF-v2\Celeb-synthesis" -Filter *.mp4).Count     # 5639
(Get-ChildItem "D:\Deepfake_Datasets\Celeb-DF-v2\YouTube-real" -Filter *.mp4).Count        # 300
(Get-ChildItem "D:\Deepfake_Datasets\UBFC-rPPG\DATASET_2" -Directory).Count                # 3
(Get-ChildItem "D:\Deepfake_Datasets\FaceForensics++\original_sequences\youtube\raw\videos").Count   # 25
```

## 7. 백엔드 실행과 화면 연결

### 7-1. 폴더 위치가 다를 때만: `.env`
가중치·데이터셋을 `D:\Deepfake_Models`, `D:\Deepfake_Datasets`가 아닌 곳에 뒀다면, **저장소 루트**에 `.env` 파일을 만들고 WSL 경로로 적습니다.
```
MODEL_HOST_DIR=/mnt/e/my_models
DATASET_HOST_DIR=/mnt/e/my_datasets
```
`.env`는 개인 설정이라 Git에 올라가지 않습니다. 기본 위치를 쓰면 만들 필요가 없습니다.

### 7-2. 띄우기
WSL 우분투에서:
```bash
cd /mnt/d/Deepfake_Detector_Web
docker compose up --build
```
- **처음 한 번은 10~20분** 걸립니다(dlib 컴파일). 그다음부터는 캐시를 써서 빨리 뜹니다.
- 로그가 계속 나오는 창은 그대로 두고, 끌 때는 `Ctrl + C`.
- 확인: 브라우저에서 http://localhost:8000/api/health → `"status":"ok"`, `"redis":true`가 나오면 됩니다. API 문서는 http://localhost:8000/docs.

자주 쓰는 명령 (WSL, 저장소 루트):

| 명령 | 하는 일 |
|---|---|
| `docker compose up --build` | 이미지를 (다시) 빌드하고 Redis·API·워커를 띄운다 |
| `docker compose up` | 이미지 변경 없이 띄운다 |
| `docker compose down` | 컨테이너를 끈다. 볼륨(DB·업로드 영상)은 남는다 |
| `docker compose down -v` | 볼륨까지 지운다(DB 초기화). 테이블 구조를 바꿨을 때만 |
| `docker compose restart worker` | 워커만 다시 시작. **워커 코드(`app/tasks.py`, `analysis/` 등)를 고치면 필요** (API 서버는 자동 반영) |
| `docker compose logs -f worker` | 워커 로그를 계속 본다 |

- 코드는 볼륨으로 연결돼 있어 고쳐도 다시 빌드할 필요가 없습니다. `requirements*.txt`나 `Dockerfile`이 바뀌었을 때만 `--build`.
- 분석 중에 워커를 다시 시작해도 작업은 처음부터 다시 분석됩니다(멈춘 채 남지 않음).

### 7-3. 프론트엔드를 실제 백엔드에 붙이기
`frontend/.env.development.local` 파일을 만들고 한 줄을 적은 뒤, `npm run dev`를 다시 시작합니다.
```
VITE_USE_MOCK=false
```
- 이 파일도 PC마다 따로 정하며 Git에 올라가지 않습니다. 목을 끄면 화면 아래 DEV 패널이 사라집니다.
- 다시 목으로 보려면 이 줄을 지우거나 `true`로 바꿉니다.

## 8. 설치 확인 — 다른 PC와 같은 결과가 나오는지

분석은 같은 영상에 항상 같은 결과를 냅니다. 아래 값이 같게 나오면 가중치·데이터셋·코드가 팀원 PC와 같은 상태입니다.

1. **DSP 확인** (직접 구현한 필터·스펙트럼을 scipy와 비교):
   ```bash
   docker compose run --rm worker python -m scripts.check_dsp
   ```
   마지막 줄이 `결과: 모두 같음`이면 됩니다.
2. **웹에서 영상 올리기**: http://localhost:5173 에서 아래 두 영상을 올려 결과 화면의 값을 비교합니다(평가 세트 밖 영상).

   | 영상 | 판정 | S | P_model | P_rppg | rPPG 심박 | SQI (가장 약한 항목) |
   |---|---|---|---|---|---|---|
   | `Celeb-DF-v2\Celeb-synthesis\id0_id16_0000.mp4` | 가짜 | 0.92 | 0.92 | 0.42 | 89 BPM | 0.01 (얼굴 크기) |
   | `Celeb-DF-v2\Celeb-real\id0_0000.mp4` | 가짜 (메인 모델 오판) | 0.84 | 0.85 | 0.51 | 88 BPM | 0.04 (얼굴 크기) |

   - 5단계 코드(P_rppg 분류기 연결 후) 기준 값입니다. 두 영상 모두 SQI가 낮아 화면에 "rPPG 미반영(신호 품질 낮음)"이 나와야 정상입니다.
   - P_rppg가 P_model과 같게 나오고 "P_rppg 분류기 미적용"이 보이면 예전(4단계) 코드입니다 — `git pull`로 최신 `main`을 받습니다.
   - 처리 시간은 영상 1편 약 30~50초입니다(첫 작업은 모델을 불러오느라 조금 더 걸림). CPU에 따라 다를 수 있지만 **값은 같아야** 합니다.
3. 이력 화면에서 두 건을 다시 열어 같은 값이 나오는지, 근거 화면(파형·스펙트럼·특징 표)이 나오는지 봅니다.

값이 다르면 가중치 파일(5단계)과 데이터셋 파일이 같은지 먼저 확인합니다.

## Claude Code로 맞출 때

저장소를 클론한 폴더에서 Claude Code를 열면 루트 `CLAUDE.md`(프로젝트 규칙)를 자동으로 읽습니다. 이 문서를 함께 주고 순서대로 맞추게 하면 됩니다. 다만 아래는 사람이 직접 해야 합니다.
- 데이터셋 사용 신청(Celeb-DF, FaceForensics++)은 **본인 이름으로 직접** 합니다(6절).
- WSL 설치·재부팅, 우분투 비밀번호 입력, `sudo`가 필요한 Docker 설치는 직접 입력합니다.
- 데이터셋·가중치 복사(USB 등)는 직접 합니다. 직접 찍은 얼굴 영상은 넘겨받을지 당사자에게 확인합니다.
- 다른 PC의 Claude Code 기억(작업 방식 선호 등)은 옮겨지지 않습니다. 규칙은 `CLAUDE.md`와 `docs/backend-plan.md`에 있는 것이 기준입니다.

---

## 지키는 규칙
- 데이터셋 영상, 가중치, ZIP 파일은 **저장소 안에 넣지 않습니다.** (`.gitignore`가 막아 두었지만 처음부터 저장소 밖에 둡니다.)
- 데이터셋 인물 얼굴(Celeb-DF, UBFC, FF++)이 담긴 캡처를 저장소, 문서, 발표 자료에 넣지 않습니다.
- 직접 찍은 영상은 `backend/out/`(Git 제외)에 둡니다. 다른 사람이 찍힌 영상은 본인 동의를 받습니다.
- 작업 진행 기준은 `docs/backend-plan.md`, 전체 규칙은 루트 `CLAUDE.md`를 봅니다.
