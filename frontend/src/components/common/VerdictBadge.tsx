import { VERDICT_META } from '@/lib/verdict';
import type { VerdictKind } from '@/types/api';

interface Props {
  kind: VerdictKind;
}

/** 판정 배지: 기호 + 텍스트 병기 (□진짜 ■가짜 ◆판단 보류 ×분석 불가 ◐진행 중) */
export function VerdictBadge({ kind }: Props) {
  const meta = VERDICT_META[kind];
  return (
    <span className={`verdict-badge verdict-badge--${kind}`}>
      <span aria-hidden="true">{meta.symbol}</span>
      {meta.label}
    </span>
  );
}
