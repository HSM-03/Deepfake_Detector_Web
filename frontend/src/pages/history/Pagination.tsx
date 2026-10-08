import { PAGE_SIZES } from './historyQuery';

interface Props {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  onPageSize: (pageSize: number) => void;
}

/** 현재 페이지 앞뒤로 보여 줄 번호 개수 */
const WINDOW = 5;

/** SCR-05 ⑤ 페이지네이션 — 페이지당 10/20/50건 */
export function Pagination({ page, pageSize, total, onPage, onPageSize }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = Math.max(1, Math.min(page - Math.floor(WINDOW / 2), totalPages - WINDOW + 1));
  const pages = Array.from({ length: Math.min(WINDOW, totalPages) }, (_, i) => first + i);
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="pagination">
      <span className="muted">
        {start}–{end} / 총 {total}건
      </span>
      <nav className="pagination__pages" aria-label="페이지">
        <button type="button" className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          이전
        </button>
        {pages.map((p) => (
          <button
            key={p}
            type="button"
            className="btn"
            aria-current={p === page ? 'page' : undefined}
            onClick={() => onPage(p)}
          >
            {p}
          </button>
        ))}
        <button type="button" className="btn" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          다음
        </button>
      </nav>
      <label className="row">
        <span className="muted">페이지당</span>
        <select className="input pagination__size" value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))}>
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}건
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
