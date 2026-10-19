/**
 * API 계약(프론트엔드 ↔ FastAPI 백엔드)
 *
 * 화면설계서 v1.3 「5. 화면–API 연계 요약」의 엔드포인트 7개에 대한 요청·응답 타입.
 * 이 파일이 두 팀원 사이의 인터페이스 기준이다. 필드를 바꿀 때는
 *   1) 이 파일 → 2) src/mocks (목 데이터) → 3) 백엔드 Pydantic 스키마
 * 순서로 같이 고친다.
 *
 * 규칙
 * - 필드명은 백엔드(Python)와 맞춰 snake_case.
 * - 시각은 ISO 8601 문자열(UTC).
 * - 확률·점수·SQI는 0~1 실수. P_model, P_rppg, S 모두 "조작(가짜)일 확률" 방향
 *   (1에 가까울수록 가짜). ※ P_rppg의 방향은 가정이며 CLAUDE.md '미결정 사항' 참고.
 */

/* ────────────────────────────── 공통 ────────────────────────────── */

/** rPPG 관심 영역 */
export type RoiKey = 'forehead' | 'left_cheek' | 'right_cheek';
/** SCR-04 ROI 선택기 값 (전체 + 개별 ROI) */
export type RoiSelector = 'all' | RoiKey;

/** SCR-02 5단계 스테퍼의 단계. model·rppg는 병렬로 수행된다. */
export type StageKey = 'upload' | 'preprocess' | 'model' | 'rppg' | 'fusion';
export type StageState = 'waiting' | 'running' | 'done' | 'failed' | 'canceled';

/** 분석이 끝났을 때의 결과 종류. SCR-02가 이 값으로 이동할 화면을 정한다.
 *  done → SCR-03, failed → SCR-06, hold → SCR-07 */
export type ResultType = 'done' | 'failed' | 'hold';

/** 작업 상태. 종료 상태 중 done/failed/hold는 ResultType과 같은 값을 쓴다. */
export type JobState = 'queued' | 'running' | 'done' | 'failed' | 'hold' | 'canceled';

/** 최종 판정 3분류 */
export type Verdict = 'real' | 'fake' | 'hold';

/** 백엔드 오류 응답 (FastAPI HTTPException 기본 형태) */
export interface ApiError {
  detail: string;
}

/* ─────────────────── POST /api/videos (SCR-01) ─────────────────── */

/** multipart/form-data 필드. 실제 전송은 FormData로 한다. */
export interface UploadVideoRequest {
  file: File;
  /** 이력 저장 여부 (기본 true) */
  save_history: boolean;
  /** 메모(선택). 이력 검색 대상 */
  memo?: string;
}

export interface UploadVideoResponse {
  job_id: string;
}

/* ─────────────── GET /api/jobs/{id}/status (SCR-02, 05) ─────────────── */

export interface StageStatus {
  key: StageKey;
  label: string;
  state: StageState;
  /** 단계 내 진행률 0~100 */
  progress: number;
}

/** 완료된 단계의 중간 결과 로그 (프레임 수, 얼굴 검출률, P_model 등) */
export interface JobLogEntry {
  at: string;
  stage: StageKey;
  message: string;
}

export interface JobStatusResponse {
  job_id: string;
  filename: string;
  created_at: string;
  state: JobState;
  /** 전체 진행률 0~100 */
  progress: number;
  /** 현재 진행 중인 단계. 병렬 구간에서는 먼저 끝나지 않은 단계 하나. 종료 시 null */
  current_stage: StageKey | null;
  /** 현재 작업 설명 (진행률 바 아래 문구) */
  message: string;
  stages: StageStatus[];
  logs: JobLogEntry[];
  /** 남은 예상 시간(초). 알 수 없거나 종료 상태면 null */
  eta_seconds: number | null;
  /** 분석 중에는 null. 값이 생기면 결과 화면으로 이동한다. */
  result_type: ResultType | null;
}

/* ─────────── GET /api/jobs/{id}/result (SCR-03, 06, 07) ─────────── */

export interface VideoMeta {
  filename: string;
  size_bytes: number;
  width: number;
  height: number;
  fps: number;
  duration_sec: number;
  frame_count: number;
  codec: string;
}

export type SqiGrade = 'good' | 'fair' | 'poor';

/** 신호품질지수. components는 각 0~1 (1이 좋음) */
export interface SqiInfo {
  value: number;
  grade: SqiGrade;
  components: {
    /** 얼굴 영역 픽셀 수 */
    face_pixels: number;
    /** 압축 정도 — 코덱과 영상 스트림의 픽셀당 비트(bpp)로 판단 (1 = 압축 손상 적음) */
    compression: number;
    /** 평균 조도·조도 변동 */
    illumination: number;
    /** 머리·얼굴 움직임 — 머리 이동과 입·턱 움직임 중 큰 쪽 (1 = 움직임 적음) */
    motion: number;
  };
}

