import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Customized,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AXIS_TICK, GRID_STROKE, THRESHOLD_STROKE, TOOLTIP_STYLE, ZONE_STYLE } from '@/lib/chartStyle';
import { formatScore } from '@/lib/format';
import { TERMS } from '@/lib/terms';
import { scoreZone, type ScoreZone } from '@/lib/verdict';
import type { DoneResult } from '@/types/api';

interface Props {
  /** 점수가 산출된 결과의 공통 필드 (SCR-03·07) */
  result: Pick<DoneResult, 'p_model' | 'p_rppg' | 'thresholds'>;
  /** 종합 점수 S. 판단 보류 건은 null(표시하지 않음) */
  score: number | null;
  /** 두 막대 사이 차이를 화살표로 이어 상충 정도를 보여 준다 (SCR-07) */
  gapArrow?: boolean;
}

interface Axis {
  /** 쉬운 말 이름 (예: 영상 조작 흔적) */
  name: string;
  /** 기술 용어 (예: P_model) */
  term: string;
  value: number;
  zone: ScoreZone;
}

/** Y축 눈금: '이름 점수' + '용어 · 위치' 두 줄. 점수를 막대 끝에 두면 S 실선과 겹쳐서 여기에 적는다 */
function AxisTick({ x, y, axis }: { x: number; y: number; axis: Axis }) {
  return (
    <text x={x} y={y} textAnchor="end" fontSize={13.5}>
      <tspan x={x} dy="-0.2em" fontWeight={700} fill="var(--color-text)">
        {axis.name} {formatScore(axis.value)}
      </tspan>
      <tspan x={x} dy="1.45em" fontSize={12} fill="var(--color-text-muted)">
        {axis.term} · {ZONE_STYLE[axis.zone].label}
      </tspan>
    </text>
  );
}

/** Recharts가 Customized에 넘겨 주는 차트 좌표 정보 중 쓰는 것만 */
interface ChartGeometry {
  xAxisMap?: Record<string, { scale: (value: number) => number }>;
  offset?: { top: number; height: number };
}

/** 두 막대 사이(세로 가운데)에 그리는 양방향 화살표 */
function GapArrow({ xAxisMap, offset, from, to, label }: ChartGeometry & { from: number; to: number; label: string }) {
  const scale = xAxisMap && Object.values(xAxisMap)[0]?.scale;
  if (!scale || !offset) return null;
  const x1 = scale(Math.min(from, to));
  const x2 = scale(Math.max(from, to));
  const y = offset.top + offset.height / 2;
  const head = 7;
  return (
    <g fill="var(--color-text)">
      <line x1={x1 + head} y1={y} x2={x2 - head} y2={y} stroke="var(--color-text)" strokeWidth={2} />
      <polygon points={`${x1},${y} ${x1 + head},${y - 4} ${x1 + head},${y + 4}`} />
      <polygon points={`${x2},${y} ${x2 - head},${y - 4} ${x2 - head},${y + 4}`} />
      <text x={(x1 + x2) / 2} y={y - 8} textAnchor="middle" fontSize={12.5} fontWeight={700}>
        {label}
      </text>
    </g>
  );
}

/**
 * SCR-03 ② 두 판별 축 점수 — P_model·P_rppg를 같은 0~1 막대로 나열하고
 * 경계 구간(점선), 축 간 차이와 상충 임계를 같이 보여 준다. SCR-07에서도 쓴다.
 */
