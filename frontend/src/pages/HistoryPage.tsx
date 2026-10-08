import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { deleteJobs, listJobs } from '@/api/jobs';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { paths } from '@/lib/paths';
import type { JobListResponse } from '@/types/api';
import { FilterBar } from './history/FilterBar';
import { HistoryTable, isActive } from './history/HistoryTable';
import { hasFilters, parseHistoryQuery } from './history/historyQuery';
import { Pagination } from './history/Pagination';
import { VerdictChips } from './history/VerdictChips';
import './HistoryPage.css';

/** 화면설계서: 진행 중 행은 5초 간격으로 갱신 */
const REFRESH_INTERVAL_MS = 5000;

/** SCR-05 분석 이력 (UC-06 조회, UC-07 삭제) */
export function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // 검색·필터·페이지는 주소의 쿼리가 원본이다
  const queryKey = searchParams.toString();
  const query = useMemo(() => parseHistoryQuery(new URLSearchParams(queryKey)), [queryKey]);

  const [list, setList] = useState<JobListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    listJobs(query, controller.signal)
      .then((data) => {
        setList(data);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(getErrorMessage(err));
        setLoading(false);
      });
    return () => controller.abort();
  }, [query, reloadKey]);

  // 진행 중인 행이 있으면 화면 깜빡임 없이 조용히 다시 읽는다
  const hasActive = list?.items.some(isActive) ?? false;
  useEffect(() => {
    if (!hasActive) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      listJobs(query, controller.signal)
        .then(setList)
        .catch(() => {
          // 다음 주기에 다시 시도한다
        });
    }, REFRESH_INTERVAL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [hasActive, query, reloadKey]);

  // 조건이 바뀌면 선택을 비운다
  useEffect(() => setSelected(new Set()), [queryKey]);

  // 삭제 등으로 현재 페이지가 비면 마지막 페이지로 옮긴다
  useEffect(() => {
    if (!list || list.items.length > 0 || list.total === 0 || list.page !== query.page) return;
    const lastPage = Math.ceil(list.total / list.page_size);
    if (query.page > lastPage) updateQuery({ page: String(lastPage) }, true);
    // updateQuery는 매 렌더마다 새로 만들어진다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list, query.page]);

  /** 주소의 쿼리를 고친다. 조건이 바뀌면 1페이지로 돌아간다 */
  function updateQuery(patch: Record<string, string | null>, keepPage = false) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(patch)) {
      if (value === null) next.delete(key);
      else next.set(key, value);
    }
    if (!keepPage) next.delete('page');
    setSearchParams(next);
  }

  function resetFilters() {
    // 페이지당 건수는 조건이 아니므로 남긴다
    const pageSize = searchParams.get('page_size');
    setSearchParams(pageSize ? { page_size: pageSize } : {});
  }

  function toggle(jobId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(jobId)) next.add(jobId);
      return next;
    });
  }

  const items = list?.items ?? [];
  // 조용한 갱신으로 목록에서 빠진 건은 선택에서도 뺀다
  const selectedItems = items.filter((item) => selected.has(item.job_id));
  const selectedActive = selectedItems.filter(isActive).length;

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteJobs(selectedItems.map((item) => item.job_id));
      setSelected(new Set());
      setReloadKey((key) => key + 1);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDeleting(false);
      setConfirming(false);
    }
  }

  const filtered = hasFilters(query);

  return (
    <section className="stack">
      <header className="page-header">
        <h1>분석 이력</h1>
        <p className="muted">지난 분석을 검색해 다시 열어 보고, 필요 없는 건은 삭제합니다.</p>
      </header>

      <FilterBar query={query} onChange={updateQuery} filtered={filtered} onReset={resetFilters} />

      {list && (
        <VerdictChips
          counts={list.counts}
          selected={query.verdict}
          onSelect={(kind) => updateQuery({ verdict: kind ?? null })}
        />
      )}

      {error && (
        <div className="error-box row" role="alert">
          <span>{error}</span>
          <button type="button" className="btn" onClick={() => setReloadKey((key) => key + 1)}>
            다시 시도
          </button>
        </div>
      )}

      {!list && !error && <p className="muted">불러오는 중…</p>}

      {list && (
        <div className="card stack history-card" aria-busy={loading}>
          <div className="history-actions">
            <span className="muted">
              {selectedItems.length > 0 ? `${selectedItems.length}건 선택` : '행을 누르면 해당 분석을 엽니다.'}
            </span>
            <div className="row">
              {/* 일괄 내보내기용 엔드포인트가 아직 정해지지 않아 비활성으로 둔다 (CLAUDE.md 미결정 사항) */}
              <button type="button" className="btn" disabled title="일괄 내보내기 API가 정해지면 활성화됩니다">
                리포트 ZIP 내보내기 (준비 중)
              </button>
              <button
                type="button"
                className="btn"
                disabled={selectedItems.length === 0}
                onClick={() => setConfirming(true)}
              >
                선택 삭제
              </button>
            </div>
          </div>

          {items.length > 0 ? (
            <HistoryTable
              items={items}
              selected={selected}
              onToggle={toggle}
              onToggleAll={(checked) => setSelected(checked ? new Set(items.map((item) => item.job_id)) : new Set())}
            />
          ) : (
            <div className="history-empty">
              {filtered ? (
                <>
                  <p>조건에 맞는 분석 이력이 없습니다.</p>
                  <button type="button" className="btn" onClick={resetFilters}>
                    필터 초기화
                  </button>
                </>
              ) : (
                <>
                  <p>아직 분석 이력이 없습니다.</p>
                  <Link to={paths.upload()} className="btn btn--primary">
                    새 분석
                  </Link>
                </>
              )}
            </div>
          )}

          <Pagination
            page={query.page}
            pageSize={query.page_size}
            total={list.total}
            onPage={(page) => updateQuery({ page: page === 1 ? null : String(page) }, true)}
            onPageSize={(size) => updateQuery({ page_size: String(size) })}
          />
        </div>
      )}

      <p className="caption">
        업로드한 원본 영상은 보관 기간이 지나면 자동으로 삭제되지만, 분석 결과와 특징 데이터는 이력에 남습니다.
      </p>

      <ConfirmDialog
        open={confirming}
        title={`선택한 ${selectedItems.length}건을 삭제할까요?`}
        confirmLabel={deleting ? '삭제하는 중…' : '삭제'}
        cancelLabel="취소"
        busy={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirming(false)}
      >
        삭제한 분석 결과는 되돌릴 수 없습니다.
        {selectedActive > 0 && ` 진행 중인 분석 ${selectedActive}건도 함께 삭제됩니다.`}
      </ConfirmDialog>
    </section>
  );
}