/** 판정에 적용된 임계값. 값은 모두 예시이며 성능 평가 단계에서 확정한다. */
export interface Thresholds {
  /** S가 이 값 이하면 진짜 */
  score_real_max: number;
  /** S가 이 값 이상이면 가짜 */
  score_fake_min: number;
  /** |P_model − P_rppg|가 이 값 이상이면 상충 */
  conflict_gap: number;
  /** SQI 하한. 미만이면 rPPG 기여도 낮음 경고 */
  sqi_min: number;
  /** w = alpha · SQI */
  alpha: number;
}

/** ROI별 추정 심박(BPM). 추정 실패 시 null */
export type RoiBpm = Record<RoiKey, number | null>;

interface ResultBase {
  job_id: string;
  created_at: string;
  completed_at: string;
  video: VideoMeta;
  memo: string | null;
}

/** 점수가 산출된 결과(done, hold)에 공통인 필드 */
interface ScoredFields {
  /** 메인 모델(시각 아티팩트) 조작 확률 */
  p_model: number;
  /** 프레임 점수의 표준편차 (안정성 지표) */
  p_model_std: number;
  /** rPPG 축 조작 확률 */
  p_rppg: number;
  /**
   * P_rppg가 분류기 없이 임시로 P_model 값을 쓴 결과인지(백엔드 5단계 전). true면 판단 보류가 나올 수 없고
   * 종합 점수 S도 사실상 메인 모델 단독 값이다 — 화면에 "분류기 미적용"을 표시한다
   */
  p_rppg_provisional: boolean;
  /** 적용된 rPPG 가중치. S = (1 − w)·P_model + w·P_rppg */
  w: number;
  sqi: SqiInfo;
  roi_bpm: RoiBpm;
  thresholds: Thresholds;
  /** 자연어 해석 (판정 카드에 표시) */
  interpretation: string;
}

/** SCR-03 분석 결과 요약 */
export interface DoneResult extends ResultBase, ScoredFields {
  result_type: 'done';
  verdict: 'real' | 'fake';
  /** 종합 점수 S */
  score: number;
  /** SQI < sqi_min → 'rPPG 미반영(신호 품질 낮음) — 메인 모델 중심 판정' 표기 */
  rppg_low_contribution: boolean;
}

/** SCR-07 판단 보류 결과 */
export interface HoldResult extends ResultBase, ScoredFields {
  result_type: 'hold';
  verdict: 'hold';
  /** 보류 건은 S를 표시하지 않는다('—') */
  score: null;
  /** |P_model − P_rppg| */
  axis_gap: number;
  /** 검토자 최종 판단. 아직 기록 전이면 null */
  review: Review | null;
}

export type FailureCode =
  | 'FACE_NOT_DETECTED'
  | 'VIDEO_TOO_SHORT'
  | 'FILE_CORRUPTED'
  | 'UNKNOWN';

/** 기준 대비 측정값 한 줄. 예) 얼굴 검출 프레임 5.3% < 기준 80% */
export interface FailureCheck {
  label: string;
  measured: string;
  criterion: string;
  passed: boolean;
}

export interface FailureInfo {
  code: FailureCode;
  /** 사유를 한 문장으로 (안내 헤더 제목) */
  title: string;
  stopped_stage: StageKey;
  /** 중단 단계 번호 n (n/5 표기용, 1부터) */
  stopped_stage_index: number;
  checks: FailureCheck[];
  /** 사유 코드별 권장 조치 */
  suggestions: string[];
}

/** SCR-06 분석 불가 안내 */
export interface FailedResult extends ResultBase {
  result_type: 'failed';
  failure: FailureInfo;
}

/** result_type으로 구분되는 유니언. switch로 좁혀서 쓴다. */
export type JobResultResponse = DoneResult | HoldResult | FailedResult;

/* ─────────── POST /api/jobs/{id}/review (SCR-07) ─────────── */

export type ReviewDecision = 'real' | 'fake' | 'needs_more_review';

export interface ReviewRequest {
  decision: ReviewDecision;
  reason: string;
}

export interface Review extends ReviewRequest {
  reviewed_at: string;
}

/* ─────────── GET /api/jobs/{id}/evidence?roi= (SCR-04) ─────────── */

export interface SignalPoint {
  /** 초 */
  t: number;
  v: number;
}

export interface PsdPoint {
  hz: number;
  power: number;
}

export interface WindowBpm {
  /** 8초 슬라이딩 윈도우(1초 간격) 시작 시각(초). 화면설계서는 3초였으나 해상도 문제로 바꿈(docs/backend-plan.md 4단계) */
  t_start: number;
  bpm: number | null;
}

/** 메인 모델 구간별 조작 확률 프로파일 */
export interface ModelSegment {
  t_start: number;
  t_end: number;
  p: number;
}

export type FeatureKey =
  | 'hr_in_range'
  | 'snr'
  | 'spectral_entropy'
  | 'roi_bpm_std'
  | 'phase_consistency'
  | 'window_bpm_var';

/** 판단: ok ○ / warn △ / bad × */
export type FeatureJudgement = 'ok' | 'warn' | 'bad';

