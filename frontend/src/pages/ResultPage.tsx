import { useParams } from 'react-router-dom';
import { getJobResult } from '@/api/jobs';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { useAsync } from '@/hooks/useAsync';
import { HoldResultView } from './result/HoldResultView';
import { ResultSummaryView } from './result/ResultSummaryView';
import { UnanalyzableView } from './result/UnanalyzableView';

/**
 * 결과 경로(/jobs/:jobId/result)의 분기점.
 * GET /api/jobs/{id}/result 의 result_type에 따라 세 화면 중 하나를 그린다.
 *   done → SCR-03 분석 결과 요약 / failed → SCR-06 분석 불가 안내 / hold → SCR-07 판단 보류 결과
 * 한 경로로 묶어 두면 '결과 링크 복사'와 이력 재진입이 판정 종류와 무관하게 같은 주소를 쓴다.
 */
export function ResultPage() {
  const { jobId = '' } = useParams();
  const state = useAsync((signal) => getJobResult(jobId, signal), [jobId]);

  return (
    <AsyncBoundary state={state}>
      {(result) => {
        switch (result.result_type) {
          case 'done':
            return <ResultSummaryView result={result} />;
          case 'failed':
            return <UnanalyzableView result={result} />;
          case 'hold':
            return <HoldResultView result={result} />;
        }
      }}
    </AsyncBoundary>
  );
}
