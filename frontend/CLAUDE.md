# 딥페이크 탐지기 — 웹 대시보드 (프론트엔드)

2026년도 심화응용프로젝트(인하공업전문대학 컴퓨터시스템공학과, 지능·응용S/W 분야).
rPPG 생체신호 교차검증 기반 영상 진위 판별 시스템의 **React 웹 대시보드**다.
사용자가 영상을 올리면 백엔드가 두 개의 판별 축(메인 모델 `P_model`, rPPG `P_rppg`)을 돌려 융합 판정
`S = (1 − w)·P_model + w·P_rppg` (w = α·SQI)을 내고, 이 대시보드가 판정과 근거를 보여 준다.

이 폴더(`frontend/`)가 프론트엔드다. 저장소 전체 구조와 공통 규칙은 루트 `CLAUDE.md`를 본다.
백엔드(`backend/`, FastAPI + Celery/Redis + SQLite)와 rPPG 파이프라인이 붙기 전까지는 목 API(MSW)로 화면을 개발한다.

## 기준 문서

- `../docs/screen-spec.md` — 화면설계서 v1.3(2026-09-29 제출본)의 화면별 구성요소·예외·API를 옮긴 것. **화면 구현의 기준.**
- `src/types/api.ts` — API 요청·응답 타입. **백엔드와의 인터페이스 기준.**

두 문서와 코드가 어긋나면 코드를 문서에 맞춘다. 문서를 바꿔야 할 것 같으면 임의로 바꾸지 말고 사용자에게 확인한다.

## 명령

```bash
# frontend/ 폴더에서 실행한다
npm install
npm run dev        # http://localhost:5173 (목 API 켜진 상태)
npm run typecheck  # tsc --noEmit
npm run build      # 타입 체크 + 프로덕션 빌드
```

Node 20 LTS(20.19 이상) 기준. 테스트 러너와 린터는 아직 설정하지 않았다.

## 기술 스택

React 18 · Vite · TypeScript(strict) · React Router 6 · Axios · Recharts 2 · MSW 2(목 API).
글꼴은 Pretendard 가변 글꼴(`pretendard` 패키지, `main.tsx`에서 불러와 빌드에 포함 — 인터넷 없이도 나온다).
상세제안서에 적힌 스택이므로 다른 라이브러리(상태 관리, UI 키트, CSS 프레임워크 등)를 추가하기 전에 사용자에게 확인한다.
React는 18로 고정한다(19로 올리지 않는다). MSW도 2.x로 고정한다(3.x는 Node 22.12 이상을 요구한다).

## 폴더 구조