/** rPPG 특징 벡터 한 항목 (SCR-04 특징 표) */
export interface FeatureRow {
  key: FeatureKey;
  label: string;
  /** 분류기 입력값 */
  value: number;
  /** 화면 표시용 측정값 문자열 */
  display: string;
  /** 실제 얼굴 기준 (예시) */
  reference: string;
  judgement: FeatureJudgement;
  /** 판단 보류 건에서 상충을 만든 특징이면 true (강조 표시) */
  conflict_source: boolean;
}

export interface EvidenceResponse {
  job_id: string;
  roi: RoiSelector;
  /** 샘플링 주파수(=영상 fps) */
  fs: number;
  /** 원신호 (ROI 평균 RGB → CHROM 결합 후, 필터 전) */
  raw_signal: SignalPoint[];
  /** Butterworth 대역통과 필터 후 파형 */
  filtered_signal: SignalPoint[];
  /** Welch 파워 스펙트럼 */
  psd: PsdPoint[];
  /** 심박 대역 [저역, 고역] Hz — 스펙트럼 음영 구간 */
  hr_band: [number, number];
  /** 심박 대역 내 최대 피크. 검출 실패 시 null */
  peak: { hz: number; bpm: number; power: number } | null;
  roi_bpm: RoiBpm;
  /** ROI 간 BPM 표준편차 σ */
  roi_bpm_std: number | null;
  window_bpm: WindowBpm[];
  model_profile: ModelSegment[];
  features: FeatureRow[];
  /** 두 축 대조 요약 */
  axis_summary: {
    p_model: number;
    p_rppg: number;
    w: number;
    sqi: number;
    text: string;
  };
  /** SQI < sqi_min일 때 true → 'rPPG 미반영(신호 품질 낮음)' 배너 표시 */
  rppg_low_contribution: boolean;
  /** 결과의 p_rppg_provisional과 같다 (근거 화면의 P_rppg 자리에 "분류기 미적용" 표시) */
  p_rppg_provisional: boolean;
  /** rPPG가 분석한 길이(초). 긴 영상은 앞 60초만 분석한다 */
  rppg_analyzed_sec: number;
  /** 영상이 더 길어 앞부분만 분석했으면 true → "앞 N초 분석" 표시 */
  rppg_truncated: boolean;
}

/* ─────────── GET /api/jobs (SCR-05) ─────────── */

/** 이력 테이블의 판정 표시 종류: ■가짜 □진짜 ◆보류 ×불가 ◐진행 (+취소) */
export type VerdictKind = 'real' | 'fake' | 'hold' | 'failed' | 'running' | 'canceled';

/**
 * 보류 건의 검토 상태. 보류가 아니면 none
 * - pending: 검토 대기 — 아직 검토 기록이 없음
 * - needs_more_review: 추가 검토 필요 — 검토자가 '추가 검토 필요'로 기록함
 * - reviewed: 검토 완료 — 검토자가 진짜·가짜로 결론을 냄
 */
export type ReviewState = 'none' | 'pending' | 'needs_more_review' | 'reviewed';

export interface JobListItem {
  job_id: string;
  filename: string;
  created_at: string;
  state: JobState;
  /** 판정. 분석 불가·진행 중·취소 건은 null */
  verdict: Verdict | null;
  score: number | null;
  p_model: number | null;
  p_rppg: number | null;
  sqi: number | null;
  review_state: ReviewState;
  memo: string | null;
  /** 진행 중 행 표시용 0~100 */
  progress: number;
}

/** 쿼리 파라미터. SCR-05는 이 값을 URL 쿼리에도 반영한다. */
export interface JobListQuery {
  /** 파일명·작업 ID·메모 통합 검색 */
  q?: string;
  /** 판정 필터 */
  verdict?: VerdictKind;
  /** 기간 시작·끝 (YYYY-MM-DD, 양끝 포함) */
  from?: string;
  to?: string;
  /** SQI 하한 */
  sqi_min?: number;
  /** 보류 건 검토 상태 필터 (검토 대기 / 추가 검토 필요 / 검토 완료) */
  review?: Exclude<ReviewState, 'none'>;
  /** 1부터 */
  page?: number;
  /** 10 / 20 / 50 */
  page_size?: number;
}

export interface JobListResponse {
  items: JobListItem[];
  total: number;
  page: number;
  page_size: number;
  /** 판정 칩에 표시할 판정별 건수 (검색어·기간은 반영, 판정 필터는 미반영) */
  counts: Record<VerdictKind, number>;
}

/* ─────────── DELETE /api/jobs, /api/jobs/{id} (SCR-05, 02) ─────────── */

/** DELETE /api/jobs 요청 본문 (선택 건 일괄 삭제, UC-07) */
export interface DeleteJobsRequest {
  job_ids: string[];
}

export interface DeleteJobsResponse {
  deleted: string[];
}

/** DELETE /api/jobs/{id} — 진행 중이면 취소(revoke), 종료 건이면 삭제 */
export interface DeleteJobResponse {
  job_id: string;
  action: 'canceled' | 'deleted';
}

/* ─────────── GET /api/jobs/{id}/report (SCR-03, 04, 07) ───────────
 * 응답은 application/pdf 바이너리(Blob). 별도 JSON 타입 없음. (UC-05) */
