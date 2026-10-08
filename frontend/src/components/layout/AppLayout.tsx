import { Outlet } from 'react-router-dom';
import { AppHeader } from './AppHeader';
import { DevMockPanel } from './DevMockPanel';

/** 모든 화면의 공통 틀: 고정 헤더 + 최대 폭 1200px 콘텐츠 영역 */
export function AppLayout() {
  return (
    <div className="app">
      <AppHeader />
      <main className="app-main">
        <Outlet />
      </main>
      {import.meta.env.VITE_USE_MOCK === 'true' && <DevMockPanel />}
    </div>
  );
}
