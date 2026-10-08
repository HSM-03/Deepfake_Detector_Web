import { useState, type FormEvent } from 'react';
import { getErrorMessage } from '@/api/client';
import { submitReview } from '@/api/jobs';
import { formatDateTime } from '@/lib/format';
import type { Review, ReviewDecision } from '@/types/api';

interface Props {
  jobId: string;
  /** 이미 기록된 판단. 없으면 입력 폼부터 보여 준다 */
  review: Review | null;
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
export function ReviewPanel({ jobId, review }: Props) {
  const [saved, setSaved] = useState(review);
  const [editing, setEditing] = useState(review === null);
  const [decision, setDecision] = useState<ReviewDecision | null>(review?.decision ?? null);
  const [reason, setReason] = useState(review?.reason ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!decision) return;
    setSaving(true);
    setError(null);
    try {
      setSaved(await submitReview(jobId, { decision, reason: reason.trim() }));
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
    // '추가 검토 필요'로 기록한 건은 이력에서 계속 '재검토'로 남는다
    const done = saved.decision !== 'needs_more_review';
    return (
      <section className="card stack">
        <div className="review__head">
          <h2 className="section-title">검토자 최종 판단</h2>
          <span className={done ? 'review__state review__state--done' : 'review__state'}>
            {done ? '✓ 검토 완료' : '◆ 재검토'}
          </span>
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
        {!saved && <span className="review__state">◆ 재검토</span>}
      </div>
      <p className="muted">
        시스템은 판단을 보류했습니다. 근거를 검토한 뒤 최종 판단을 기록하면 이력의 상태가 '재검토'에서 '검토 완료'로
        바뀝니다.
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
