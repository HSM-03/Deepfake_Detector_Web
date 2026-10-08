import type { ReactNode } from 'react';

/** 화면 위쪽에 잠깐 띄우는 알림 (SCR-02 완료 토스트) */
export function Toast({ children }: { children: ReactNode }) {
  return (
    <div className="toast" role="status">
      {children}
    </div>
  );
}
