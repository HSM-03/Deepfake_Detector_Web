import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { InfoTip } from '@/components/common/InfoTip';
import { GRID_STROKE, SERIES_COLOR } from '@/lib/chartStyle';
import { ROI_KEYS, ROI_LABEL } from '@/lib/roi';
import { TERMS } from '@/lib/terms';
import type { RoiBpm } from '@/types/api';

interface Props {
  roiBpm: RoiBpm;
  /** ROI 간 BPM 표준편차 σ. SCR-04에서만 넘긴다 */
  std?: number | null;
}

/** SCR-03 ④ ROI별 BPM — 이마·좌볼·우볼 추정 심박 비교 미니 차트. SCR-04·07에서도 쓴다 */
export function RoiBpmCard({ roiBpm, std }: Props) {
  const data = ROI_KEYS.map((key) => ({
    // 추정 실패는 막대가 없으므로 이름에 적어 준다
    name: roiBpm[key] === null ? `${ROI_LABEL[key]} (추정 실패)` : ROI_LABEL[key],
    bpm: roiBpm[key],
  }));
  const estimated = data.flatMap((d) => (d.bpm === null ? [] : [d.bpm]));
  const spread = estimated.length >= 2 ? Math.max(...estimated) - Math.min(...estimated) : null;
  const summary = ROI_KEYS.map((key) => `${ROI_LABEL[key]} ${roiBpm[key] ?? '추정 실패'}`).join(', ');

  return (
    <section className="card stack">
      <h2 className="section-title">
        {TERMS.roi.label}별 심박수 <span className="term">ROI별 BPM</span>
        <InfoTip label={TERMS.roi.label}>{TERMS.roi.help}</InfoTip>
      </h2>
      <p className="lead">실제 얼굴이면 세 부위의 심박수가 서로 비슷하게 나옵니다.</p>

      {estimated.length === 0 ? (
        <p className="muted">세 부위 모두 심박을 추정하지 못했습니다.</p>
      ) : (
        <div role="img" aria-label={`얼굴 부위별 추정 심박수: ${summary}`}>
          <ResponsiveContainer width="100%" height={150}>
            <BarChart data={data} margin={{ top: 22, right: 16, bottom: 0, left: 16 }}>
              <CartesianGrid vertical={false} stroke={GRID_STROKE} />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 13, fill: 'var(--color-text)' }}
                stroke={GRID_STROKE}
                tickLine={false}
              />
              <YAxis hide domain={[0, (max: number) => Math.ceil(max * 1.1)]} />
              <Bar dataKey="bpm" barSize={24} radius={[4, 4, 0, 0]} fill={SERIES_COLOR} isAnimationActive={false}>
                <LabelList dataKey="bpm" position="top" fontSize={13} fontWeight={700} fill="var(--color-text)" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="roi__summary">
        {spread !== null ? (
          <>
            부위 간 최대 차이 <strong>{spread} BPM</strong>
            {std != null && <> · 표준편차 σ = {std} BPM</>}
            {estimated.length < ROI_KEYS.length && <> · 추정된 {estimated.length}곳 기준</>}
          </>
        ) : (
          '비교할 수 있는 부위가 2곳 미만입니다.'
        )}
      </p>
    </section>
  );
}
