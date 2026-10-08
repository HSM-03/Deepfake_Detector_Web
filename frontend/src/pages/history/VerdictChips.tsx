import { VERDICT_META } from '@/lib/verdict';
import type { VerdictKind } from '@/types/api';
import { VERDICT_KINDS } from './historyQuery';

interface Props {
  /** 판정별 건수 (검색어·기간 등은 반영, 판정 필터는 미반영) */
  counts: Record<VerdictKind, number>;
  selected: VerdictKind | undefined;
  /** 같은 칩을 다시 누르면 undefined(해제) */
  onSelect: (kind: VerdictKind | undefined) => void;
}

/** SCR-05 ② 판정 칩 — 판정별 건수 + 필터 토글 */
export function VerdictChips({ counts, selected, onSelect }: Props) {
  const total = VERDICT_KINDS.reduce((sum, kind) => sum + counts[kind], 0);
  // '취소됨'은 해당 건이 있을 때만 보여 준다
  const kinds = VERDICT_KINDS.filter((kind) => kind !== 'canceled' || counts.canceled > 0 || selected === 'canceled');

  return (
    <div className="chips" role="group" aria-label="판정 필터">
      <button type="button" className="chip" aria-pressed={selected === undefined} onClick={() => onSelect(undefined)}>
        전체 <strong>{total}</strong>
      </button>
      {kinds.map((kind) => (
        <button
          key={kind}
          type="button"
          className="chip"
          aria-pressed={selected === kind}
          onClick={() => onSelect(selected === kind ? undefined : kind)}
        >
          <span aria-hidden="true">{VERDICT_META[kind].symbol}</span>
          {VERDICT_META[kind].label} <strong>{counts[kind]}</strong>
        </button>
      ))}
    </div>
  );
}
