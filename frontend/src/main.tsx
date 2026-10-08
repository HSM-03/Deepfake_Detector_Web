import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';
// 글꼴과 전역 스타일을 먼저 불러와야 화면별 CSS가 공통 클래스를 덮어쓸 수 있다
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css';
import './styles/global.css';
import { router } from './router';

/** VITE_USE_MOCK=true 일 때만 MSW 목 서버를 켠다 (.env.development 참고) */
async function enableMocking() {
  if (import.meta.env.VITE_USE_MOCK !== 'true') return;
  const { worker } = await import('./mocks/browser');
  await worker.start({ onUnhandledRequest: 'bypass' });

  // 탭이 오래 백그라운드에 있으면 브라우저가 서비스 워커를 멈췄다 다시 깨우는데, 깨어난 워커는 이 페이지를 잊는다.
  // 그러면 /api 요청이 목을 거치지 않고 Vite 프록시(localhost:8000, 아직 없는 백엔드)로 가서 502가 난다.
  // 탭이 다시 보일 때 목 연결을 새로 맺는다. 목 데이터는 페이지 메모리에 있어 그대로 남는다.
  let restarting = false;
  document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState !== 'visible' || restarting) return;
    restarting = true;
    try {
      worker.stop();
      await worker.start({ onUnhandledRequest: 'bypass', quiet: true });
    } finally {
      restarting = false;
    }
  });
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  );
});
