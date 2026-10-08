import { Link, useNavigate } from 'react-router-dom';
import { ProgressBar } from '@/components/common/ProgressBar';
import { VerdictBadge } from '@/components/common/VerdictBadge';
import { formatDateTime, formatScore } from '@/lib/format';
import { pathForJob } from '@/lib/paths';
import { verdictKindOf } from '@/lib/verdict';
import type { JobListItem } from '@/types/api';

interface Props {
  items: JobListItem[];
  selected: Set<string>;
  onToggle: (jobId: string) => void;
  /** 이 페이지 전체 선택·해제 */
  onToggleAll: (checked: boolean) => void;
}

const score = (value: number | null) => (value === null ? '—' : formatScore(value));

export const isActive = (item: JobListItem) => item.state === 'queued' || item.state === 'running';

function statusText(item: JobListItem): string {
  if (isActive(item)) return `진행 중 ${item.progress}%`;
  if (item.state === 'failed') return '분석 불가';
  if (item.state === 'canceled') return '취소됨';
  if (item.review_state === 'pending') return '재검토';
  if (item.review_state === 'reviewed') return '검토 완료';
  return '완료';
}

/** SCR-05 ③·④ 이력 테이블 — 행을 누르면 상태에 맞는 화면(SCR-02/03/06/07)으로 간다 */
export function HistoryTable({ items, selected, onToggle, onToggleAll }: Props) {
  const navigate = useNavigate();
  const allSelected = items.length > 0 && items.every((item) => selected.has(item.job_id));

  return (
    <table className="data-table history-table">
      <thead>
        <tr>
          <th scope="col">
            <input
              type="checkbox"
              aria-label="이 페이지 전체 선택"
              checked={allSelected}
              onChange={(e) => onToggleAll(e.target.checked)}
            />
          </th>
          <th scope="col">작업 ID</th>
          <th scope="col">파일명</th>
          <th scope="col">일시</th>
          <th scope="col">판정</th>
          <th scope="col" className="num">
            S
          </th>
          <th scope="col" className="num">
            P_model
          </th>
          <th scope="col" className="num">
            P_rppg
          </th>
          <th scope="col" className="num">
            SQI
          </th>
          <th scope="col">상태</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => {
          const to = pathForJob(item.job_id, item.state);
          return (
            <tr key={item.job_id} className="history-table__row" onClick={() => navigate(to)}>
              {/* 체크박스 칸은 눌러도 이동하지 않는다 */}
              <td onClick={(e) => e.stopPropagation()}>
                <input
                  type="checkbox"
                  aria-label={`${item.job_id} 선택`}
                  checked={selected.has(item.job_id)}
                  onChange={() => onToggle(item.job_id)}
                />
              </td>
              <td>
                {/* 키보드로도 이동할 수 있게 작업 ID는 실제 링크로 둔다 */}
                <Link to={to} onClick={(e) => e.stopPropagation()}>
                  <code>{item.job_id}</code>
                </Link>
              </td>
              <td className="history-table__file">
                <span title={item.filename}>{item.filename}</span>
                {item.memo && (
                  <small className="muted" title={item.memo}>
                    {item.memo}
                  </small>
                )}
              </td>
              <td className="history-table__date">{formatDateTime(item.created_at)}</td>
              <td>
                <VerdictBadge kind={verdictKindOf(item)} />
              </td>
              <td className="num">{score(item.score)}</td>
              <td className="num">{score(item.p_model)}</td>
              <td className="num">{score(item.p_rppg)}</td>
              <td className="num">{score(item.sqi)}</td>
              <td className="history-table__status">
                {statusText(item)}
                {isActive(item) && <ProgressBar value={item.progress} label={`${item.job_id} 진행률`} />}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
