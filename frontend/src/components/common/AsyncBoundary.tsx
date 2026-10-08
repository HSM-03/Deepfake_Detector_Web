import type { ReactNode } from 'react';
import type { AsyncState } from '@/hooks/useAsync';

interface Props<T> {
  state: AsyncState<T>;
  children: (data: T) => ReactNode;
}

/** useAsync 결과의 로딩·오류·성공 상태를 나눠 그린다. */
export function AsyncBoundary<T>({ state, children }: Props<T>) {
  if (state.error) {
    return (
      <div className="error-box row" role="alert">
        <span>{state.error}</span>
        <button type="button" className="btn" onClick={state.reload}>
          다시 시도
        </button>
      </div>
    );
  }
  if (state.loading || state.data === null) {
    return <p className="muted">불러오는 중…</p>;
  }
  return <>{children(state.data)}</>;
}
