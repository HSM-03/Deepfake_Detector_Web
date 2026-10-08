import { TriageNotice } from '@/components/common/TriageNotice';
import type { DoneResult } from '@/types/api';
import { AxisScores } from './AxisScores';
import { ResultActionBar } from './ResultActionBar';
import { ResultHeader } from './ResultHeader';
import { RoiBpmCard } from './RoiBpmCard';
import { ScoreFormula } from './ScoreFormula';
import { SqiCard } from './SqiCard';
import { VerdictCard } from './VerdictCard';
import './result.css';

interface Props {
  result: DoneResult;
}

/**
 * SCR-03 분석 결과 요약 (UC-03, UC-05 버튼)
 * 위에서 아래로 결론(판정) → 이유(두 축, 계산) → 근거(신호 품질, 부위별 심박) 순서로 읽힌다.
 * 카드들은 SCR-07에서도 상태만 바꿔 다시 쓴다.
 */
export function ResultSummaryView({ result }: Props) {
  return (
    <section className="stack result">
      <ResultHeader title="분석 결과 요약" result={result} />
      <VerdictCard result={result} />
      <div className="result-grid">
        <AxisScores result={result} score={result.score} />
        <ScoreFormula result={result} />
        <SqiCard sqi={result.sqi} thresholds={result.thresholds} w={result.w} low={result.rppg_low_contribution} />
        <RoiBpmCard roiBpm={result.roi_bpm} />
      </div>
      <ResultActionBar jobId={result.job_id} />
      <TriageNotice />
    </section>
  );
}
