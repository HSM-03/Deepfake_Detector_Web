import { useEffect, useState, type FormEvent } from 'react';
import { REVIEW_STATE_META } from '@/lib/verdict';
import type { HistoryQuery } from './historyQuery';

interface Props {
  query: HistoryQuery;
  /** 값이 null이면 그 조건을 지운다 */
  onChange: (patch: Record<string, string | null>) => void;
  /** 조건이 걸려 있을 때만 [필터 초기화]를 켠다 */
  filtered: boolean;
  onReset: () => void;
}

/** SCR-05 ① 검색·필터 바 — 통합 검색, 기간, SQI 하한, 검토 상태. 값은 주소의 쿼리에 반영된다 */
export function FilterBar({ query, onChange, filtered, onReset }: Props) {
  const [keyword, setKeyword] = useState(query.q ?? '');

  // 뒤로 가기·초기화로 주소가 바뀌면 입력란도 맞춘다
  useEffect(() => setKeyword(query.q ?? ''), [query.q]);

  function handleSearch(event: FormEvent) {
    event.preventDefault();
    onChange({ q: keyword.trim() || null });
  }

  return (
    <div className="card history-filter">
      <form className="history-filter__search" role="search" onSubmit={handleSearch}>
        <input
          type="search"
          className="input"
          placeholder="파일명·작업 ID·메모 검색"
          aria-label="파일명·작업 ID·메모 검색"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <button type="submit" className="btn">
          검색
        </button>
      </form>

      <label className="history-filter__field">
        기간
        <span className="row">
          <input
            type="date"
            className="input"
            aria-label="기간 시작"
            value={query.from ?? ''}
            max={query.to}
            onChange={(e) => onChange({ from: e.target.value || null })}
          />
          ~
          <input
            type="date"
            className="input"
            aria-label="기간 끝"
            value={query.to ?? ''}
            min={query.from}
            onChange={(e) => onChange({ to: e.target.value || null })}
          />
        </span>
      </label>

      <label className="history-filter__field">
        SQI 하한
        <select
          className="input"
          value={query.sqi_min === undefined ? '' : String(query.sqi_min)}
          onChange={(e) => onChange({ sqi_min: e.target.value || null })}
        >
          <option value="">전체</option>
          {/* 주소로 직접 넣은 값도 선택 상태로 보이게 한다 */}
          {[...new Set(['0.3', '0.5', '0.7', ...(query.sqi_min === undefined ? [] : [String(query.sqi_min)])])]
            .sort()
            .map((value) => (
              <option key={value} value={value}>
                {value} 이상
              </option>
            ))}
        </select>
      </label>

      <label className="history-filter__field">
        검토 상태
        <select className="input" value={query.review ?? ''} onChange={(e) => onChange({ review: e.target.value || null })}>
          <option value="">전체</option>
          {(Object.keys(REVIEW_STATE_META) as Array<keyof typeof REVIEW_STATE_META>).map((state) => (
            <option key={state} value={state}>
              {REVIEW_STATE_META[state].label}
            </option>
          ))}
        </select>
      </label>

      <button type="button" className="btn" disabled={!filtered} onClick={onReset}>
        필터 초기화
      </button>
    </div>
  );
}
