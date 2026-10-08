import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { downloadReport } from '@/api/jobs';
import { saveBlob } from '@/lib/download';
import { paths } from '@/lib/paths';

interface Props {
  jobId: string;
  /** 근거 상세(SCR-04)에서는 첫 버튼이 [결과 요약으로]가 된다 */
  onEvidencePage?: boolean;
}

/** SCR-03 ⑥ 액션 바 — [판정 근거 상세 보기] [리포트 내보내기(PDF)] [결과 링크 복사]. SCR-04·07에서도 쓴다. */
export function ResultActionBar({ jobId, onEvidencePage = false }: Props) {
  const [exporting, setExporting] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** UC-05 리포트 내보내기 */
  async function handleExport() {
    setExporting(true);
    setError(null);
    try {
      saveBlob(await downloadReport(jobId), `report_${jobId}.pdf`);
    } catch (err) {
      setError(`리포트를 내보내지 못했습니다. ${getErrorMessage(err)}`);
    } finally {
      setExporting(false);
    }
  }

  async function handleCopy() {
    setError(null);
    setCopied(false);
    try {
      await navigator.clipboard.writeText(new URL(paths.result(jobId), window.location.origin).href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('링크를 복사하지 못했습니다. 브라우저의 클립보드 권한을 확인해 주세요.');
    }
  }

  return (
    <div className="stack">
      <div className="action-bar">
        <span className="action-bar__spacer">
          {onEvidencePage
            ? '판정과 점수 요약으로 돌아갑니다.'
            : '파형·스펙트럼 같은 신호 수준의 근거는 상세 화면에서 볼 수 있습니다.'}
        </span>
        {onEvidencePage ? (
          <Link to={paths.result(jobId)} className="btn btn--primary">
            결과 요약으로
          </Link>
        ) : (
          <Link to={paths.evidence(jobId)} className="btn btn--primary">
            판정 근거 상세 보기
          </Link>
        )}
        <button type="button" className="btn" disabled={exporting} onClick={handleExport}>
          {exporting ? '리포트 만드는 중…' : '리포트 내보내기(PDF)'}
        </button>
        <button type="button" className="btn" onClick={handleCopy}>
          {copied ? '✓ 링크를 복사했습니다' : '결과 링크 복사'}
        </button>
      </div>
      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
