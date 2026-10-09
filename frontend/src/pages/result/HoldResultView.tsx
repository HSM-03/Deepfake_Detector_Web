import { useState } from 'react';
import { Link } from 'react-router-dom';
import { TriageNotice } from '@/components/common/TriageNotice';
import { paths } from '@/lib/paths';
import type { HoldResult, Review } from '@/types/api';
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
  // 검토 판단을 저장하면 판정 카드의 검토 상태와 검토 칸이 함께 바뀌도록 여기서 들고 있는다
  const [review, setReview] = useState<Review | null>(result.review);

  return (
    <section className="stack result">
      <ResultHeader title="판단 보류 결과" result={result} />
      <VerdictCard result={{ ...result, review }} />
      <div className="result-grid">
        <AxisScores result={result} score={null} gapArrow />
        <HoldConditionCard result={result} />
        <SqiCard sqi={result.sqi} thresholds={result.thresholds} w={result.w} low={false} />
        <RoiBpmCard roiBpm={result.roi_bpm} />
      </div>
      <ReviewPanel jobId={result.job_id} review={review} onSaved={setReview} />
      <ResultActionBar jobId={result.job_id} />
      <p className="caption">
        판단 보류 건은 <Link to={paths.historyHold()}>분석 이력의 '판단 보류' 칩</Link>으로 모아 볼 수 있습니다.
      </p>
      <TriageNotice />
    </section>
  );
}
