import { InfoTip } from '@/components/common/InfoTip';
import { formatScore } from '@/lib/format';
import { TERMS } from '@/lib/terms';
import type { SqiGrade, SqiInfo, Thresholds } from '@/types/api';

interface Props {
  sqi: SqiInfo;
  thresholds: Thresholds;
  /** 적용된 rPPG 가중치 */
  w: number;
  /** SQI가 하한 미만이라 rPPG 기여도가 낮은 건 (경고 표시) */
  low: boolean;
}

const GRADE_LABEL: Record<SqiGrade, string> = { good: '양호', fair: '보통', poor: '낮음' };

/** 구성 요소는 모두 0~1이고 1에 가까울수록 신호를 뽑기 좋은 조건이다 */
const COMPONENTS: Array<{ key: keyof SqiInfo['components']; label: string; hint: string }> = [
  { key: 'face_pixels', label: '얼굴 크기', hint: '얼굴 영역의 픽셀 수' },
  { key: 'compression', label: '압축 상태', hint: '압축 손상이 적을수록 높음' },
  { key: 'illumination', label: '조명', hint: '밝고 변동이 적을수록 높음' },
  { key: 'motion', label: '움직임', hint: '머리·얼굴 움직임이 적을수록 높음' },
];

/**
 * SCR-03 ③ SQI 카드 — 신호품질지수와 등급, 구성 요소 4개. SQI가 하한 미만이면 "rPPG 미반영" 경고.
 * SQI는 네 항목 중 가장 낮은 값이라(백엔드 analysis/sqi.py), 가장 낮은 항목을 "병목"으로 표시한다(색만이 아니라 글자로)
 */
export function SqiCard({ sqi, thresholds, w, low }: Props) {
  const f = formatScore;
  const percent = (n: number) => `${n * 100}%`;
  const weakest = COMPONENTS.reduce((min, c) => (sqi.components[c.key] < sqi.components[min.key] ? c : min));
  // 네 항목이 모두 1이면 SQI를 깎은 항목이 없다 — 첫 항목에 "병목"을 붙이지 않는다
  const hasBottleneck = sqi.components[weakest.key] < 1;

  return (
    <section className="card stack">
      <h2 className="section-title">
        {TERMS.sqi.label} <span className="term">{TERMS.sqi.term}</span>
        <InfoTip label={TERMS.sqi.label}>{TERMS.sqi.help}</InfoTip>
      </h2>
      <p className="lead">심박 신호를 얼마나 믿을 수 있는지입니다. 하한보다 낮으면 생체신호 축을 거의 반영하지 않습니다.</p>

      <div className="sqi__head">
        <strong className="sqi__value">{f(sqi.value)}</strong>
        <span className={`sqi__grade sqi__grade--${sqi.grade}`}>{GRADE_LABEL[sqi.grade]}</span>
      </div>
      <div className="sqi__scale">
        <div
          className={`meter meter--lg meter--${sqi.grade}`}
          role="meter"
          aria-label={TERMS.sqi.label}
          aria-valuemin={0}
          aria-valuemax={1}
          aria-valuenow={sqi.value}
        >
          <div className="meter__fill" style={{ width: percent(sqi.value) }} />
        </div>
        <span className="sqi__threshold" style={{ left: percent(thresholds.sqi_min) }}>
          하한 {f(thresholds.sqi_min)}
        </span>
      </div>

      {low && (
        <p className="warn-box">
          <strong>
            <span aria-hidden="true">△ </span>rPPG 미반영(신호 품질 낮음)
          </strong>{' '}
          — SQI가 하한({f(thresholds.sqi_min)}) 미만이라 rPPG 축 가중치를 줄였습니다(w = {f(w)}). 가장 약한 항목:{' '}
          {weakest.label}.
        </p>
      )}

      <ul className="sqi__components">
        {COMPONENTS.map(({ key, label, hint }) => {
          const value = sqi.components[key];
          const isWeakest = hasBottleneck && key === weakest.key;
          return (
            <li key={key} title={hint} className={isWeakest ? 'sqi__component--weakest' : undefined}>
              <span>
                {label}
                {isWeakest && <span className="sqi__weakest-tag">병목</span>}
              </span>
              <div
                className="meter"
                role="meter"
                aria-label={`${label} (${hint})`}
                aria-valuemin={0}
                aria-valuemax={1}
                aria-valuenow={value}
              >
                <div className="meter__fill" style={{ width: percent(value) }} />
              </div>
              <span className="sqi__component-value">{f(value)}</span>
            </li>
          );
        })}
      </ul>
      <p className="caption">
        구성 요소는 0~1이며 1에 가까울수록 신호를 뽑기 좋은 조건입니다. SQI는 네 항목 중 가장 낮은 값입니다
        {hasBottleneck ? (
          <>
            (지금 SQI를 정한 항목: <strong>{weakest.label}</strong>).
          </>
        ) : (
          <>(지금은 네 항목 모두 1.00이라 SQI를 깎은 항목이 없습니다).</>
        )}
      </p>
    </section>
  );
}
