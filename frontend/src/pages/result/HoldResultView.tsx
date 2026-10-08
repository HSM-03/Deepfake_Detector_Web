import { Link } from 'react-router-dom';
import { TriageNotice } from '@/components/common/TriageNotice';
import { paths } from '@/lib/paths';
import type { HoldResult } from '@/types/api';
import { AxisScores } from './AxisScores';
import { HoldConditionCard } from './HoldConditionCard';
import { ResultActionBar } from './ResultActionBar';
import { ResultHeader } from './ResultHeader';
import { ReviewPanel } from './ReviewPanel';
import { RoiBpmCard } from './RoiBpmCard';
import { SqiCard } from './SqiCard';
import { VerdictCard } from './VerdictCard';
import './result.css';

interface Props {
  result: HoldResult;
}

/** SCR-07 판단 보류 결과 (UC-17, UC-12 확장) — SCR-03과 같은 레이아웃의 상태 변형 */
export function HoldResultView({ result }: Props) {
  return (
    <section className="stack result">
      <ResultHeader title="판단 보류 결과" result={result} />
      <VerdictCard result={result} />
      <div className="result-grid">
        <AxisScores result={result} score={null} gapArrow />
        <HoldConditionCard result={result} />
        <SqiCard sqi={result.sqi} thresholds={result.thresholds} w={result.w} low={false} />
        <RoiBpmCard roiBpm={result.roi_bpm} />
      </div>
      <ReviewPanel jobId={result.job_id} review={result.review} />
      <ResultActionBar jobId={result.job_id} />
      <p className="caption">
        판단 보류 건은 <Link to={paths.historyPendingReview()}>분석 이력의 '재검토' 필터</Link>로 모아 볼 수 있습니다.
      </p>
      <TriageNotice />
    </section>
  );
}
