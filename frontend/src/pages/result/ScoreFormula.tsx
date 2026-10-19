import { InfoTip } from '@/components/common/InfoTip';
import { formatScore } from '@/lib/format';
import { TERMS } from '@/lib/terms';
import type { DoneResult } from '@/types/api';

interface Props {
  result: Pick<DoneResult, 'score' | 'p_model' | 'p_rppg' | 'p_rppg_provisional' | 'w' | 'sqi' | 'thresholds'>;
}

/**
 * SCR-03 ①의 산출식 — S = (1 − w)·P_model + w·P_rppg 에 실제 값을 넣어 보여 주고,
 * 적용된 w가 어디서 나왔는지(α × SQI) 설명한다.
 */
export function ScoreFormula({ result }: Props) {
  const { score, p_model, p_rppg, w, sqi, thresholds: t } = result;
  const f = formatScore;
  const rppgPercent = Math.round(w * 100);

  return (
    <section className="card stack">
      <h2 className="section-title">종합 점수는 이렇게 계산했습니다</h2>
      <p className="lead">두 축의 점수를 비중대로 섞은 값입니다.</p>

      <div className="equation" aria-label={`S = (1 − ${f(w)}) × ${f(p_model)} + ${f(w)} × ${f(p_rppg)} = ${f(score)}`}>
        <div className="equation__group">
          <span className="equation__name">메인 모델 축</span>
          <span className="equation__numbers">
            <b>{f(1 - w)}</b> × <b>{f(p_model)}</b>
          </span>
          <span className="equation__legend">비중 × {TERMS.pModel.label}</span>
        </div>
        <span className="equation__op">+</span>
        <div className="equation__group">
          <span className="equation__name">생체신호 축</span>
          <span className="equation__numbers">
            <b>{f(w)}</b> × <b>{f(p_rppg)}</b>
          </span>
          <span className="equation__legend">비중 × {TERMS.pRppg.label}</span>
        </div>
        <span className="equation__op">=</span>
        <div className="equation__group equation__group--result">
          <span className="equation__name">{TERMS.score.label}</span>
          <span className="equation__numbers">
            <b>{f(score)}</b>
          </span>
          <span className="equation__legend">S</span>
        </div>
      </div>
      <p className="formula">S = (1 − w)·P_model + w·P_rppg</p>
      {result.p_rppg_provisional && (
        <p className="warn-box">
          <span aria-hidden="true">ⓘ </span>P_rppg 분류기 미적용(5단계 예정) — 임시로 메인 모델 값 사용. 그래서 위 식의 S도 사실상 메인 모델 단독 값입니다.
        </p>
      )}

      <div className="stack weight">
        <p className="weight__title">
          {TERMS.w.label} <span className="term">{TERMS.w.term}</span>
          <InfoTip label={TERMS.w.label}>{TERMS.w.help}</InfoTip>
        </p>
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
      </div>
    </section>
  );
}
