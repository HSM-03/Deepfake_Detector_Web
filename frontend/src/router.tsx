import { createBrowserRouter } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { EvidencePage } from '@/pages/EvidencePage';
import { HistoryPage } from '@/pages/HistoryPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { ProgressPage } from '@/pages/ProgressPage';
import { ResultPage } from '@/pages/ResultPage';
import { UploadPage } from '@/pages/UploadPage';

/**
 * 화면 ↔ 경로 (경로 문자열은 src/lib/paths.ts와 맞춘다)
 *   /                      SCR-01 영상 업로드
 *   /jobs/:jobId           SCR-02 분석 진행 상태
 *   /jobs/:jobId/result    SCR-03 요약 · SCR-06 분석 불가 · SCR-07 판단 보류 (result_type으로 분기)
 *   /jobs/:jobId/evidence  SCR-04 판정 근거 상세
 *   /history               SCR-05 분석 이력
 */
export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: <UploadPage /> },
      { path: '/jobs/:jobId', element: <ProgressPage /> },
      { path: '/jobs/:jobId/result', element: <ResultPage /> },
      { path: '/jobs/:jobId/evidence', element: <EvidencePage /> },
      { path: '/history', element: <HistoryPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
