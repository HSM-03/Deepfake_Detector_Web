import { useEffect, useRef, type ReactNode } from 'react';

interface Props {
  open: boolean;
  title: string;
  /** 본문 안내 */
  children: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  /** 확인 처리 중이면 버튼을 잠근다 */
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 확인 대화상자 (SCR-02 분석 취소, SCR-05 삭제). 되돌릴 수 없는 동작 전에 띄운다. */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = '닫기',
  busy = false,
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="dialog"
      onCancel={(event) => {
        // Esc: 닫힘 상태는 부모의 open으로만 바꾼다
        event.preventDefault();
        if (!busy) onCancel();
      }}
    >
      <h2 className="section-title">{title}</h2>
      <div>{children}</div>
      <div className="dialog__actions">
        <button type="button" className="btn" disabled={busy} onClick={onCancel}>
          {cancelLabel}
        </button>
        <button type="button" className="btn btn--danger" disabled={busy} onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
