/** 화면 표시용 포맷 함수 */

/** 확률·점수·SQI (0~1) */
export function formatScore(value: number): string {
  return value.toFixed(2);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}초`;
  return `${Math.floor(sec / 60)}분 ${Math.round(sec % 60)}초`;
}

/** 남은 예상 시간 */
export function formatEta(sec: number): string {
  return sec < 60 ? `약 ${sec}초` : `약 ${Math.ceil(sec / 60)}분`;
}

/** ISO 시각 → '2026. 10. 1. 오후 3:20' */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('ko-KR', { dateStyle: 'medium', timeStyle: 'short' });
}

/** ISO 시각 → '15:20:07' (로그용) */
export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
}
