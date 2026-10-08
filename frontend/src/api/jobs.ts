/**
 * API 함수 모음. 화면(페이지)은 axios를 직접 부르지 않고 이 함수들만 사용한다.
 * 엔드포인트와 타입은 src/types/api.ts 기준.
 */
import type {
  DeleteJobResponse,
  DeleteJobsRequest,
  DeleteJobsResponse,
  EvidenceResponse,
  JobListQuery,
  JobListResponse,
  JobResultResponse,
  JobStatusResponse,
  Review,
  ReviewRequest,
  RoiSelector,
  UploadVideoRequest,
  UploadVideoResponse,
} from '@/types/api';
import { api } from './client';

/** POST /api/videos — 업로드 후 job_id를 받는다 (SCR-01) */
export async function uploadVideo(
  input: UploadVideoRequest,
  onUploadProgress?: (percent: number) => void,
): Promise<UploadVideoResponse> {
  const form = new FormData();
  form.append('file', input.file);
  form.append('save_history', String(input.save_history));
  if (input.memo) form.append('memo', input.memo);

  const { data } = await api.post<UploadVideoResponse>('/videos', form, {
    // 대용량 업로드는 기본 타임아웃(30초)을 넘길 수 있다
    timeout: 0,
    onUploadProgress: (event) => {
      if (onUploadProgress && event.total) onUploadProgress(Math.round((event.loaded / event.total) * 100));
    },
  });
  return data;
}

/** GET /api/jobs/{id}/status — SCR-02가 2초 간격으로 폴링 */
export async function getJobStatus(jobId: string, signal?: AbortSignal): Promise<JobStatusResponse> {
  const { data } = await api.get<JobStatusResponse>(`/jobs/${jobId}/status`, { signal });
  return data;
}

/** GET /api/jobs/{id}/result — SCR-03 / 06 / 07 */
export async function getJobResult(jobId: string, signal?: AbortSignal): Promise<JobResultResponse> {
  const { data } = await api.get<JobResultResponse>(`/jobs/${jobId}/result`, { signal });
  return data;
}

/** GET /api/jobs/{id}/evidence?roi= — SCR-04 */
export async function getJobEvidence(
  jobId: string,
  roi: RoiSelector = 'all',
  signal?: AbortSignal,
): Promise<EvidenceResponse> {
  const { data } = await api.get<EvidenceResponse>(`/jobs/${jobId}/evidence`, { params: { roi }, signal });
  return data;
}

/** POST /api/jobs/{id}/review — 검토자 최종 판단 기록 (SCR-07) */
export async function submitReview(jobId: string, body: ReviewRequest): Promise<Review> {
  const { data } = await api.post<Review>(`/jobs/${jobId}/review`, body);
  return data;
}

/** GET /api/jobs — 이력 목록 (SCR-05) */
export async function listJobs(query: JobListQuery = {}, signal?: AbortSignal): Promise<JobListResponse> {
  const { data } = await api.get<JobListResponse>('/jobs', { params: query, signal });
  return data;
}

/** DELETE /api/jobs/{id} — 진행 중이면 취소, 종료 건이면 삭제 */
export async function deleteJob(jobId: string): Promise<DeleteJobResponse> {
  const { data } = await api.delete<DeleteJobResponse>(`/jobs/${jobId}`);
  return data;
}

/** DELETE /api/jobs — 선택 건 일괄 삭제 (UC-07) */
export async function deleteJobs(jobIds: string[]): Promise<DeleteJobsResponse> {
  const body: DeleteJobsRequest = { job_ids: jobIds };
  const { data } = await api.delete<DeleteJobsResponse>('/jobs', { data: body });
  return data;
}

/** GET /api/jobs/{id}/report — 결과 리포트 PDF (UC-05) */
export async function downloadReport(jobId: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/jobs/${jobId}/report`, { responseType: 'blob', timeout: 120_000 });
  return data;
}
