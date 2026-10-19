"""
API 요청·응답 형식 — frontend/src/types/api.ts를 그대로 옮긴 것. **두 파일은 항상 같아야 한다.**

형식을 바꿔야 하면 api.ts → 프론트 목(frontend/src/mocks/) → 이 파일 순으로 함께 고친다(루트 CLAUDE.md).
FastAPI는 엔드포인트의 response_model로 응답을 이 형식대로 검사·변환하고, /docs 화면에도 이 형식을 보여 준다.
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

# ── 공통 ──
RoiKey = Literal['forehead', 'left_cheek', 'right_cheek']
RoiSelector = Literal['all', 'forehead', 'left_cheek', 'right_cheek']
StageKey = Literal['upload', 'preprocess', 'model', 'rppg', 'fusion']
StageState = Literal['waiting', 'running', 'done', 'failed', 'canceled']
ResultType = Literal['done', 'failed', 'hold']
JobState = Literal['queued', 'running', 'done', 'failed', 'hold', 'canceled']
Verdict = Literal['real', 'fake', 'hold']


class ApiError(BaseModel):
    detail: str


# ── POST /api/videos (SCR-01) ──
class UploadVideoResponse(BaseModel):
    job_id: str


# ── GET /api/jobs/{id}/status (SCR-02, 05) ──
class StageStatus(BaseModel):
    key: StageKey
    label: str
    state: StageState
    progress: int  # 단계 내 진행률 0~100


class JobLogEntry(BaseModel):
    at: str  # ISO 8601 (UTC)
    stage: StageKey
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    filename: str
    created_at: str
    state: JobState
    progress: int  # 전체 진행률 0~100
    current_stage: StageKey | None
    message: str
    stages: list[StageStatus]
    logs: list[JobLogEntry]
    eta_seconds: int | None
    result_type: ResultType | None


# ── GET /api/jobs/{id}/result (SCR-03, 06, 07) ──
class VideoMeta(BaseModel):
    filename: str
    size_bytes: int
    width: int
    height: int
    fps: float
    duration_sec: float
    frame_count: int
    codec: str


class SqiComponents(BaseModel):
    face_pixels: float
    compression: float
    illumination: float
    motion: float


class SqiInfo(BaseModel):
    value: float
    grade: Literal['good', 'fair', 'poor']
    components: SqiComponents


class Thresholds(BaseModel):
    score_real_max: float
    score_fake_min: float
    conflict_gap: float
    sqi_min: float
    alpha: float


class RoiBpm(BaseModel):
    forehead: float | None
    left_cheek: float | None
    right_cheek: float | None


class _ResultBase(BaseModel):
    job_id: str
    created_at: str
    completed_at: str
    video: VideoMeta
    memo: str | None


class _ScoredFields(BaseModel):
    p_model: float
    p_model_std: float
    p_rppg: float
    # P_rppg가 분류기 없이 임시로 P_model 값을 쓴 결과(5단계 전). true면 S도 사실상 메인 모델 단독 값
    p_rppg_provisional: bool
    w: float
    sqi: SqiInfo
    roi_bpm: RoiBpm
    thresholds: Thresholds
    interpretation: str


class ReviewRequest(BaseModel):
    decision: Literal['real', 'fake', 'needs_more_review']
    reason: str = ''


class Review(ReviewRequest):
    reviewed_at: str


class DoneResult(_ResultBase, _ScoredFields):
    result_type: Literal['done']
    verdict: Literal['real', 'fake']
    score: float
    rppg_low_contribution: bool


class HoldResult(_ResultBase, _ScoredFields):
    result_type: Literal['hold']
    verdict: Literal['hold']
    score: None
    axis_gap: float
    review: Review | None


class FailureCheck(BaseModel):
    label: str
    measured: str
    criterion: str
    passed: bool


class FailureInfo(BaseModel):
    code: Literal['FACE_NOT_DETECTED', 'VIDEO_TOO_SHORT', 'FILE_CORRUPTED', 'UNKNOWN']
    title: str
    stopped_stage: StageKey
    stopped_stage_index: int
    checks: list[FailureCheck]
    suggestions: list[str]


class FailedResult(_ResultBase):
    result_type: Literal['failed']
    failure: FailureInfo


# result_type 값으로 세 형식 중 하나를 고른다 (api.ts의 JobResultResponse 유니언)
JobResultResponse = Annotated[Union[DoneResult, HoldResult, FailedResult], Field(discriminator='result_type')]


# ── GET /api/jobs/{id}/evidence?roi= (SCR-04) ──
class SignalPoint(BaseModel):
    t: float
    v: float


class PsdPoint(BaseModel):
    hz: float
    power: float


class WindowBpm(BaseModel):
    t_start: float
    bpm: float | None


class ModelSegment(BaseModel):
    t_start: float
    t_end: float
    p: float


class FeatureRow(BaseModel):
    key: Literal['hr_in_range', 'snr', 'spectral_entropy', 'roi_bpm_std', 'phase_consistency', 'window_bpm_var']
    label: str
    value: float
    display: str
    reference: str
    judgement: Literal['ok', 'warn', 'bad']
    conflict_source: bool


class Peak(BaseModel):
    hz: float
    bpm: float
    power: float


class AxisSummary(BaseModel):
    p_model: float
    p_rppg: float
    w: float
    sqi: float
    text: str


class EvidenceResponse(BaseModel):
    job_id: str
    roi: RoiSelector
    fs: float
    raw_signal: list[SignalPoint]
    filtered_signal: list[SignalPoint]
    psd: list[PsdPoint]
    hr_band: tuple[float, float]
    peak: Peak | None
    roi_bpm: RoiBpm
    roi_bpm_std: float | None
    window_bpm: list[WindowBpm]
    model_profile: list[ModelSegment]
    features: list[FeatureRow]
    axis_summary: AxisSummary
    rppg_low_contribution: bool
    p_rppg_provisional: bool
    rppg_analyzed_sec: float  # rPPG가 분석한 길이(초). 긴 영상은 앞 RPPG_MAX_ANALYSIS_SEC초만
    rppg_truncated: bool  # 영상이 그보다 길어 앞부분만 분석했으면 true


# ── GET /api/jobs (SCR-05) ──
VerdictKind = Literal['real', 'fake', 'hold', 'failed', 'running', 'canceled']
# 보류 건 검토 상태: pending 검토 대기(기록 없음) / needs_more_review 추가 검토 필요 / reviewed 검토 완료(진짜·가짜로 결론)
ReviewState = Literal['none', 'pending', 'needs_more_review', 'reviewed']


class JobListItem(BaseModel):
    job_id: str
    filename: str
    created_at: str
    state: JobState
    verdict: Verdict | None
    score: float | None
    p_model: float | None
    p_rppg: float | None
    sqi: float | None
    review_state: ReviewState
    memo: str | None
    progress: int


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int
    page: int
    page_size: int
    counts: dict[VerdictKind, int]


# ── DELETE /api/jobs, /api/jobs/{id} (SCR-05, 02) ──
class DeleteJobsRequest(BaseModel):
    job_ids: list[str]


class DeleteJobsResponse(BaseModel):
    deleted: list[str]


class DeleteJobResponse(BaseModel):
    job_id: str
    action: Literal['canceled', 'deleted']
