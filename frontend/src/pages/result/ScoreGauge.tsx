import { formatScore } from '@/lib/format';
import type { Thresholds } from '@/types/api';

interface Props {
  /** 종합 점수 S. 판단 보류 건은 null(바늘 없이 구간만 보여 준다) */
  value: number | null;
  thresholds: Thresholds;
}

/** 0~1 눈금 위에 진짜·경계·가짜 구간과 종합 점수의 위치를 보여 주는 게이지 (판정 카드용) */
export function ScoreGauge({ value, thresholds: t }: Props) {
  const percent = (n: number) => `${n * 100}%`;
  const zones = [
    { key: 'real', label: '진짜', width: t.score_real_max },
    { key: 'hold', label: '경계', width: t.score_fake_min - t.score_real_max },
    { key: 'fake', label: '가짜', width: 1 - t.score_fake_min },
  ];

  return (
    <div
      className="score-gauge"
      role="meter"
      aria-label="종합 점수 S"
      aria-valuemin={0}
      aria-valuemax={1}
      aria-valuenow={value ?? undefined}
      aria-valuetext={value === null ? '산출하지 않음' : formatScore(value)}
    >
      <div className="score-gauge__track">
        {zones.map((zone) => (
          <div key={zone.key} className={`score-gauge__zone score-gauge__zone--${zone.key}`} style={{ flexGrow: zone.width }}>
            <span>{zone.label}</span>
          </div>
        ))}
        {value !== null && <div className="score-gauge__needle" style={{ left: percent(value) }} />}
      </div>
      <div className="score-gauge__ticks" aria-hidden="true">
        <span style={{ left: 0 }}>0</span>
        <span style={{ left: percent(t.score_real_max) }}>{formatScore(t.score_real_max)}</span>
        <span style={{ left: percent(t.score_fake_min) }}>{formatScore(t.score_fake_min)}</span>
        <span style={{ left: '100%' }}>1</span>
      </div>
    </div>
  );
}
