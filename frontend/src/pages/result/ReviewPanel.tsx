import { useState, type FormEvent } from 'react';
import { getErrorMessage } from '@/api/client';
import { submitReview } from '@/api/jobs';
import { formatDateTime } from '@/lib/format';
import { REVIEW_STATE_META, reviewStateOf } from '@/lib/verdict';
import type { Review, ReviewDecision } from '@/types/api';

interface Props {
  jobId: string;
  /** 기록된 판단. 없으면 입력 폼부터 보여 준다 */
  review: Review | null;
  /** 저장에 성공하면 새 판단을 알린다 (판정 카드의 검토 상태도 함께 바뀌게) */
  onSaved: (review: Review) => void;
}

/** 검토 상태 배지: ◆ 검토 대기 / ◆ 추가 검토 필요 / ✓ 검토 완료 */
function ReviewStateBadge({ review }: { review: Review | null }) {
  const state = reviewStateOf(review);
  const meta = REVIEW_STATE_META[state];
  return (
    <span className={state === 'reviewed' ? 'review__state review__state--done' : 'review__state'}>
      {meta.symbol} {meta.label}
    </span>
  );
}

const DECISIONS: Array<{ value: ReviewDecision; label: string }> = [
  { value: 'real', label: '진짜' },
  { value: 'fake', label: '가짜' },
  { value: 'needs_more_review', label: '추가 검토 필요' },
];

const decisionLabel = (decision: ReviewDecision) => DECISIONS.find((d) => d.value === decision)?.label ?? decision;

/**
 * SCR-07 ③ 검토자 최종 판단 기록 — 진짜 / 가짜 / 추가 검토 필요 + 사유 메모.
 * 기록 후에는 읽기 전용 카드와 [수정]으로 바뀐다.
 */
export function ReviewPanel({ jobId, review: saved, onSaved }: Props) {
  const [editing, setEditing] = useState(saved === null);
  const [decision, setDecision] = useState<ReviewDecision | null>(saved?.decision ?? null);
  const [reason, setReason] = useState(saved?.reason ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!decision) return;
    setSaving(true);
    setError(null);
    try {
      onSaved(await submitReview(jobId, { decision, reason: reason.trim() }));
      setEditing(false);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  function handleCancelEdit() {
    if (!saved) return;
    setDecision(saved.decision);
    setReason(saved.reason);
    setError(null);
    setEditing(false);
  }

  if (saved && !editing) {
    return (
      <section className="card stack">
        <div className="review__head">
          <h2 className="section-title">검토자 최종 판단</h2>
          <ReviewStateBadge review={saved} />
        </div>
        <dl className="review__summary">
          <div>
            <dt>검토자 판단</dt>
            <dd>
              <strong>{decisionLabel(saved.decision)}</strong>
            </dd>
          </div>
          <div>
            <dt>기록 일시</dt>
            <dd>{formatDateTime(saved.reviewed_at)}</dd>
          </div>
          <div>
            <dt>사유</dt>
            <dd>{saved.reason || <span className="muted">적지 않음</span>}</dd>
          </div>
        </dl>
        <div>
          <button type="button" className="btn" onClick={() => setEditing(true)}>
            수정
          </button>
        </div>
      </section>
    );
  }

  return (
    <form className="card stack" onSubmit={handleSubmit}>
      <div className="review__head">
        <h2 className="section-title">검토자 최종 판단 기록</h2>
        <ReviewStateBadge review={saved} />
      </div>
      <p className="muted">
        시스템은 판단을 보류했습니다. 근거를 검토한 뒤 진짜·가짜로 기록하면 이력의 상태가 '검토 완료'로 바뀝니다. 결론을
        내리기 어려우면 '추가 검토 필요'로 기록해 두세요.
      </p>
      <fieldset className="review__choices" disabled={saving}>
        <legend>판단</legend>
        {DECISIONS.map((d) => (
          <label key={d.value} className="row">
            <input
              type="radio"
              name="decision"
              checked={decision === d.value}
              onChange={() => setDecision(d.value)}
            />
            {d.label}
          </label>
        ))}
      </fieldset>
      <label className="review__reason">
        사유 메모
        <textarea
          className="input"
          rows={3}
          placeholder="예: 원본 출처 확인 결과 합성본으로 판명"
          value={reason}
          disabled={saving}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button type="submit" className="btn btn--primary" disabled={!decision || saving}>
          {saving ? '저장 중…' : '판단 저장'}
        </button>
        {saved && (
          <button type="button" className="btn" disabled={saving} onClick={handleCancelEdit}>
            수정 취소
          </button>
        )}
        {!decision && <span className="caption">판단을 고르면 저장할 수 있습니다.</span>}
      </div>
    </form>
  );
}
