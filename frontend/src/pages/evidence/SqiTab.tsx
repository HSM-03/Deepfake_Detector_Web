import { InfoTip } from '@/components/common/InfoTip';
import { formatScore } from '@/lib/format';
import { TERMS } from '@/lib/terms';
import type { DoneResult } from '@/types/api';
import { SqiCard } from '../result/SqiCard';

interface Props {
  result: Pick<DoneResult, 'sqi' | 'w' | 'thresholds'>;
  /** SQI가 하한 미만이라 rPPG 기여도가 낮은 건 */
  low: boolean;
}

/** SCR-04 SQI 탭 — 신호 품질과 구성 요소, 그리고 신호 품질이 두 축의 비중을 어떻게 정했는지 */
export function SqiTab({ result, low }: Props) {
  const { sqi, w, thresholds: t } = result;
  const f = formatScore;
  const rppgPercent = Math.round(w * 100);

  return (
    <div className="evidence-grid">
      <SqiCard sqi={sqi} thresholds={t} w={w} low={low} />

      <section className="card stack">
        <h3 className="section-title">
          {TERMS.w.label} <span className="term">{TERMS.w.term}</span>
          <InfoTip label={TERMS.w.label}>{TERMS.w.help}</InfoTip>
        </h3>
        <p className="lead">신호 품질이 두 축을 어떤 비중으로 섞을지 정합니다.</p>
        <div className="weight__bar" role="img" aria-label={`메인 모델 ${100 - rppgPercent}%, 생체신호 ${rppgPercent}%`}>
          <div className="weight__model" style={{ flexGrow: 1 - w }} />
          <div className="weight__rppg" style={{ flexGrow: w }} />
        </div>
        <div className="weight__legend">
          <span>메인 모델 {100 - rppgPercent}%</span>
          <span>생체신호 {rppgPercent}%</span>
        </div>
        <p className="formula">
          w = α × SQI = {f(t.alpha)} × {f(sqi.value)} = {f(w)}
        </p>
        <p className="formula">S = (1 − w)·P_model + w·P_rppg</p>
        <p className="read-hint">
          <strong>읽는 법</strong>
          <span>신호 품질이 낮을수록 w가 0에 가까워져 생체신호 축의 영향이 줄고, 판정은 메인 모델 쪽으로 기웁니다.</span>
        </p>
      </section>
    </div>
  );
}
