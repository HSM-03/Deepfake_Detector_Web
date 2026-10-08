import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { getErrorMessage, getErrorStatus } from '@/api/client';
import { deleteJob, getJobStatus } from '@/api/jobs';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { ProgressBar } from '@/components/common/ProgressBar';
import { Toast } from '@/components/common/Toast';
import { VerdictBadge } from '@/components/common/VerdictBadge';
import { formatClock, formatDateTime, formatEta } from '@/lib/format';
import { paths } from '@/lib/paths';
import type { JobState, JobStatusResponse, ResultType, VerdictKind } from '@/types/api';
import { StageStepper } from './progress/StageStepper';
import './ProgressPage.css';

/** 화면설계서: GET /api/jobs/{id}/status 를 2초 간격으로 폴링 */
const POLL_INTERVAL_MS = 2000;
/** 완료 토스트를 보여 준 뒤 결과 화면으로 넘어가기까지의 시간 */
const REDIRECT_DELAY_MS = 1500;

const TOAST_TEXT: Record<ResultType, string> = {
  done: '분석이 완료되었습니다. 결과 화면으로 이동합니다.',
  failed: '분석을 계속할 수 없어 중단했습니다. 안내 화면으로 이동합니다.',
  hold: '두 축의 판단이 상충해 판단을 보류했습니다. 결과 화면으로 이동합니다.',
};

/** 헤더에 보여 줄 상태 배지. 판정이 난 상태(done·hold)는 결과 화면에서 보여 주므로 없다 */
const STATE_BADGE: Partial<Record<JobState, VerdictKind>> = {
  queued: 'running',
  running: 'running',
  failed: 'failed',
  canceled: 'canceled',
};

/** SCR-02 분석 진행 상태 (UC-02) */
export function ProgressPage() {
  const { jobId = '' } = useParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** 작업이 없어 더 조회하지 않는 상태 (404) */
  const [missing, setMissing] = useState(false);
  /** 이 화면을 보는 중에 분석이 끝나면 토스트를 띄운다 */
  const [finished, setFinished] = useState<ResultType | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    // 이미 끝난 작업의 주소로 들어온 경우에는 토스트 없이 바로 결과 화면으로 보낸다
    let watched = false;

    setStatus(null);
    setError(null);
    setMissing(false);
    setFinished(null);

    async function poll() {
      try {
        const next = await getJobStatus(jobId);
        if (stopped) return;
        setStatus(next);
        setError(null);
        if (next.result_type !== null) {
          // done → SCR-03, failed → SCR-06, hold → SCR-07 (결과 경로에서 분기)
          const goResult = () => navigate(paths.result(jobId), { replace: true });
          if (!watched) return goResult();
          setFinished(next.result_type);
          timer = window.setTimeout(goResult, REDIRECT_DELAY_MS);
          return;
        }
        if (next.state === 'canceled') return;
        watched = true;
      } catch (err) {
        if (stopped) return;
        setError(getErrorMessage(err));
        if (getErrorStatus(err) === 404) {
          setMissing(true);
          return;
        }
      }
      timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    }

    poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [jobId, navigate]);

  async function handleCancel() {
    setCanceling(true);
    try {
      // DELETE는 끝난 작업이면 '삭제'로 동작한다. 그 사이 분석이 끝났으면 취소하지 않고 결과로 보낸다.
      const latest = await getJobStatus(jobId);
      if (latest.result_type !== null) {
        navigate(paths.result(jobId), { replace: true });
        return;
      }
      if (latest.state !== 'canceled') await deleteJob(jobId);
      setStatus(await getJobStatus(jobId));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setCanceling(false);
      setConfirming(false);
    }
  }

  if (!status) {
    return (
      <section className="stack">
        <header className="page-header">
          <h1>분석 진행 상태</h1>
        </header>
        {error ? (
          <p className="error-box" role="alert">
            {error}
          </p>
        ) : (
          <p className="muted">불러오는 중…</p>
        )}
        {missing && (
          <div className="row">
            <Link to={paths.upload()} className="btn btn--primary">
              새 분석
            </Link>
            <Link to={paths.history()} className="btn">
              분석 이력
            </Link>
          </div>
        )}
      </section>
    );
  }

  const active = status.state === 'queued' || status.state === 'running';
  const canceled = status.state === 'canceled';
  const badge = STATE_BADGE[status.state];
  const stageLabel = (key: string) => status.stages.find((stage) => stage.key === key)?.label ?? key;

  return (
    <section className="stack">
      <header className="page-header progress__header">
        <div>
          <h1>분석 진행 상태</h1>
          <p className="muted">
            {status.filename} · 작업 ID <code>{status.job_id}</code> · {formatDateTime(status.created_at)} 시작
          </p>
        </div>
        {badge && <VerdictBadge kind={badge} />}
      </header>

      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}

      <div className="card progress__card">
        <div className="progress__summary">
          <strong className="progress__percent">
            {status.progress}
            <small>%</small>
          </strong>
          <div>
            <p className="progress__message">
              <span>{status.message}</span>
              {status.eta_seconds !== null && <span className="muted">남은 시간 {formatEta(status.eta_seconds)}</span>}
            </p>
            <ProgressBar value={status.progress} label="전체 진행률" muted={canceled} />
          </div>
        </div>
        <StageStepper stages={status.stages} canceled={canceled} />
      </div>

      <div className="card stack">
        <h2 className="section-title">단계 로그</h2>
        <p className="lead">단계가 끝날 때마다 그 단계에서 확인된 값을 기록합니다.</p>
        {status.logs.length === 0 ? (
          <p className="muted">아직 끝난 단계가 없습니다.</p>
        ) : (
          <ol className="progress-log" aria-live="polite">
            {status.logs.map((log) => (
              <li key={`${log.stage}-${log.at}`}>
                <time dateTime={log.at}>{formatClock(log.at)}</time>
                <span className="progress-log__stage">{stageLabel(log.stage)}</span>
                <span>{log.message}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      {active && (
        <div className="row progress__actions">
          <span className="muted">
            이 화면을 벗어나도 분석은 계속됩니다. 분석 이력에서 다시 열어 볼 수 있습니다.
          </span>
          <button type="button" className="btn" disabled={finished !== null} onClick={() => setConfirming(true)}>
            분석 취소
          </button>
        </div>
      )}
      {canceled && (
        <div className="row">
          <Link to={paths.upload()} className="btn btn--primary">
            새 분석
          </Link>
          <Link to={paths.history()} className="btn">
            분석 이력
          </Link>
        </div>
      )}

      <ConfirmDialog
        open={confirming}
        title="분석을 취소할까요?"
        confirmLabel={canceling ? '취소하는 중…' : '분석 취소'}
        cancelLabel="계속 분석"
        busy={canceling}
        onConfirm={handleCancel}
        onCancel={() => setConfirming(false)}
      >
        취소한 분석은 이어서 할 수 없습니다. 다시 분석하려면 영상을 새로 올려야 합니다.
      </ConfirmDialog>

      {finished && <Toast>{TOAST_TEXT[finished]}</Toast>}
    </section>
  );
}