export function AxisScores({ result, score, gapArrow = false }: Props) {
  const { p_model, p_rppg, thresholds: t } = result;
  const f = formatScore;
  const gap = Math.abs(p_model - p_rppg);
  const conflict = gap >= t.conflict_gap;

  const axes: Axis[] = [
    { name: TERMS.pModel.label, term: TERMS.pModel.term, value: p_model, zone: scoreZone(p_model, t) },
    { name: TERMS.pRppg.label, term: TERMS.pRppg.term, value: p_rppg, zone: scoreZone(p_rppg, t) },
  ];
  const summary = axes.map((axis) => `${axis.name} ${f(axis.value)} ${ZONE_STYLE[axis.zone].label}`).join(', ');

  return (
    <section className="card stack">
      <h2 className="section-title">두 판별 축은 이렇게 봤습니다</h2>
      <p className="lead">두 축을 같은 0~1 눈금에 놓았습니다. 오른쪽으로 갈수록 조작 가능성이 큽니다.</p>

      <div role="img" aria-label={`두 축 점수 막대 차트: ${summary}`}>
        {/* 화살표와 글자가 들어갈 자리가 필요해 상충 표시 때는 막대 사이를 넓힌다 */}
        <ResponsiveContainer width="100%" height={gapArrow ? 196 : 160}>
          <BarChart data={axes} layout="vertical" margin={{ top: 24, right: 24, bottom: 0, left: 8 }}>
            <CartesianGrid horizontal={false} stroke={GRID_STROKE} />
            <XAxis
              type="number"
              domain={[0, 1]}
              ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
              tickFormatter={(v: number) => v.toFixed(1)}
              tick={AXIS_TICK}
              stroke={GRID_STROKE}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={168}
              tick={({ x, y, index }: { x: number; y: number; index: number }) => (
                <AxisTick x={x} y={y} axis={axes[index]} />
              )}
              axisLine={false}
              tickLine={false}
            />
            <ReferenceArea x1={t.score_real_max} x2={t.score_fake_min} fill="var(--verdict-hold-bg)" />
            <ReferenceLine x={t.score_real_max} stroke={THRESHOLD_STROKE} strokeDasharray="4 4" />
            <ReferenceLine x={t.score_fake_min} stroke={THRESHOLD_STROKE} strokeDasharray="4 4" />
            <Tooltip
              {...TOOLTIP_STYLE}
              cursor={{ fill: 'var(--color-surface-sunken)' }}
              formatter={(v: number) => [`${f(v)} · ${ZONE_STYLE[scoreZone(v, t)].label}`, '점수']}
            />
            <Bar dataKey="value" barSize={20} radius={[0, 4, 4, 0]} isAnimationActive={false}>
              {axes.map((axis) => (
                <Cell key={axis.term} fill={ZONE_STYLE[axis.zone].color} />
              ))}
            </Bar>
            {score !== null && (
              <ReferenceLine
                x={score}
                stroke="var(--color-text)"
                strokeWidth={2}
                label={{ value: `S ${f(score)}`, position: 'top', fontSize: 12.5, fontWeight: 700, fill: 'var(--color-text)' }}
              />
            )}
            {gapArrow && (
              <Customized
                component={(geometry: ChartGeometry) => (
                  <GapArrow {...geometry} from={p_model} to={p_rppg} label={`차이 ${f(gap)}`} />
                )}
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="chart-legend">
        {(Object.keys(ZONE_STYLE) as ScoreZone[]).map((zone) => (
          <li key={zone}>
            <span className="chart-legend__swatch" style={{ background: ZONE_STYLE[zone].color }} />
            {ZONE_STYLE[zone].label}
          </li>
        ))}
        <li>
          <span className="chart-legend__dash" />
          경계선 {f(t.score_real_max)} · {f(t.score_fake_min)}
        </li>
        {score !== null && (
          <li>
            <span className="chart-legend__line" />
            종합 점수 S
          </li>
        )}
      </ul>

      <p className={conflict ? 'callout callout--warn' : 'callout callout--ok'}>
        <span className="callout__icon" aria-hidden="true">
          {conflict ? '△' : '✓'}
        </span>
        <span>
          <strong>{conflict ? '두 축의 판단이 크게 다릅니다.' : '두 축의 판단이 상충하지 않습니다.'}</strong>{' '}
          <span className="callout__detail">
            축 간 차이 |P_model − P_rppg| = {f(gap)} {conflict ? '≥' : '<'} 상충 임계 {f(t.conflict_gap)}
          </span>
        </span>
      </p>
    </section>
  );
}