```
src/
  types/api.ts            API 계약 (엔드포인트 7개의 요청·응답 타입)
  api/client.ts           Axios 인스턴스, 오류 메시지 추출
  api/jobs.ts             엔드포인트별 호출 함수 — 화면은 이 함수만 쓴다
  mocks/                  MSW 목 서버
    scenarios.ts            시나리오 5종 템플릿, 임계값(예시)
    db.ts                   메모리 DB, 진행 상태 시뮬레이션, status/result/이력 생성
    evidence.ts             SCR-04용 파형·스펙트럼 합성
    handlers.ts             엔드포인트 핸들러
  lib/paths.ts            화면 경로 함수
  lib/verdict.ts          판정 기호·라벨 (□진짜 ■가짜 ◆보류 ×불가 ◐진행), 점수 구간(scoreZone)
  lib/format.ts           표시용 포맷 (점수·용량·길이·시각)
  lib/videoFile.ts        SCR-01 브라우저 검증(형식·용량·길이), <video>로 해상도·fps·썸네일 읽기
  lib/roi.ts              ROI 순서·이름 / lib/stages.ts  분석 5단계 이름 / lib/download.ts  Blob 저장
  lib/chartStyle.ts       Recharts 공통 모양(눈금·격자·툴팁), 점수 구간별 색·이름(ZONE_STYLE)
  lib/terms.ts            화면 용어(쉬운 말 + 기술 용어 + 설명) — 용어 표기는 여기서 가져다 쓴다
  hooks/useAsync.ts       조회 훅 (로딩·오류·재시도)
  components/layout/      AppLayout(헤더 고정 + 1200px), AppHeader, DevMockPanel
  components/common/      VerdictBadge, TriageNotice, AsyncBoundary, ProgressBar, ConfirmDialog, Toast, InfoTip(? 말풍선)
  pages/                  화면별 페이지. 화면 전용 스타일은 페이지 옆 CSS 파일(UploadPage.css 등)에 둔다
    upload/                 SCR-01 Dropzone, SelectedFileCard
    progress/               SCR-02 StageStepper
    result/                 SCR-03·06·07 뷰와 카드(VerdictCard+ScoreGauge, AxisScores, ScoreFormula, HoldConditionCard,
                            SqiCard, RoiBpmCard, ReviewPanel, ResultHeader, ResultActionBar). 카드 일부는 SCR-04에서도 쓴다
    evidence/               SCR-04 탭(RppgTab, ModelTab, SqiTab, FeatureTab), ChartCard
    history/                SCR-05 FilterBar, VerdictChips, HistoryTable, Pagination, historyQuery(주소 쿼리 해석)
  styles/tokens.css       디자인 토큰 (색·간격·그림자·글꼴)
  styles/global.css       전역·공통 클래스
  router.tsx              라우팅
```

## 화면 ↔ 경로 ↔ API

| 화면 | 경로 | 파일 | API |
|---|---|---|---|
| SCR-01 영상 업로드 | `/` | `pages/UploadPage.tsx` | `POST /api/videos` |
| SCR-02 분석 진행 상태 | `/jobs/:jobId` | `pages/ProgressPage.tsx` | `GET /api/jobs/{id}/status` (2초 폴링), `DELETE /api/jobs/{id}` |
| SCR-03 분석 결과 요약 | `/jobs/:jobId/result` | `pages/result/ResultSummaryView.tsx` | `GET /api/jobs/{id}/result`, `GET …/report` |
| SCR-06 분석 불가 안내 | `/jobs/:jobId/result` | `pages/result/UnanalyzableView.tsx` | `GET /api/jobs/{id}/result` |
| SCR-07 판단 보류 결과 | `/jobs/:jobId/result` | `pages/result/HoldResultView.tsx` | `GET …/result`, `POST /api/jobs/{id}/review` |
| SCR-04 판정 근거 상세 | `/jobs/:jobId/evidence?roi=` | `pages/EvidencePage.tsx` | `GET /api/jobs/{id}/evidence?roi=` |
| SCR-05 분석 이력 | `/history` | `pages/HistoryPage.tsx` | `GET /api/jobs`, `DELETE /api/jobs` |

SCR-03·06·07은 한 경로를 쓰고 `pages/ResultPage.tsx`가 응답의 `result_type`(`done`/`failed`/`hold`)으로 분기한다.
화면설계서에서 SCR-07은 "SCR-03과 같은 레이아웃의 상태 변형"이므로, 판정 카드와 두 축 점수 막대는
SCR-03·07이 같이 쓰는 컴포넌트로 만든다.

## 목 API

`.env.development`의 `VITE_USE_MOCK=true`일 때 MSW가 `/api` 요청을 가로챈다.
실제 백엔드에 붙일 때는 `.env.development.local`에 `VITE_USE_MOCK=false`를 넣는다(그러면 `/api`가 `localhost:8000`으로 프록시된다).
화면 코드는 목 여부를 몰라야 한다. 목 전용 분기는 `import.meta.env.VITE_USE_MOCK` 확인이 필요한 개발용 안내에만 쓴다.

고정 ID 작업(주소로 바로 열 수 있고, 화면 하단 DEV 패널에도 링크가 있다):

