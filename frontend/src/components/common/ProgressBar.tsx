interface Props {
  /** 0~100 */
  value: number;
  /** 스크린 리더용 이름 (예: '업로드 진행률') */
  label: string;
  /** 취소 등 멈춘 상태면 회색으로 그린다 */
  muted?: boolean;
}

/** 진행률 바 (SCR-01 업로드, SCR-02 분석 진행) */
export function ProgressBar({ value, label, muted = false }: Props) {
  const percent = Math.min(100, Math.max(0, Math.round(value)));
  return (
    <div
      className={muted ? 'progress-bar progress-bar--muted' : 'progress-bar'}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="progress-bar__fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
