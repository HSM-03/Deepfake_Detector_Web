import type { RoiKey, RoiSelector } from '@/types/api';

/** rPPG 관심 영역의 표시 순서와 이름 */
export const ROI_KEYS: RoiKey[] = ['forehead', 'left_cheek', 'right_cheek'];

export const ROI_LABEL: Record<RoiKey, string> = {
  forehead: '이마',
  left_cheek: '좌볼',
  right_cheek: '우볼',
};

/** SCR-04 ROI 선택기 (전체 + 개별 ROI) */
export const ROI_OPTIONS: Array<{ value: RoiSelector; label: string }> = [
  { value: 'all', label: '전체' },
  ...ROI_KEYS.map((key) => ({ value: key, label: ROI_LABEL[key] })),
];
