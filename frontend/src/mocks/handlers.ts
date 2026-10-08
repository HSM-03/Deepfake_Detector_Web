/**
 * MSW 요청 핸들러 — 화면설계서 5장의 엔드포인트 7개를 흉내 낸다.
 * 실제 FastAPI 서버가 준비되면 VITE_USE_MOCK=false 로 끄기만 하면 된다(화면 코드는 그대로).
 */
import { delay, http, HttpResponse, type JsonBodyType } from 'msw';
import type {
  ApiError,
  DeleteJobResponse,
  DeleteJobsRequest,
  DeleteJobsResponse,
  EvidenceResponse,
  JobListResponse,
  JobResultResponse,
  JobStatusResponse,
  Review,
  ReviewRequest,
  RoiSelector,
  UploadVideoResponse,
  VerdictKind,
} from '@/types/api';
import { verdictKindOf } from '@/lib/verdict';
import {
  buildResult,
  cancelRecord,
  computeStatus,
  createRecord,
  deleteRecord,
  getRecord,
  listItems,
} from './db';
import { buildEvidence } from './evidence';
import { SCENARIOS, scenarioFromFilename } from './scenarios';

const API = '/api';
const ROI_VALUES: RoiSelector[] = ['all', 'forehead', 'left_cheek', 'right_cheek'];

/** JSON 응답. 본문 타입을 json<타입>(...) 으로 명시해 API 계약(types/api.ts)과 어긋나면 컴파일 오류가 나게 한다. */
function json<T>(body: T, init?: ResponseInit): Response {
  return HttpResponse.json(body as JsonBodyType, init);
}

function error(status: number, detail: string): Response {
  return json<ApiError>({ detail }, { status });
}

const notFound = (jobId: string) => error(404, `작업을 찾을 수 없습니다: ${jobId}`);

/** 목 리포트용 최소 PDF (내용 없는 1쪽) */
const MOCK_PDF = [
  '%PDF-1.4',
  '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj',
  '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj',
  '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj',
  'trailer<</Root 1 0 R>>',
  '%%EOF',
].join('\n');

