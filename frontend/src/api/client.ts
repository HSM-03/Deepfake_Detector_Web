import axios, { AxiosError } from 'axios';
import type { ApiError } from '@/types/api';

/** 모든 API 호출이 공유하는 Axios 인스턴스 */
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 30_000,
});

/** 백엔드의 { detail } 오류 메시지를 꺼낸다. 없으면 일반 문구 */
export function getErrorMessage(err: unknown): string {
  if (err instanceof AxiosError) {
    const detail = (err.response?.data as Partial<ApiError> | undefined)?.detail;
    if (typeof detail === 'string') return detail;
    if (err.code === 'ECONNABORTED') return '서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.';
    if (!err.response) return '서버에 연결할 수 없습니다.';
    return `요청을 처리하지 못했습니다 (HTTP ${err.response.status}).`;
  }
  return err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.';
}

/** HTTP 상태 코드 (없으면 null) */
export function getErrorStatus(err: unknown): number | null {
  return err instanceof AxiosError ? (err.response?.status ?? null) : null;
}
