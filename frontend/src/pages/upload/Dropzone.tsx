import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { FORMAT_LABELS, MAX_VIDEO_MB, MIN_DURATION_SEC, VIDEO_ACCEPT } from '@/lib/videoFile';

interface Props {
  disabled: boolean;
  /** 파일을 이미 골랐으면 높이를 줄이고 버튼 문구를 바꾼다 */
  hasFile: boolean;
  onFiles: (files: File[]) => void;
}

/** SCR-01 ① 업로드 드롭존 — 드래그&드롭 또는 [파일 선택] */
export function Dropzone({ disabled, hasFile, onFiles }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [active, setActive] = useState(false);

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (disabled || !event.dataTransfer.types.includes('Files')) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    setActive(true);
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    // 자식 요소 위로 옮겨 갈 때도 dragleave가 오므로 영역을 실제로 벗어났을 때만 해제한다
    if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
    setActive(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setActive(false);
    if (disabled) return;
    const files = Array.from(event.dataTransfer.files);
    if (files.length > 0) onFiles(files);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    // 같은 파일을 다시 고를 수 있게 비운다
    event.target.value = '';
    if (files.length > 0) onFiles(files);
  }

  const className = ['dropzone', active && 'dropzone--active', hasFile && 'dropzone--compact', disabled && 'dropzone--disabled']
    .filter(Boolean)
    .join(' ');

  return (
    <div className={className} onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}>
      <span className="dropzone__icon" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
          <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
        </svg>
      </span>
      <p className="dropzone__title">
        {active ? '여기에 놓으면 선택됩니다' : '분석할 영상을 여기에 끌어다 놓으세요'}
      </p>
      <div className="row">
        <span className="muted">또는</span>
        <button type="button" className="btn" disabled={disabled} onClick={() => inputRef.current?.click()}>
          {hasFile ? '다른 파일 선택' : '파일 선택'}
        </button>
      </div>
      <input ref={inputRef} type="file" accept={VIDEO_ACCEPT} hidden onChange={handleChange} />
      <ul className="dropzone__guide">
        <li>지원 형식: {FORMAT_LABELS}</li>
        <li>최대 {MAX_VIDEO_MB}MB</li>
        <li>정면 얼굴이 {MIN_DURATION_SEC}초 이상 나오는 영상 권장</li>
      </ul>
    </div>
  );
}
