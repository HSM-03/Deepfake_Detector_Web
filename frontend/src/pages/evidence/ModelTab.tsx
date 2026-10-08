import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AXIS_TICK, GRID_STROKE, THRESHOLD_STROKE, TOOLTIP_STYLE, ZONE_STYLE } from '@/lib/chartStyle';
import { formatScore } from '@/lib/format';
import { scoreZone } from '@/lib/verdict';
import type { DoneResult, EvidenceResponse } from '@/types/api';
import { ChartCard } from './ChartCard';

interface Props {
  evidence: EvidenceResponse;
  result: Pick<DoneResult, 'p_model' | 'p_model_std' | 'thresholds'>;
}

/** SCR-04 ⑤ 메인 모델 구간별 프로파일 */
export function ModelTab({ evidence, result }: Props) {
  const { thresholds: t } = result;
  const f = formatScore;
  const segments = evidence.model_profile.map((segment) => ({
    ...segment,
    range: `${segment.t_start}~${segment.t_end}`,
    zone: scoreZone(segment.p, t),
  }));
  const fakeCount = segments.filter((s) => s.zone === 'fake').length;

  return (
    <ChartCard
      title="구간별 영상 조작 흔적"
      term="메인 모델 프로파일"
      hint="영상을 구간으로 나눠 각각 조작 확률을 잰 값입니다. 막대가 경계 구간(음영) 위로 올라간 곳이 조작이 의심되는 부분입니다."
      loading={false}
      height={260}
      caption={`구간 ${segments.length}개 중 가짜 쪽(${f(t.score_fake_min)} 이상) ${fakeCount}개 · 전체 P_model = ${f(result.p_model)} (프레임 점수 표준편차 ±${f(result.p_model_std)}) · 실선은 전체 P_model`}
    >
      <div role="img" aria-label={`메인 모델 구간별 조작 확률, 전체 P_model ${f(result.p_model)}`}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={segments} margin={{ top: 24, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={GRID_STROKE} />
            <XAxis dataKey="range" unit="초" tick={AXIS_TICK} stroke={GRID_STROKE} tickLine={false} />
            <YAxis width={44} domain={[0, 1]} ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <ReferenceArea y1={t.score_real_max} y2={t.score_fake_min} fill="var(--verdict-hold-bg)" />
            <ReferenceLine y={t.score_real_max} stroke={THRESHOLD_STROKE} strokeDasharray="4 4" />
            <ReferenceLine y={t.score_fake_min} stroke={THRESHOLD_STROKE} strokeDasharray="4 4" />
            <Tooltip
              {...TOOLTIP_STYLE}
              cursor={{ fill: 'var(--color-surface-sunken)' }}
              formatter={(p: number) => [`${f(p)} · ${ZONE_STYLE[scoreZone(p, t)].label}`, '조작 확률']}
              labelFormatter={(range: string) => `${range}초 구간`}
            />
            <Bar dataKey="p" barSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {segments.map((segment) => (
                <Cell key={segment.range} fill={ZONE_STYLE[segment.zone].color} />
              ))}
            </Bar>
            <ReferenceLine
              y={result.p_model}
              stroke="var(--color-text)"
              strokeWidth={2}
              label={{
                value: `P_model ${f(result.p_model)}`,
                position: 'insideTopRight',
                fontSize: 12,
                fontWeight: 700,
                fill: 'var(--color-text)',
              }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="chart-legend">
        {(['real', 'boundary', 'fake'] as const).map((zone) => (
          <li key={zone}>
            <span className="chart-legend__swatch" style={{ background: ZONE_STYLE[zone].color }} />
            {ZONE_STYLE[zone].label}
          </li>
        ))}
      </ul>
    </ChartCard>
  );
}
