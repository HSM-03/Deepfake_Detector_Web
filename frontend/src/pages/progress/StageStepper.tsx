import type { StageKey, StageState, StageStatus } from '@/types/api';

interface Props {
  stages: StageStatus[];
  /** 취소된 작업이면 완료 단계까지 회색으로 그린다 */
  canceled: boolean;
}

interface NumberedStage {
  stage: StageStatus;
  /** 1부터 (대기 상태의 마커, 분석 불가 안내의 n/5 표기와 같은 번호) */
  number: number;
}

/** 메인 모델과 rPPG는 병렬로 수행되므로 한 칸에 묶어 그린다 */
const PARALLEL: StageKey[] = ['model', 'rppg'];

function stateText(stage: StageStatus): string {
  const text: Record<StageState, string> = {
    waiting: '대기',
    running: `진행 중 ${stage.progress}%`,
    done: '완료',
    failed: '중단',
    canceled: '취소됨',
  };
  return text[stage.state];
}

/** 완료 ✓ / 진행 ● / 실패 × / 대기·취소는 단계 번호 */
function marker({ stage, number }: NumberedStage): string {
  if (stage.state === 'done') return '✓';
  if (stage.state === 'running') return '●';
  if (stage.state === 'failed') return '×';
  return String(number);
}

function Step(item: NumberedStage) {
  const { stage } = item;
  return (
    <div className={`step step--${stage.state}`} aria-current={stage.state === 'running' ? 'step' : undefined}>
      <span className="step__marker" aria-hidden="true">
        {marker(item)}
      </span>
      <span className="step__text">
        <span className="step__label">{stage.label}</span>
        <span className="step__state">{stateText(stage)}</span>
      </span>
    </div>
  );
}

/** SCR-02 ② 5단계 스테퍼 — 업로드·검증 → 전처리·ROI 추적 → 메인 모델 ∥ rPPG(병렬) → 융합 판정 */
export function StageStepper({ stages, canceled }: Props) {
  // 연속한 병렬 단계는 같은 칸으로 모은다
  const columns: NumberedStage[][] = [];
  stages.forEach((stage, index) => {
    const item = { stage, number: index + 1 };
    const last = columns[columns.length - 1];
    if (last && PARALLEL.includes(stage.key) && PARALLEL.includes(last[0].stage.key)) last.push(item);
    else columns.push([item]);
  });

  return (
    <ol className={canceled ? 'stepper stepper--canceled' : 'stepper'} aria-label="분석 단계">
      {columns.map((column) => (
        <li
          key={column[0].stage.key}
          className={column.length > 1 ? 'stepper__col stepper__col--parallel' : 'stepper__col'}
        >
          {column.length > 1 && <span className="stepper__parallel">병렬 수행</span>}
          {column.map((item) => (
            <Step key={item.stage.key} {...item} />
          ))}
        </li>
      ))}
    </ol>
  );
}
