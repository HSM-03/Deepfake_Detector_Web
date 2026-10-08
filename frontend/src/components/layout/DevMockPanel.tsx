import { Link } from 'react-router-dom';
import { paths } from '@/lib/paths';

/** 고정 ID 목 작업 (src/mocks/db.ts의 FIXTURE_IDS와 같은 값) */
const LINKS: Array<{ label: string; to: string }> = [
  { label: '진짜 (SCR-03)', to: paths.result('job-real-0001') },
  { label: '가짜 (SCR-03)', to: paths.result('job-fake-0002') },
  { label: '판단 보류 (SCR-07)', to: paths.result('job-hold-0003') },
  { label: '분석 불가 (SCR-06)', to: paths.result('job-failed-0004') },
  { label: 'SQI 낮음 (SCR-03 경고)', to: paths.result('job-lowsqi-0005') },
  { label: '진행 중 (SCR-02)', to: paths.progress('job-running-0006') },
  { label: '근거 상세 (SCR-04)', to: paths.evidence('job-real-0001') },
];

/** 개발 전용: 목 시나리오 바로가기. VITE_USE_MOCK=true 일 때만 화면 하단에 보인다. */
export function DevMockPanel() {
  return (
    <aside className="dev-panel" aria-label="개발용 목 시나리오">
      <div className="dev-panel__inner">
        <strong>DEV · 목 시나리오</strong>
        {LINKS.map((link) => (
          <Link key={link.to} to={link.to}>
            {link.label}
          </Link>
        ))}
      </div>
    </aside>
  );
}
