import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { getErrorMessage } from '@/api/client';
import { uploadVideo } from '@/api/jobs';
import { ProgressBar } from '@/components/common/ProgressBar';
import { paths } from '@/lib/paths';
import { checkDuration, checkFormat, checkSize, probeVideo, type ProbeState } from '@/lib/videoFile';
import { Dropzone } from './upload/Dropzone';
import { SelectedFileCard } from './upload/SelectedFileCard';
import './UploadPage.css';

/**
 * SCR-01 영상 업로드 (UC-01)
 * 형식·용량은 브라우저에서 바로 검증하고, 통과한 파일만 서버로 보낸다(대안 흐름 2a).
 */
export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [probe, setProbe] = useState<ProbeState>({ status: 'idle' });
  const [notice, setNotice] = useState<string | null>(null);
  const [memo, setMemo] = useState('');
  const [saveHistory, setSaveHistory] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const formatCheck = file ? checkFormat(file) : null;
  const sizeCheck = file ? checkSize(file) : null;
  const valid = formatCheck?.state === 'pass' && sizeCheck?.state === 'pass';

  // 드롭존을 벗어난 곳에 파일을 놓아도 브라우저가 그 파일을 열어 화면을 떠나지 않게 한다
  useEffect(() => {
    const prevent = (event: DragEvent) => event.preventDefault();
    window.addEventListener('dragover', prevent);
    window.addEventListener('drop', prevent);
    return () => {
      window.removeEventListener('dragover', prevent);
      window.removeEventListener('drop', prevent);
    };
  }, []);

  // 검증을 통과한 파일만 <video>로 열어 해상도·fps·길이·썸네일을 읽는다
  useEffect(() => {
    if (!file || !valid) {
      setProbe({ status: 'idle' });
      return;
    }
    let ignore = false;
    setProbe({ status: 'probing' });
    probeVideo(file)
      .catch(() => null)
      .then((result) => {
        if (!ignore) setProbe({ status: 'done', probe: result });
      });
    return () => {
      ignore = true;
    };
  }, [file, valid]);

  function handleFiles(files: File[]) {
    setFile(files[0]);
    setNotice(files.length > 1 ? '영상은 한 번에 1개만 분석할 수 있어 첫 번째 파일만 선택했습니다.' : null);
    setError(null);
  }

  function handleRemove() {
    setFile(null);
    setNotice(null);
    setError(null);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file || !valid || submitting) return;
    setSubmitting(true);
    setUploadPercent(0);
    setError(null);
    try {
      const { job_id } = await uploadVideo(
        { file, save_history: saveHistory, memo: memo.trim() || undefined },
        setUploadPercent,
      );
      navigate(paths.progress(job_id));
    } catch (err) {
      setError(getErrorMessage(err));
      setSubmitting(false);
    }
  }

  let hint = '영상을 선택하면 분석을 시작할 수 있습니다.';
  if (file) {
    hint = valid
      ? '업로드가 끝나면 분석 진행 화면으로 이동합니다.'
      : '형식·용량 조건에 맞는 영상을 다시 선택해 주세요.';
  }

  return (
    <section className="stack">
      <header className="page-header">
        <h1>영상 업로드</h1>
        <p className="muted">영상을 올리면 서로 다른 두 가지 근거로 진위를 판별하고, 그 이유까지 보여 드립니다.</p>
      </header>

      <form className="upload" onSubmit={handleSubmit}>
        <div className="stack">
          <Dropzone disabled={submitting} hasFile={file !== null} onFiles={handleFiles} />
          {notice && <p className="muted">{notice}</p>}
          {file && formatCheck && sizeCheck && (
            <SelectedFileCard
              file={file}
              probe={probe}
              checks={[
                { label: '형식', check: formatCheck },
                { label: '용량', check: sizeCheck },
                { label: '길이', check: checkDuration(probe) },
              ]}
              disabled={submitting}
              onRemove={handleRemove}
            />
          )}
        </div>

        <aside className="card stack">
          <h2 className="section-title">분석 옵션</h2>
          <div className="upload__field">
            <label className="row">
              <input
                type="checkbox"
                checked={saveHistory}
                disabled={submitting}
                onChange={(e) => setSaveHistory(e.target.checked)}
              />
              분석 이력에 저장
            </label>
            <small>
              {saveHistory ? '결과를 분석 이력에서 다시 볼 수 있습니다.' : '이 분석은 이력에 남기지 않습니다.'}
            </small>
          </div>
          <label className="upload__field">
            메모 (선택)
            <textarea
              className="input"
              rows={3}
              placeholder="예: 제보 영상 1차 확인"
              value={memo}
              disabled={submitting}
              onChange={(e) => setMemo(e.target.value)}
            />
            <small>분석 이력에서 메모로 검색할 수 있습니다.</small>
          </label>

          {error && (
            <p className="error-box" role="alert">
              {error}
            </p>
          )}
          {submitting && <ProgressBar value={uploadPercent} label="업로드 진행률" />}
          <button type="submit" className="btn btn--primary upload__submit" disabled={!valid || submitting}>
            {submitting ? `업로드 중… ${uploadPercent}%` : '분석 시작'}
          </button>
          <p className="upload__hint">{hint}</p>
          {import.meta.env.VITE_USE_MOCK === 'true' && (
            <p className="upload__hint">
              목 모드: 파일명에 fake / hold / fail / lowsqi 가 들어 있으면 해당 시나리오로, 그 외에는 '진짜'로 진행됩니다.
              이력 저장 옵션은 목 서버가 무시합니다.
            </p>
          )}
        </aside>
      </form>

      <ol className="upload-steps" aria-label="분석이 진행되는 방식">
        <li>
          <span className="upload-steps__number" aria-hidden="true">
            1
          </span>
          <div>
            <strong>영상 조작 흔적 찾기</strong>
            <span>메인 모델이 화면에 남은 합성 흔적(시각 아티팩트)을 찾습니다.</span>
          </div>
        </li>
        <li>
          <span className="upload-steps__number" aria-hidden="true">
            2
          </span>
          <div>
            <strong>생체신호 확인</strong>
            <span>얼굴 피부색의 미세한 변화에서 심박 신호(rPPG)를 뽑아 실제 사람다운지 봅니다.</span>
          </div>
        </li>
        <li>
          <span className="upload-steps__number" aria-hidden="true">
            3
          </span>
          <div>
            <strong>두 결과 교차검증</strong>
            <span>신호 품질에 따라 두 결과를 합쳐 진짜·가짜·판단 보류 중 하나로 판정합니다.</span>
          </div>
        </li>
      </ol>
    </section>
  );
}
