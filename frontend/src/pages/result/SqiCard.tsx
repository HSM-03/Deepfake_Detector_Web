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

/** SCR-03 ③ SQI 카드 — 신호품질지수와 등급, 구성 요소 4개. SQI가 하한 미만이면 경고 */
export function SqiCard({ sqi, thresholds, w, low }: Props) {
  const f = formatScore;
  const percent = (n: number) => `${n * 100}%`;

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
          <span aria-hidden="true">△ </span>SQI가 하한({f(thresholds.sqi_min)}) 미만 — rPPG 축 가중치가 w = {f(w)}로
          줄었습니다.
        </p>
      )}

      <ul className="sqi__components">
        {COMPONENTS.map(({ key, label, hint }) => {
          const value = sqi.components[key];
          return (
            <li key={key} title={hint}>
              <span>{label}</span>
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
      <p className="caption">구성 요소는 0~1이며 1에 가까울수록 신호를 뽑기 좋은 조건입니다.</p>
    </section>
  );
}
