import type { JobState } from '@/types/api';

/** 화면 경로. 링크·이동은 문자열을 직접 쓰지 않고 이 함수들을 사용한다. */
export const paths = {
  /** SCR-01 영상 업로드 */
  upload: () => '/',
  /** SCR-02 분석 진행 상태 */
  progress: (jobId: string) => `/jobs/${jobId}`,
  /** SCR-03 / 06 / 07 — result_type에 따라 한 경로에서 분기 */
  result: (jobId: string) => `/jobs/${jobId}/result`,
  /** SCR-04 판정 근거 상세 */
  evidence: (jobId: string) => `/jobs/${jobId}/evidence`,
  /** SCR-05 분석 이력 */
  history: () => '/history',
  /** SCR-05에서 판단 보류 건만 (검토 대기·추가 검토 필요·검토 완료 모두) */
  historyHold: () => '/history?verdict=hold',
};

/** 이력 행 클릭 시 상태별 이동 경로 (SCR-05 → SCR-02 / 03 / 06 / 07) */
export function pathForJob(jobId: string, state: JobState): string {
  return state === 'done' || state === 'failed' || state === 'hold' ? paths.result(jobId) : paths.progress(jobId);
}
