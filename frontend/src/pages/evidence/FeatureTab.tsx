import { formatScore } from '@/lib/format';
import { TERMS } from '@/lib/terms';
import type { EvidenceResponse, FeatureJudgement, FeatureKey } from '@/types/api';

interface Props {
  evidence: EvidenceResponse;
}

/** 판단: ○ / △ / × (기호와 글자를 같이 쓴다) */
const JUDGEMENT: Record<FeatureJudgement, { symbol: string; label: string }> = {
  ok: { symbol: '○', label: '기준 충족' },
  warn: { symbol: '△', label: '주의' },
  bad: { symbol: '×', label: '기준 벗어남' },
};

/** 특징이 무엇을 보는지 쉬운 말로 */
const FEATURE_MEANING: Record<FeatureKey, string> = {
  hr_in_range: '추정 심박수가 사람에게서 나올 수 있는 범위인지',
  snr: '심박 봉우리가 잡음보다 얼마나 또렷한지',
  spectral_entropy: '신호가 한 주파수에 모여 있는지 (낮을수록 규칙적)',
  roi_bpm_std: '얼굴 부위들의 심박수가 서로 같은지',
  phase_consistency: '얼굴 부위들의 맥파가 같은 박자로 움직이는지',
  window_bpm_var: '시간이 지나도 심박수가 안정적인지',
};

/** SCR-04 ⑥ 특징 표(특징 6개의 측정값 / 실제 얼굴 기준 / 판단)와 두 축 대조 요약 */
export function FeatureTab({ evidence }: Props) {
  const { features, axis_summary: axis } = evidence;
  const f = formatScore;
  const hasConflictSource = features.some((feature) => feature.conflict_source);
  const summary = [
    { ...TERMS.pModel, value: axis.p_model },
    { ...TERMS.pRppg, value: axis.p_rppg, note: evidence.p_rppg_provisional ? '임시: 메인 모델 값' : undefined },
    { ...TERMS.sqi, value: axis.sqi },
    { ...TERMS.w, value: axis.w },
  ];

  return (
    <div className="stack">
      <section className="card stack">
        <h3 className="section-title">
          생체신호 특징 6가지 <span className="term">rPPG 특징 벡터</span>
        </h3>
        <p className="lead">심박 신호가 실제 사람다운지 따지는 여섯 가지 기준입니다. 이 값들로 생체신호 축의 점수가 정해집니다.</p>
        {hasConflictSource && (
          <p className="warn-box">
            <span aria-hidden="true">◆ </span>'상충 요인'으로 표시한 특징이 생체신호 축을 가짜 쪽으로 끌어, 메인 모델과의
            상충을 만들었습니다.
          </p>
        )}
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">특징</th>
              <th scope="col">측정값</th>
              {/* 지금 기준값은 신호가 좋았던 영상 10편으로 잡은 임시값이다(docs/backend-plan.md 4-3). 5단계에서 재산출하면 바꾼다 */}
              <th scope="col">임시 기준</th>
              <th scope="col">판단</th>
            </tr>
          </thead>
          <tbody>
            {features.map((feature) => (
              <tr key={feature.key} className={feature.conflict_source ? 'feature-row--conflict' : undefined}>
                <th scope="row">
                  {feature.label}
                  {feature.conflict_source && <span className="feature-row__tag">◆ 상충 요인</span>}
                  <small className="feature-row__meaning">{FEATURE_MEANING[feature.key]}</small>
                </th>
                <td className="feature-row__value">{feature.display}</td>
                <td>{feature.reference}</td>
                <td>
                  <span className={`feature-judgement feature-judgement--${feature.judgement}`}>
                    <span aria-hidden="true">{JUDGEMENT[feature.judgement].symbol}</span>
                    {JUDGEMENT[feature.judgement].label}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="caption">
          임시 기준입니다 — 신호가 좋았던 영상 10편으로 잡았고, 5단계에서 학습용 진짜 영상으로 다시 산출합니다.
        </p>
      </section>

      <section className="card stack">
        <h3 className="section-title">두 축 대조 요약</h3>
        <dl className="axis-summary">
          {summary.map((item) => (
            <div key={item.term}>
              <dt>
                {item.label} <span className="term">{item.term}</span>
              </dt>
              <dd>
                {f(item.value)}
                {'note' in item && item.note && <small className="axis-summary__note"> ({item.note})</small>}
              </dd>
            </div>
          ))}
        </dl>
        <p>{axis.text}</p>
        {evidence.p_rppg_provisional && (
          <p className="warn-box">
            <span aria-hidden="true">ⓘ </span>P_rppg 분류기 미적용(5단계 예정) — 임시로 메인 모델 값 사용. 그래서 종합 점수 S도 사실상 메인 모델 단독 값입니다.
          </p>
        )}
      </section>
    </div>
  );
}
