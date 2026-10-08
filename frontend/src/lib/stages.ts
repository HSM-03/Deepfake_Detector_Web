import type { StageKey } from '@/types/api';

/** 분석 5단계의 이름 (SCR-02 스테퍼와 같은 순서). 결과 응답에는 단계 이름이 없어 여기서 붙인다 */
export const STAGE_LABEL: Record<StageKey, string> = {
  upload: '업로드·검증',
  preprocess: '전처리·ROI 추적',
  model: '메인 모델 판별',
  rppg: 'rPPG 신호 분석',
  fusion: '융합 판정',
};

export const STAGE_COUNT = Object.keys(STAGE_LABEL).length;
