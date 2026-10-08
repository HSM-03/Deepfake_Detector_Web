import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

/** 브라우저에서 /api 요청을 가로채는 목 서버 (public/mockServiceWorker.js 필요) */
export const worker = setupWorker(...handlers);
