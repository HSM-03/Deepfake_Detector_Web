import { useCallback, useEffect, useState } from 'react';
import { getErrorMessage } from '@/api/client';

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** 다시 불러오기 */
  reload: () => void;
}

/**
 * 비동기 조회 훅. deps가 바뀌면 이전 요청을 취소하고 다시 부른다.
 * 예) const { data, loading, error } = useAsync((signal) => getJobResult(jobId, signal), [jobId]);
 */
export function useAsync<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fn(controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setData(value);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(getErrorMessage(err));
        setLoading(false);
      });
    return () => controller.abort();
    // fn은 매 렌더마다 새로 만들어지므로 deps로만 재실행을 제어한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
