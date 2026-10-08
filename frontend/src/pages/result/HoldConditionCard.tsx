import { formatScore } from '@/lib/format';
import type { HoldResult } from '@/types/api';

interface Props {
  result: Pick<HoldResult, 'p_model' | 'p_rppg' | 'axis_gap' | 'sqi' | 'thresholds'>;
}

/** SCR-07 ①의 보류 조건 — SQI ≥ 하한 AND |P_model − P_rppg| ≥ 상충 임계 를 실제 수치로 보여 준다 */
export function HoldConditionCard({ result }: Props) {
  const { p_model, p_rppg, axis_gap, sqi, thresholds: t } = result;
  const f = formatScore;
  const conditions = [
    {
      met: sqi.value >= t.sqi_min,
      title: '신호 품질은 충분합니다',
      detail: `SQI ${f(sqi.value)} ≥ 하한 ${f(t.sqi_min)}`,
    },
    {
      met: axis_gap >= t.conflict_gap,
      title: '두 축의 판단이 크게 다릅니다',
      detail: `|${f(p_model)} − ${f(p_rppg)}| = ${f(axis_gap)} ≥ 상충 임계 ${f(t.conflict_gap)}`,
    },
  ];

  return (
    <section className="card stack">
      <h2 className="section-title">판단을 보류한 이유</h2>
      <p className="lead">아래 두 조건이 함께 성립하면 한쪽을 임의로 택하지 않고 보류합니다.</p>
      <ol className="hold-conditions">
        {conditions.map((condition) => (
          <li key={condition.title}>
            <span className="hold-conditions__mark" role="img" aria-label={condition.met ? '성립' : '불성립'}>
              {condition.met ? '✓' : '×'}
            </span>
            <span>
              <strong>{condition.title}</strong>
              <span className="hold-conditions__detail">{condition.detail}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="formula">보류 조건: SQI ≥ 하한 AND |P_model − P_rppg| ≥ 상충 임계</p>
      <p className="caption">신호가 나빠서가 아니라, 믿을 만한 두 근거가 서로 반대를 가리켜서 사람의 검토가 필요한 경우입니다.</p>
    </section>
  );
}
