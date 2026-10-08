import type { ReactNode } from 'react';

interface Props {
  /** 쉬운 말 제목 */
  title: string;
  /** 제목 옆에 붙이는 기술 용어 (예: Welch 파워 스펙트럼) */
  term?: string;
  /** 읽는 법 — 정상이면 어떻게 보이는지 한 줄 */
  hint?: string;
  /** 차트 아래 보조 설명 (수치 요약 등) */
  caption?: ReactNode;
  /** 불러오는 중이면 차트 자리에 스켈레톤을 그린다 */
  loading: boolean;
  /** 차트(=스켈레톤) 높이 px */
  height: number;
  children: ReactNode;
}

/** SCR-04 차트 한 칸: 제목 + 읽는 법 + 차트 + 설명 */
export function ChartCard({ title, term, hint, caption, loading, height, children }: Props) {
  return (
    <section className="card stack">
      <h3 className="section-title">
        {title} {term && <span className="term">{term}</span>}
      </h3>
      {hint && (
        <p className="read-hint">
          <strong>읽는 법</strong>
          <span>{hint}</span>
        </p>
      )}
      {loading ? <div className="skeleton" style={{ height }} role="status" aria-label="불러오는 중" /> : children}
      {caption && !loading && <p className="caption">{caption}</p>}
    </section>
  );
}
