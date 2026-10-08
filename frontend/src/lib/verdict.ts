import type { JobListItem, Thresholds, VerdictKind } from '@/types/api';

/**
 * 판정 표기 규격 (화면설계서 1장 공통 규격).
 * 색만으로 구분하지 않도록 아이콘(기호)과 텍스트를 항상 같이 쓴다.
 */
export const VERDICT_META: Record<VerdictKind, { symbol: string; label: string }> = {
  real: { symbol: '□', label: '진짜' },
  fake: { symbol: '■', label: '가짜' },
  hold: { symbol: '◆', label: '판단 보류' },
  failed: { symbol: '×', label: '분석 불가' },
  running: { symbol: '◐', label: '진행 중' },
  canceled: { symbol: '–', label: '취소됨' },
};

/** 0~1 점수(S, P_model, P_rppg)가 놓인 구간: 진짜 기준 이하 / 경계 구간 / 가짜 기준 이상 */
export type ScoreZone = 'real' | 'boundary' | 'fake';

export function scoreZone(value: number, thresholds: Thresholds): ScoreZone {
  if (value <= thresholds.score_real_max) return 'real';
  if (value >= thresholds.score_fake_min) return 'fake';
  return 'boundary';
}

/** 이력 행 → 판정 표시 종류 */
export function verdictKindOf(item: Pick<JobListItem, 'verdict' | 'state'>): VerdictKind {
  if (item.verdict) return item.verdict;
  if (item.state === 'failed') return 'failed';
  if (item.state === 'canceled') return 'canceled';
  return 'running';
}
