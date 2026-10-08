import { InfoTip } from '@/components/common/InfoTip';
import { formatScore } from '@/lib/format';
import { TERMS } from '@/lib/terms';
import { scoreZone, VERDICT_META, type ScoreZone } from '@/lib/verdict';
import type { DoneResult, HoldResult, Thresholds } from '@/types/api';
import { ScoreGauge } from './ScoreGauge';

interface Props {
  result: DoneResult | HoldResult;
}

/** 종합 점수 S가 놓인 구간 설명 */
function zoneText(zone: ScoreZone, t: Thresholds): string {
  const text: Record<ScoreZone, string> = {
    real: `진짜 구간 (S ≤ ${formatScore(t.score_real_max)})`,
    boundary: `경계 구간 (${formatScore(t.score_real_max)} < S < ${formatScore(t.score_fake_min)})`,
    fake: `가짜 구간 (S ≥ ${formatScore(t.score_fake_min)})`,
  };
  return text[zone];
}

/**
 * SCR-03 ① 최종 판정 카드 — 화면에서 가장 먼저 읽히는 자리.
 * 판정 라벨과 자연어 해석, 종합 점수 S와 그 위치를 보여 준다. (산출식은 바로 아래 ScoreFormula)
 * SCR-07에서는 보류 변형으로 그린다: '판단 보류 · 재검토 필요', S는 '—'.
 */
export function VerdictCard({ result }: Props) {
  const meta = VERDICT_META[result.verdict];
  const t = result.thresholds;

  return (
    <section className={`verdict-hero verdict-hero--${result.verdict}`} aria-label="최종 판정">
      <div className="verdict-hero__main">
        <p className="verdict-hero__eyebrow">최종 판정</p>
        <p className="verdict-hero__label">
          <span aria-hidden="true">{meta.symbol}</span>
          {meta.label}
          {result.result_type === 'hold' && <small>재검토 필요</small>}
        </p>
        <p className="verdict-hero__text">{result.interpretation}</p>
        {result.result_type === 'done' && result.rppg_low_contribution && (
          <p className="verdict-hero__flag">
            <span aria-hidden="true">△ </span>rPPG 기여도 낮음 — 메인 모델 중심 판정
          </p>
        )}
      </div>

      <div className="verdict-hero__score">
        <p className="verdict-hero__eyebrow">
          {TERMS.score.label} {TERMS.score.term}
          <InfoTip label={TERMS.score.label}>{TERMS.score.help}</InfoTip>
        </p>
        {result.result_type === 'hold' ? (
          <>
            <p className="verdict-hero__value verdict-hero__value--empty">—</p>
            <ScoreGauge value={null} thresholds={t} />
            <p className="verdict-hero__zone">두 축이 상충해 점수를 내지 않았습니다</p>
          </>
        ) : (
          <>
            <p className="verdict-hero__value">{formatScore(result.score)}</p>
            <ScoreGauge value={result.score} thresholds={t} />
            <p className="verdict-hero__zone">{zoneText(scoreZone(result.score, t), t)}</p>
          </>
        )}
      </div>
    </section>
  );
}
