import { Link, useParams, useSearchParams } from 'react-router-dom';
import { getJobEvidence, getJobResult } from '@/api/jobs';
import { AsyncBoundary } from '@/components/common/AsyncBoundary';
import { TriageNotice } from '@/components/common/TriageNotice';
import { VerdictBadge } from '@/components/common/VerdictBadge';
import { useAsync } from '@/hooks/useAsync';
import { paths } from '@/lib/paths';
import { ROI_OPTIONS } from '@/lib/roi';
import type { DoneResult, HoldResult, RoiSelector } from '@/types/api';
import { FeatureTab } from './evidence/FeatureTab';
import { ModelTab } from './evidence/ModelTab';
import { RppgTab } from './evidence/RppgTab';
import { SqiTab } from './evidence/SqiTab';
import { ResultActionBar } from './result/ResultActionBar';
import { ResultHeader } from './result/ResultHeader';
import './result/result.css';
import './EvidencePage.css';

const TABS = [
  { key: 'rppg', label: '생체신호 · rPPG' },
  { key: 'model', label: '메인 모델' },
  { key: 'sqi', label: '신호 품질 · SQI' },
  { key: 'features', label: '특징 벡터' },
] as const;

type TabKey = (typeof TABS)[number]['key'];

/**
 * SCR-04 판정 근거 상세 (UC-04)
 * 근거 데이터 외에 임계값·SQI 구성 요소·판정이 필요해 결과(GET …/result)도 같이 읽는다.
 */
export function EvidencePage() {
  const { jobId = '' } = useParams();
  const state = useAsync((signal) => getJobResult(jobId, signal), [jobId]);

  return (
    <AsyncBoundary state={state}>
      {(result) =>
        result.result_type === 'failed' ? (
          <section className="stack">
            <header className="page-header">
              <h1>판정 근거 상세</h1>
            </header>
            <p className="muted">분석 불가로 끝난 작업이라 근거 데이터가 없습니다.</p>
            <div>
              <Link to={paths.result(jobId)} className="btn btn--primary">
                분석 불가 안내 보기
              </Link>
            </div>
          </section>
        ) : (
          <EvidenceView result={result} />
        )
      }
    </AsyncBoundary>
  );
}

function EvidenceView({ result }: { result: DoneResult | HoldResult }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab: TabKey = TABS.find((t) => t.key === searchParams.get('tab'))?.key ?? 'rppg';
  const roi: RoiSelector = ROI_OPTIONS.find((o) => o.value === searchParams.get('roi'))?.value ?? 'all';

  const state = useAsync((signal) => getJobEvidence(result.job_id, roi, signal), [result.job_id, roi]);
  const evidence = state.data;

  /** 탭·ROI는 주소의 쿼리에 둔다(기본값이면 생략) */
  function setParam(key: 'tab' | 'roi', value: string, fallback: string) {
    const next = new URLSearchParams(searchParams);
    if (value === fallback) next.delete(key);
    else next.set(key, value);
    setSearchParams(next, { replace: true });
  }

  function renderTab() {
    if (state.error) {
      return (
        <div className="error-box row" role="alert">
          <span>{state.error}</span>
          <button type="button" className="btn" onClick={state.reload}>
            다시 시도
          </button>
        </div>
      );
    }
    if (!evidence) {
      return (
        <div className="evidence-grid" role="status" aria-label="불러오는 중">
          <div className="skeleton" style={{ height: 300 }} />
          <div className="skeleton" style={{ height: 300 }} />
        </div>
      );
    }
    switch (tab) {
      case 'rppg':
        return <RppgTab evidence={evidence} loading={state.loading} />;
      case 'model':
        return <ModelTab evidence={evidence} result={result} />;
      case 'sqi':
        return <SqiTab result={result} low={evidence.rppg_low_contribution} />;
      case 'features':
        return <FeatureTab evidence={evidence} />;
    }
  }

  return (
    <section className="stack">
      <div className="evidence__head">
        <ResultHeader title="판정 근거 상세" result={result} />
        <VerdictBadge kind={result.verdict} />
      </div>

      {evidence?.rppg_low_contribution && (
        <p className="warn-box">
          <span aria-hidden="true">△ </span>rPPG 축 기여도가 0에 근접합니다(w = {evidence.axis_summary.w.toFixed(2)}).
          본 판정은 사실상 메인 모델 단독 결과입니다.
        </p>
      )}

      <div className="evidence__toolbar">
        <div className="tabs" role="tablist" aria-label="근거 종류">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              className="tab"
              aria-selected={t.key === tab}
              onClick={() => setParam('tab', t.key, 'rppg')}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === 'rppg' && (
          <div className="roi-picker" role="group" aria-label="ROI 선택">
            <span className="roi-picker__label">얼굴 부위(ROI)</span>
            {ROI_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className="btn"
                aria-pressed={option.value === roi}
                onClick={() => setParam('roi', option.value, 'all')}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div role="tabpanel">{renderTab()}</div>

      <ResultActionBar jobId={result.job_id} onEvidencePage />
      <TriageNotice />
    </section>
  );
}
