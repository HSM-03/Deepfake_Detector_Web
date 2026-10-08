/** Recharts 공통 모양. 색은 tokens.css 변수만 쓴다 */
import type { ScoreZone } from './verdict';

/** 축 눈금 글자 */
export const AXIS_TICK = { fontSize: 12, fill: 'var(--color-text-muted)' };

/** 격자·축선: 실선 한 줄, 눈에 띄지 않게 */
export const GRID_STROKE = 'var(--color-border)';

/** 단일 계열의 기본 색 */
export const SERIES_COLOR = 'var(--color-primary)';

/** 임계값 표시선(점선) */
export const THRESHOLD_STROKE = 'var(--color-text-muted)';

/** 점수 구간별 채움색과 이름. 색만으로 구분하지 않도록 이름을 같이 쓴다 */
export const ZONE_STYLE: Record<ScoreZone, { label: string; color: string }> = {
  real: { label: '진짜 쪽', color: 'var(--verdict-real-fill)' },
  boundary: { label: '경계 구간', color: 'var(--verdict-hold-fill)' },
  fake: { label: '가짜 쪽', color: 'var(--verdict-fake-fill)' },
};

export const TOOLTIP_STYLE = {
  contentStyle: {
    padding: '8px 12px',
    border: '1px solid var(--color-border)',
    borderRadius: 10,
    background: 'var(--color-surface)',
    boxShadow: 'var(--shadow-card)',
    fontSize: 13,
  },
  labelStyle: { marginBottom: 2, color: 'var(--color-text-muted)' },
  itemStyle: { padding: 0, color: 'var(--color-text)', fontWeight: 600 },
};
