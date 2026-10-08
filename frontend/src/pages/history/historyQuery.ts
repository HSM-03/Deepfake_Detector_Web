import type { JobListQuery, VerdictKind } from '@/types/api';

/** 페이지당 건수 선택지 (화면설계서 SCR-05 ⑤) */
export const PAGE_SIZES = [10, 20, 50];
const DEFAULT_PAGE_SIZE = PAGE_SIZES[0];

/** 판정 칩 순서 (화면설계서 SCR-05 ③: ■가짜 □진짜 ◆보류 ×불가 ◐진행, 그리고 취소) */
export const VERDICT_KINDS: VerdictKind[] = ['fake', 'real', 'hold', 'failed', 'running', 'canceled'];

export type HistoryQuery = JobListQuery & { page: number; page_size: number };

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function dateParam(value: string | null): string | undefined {
  return value && DATE_PATTERN.test(value) ? value : undefined;
}

/** 주소의 쿼리 → 이력 조회 조건. 알 수 없는 값은 버린다 */
export function parseHistoryQuery(params: URLSearchParams): HistoryQuery {
  const verdict = params.get('verdict');
  const review = params.get('review');
  const sqiMin = params.get('sqi_min');
  const sqiMinValue = Number(sqiMin);
  const page = Number(params.get('page'));
  const pageSize = Number(params.get('page_size'));

  return {
    q: params.get('q')?.trim() || undefined,
    verdict: VERDICT_KINDS.find((kind) => kind === verdict),
    from: dateParam(params.get('from')),
    to: dateParam(params.get('to')),
    sqi_min: sqiMin && sqiMinValue >= 0 && sqiMinValue <= 1 ? sqiMinValue : undefined,
    review: review === 'pending' || review === 'reviewed' ? review : undefined,
    page: Number.isInteger(page) && page >= 1 ? page : 1,
    page_size: PAGE_SIZES.includes(pageSize) ? pageSize : DEFAULT_PAGE_SIZE,
  };
}

/** 검색·필터 조건이 하나라도 걸려 있는지 (빈 상태 문구, [필터 초기화] 표시용) */
export function hasFilters(query: HistoryQuery): boolean {
  return Boolean(query.q || query.verdict || query.from || query.to || query.review) || query.sqi_min !== undefined;
}