export const handlers = [
  /* POST /api/videos — 영상 업로드, job_id 반환 (SCR-01) */
  http.post(`${API}/videos`, async ({ request }) => {
    const form = await request.formData();
    const file = form.get('file');
    if (!(file instanceof File)) return error(422, 'file 필드가 필요합니다');

    const memo = form.get('memo');
    const record = createRecord({
      scenario: scenarioFromFilename(file.name),
      filename: file.name,
      size_bytes: file.size,
      memo: typeof memo === 'string' && memo.trim() ? memo.trim() : null,
    });
    await delay(600);
    return json<UploadVideoResponse>({ job_id: record.job_id }, { status: 201 });
  }),

  /* GET /api/jobs/{id}/status — 단계·진행률·로그 (SCR-02, 05) */
  http.get(`${API}/jobs/:jobId/status`, async ({ params }) => {
    const jobId = String(params.jobId);
    const record = getRecord(jobId);
    if (!record) return notFound(jobId);
    await delay(150);
    return json<JobStatusResponse>(computeStatus(record));
  }),

  /* GET /api/jobs/{id}/result — 판정 결과 (SCR-03, 06, 07) */
  http.get(`${API}/jobs/:jobId/result`, async ({ params }) => {
    const jobId = String(params.jobId);
    const record = getRecord(jobId);
    if (!record) return notFound(jobId);
    const result = buildResult(record);
    if (!result) return error(409, '아직 분석이 끝나지 않았거나 취소된 작업입니다');
    await delay(300);
    return json<JobResultResponse>(result);
  }),

  /* GET /api/jobs/{id}/evidence?roi= — 판정 근거 (SCR-04) */
  http.get(`${API}/jobs/:jobId/evidence`, async ({ params, request }) => {
    const jobId = String(params.jobId);
    const record = getRecord(jobId);
    if (!record) return notFound(jobId);

    const roiParam = new URL(request.url).searchParams.get('roi') ?? 'all';
    if (!ROI_VALUES.includes(roiParam as RoiSelector)) return error(422, `알 수 없는 roi: ${roiParam}`);

    const template = SCENARIOS[record.scenario];
    if (template.kind === 'failed' || computeStatus(record).result_type === null) {
      return error(409, '근거 데이터가 없는 작업입니다(분석 불가·진행 중·취소)');
    }
    await delay(500);
    return json<EvidenceResponse>(buildEvidence(record, template, roiParam as RoiSelector));
  }),

  /* POST /api/jobs/{id}/review — 검토자 최종 판단 기록 (SCR-07) */
  http.post(`${API}/jobs/:jobId/review`, async ({ params, request }) => {
    const jobId = String(params.jobId);
    const record = getRecord(jobId);
    if (!record) return notFound(jobId);
    if (record.scenario !== 'hold') return error(409, '판단 보류 건에만 검토 판단을 기록할 수 있습니다');

    const body = (await request.json()) as ReviewRequest;
    if (!['real', 'fake', 'needs_more_review'].includes(body.decision)) {
      return error(422, 'decision 값이 올바르지 않습니다');
    }
    const review: Review = {
      decision: body.decision,
      reason: body.reason ?? '',
      reviewed_at: new Date().toISOString(),
    };
    record.review = review;
    await delay(300);
    return json<Review>(review);
  }),

  /* GET /api/jobs/{id}/report — 결과 리포트 PDF (SCR-03, 04, 07 / UC-05) */
  http.get(`${API}/jobs/:jobId/report`, async ({ params }) => {
    const jobId = String(params.jobId);
    if (!getRecord(jobId)) return notFound(jobId);
    await delay(700);
    return new HttpResponse(MOCK_PDF, {
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': `attachment; filename="report_${jobId}.pdf"`,
      },
    });
  }),

  /* GET /api/jobs — 이력 목록: 검색·필터·페이지 (SCR-05) */
  http.get(`${API}/jobs`, async ({ request }) => {
    const query = new URL(request.url).searchParams;
    const q = (query.get('q') ?? '').trim().toLowerCase();
    const verdict = query.get('verdict') as VerdictKind | null;
    const from = query.get('from');
    const to = query.get('to');
    const sqiMin = query.get('sqi_min');
    const review = query.get('review');
    const page = Math.max(1, Number(query.get('page') ?? 1));
    const pageSize = Math.max(1, Number(query.get('page_size') ?? 10));

    // 검색어·기간·SQI·검토 상태를 먼저 적용하고, 판정별 건수를 센 뒤, 판정 필터를 적용한다.
    const base = listItems().filter((item) => {
      if (q && ![item.filename, item.job_id, item.memo ?? ''].some((v) => v.toLowerCase().includes(q))) return false;
      const day = item.created_at.slice(0, 10);
      if (from && day < from) return false;
      if (to && day > to) return false;
      if (sqiMin && (item.sqi === null || item.sqi < Number(sqiMin))) return false;
      if (review && item.review_state !== review) return false;
      return true;
    });

    const counts: Record<VerdictKind, number> = { real: 0, fake: 0, hold: 0, failed: 0, running: 0, canceled: 0 };
    for (const item of base) counts[verdictKindOf(item)] += 1;

    const filtered = verdict ? base.filter((item) => verdictKindOf(item) === verdict) : base;
    const start = (page - 1) * pageSize;

    await delay(300);
    return json<JobListResponse>({
      items: filtered.slice(start, start + pageSize),
      total: filtered.length,
      page,
      page_size: pageSize,
      counts,
    });
  }),

  /* DELETE /api/jobs/{id} — 진행 중이면 취소, 종료 건이면 삭제 (SCR-02, 05) */
  http.delete(`${API}/jobs/:jobId`, async ({ params }) => {
    const jobId = String(params.jobId);
    const record = getRecord(jobId);
    if (!record) return notFound(jobId);

    await delay(200);
    if (cancelRecord(record)) {
      return json<DeleteJobResponse>({ job_id: jobId, action: 'canceled' });
    }
    deleteRecord(jobId);
    return json<DeleteJobResponse>({ job_id: jobId, action: 'deleted' });
  }),

  /* DELETE /api/jobs — 선택 건 일괄 삭제 (SCR-05, UC-07) */
  http.delete(`${API}/jobs`, async ({ request }) => {
    const body = (await request.json()) as DeleteJobsRequest;
    const deleted = (body.job_ids ?? []).filter((id) => deleteRecord(id));
    await delay(300);
    return json<DeleteJobsResponse>({ deleted });
  }),
];
