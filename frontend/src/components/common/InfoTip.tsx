import type { ReactNode } from 'react';

interface Props {
  /** 무엇에 대한 설명인지 (스크린 리더용, 예: '신호 품질') */
  label: string;
  children: ReactNode;
}

/** 용어 설명 말풍선. ? 버튼에 마우스를 올리거나 포커스를 주면 보인다 */
export function InfoTip({ label, children }: Props) {
  return (
    <span className="info-tip">
      <button type="button" className="info-tip__button" aria-label={`${label} 설명`}>
        ?
      </button>
      <span className="info-tip__bubble" role="tooltip">
        {children}
      </span>
    </span>
  );
}