| 작업 ID | 시나리오 | 열리는 화면 |
|---|---|---|
| `job-real-0001` | 진짜 (S≈0.18, SQI 0.82) | SCR-03 |
| `job-fake-0002` | 가짜 (S≈0.78, ROI 심박 불일치) | SCR-03 |
| `job-hold-0003` | 판단 보류 (축 간 차이 0.62, SQI 0.79) | SCR-07 |
| `job-failed-0004` | 분석 불가 (얼굴 미검출, 2/5단계에서 중단) | SCR-06 |
| `job-lowsqi-0005` | SQI 낮음 (0.18, `rppg_low_contribution: true`, 좌볼 BPM null) | SCR-03 경고 상태 |
| `job-running-0006` | 진행 중 (약 5분에 걸쳐 천천히 진행) | SCR-02 |

그 밖에 `job-sample-0007`~`0024` 18건이 이력에 들어 있다(검색·필터·페이지 확인용).

업로드하면 새 작업이 생기고 약 13.5초 동안 5단계를 진행한다. 파일명에 `fake` / `hold` / `fail`(또는 `noface`) / `lowsqi`가
들어 있으면 그 시나리오로, 아니면 '진짜'로 끝난다. 목 DB는 메모리에 있어 새로고침하면 초기화된다.
업로드의 `save_history` 값은 목 서버가 무시한다(항상 이력에 남는다).

목 데이터의 점수·BPM·임계값·특징 기준값은 모두 화면 확인용 예시다.
특징 표의 기준값 열은 화면에도 "(예시)"로 표시해 두었다. Celeb-DF 학습 세트로 기준이 확정되면 표시를 지운다(`pages/evidence/FeatureTab.tsx`).

## 규칙

- API 필드를 바꿀 때는 `src/types/api.ts` → `src/mocks/` 순으로 같이 고치고, 바꾼 내용을 사용자에게 알린다(백엔드 담당 팀원과 맞춰야 한다).
- 화면에서 axios를 직접 부르지 않는다. `src/api/jobs.ts`의 함수를 쓴다.
- 경로 문자열을 직접 쓰지 않는다. `src/lib/paths.ts`의 함수를 쓴다.
- 색은 `tokens.css`의 변수로만 쓴다. 판정은 색만으로 구분하지 않고 기호와 텍스트를 같이 쓴다(`VerdictBadge`).
  판정색은 역할별로 셋이다: `--verdict-*`(글자), `--verdict-*-fill`(차트 채움), `--verdict-*-bright`(어두운 판정 카드 위).
- 차트는 Recharts로 그린다. 공통 모양은 `lib/chartStyle.ts`를 쓴다 — 격자는 실선, 막대 두께 24px 이하,
  점수 구간 색은 `ZONE_STYLE`(색각 이상에서도 구분되도록 검증한 조합이라 임의로 바꾸지 않는다).
- **읽는 사람**: 검토자·전문가가 기준이지만 비전문가도 읽을 수 있어야 한다. 그래서
  - 용어는 쉬운 말을 앞에, 기술 용어를 뒤에 둔다(예: "영상 조작 흔적 `P_model`"). 표기는 `lib/terms.ts`에서 가져온다.
  - 화면은 결론(판정) → 이유(두 축, 계산) → 근거(신호·차트) 순서로 읽히게 배치한다.
  - 차트에는 "읽는 법"(정상이면 어떻게 보이는지) 한 줄을 붙인다(`ChartCard`의 `hint`).
- 결과 화면(SCR-03·04·07) 하단에는 `TriageNotice`(1차 선별 도구 고지)를 둔다.
- 기준 해상도는 데스크톱 1440×1000, 콘텐츠 최대 폭 1200px. 모바일 대응은 범위 밖이다.
- 유스케이스 번호는 화면설계서 체계(UC-01~17)를 쓴다. 초기 유스케이스 명세(UC-01~13)와 번호가 다르다
  (예: 분석 불가 안내는 명세의 UC-12, 화면설계서의 UC-16).
- 화면 문구·주석은 한국어.

## 현재 상태

되어 있는 것:

