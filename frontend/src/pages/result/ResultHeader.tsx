import { formatBytes, formatDateTime, formatDuration } from '@/lib/format';
import type { JobResultResponse } from '@/types/api';

interface Props {
  title: string;
  result: Pick<JobResultResponse, 'job_id' | 'completed_at' | 'video' | 'memo'>;
}

/** 결과 화면(SCR-03·04·06·07) 공통 머리말 — 화면 제목, 어떤 영상의 결과인지, 메모 */
export function ResultHeader({ title, result }: Props) {
  const { video } = result;
  const facts = [
    `${video.width}×${video.height}`,
    `${video.fps}fps`,
    formatDuration(video.duration_sec),
    `${video.frame_count}프레임`,
    video.codec.toUpperCase(),
    formatBytes(video.size_bytes),
  ];

  return (
    <header className="page-header result-header">
      <h1>{title}</h1>
      <p className="result-header__file">
        <strong>{video.filename}</strong>
        <span className="muted">
          작업 ID <code>{result.job_id}</code> · {formatDateTime(result.completed_at)} 분석 종료
        </span>
      </p>
      <ul className="result-header__facts">
        {facts.map((fact) => (
          <li key={fact}>{fact}</li>
        ))}
        {result.memo && <li className="result-header__memo">메모: {result.memo}</li>}
      </ul>
    </header>
  );
}
