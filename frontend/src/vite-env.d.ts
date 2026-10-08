/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true'면 MSW 목 API 사용 */
  readonly VITE_USE_MOCK?: string;
  /** API 기본 경로. 기본값 '/api' */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