- API 타입, 목 서버(엔드포인트 7개 전부), API 호출 함수
- 공통 레이아웃(고정 헤더, 1200px 컨테이너), 라우팅, 판정 배지, 고지 문구
- 디자인: 색·글꼴 확정(2026-10-01), 전 화면에 적용. 결과 화면은 어두운 판정 카드(판정 + 종합 점수 게이지)로 시작한다.
- 화면 7개의 실제 UI (목 API 기준으로 동작 확인).
  - SCR-01: 드롭존, 선택 파일 카드(썸네일·해상도·fps·길이), 형식·용량 검증, 옵션, 업로드 진행률.
    길이 10초 미만은 막지 않고 주의만 표시한다. fps는 프레임 간격으로 추정한 값이다.
  - SCR-02: 5단계 스테퍼(메인 모델 ∥ rPPG 병렬 묶음), 진행률, 단계 로그, 분석 취소(확인 대화상자), 완료 토스트 후 자동 이동.
  - SCR-03: 판정 카드, 두 축 점수 차트, 산출식 카드, SQI 카드, ROI별 BPM 차트, 액션 바(리포트 내보내기·결과 링크 복사).
    `p_model_std`는 SCR-03에 표시하지 않는다(SCR-04 메인 모델 탭에만 있다).
  - SCR-06: 사유 제목과 중단 단계, 기준 대비 측정값 표, 해결 방법, 재업로드·이력 버튼.
  - SCR-07: SCR-03 카드의 보류 변형(S '—', 보류 조건 수치, 두 막대 사이 차이 화살표), 검토자 판단 기록(저장 후 읽기 전용 + 수정).
  - SCR-04: 탭 4개(`?tab=`), ROI 선택기(`?roi=`, rPPG 탭에서만), rPPG 차트 3종, ROI별 BPM·윈도우 BPM, 모델 구간 프로파일,
    SQI·가중치, 특징 표와 두 축 대조 요약. 임계값·SQI 구성 요소가 필요해 `…/result`도 같이 읽는다.
  - SCR-05: 검색·필터(주소 쿼리 반영), 판정 칩, 이력 테이블(행 클릭 이동, 진행 중 행 5초 갱신), 선택 삭제, 페이지네이션.

안 되어 있는 것:

1. 실제 백엔드 연동 확인 — 지금까지는 목 API로만 확인했다.
2. SCR-05의 `[리포트 ZIP 내보내기]` — 엔드포인트가 정해지지 않아 버튼을 비활성으로 두었다(아래 미결정 사항).
3. 테스트 러너·린터 설정.

## 미결정 사항 (임의로 정하지 말고 사용자에게 확인)

- **S가 0.4~0.6이고 두 축이 상충하지 않을 때의 판정**: 문서에 정의가 없다. 목 서버는 `S ≥ 0.6`이면 가짜, 그 외는 진짜로 처리하고,
  이 구간에 해당하는 목 데이터는 만들지 않았다.
- **P_rppg의 방향**: 타입과 목은 P_model과 같은 "조작 확률"(1에 가까울수록 가짜)로 가정했다. 융합식이 성립하려면 이 방향이어야 하지만 문서에 명시는 없다.
- **임계값**(S 0.4/0.6, 상충 임계 0.4, SQI 하한 0.5, α 0.5)과 SQI 등급 기준(0.7/0.5): 전부 예시. 성능 평가 실험으로 확정한다.
- **API 세부**: 이력 쿼리 파라미터 이름(`q`, `verdict`, `from`, `to`, `sqi_min`, `review`, `page`, `page_size`), 일괄 삭제 본문(`{ job_ids }`),
  오류 상태 코드(404/409/422)는 화면설계서에 없어서 이 저장소에서 제안한 값이다. 백엔드 담당 팀원과 합의가 필요하다.
- **리포트 ZIP 일괄 내보내기**(SCR-05): 대응 엔드포인트가 화면설계서 5장에 없다.
- 로그인·관리자 화면(UC-13·14)은 설계 범위에서 제외되어 있다.
