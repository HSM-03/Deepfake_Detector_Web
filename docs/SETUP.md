# 개발 환경 준비 가이드

새 PC(Windows 10/11)에서 이 프로젝트를 실행할 수 있게 만드는 순서입니다. 위에서부터 차례대로 따라 하면 됩니다.
디스크 여유 공간은 **약 25 GB**가 필요합니다(Celeb-DF ZIP 9.3 GB + 압축 해제 9.5 GB + 기타).

| 단계 | 내용 | 필수 여부 |
|---|---|---|
| 1 | 기본 프로그램 설치 (Git, VS Code, Node.js) | 필수 |
| 2 | 저장소 받기 | 필수 |
| 3 | 프론트엔드 실행 | 필수 |
| 4 | WSL2 + Docker 설치 | 백엔드 작업 시 필수 |
| 5 | 모델 가중치 받기 | 분석 코드 작업 시 필수 |
| 6 | Celeb-DF 데이터셋 받기 | 실험(특징 추출·평가) 시 필수 |

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

GitHub 비공개 저장소에 초대받은 계정으로 로그인한 뒤 받습니다.

```powershell
cd D:\
git clone <저장소 주소>
cd Deepfake_Detector_Web
```

저장소 구조:
```
docs/       설계 문서 (screen-spec.md, backend-plan.md, 이 파일)
frontend/   React 대시보드
backend/    (예정) FastAPI + Celery/Redis + SQLite + 분석 파이프라인
CLAUDE.md   프로젝트 전체 개요와 작업 규칙
```

## 3. 프론트엔드 실행

```powershell
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:5173 을 열어 화면이 나오면 성공입니다.
지금은 **목 API**(가짜 데이터)로 동작하므로 백엔드 없이도 모든 화면을 볼 수 있습니다. 화면 하단 DEV 패널에서 시나리오별 결과 화면으로 바로 이동할 수 있습니다.

## 4. WSL2 + Docker 설치 (백엔드용)

백엔드(API 서버, Celery 워커, Redis)는 Windows가 아니라 **WSL2 우분투 안의 Docker**에서 실행합니다. Redis와 Celery가 Windows를 공식 지원하지 않기 때문입니다.

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

- `Cannot connect to the Docker daemon` 오류가 나면 `sudo service docker start`를 실행한 뒤 다시 해 보세요. PC를 재시작한 뒤에 가끔 필요합니다.
- 이미 **Docker Desktop**을 쓰고 있다면 그대로 써도 됩니다. 같은 `docker compose` 파일로 똑같이 실행됩니다. 다만 Docker Desktop과 위의 우분투 Docker를 **둘 다** 설치하면 충돌할 수 있으니 하나만 쓰세요.

### 4-4. WSL에서 Windows 폴더 보기
WSL 안에서는 Windows 드라이브가 `/mnt` 아래에 보입니다. 같은 폴더를 가리키는 다른 이름일 뿐입니다.

| Windows | WSL |
|---|---|
| `D:\Deepfake_Datasets` | `/mnt/d/Deepfake_Datasets` |
| `D:\Deepfake_Models` | `/mnt/d/Deepfake_Models` |

## 5. 모델 가중치 받기

**저장소 밖**에 폴더를 만들고 아래 파일을 넣습니다. 기본 위치는 `D:\Deepfake_Models`입니다.

| 파일 | 크기 | 받는 곳 |
|---|---|---|
| `effnb4_best.pth` (메인 모델) | 약 71 MB | https://github.com/SCLBD/DeepfakeBench/releases/tag/v1.0.1 → Assets |
| `xception_best.pth` (비교용, 선택) | 약 84 MB | 같은 페이지 |
| `shape_predictor_81_face_landmarks.dat` (얼굴 정렬용) | — | https://github.com/SCLBD/DeepfakeBench/releases/download/v1.0.0/shape_predictor_81_face_landmarks.dat |

## 6. Celeb-DF v2 데이터셋 받기

### 6-1. 사용 신청 (각자 직접)
데이터셋 이용 약관에 각자 동의해야 하므로 **본인 이름으로 직접 신청**합니다. 제출하면 바로 다운로드 링크가 나옵니다.
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

- 신청 후 팀원에게 USB 등으로 파일을 받아도 됩니다(둘 다 약관에 동의한 상태이므로).
- **다운로드 링크와 데이터셋 파일은 팀 밖으로 공유하지 않습니다.**

### 6-2. 다운로드와 압축 해제
1. 구글 드라이브의 **Celeb-DF (v2)** 링크로 ZIP(약 9.3 GB)을 받습니다. "다운로드 할당량 초과"가 뜨면 몇 시간 뒤 다시 시도합니다.
2. **다운로드가 완전히 끝난 뒤에** 압축을 풉니다. 받는 중에 ZIP을 열면 "손상된 파일"로 보입니다.
3. Windows 기본 압축 해제 대신 **반디집**이나 **7-Zip**을 씁니다(큰 ZIP에서 오류가 날 수 있음).
4. `D:\Deepfake_Datasets` 아래에 풉니다. 폴더 이름은 팀원 PC와 같게 맞춥니다.

### 6-3. 확인
아래 네 가지가 있어야 합니다.

| 항목 | 개수 |
|---|---|
| `Celeb-real` | 영상 590개 |
| `Celeb-synthesis` | 영상 5,639개 |
| `YouTube-real` | 영상 300개 |
| `List_of_testing_videos.txt` | 518줄 |

PowerShell로 개수 확인 (경로는 실제 위치로 바꿉니다):
```powershell
(Get-ChildItem "D:\Deepfake_Datasets\<Celeb-DF 폴더>\Celeb-real" -Filter *.mp4).Count
(Get-ChildItem "D:\Deepfake_Datasets\<Celeb-DF 폴더>\Celeb-synthesis" -Filter *.mp4).Count
(Get-ChildItem "D:\Deepfake_Datasets\<Celeb-DF 폴더>\YouTube-real" -Filter *.mp4).Count
```

**주의**
- `List_of_testing_videos.txt`의 518개는 **최종 평가 전용**입니다. 학습, 기준값 산출, α 결정 등 다른 어떤 단계에도 쓰지 않습니다.
- 이 목록의 라벨은 **1 = 진짜, 0 = 가짜**입니다. 우리 시스템(1에 가까울수록 가짜)과 방향이 반대입니다.
- **FaceForensics++는 쓰지 않습니다.** 메인 모델의 학습 데이터라 평가에 쓰면 성능이 부풀려집니다.

---

## 폴더 위치를 다르게 쓰고 싶을 때

D 드라이브가 없거나 다른 위치를 쓰고 싶으면 그래도 됩니다. 코드는 경로를 환경변수 `DATASET_DIR`, `MODEL_DIR`로 받기 때문에, 백엔드가 만들어지면 `backend/.env` 파일에 본인 경로만 적으면 됩니다. `.env` 파일은 개인 설정이라 Git에 올라가지 않습니다.

## 지키는 규칙
- 데이터셋 영상, 가중치, ZIP 파일은 **저장소 안에 넣지 않습니다.** (`.gitignore`가 막아 두었지만 처음부터 저장소 밖에 둡니다.)
- 데이터셋 인물 얼굴이 담긴 캡처를 저장소, 문서, 발표 자료에 넣지 않습니다.
- 작업 진행 기준은 `docs/backend-plan.md`, 전체 규칙은 루트 `CLAUDE.md`를 봅니다.
