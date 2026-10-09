import type { JobListItem, Review, ReviewState, Thresholds, VerdictKind } from '@/types/api';

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

/** 판단 보류 건의 검토 상태 표기. 판정 카드, 검토 칸, 이력 상태 열·필터가 모두 이 이름을 쓴다 */
export const REVIEW_STATE_META: Record<Exclude<ReviewState, 'none'>, { symbol: string; label: string }> = {
  pending: { symbol: '◆', label: '검토 대기' },
  needs_more_review: { symbol: '◆', label: '추가 검토 필요' },
  reviewed: { symbol: '✓', label: '검토 완료' },
};

/** 검토 기록 → 검토 상태. 기록이 없으면 검토 대기, '추가 검토 필요'면 그대로, 진짜·가짜로 정했으면 검토 완료 */
export function reviewStateOf(review: Pick<Review, 'decision'> | null): Exclude<ReviewState, 'none'> {
  if (!review) return 'pending';
  return review.decision === 'needs_more_review' ? 'needs_more_review' : 'reviewed';
}

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
