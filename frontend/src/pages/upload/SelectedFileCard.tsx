import { formatBytes, formatDuration } from '@/lib/format';
import type { CheckState, FileCheck, ProbeState } from '@/lib/videoFile';

interface Props {
  file: File;
  probe: ProbeState;
  /** 검증 항목 (형식·용량·길이) */
  checks: Array<{ label: string; check: FileCheck }>;
  disabled: boolean;
  onRemove: () => void;
}

/** 검증 상태는 색만으로 구분하지 않고 기호와 문구를 같이 쓴다 */
const CHECK_ICON: Record<CheckState, { symbol: string; label: string }> = {
  pass: { symbol: '✓', label: '통과' },
  fail: { symbol: '×', label: '실패' },
  warn: { symbol: '△', label: '주의' },
  pending: { symbol: '…', label: '확인 중' },
  unknown: { symbol: '–', label: '확인 불가' },
};

/** SCR-01 ② 선택 파일 카드 — 썸네일·용량·해상도·fps·길이와 브라우저 검증 결과 */
export function SelectedFileCard({ file, probe, checks, disabled, onRemove }: Props) {
  const info = probe.status === 'done' ? probe.probe : null;
  const undecodable = probe.status === 'done' && probe.probe === null;

  /** 영상에서 읽는 값: 읽는 중 / 읽지 못함 / 읽지 않음(검증 실패)을 구분해 보여 준다 */
  function probed(value: string | null): string {
    if (probe.status === 'probing') return '확인 중…';
    if (probe.status === 'idle') return '—';
    return value ?? '확인 불가';
  }

  return (
    <div className="card file-card">
      <div className="file-card__thumb">
        {info?.thumbnailUrl ? (
          <img src={info.thumbnailUrl} alt="영상 썸네일" />
        ) : (
          <span className="muted">{probe.status === 'probing' ? '읽는 중…' : '미리보기 없음'}</span>
        )}
      </div>
      <div className="file-card__body stack">
        <div className="file-card__head">
          <strong className="file-card__name" title={file.name}>
            {file.name}
          </strong>
          <button type="button" className="btn" disabled={disabled} onClick={onRemove}>
            선택 해제
          </button>
        </div>
        <dl className="file-card__meta">
          <div>
            <dt>용량</dt>
            <dd>{formatBytes(file.size)}</dd>
          </div>
          <div>
            <dt>해상도</dt>
            <dd>{probed(info?.width && info.height ? `${info.width}×${info.height}` : null)}</dd>
          </div>
          <div>
            <dt>fps</dt>
            <dd>{probed(info?.fps ? `약 ${info.fps}` : null)}</dd>
          </div>
          <div>
            <dt>길이</dt>
            <dd>{probed(info?.durationSec ? formatDuration(info.durationSec) : null)}</dd>
          </div>
        </dl>
        {undecodable && (
          <p className="muted">
            이 브라우저에서 재생할 수 없는 영상이라 해상도·fps·길이를 미리 읽지 못했습니다. 업로드는 그대로 할 수 있습니다.
          </p>
        )}
        <ul className="file-checks">
          {checks.map(({ label, check }) => (
            <li key={label} className={`file-check file-check--${check.state}`}>
              <span className="file-check__icon" role="img" aria-label={CHECK_ICON[check.state].label}>
                {CHECK_ICON[check.state].symbol}
              </span>
              <span className="file-check__label">{label}</span>
              <span>{check.text}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
