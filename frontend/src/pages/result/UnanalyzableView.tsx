import { Link } from 'react-router-dom';
import { VerdictBadge } from '@/components/common/VerdictBadge';
import { paths } from '@/lib/paths';
import { STAGE_COUNT, STAGE_LABEL } from '@/lib/stages';
import type { FailedResult } from '@/types/api';
import { ResultHeader } from './ResultHeader';
import './result.css';

interface Props {
  result: FailedResult;
}

/** SCR-06 분석 불가 안내 (UC-16, UC-08 확장) */
export function UnanalyzableView({ result }: Props) {
  const { failure } = result;
  return (
    <section className="stack result">
      <ResultHeader title="분석 불가 안내" result={result} />

      <div className="card failure-head">
        <span className="failure-head__icon" aria-hidden="true">
          ×
        </span>
        <div>
          <div className="row">
            <VerdictBadge kind="failed" />
            <span className="muted">
              {STAGE_COUNT}단계 중 {failure.stopped_stage_index}단계({STAGE_LABEL[failure.stopped_stage]})에서 중단 ·{' '}
              {failure.stopped_stage_index}/{STAGE_COUNT}
            </span>
          </div>
          <h2 className="failure-head__title">{failure.title}</h2>
        </div>
      </div>

      <div className="result-grid result-grid--even">
        <section className="card stack">
          <h2 className="section-title">중단 사유 상세</h2>
          <p className="lead">분석에 필요한 기준과 이 영상의 측정값입니다.</p>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">확인 항목</th>
                <th scope="col">측정값</th>
                <th scope="col">기준</th>
                <th scope="col">결과</th>
              </tr>
            </thead>
            <tbody>
              {failure.checks.map((check) => (
                <tr key={check.label} className={check.passed ? undefined : 'failure-check--failed'}>
                  <th scope="row">{check.label}</th>
                  <td>{check.measured}</td>
                  <td>{check.criterion}</td>
                  <td>{check.passed ? '✓ 충족' : '× 미달'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card stack">
          <h2 className="section-title">해결 방법</h2>
          <p className="lead">아래 조건에 맞는 영상으로 다시 시도해 주세요.</p>
          <ol className="failure-suggestions">
            {failure.suggestions.map((suggestion) => (
              <li key={suggestion}>{suggestion}</li>
            ))}
          </ol>
        </section>
      </div>

      <div className="row">
        <Link to={paths.upload()} className="btn btn--primary">
          다른 영상 업로드
        </Link>
        <Link to={paths.history()} className="btn">
          이력으로
        </Link>
      </div>
      <p className="caption">분석 불가 건도 이력에 '분석 불가' 상태로 남아, 이 안내를 다시 볼 수 있습니다.</p>
    </section>
  );
}
