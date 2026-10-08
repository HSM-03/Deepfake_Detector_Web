import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AXIS_TICK, GRID_STROKE, SERIES_COLOR, TOOLTIP_STYLE } from '@/lib/chartStyle';
import type { EvidenceResponse, SignalPoint } from '@/types/api';
import { RoiBpmCard } from '../result/RoiBpmCard';
import { ChartCard } from './ChartCard';

interface Props {
  evidence: EvidenceResponse;
  /** ROI를 바꿔 다시 불러오는 중 */
  loading: boolean;
}

const CHART_HEIGHT = 200;

/** 시간축 파형 (원신호·필터 후 공통) */
function SignalChart({ data, label }: { data: SignalPoint[]; label: string }) {
  return (
    <div role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID_STROKE} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            domain={[0, (max: number) => Math.ceil(max)]}
            tickCount={6}
            unit="초"
            tick={AXIS_TICK}
            stroke={GRID_STROKE}
          />
          <YAxis width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v: number) => v.toFixed(1)} />
          <Tooltip
            {...TOOLTIP_STYLE}
            formatter={(v: number) => [v.toFixed(3), '신호']}
            labelFormatter={(t: number) => `${t.toFixed(2)}초`}
          />
          <Line dataKey="v" dot={false} stroke={SERIES_COLOR} strokeWidth={1.5} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** SCR-04 ④ rPPG 차트 3종 + ⑤ 일관성 차트(ROI별 BPM, 3초 윈도우 BPM 변동) */
export function RppgTab({ evidence, loading }: Props) {
  const { peak, hr_band: band, window_bpm } = evidence;
  const windowValues = window_bpm.flatMap((w) => (w.bpm === null ? [] : [w.bpm]));
  const bandText = `${band[0]}~${band[1]} Hz`;

  return (
    <div className="evidence-grid">
      <ChartCard
        title="필터 전 원신호"
        term="RGB → CHROM"
        hint="얼굴 피부색 변화에서 뽑은 신호 그대로입니다. 조명 변화에 따른 느린 출렁임이 아직 섞여 있습니다."
        loading={loading}
        height={CHART_HEIGHT}
        caption={`샘플링 ${evidence.fs} Hz (영상 프레임률과 같음)`}
      >
        <SignalChart data={evidence.raw_signal} label="rPPG 원신호 파형" />
      </ChartCard>

      <ChartCard
        title="심박 대역만 남긴 파형"
        term={`Butterworth ${bandText}`}
        hint="실제 얼굴이면 일정한 간격의 맥파가 또렷하게 반복됩니다. 들쭉날쭉하면 생체신호가 약하다는 뜻입니다."
        loading={loading}
        height={CHART_HEIGHT}
      >
        <SignalChart data={evidence.filtered_signal} label="대역통과 필터 후 파형" />
      </ChartCard>

      <ChartCard
        title="주파수별 세기"
        term="Welch 파워 스펙트럼"
        hint="실제 얼굴이면 심박 대역(음영) 안에 뾰족한 봉우리가 하나 섭니다. 봉우리가 여럿이거나 낮으면 의심 신호입니다."
        loading={loading}
        height={CHART_HEIGHT}
        caption={
          peak
            ? `음영: 심박 대역 ${bandText} · 점: 가장 센 주파수 ${peak.hz.toFixed(2)} Hz = 분당 ${peak.bpm}회(BPM)`
            : `음영: 심박 대역 ${bandText} · 이 부위에서는 심박 봉우리를 찾지 못했습니다.`
        }
      >
        <div role="img" aria-label={peak ? `파워 스펙트럼, 피크 ${peak.bpm} BPM` : '파워 스펙트럼, 피크 미검출'}>
          <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
            <AreaChart data={evidence.psd} margin={{ top: 24, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={GRID_STROKE} vertical={false} />
              <XAxis dataKey="hz" type="number" domain={[0, 'dataMax']} tickCount={6} unit="Hz" tick={AXIS_TICK} stroke={GRID_STROKE} />
              <YAxis width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v: number) => v.toFixed(1)} />
              <ReferenceArea x1={band[0]} x2={band[1]} fill="var(--color-primary-bg)" />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(v: number) => [v.toFixed(3), '세기']}
                labelFormatter={(hz: number) => `${hz.toFixed(2)} Hz (${Math.round(hz * 60)} BPM)`}
              />
              <Area dataKey="power" stroke={SERIES_COLOR} strokeWidth={2} fill={SERIES_COLOR} fillOpacity={0.1} isAnimationActive={false} />
              {peak && (
                <ReferenceDot
                  x={peak.hz}
                  y={peak.power}
                  r={5}
                  fill="var(--color-text)"
                  stroke="var(--color-surface)"
                  strokeWidth={2}
                  label={{
                    value: `${peak.hz.toFixed(2)} Hz = ${peak.bpm} BPM`,
                    position: 'top',
                    fontSize: 12,
                    fontWeight: 700,
                    fill: 'var(--color-text)',
                  }}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      {/* 부위별 심박은 ROI 선택과 무관하게 세 곳을 항상 같이 보여 준다 */}
      <RoiBpmCard roiBpm={evidence.roi_bpm} std={evidence.roi_bpm_std} />

      <div className="evidence-grid__wide">
        <ChartCard
          title="시간에 따른 심박수 변화"
          term="3초 윈도우 BPM"
          hint="영상을 3초씩 잘라 구간마다 심박수를 다시 잰 값입니다. 실제 얼굴이면 구간마다 크게 흔들리지 않습니다."
          loading={loading}
          height={CHART_HEIGHT}
          caption={
            windowValues.length > 0
              ? `구간 ${windowValues.length}개 · 최소 ${Math.min(...windowValues)} ~ 최대 ${Math.max(...windowValues)} BPM`
              : undefined
          }
        >
          {windowValues.length === 0 ? (
            <p className="muted">이 부위에서는 심박을 추정하지 못해 구간별 값이 없습니다.</p>
          ) : (
            <div role="img" aria-label="3초 윈도우별 추정 BPM">
              <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
                <LineChart data={window_bpm} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={GRID_STROKE} vertical={false} />
                  <XAxis dataKey="t_start" type="number" domain={[0, 'dataMax']} tickCount={8} unit="초" tick={AXIS_TICK} stroke={GRID_STROKE} />
                  <YAxis
                    width={44}
                    tick={AXIS_TICK}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                    domain={[
                      (min: number) => Math.floor((min - 5) / 10) * 10,
                      (max: number) => Math.ceil((max + 5) / 10) * 10,
                    ]}
                  />
                  <Tooltip
                    {...TOOLTIP_STYLE}
                    formatter={(v: number) => [`${v} BPM`, '추정 심박수']}
                    labelFormatter={(t: number) => `${t}~${t + 3}초`}
                  />
                  <Line
                    dataKey="bpm"
                    stroke={SERIES_COLOR}
                    strokeWidth={2}
                    dot={{ r: 4, fill: SERIES_COLOR, stroke: 'var(--color-surface)', strokeWidth: 2 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
