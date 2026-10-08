/**
 * SCR-01의 브라우저 1차 검증과 영상 정보 읽기 (UC-01).
 * 형식·용량은 파일 객체만으로 바로 판단하고, 해상도·fps·길이·썸네일은 <video>로 읽는다.
 */
import { formatBytes, formatDuration } from './format';

/** 지원 형식 (확장자 → 표시 이름). 화면설계서 SCR-01 ① */
const FORMATS: Record<string, string> = { mp4: 'MP4', mov: 'MOV', avi: 'AVI', webm: 'WebM' };
export const FORMAT_LABELS = Object.values(FORMATS).join(' · ');
export const VIDEO_ACCEPT = '.mp4,.mov,.avi,.webm,video/mp4,video/quicktime,video/x-msvideo,video/webm';

export const MAX_VIDEO_MB = 500;
const MAX_VIDEO_BYTES = MAX_VIDEO_MB * 1024 * 1024;
/** 권장 최소 길이. 미만이면 서버에서 분석 불가(VIDEO_TOO_SHORT)로 끝난다 */
export const MIN_DURATION_SEC = 10;

const THUMBNAIL_WIDTH = 320;
const LOAD_TIMEOUT_MS = 8000;
const SEEK_TIMEOUT_MS = 5000;
const FPS_SAMPLE_FRAMES = 12;
const FPS_TIMEOUT_MS = 2500;

/** pass ✓ / fail × / warn △ / pending 확인 중 / unknown 확인 불가 */
export type CheckState = 'pass' | 'fail' | 'warn' | 'pending' | 'unknown';

export interface FileCheck {
  state: CheckState;
  text: string;
}

/** <video>로 읽은 영상 정보. 읽지 못한 항목은 null */
export interface VideoProbe {
  width: number | null;
  height: number | null;
  durationSec: number | null;
  /** 프레임 표시 시각 간격으로 추정한 값 */
  fps: number | null;
  thumbnailUrl: string | null;
}

/** probe가 null이면 브라우저가 디코딩하지 못한 영상 (AVI 등) */
export type ProbeState = { status: 'idle' } | { status: 'probing' } | { status: 'done'; probe: VideoProbe | null };

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.');
  return dot < 0 ? '' : filename.slice(dot + 1).toLowerCase();
}

export function checkFormat(file: File): FileCheck {
  const ext = extensionOf(file.name);
  const label = FORMATS[ext];
  if (label) return { state: 'pass', text: label };
  return {
    state: 'fail',
    text: `지원하지 않는 형식입니다${ext ? `(.${ext})` : ''}. MP4·MOV·AVI·WebM 영상만 올릴 수 있습니다.`,
  };
}

export function checkSize(file: File): FileCheck {
  if (file.size === 0) return { state: 'fail', text: '빈 파일입니다(0바이트).' };
  if (file.size > MAX_VIDEO_BYTES) {
    return { state: 'fail', text: `${formatBytes(file.size)} — 최대 ${MAX_VIDEO_MB}MB를 넘습니다.` };
  }
  return { state: 'pass', text: `${formatBytes(file.size)} (최대 ${MAX_VIDEO_MB}MB)` };
}

/** 길이는 권장 조건이라 미달이어도 실패가 아닌 주의로 둔다 */
export function checkDuration(probe: ProbeState): FileCheck {
  if (probe.status === 'idle') return { state: 'unknown', text: '—' };
  if (probe.status === 'probing') return { state: 'pending', text: '확인 중…' };
  const duration = probe.probe?.durationSec ?? null;
  if (duration === null) {
    return { state: 'unknown', text: '브라우저에서 확인할 수 없습니다. 서버 분석 단계에서 확인합니다.' };
  }
  if (duration < MIN_DURATION_SEC) {
    return {
      state: 'warn',
      text: `${formatDuration(duration)} — ${MIN_DURATION_SEC}초 미만 영상은 분석 불가로 끝날 수 있습니다.`,
    };
  }
  return { state: 'pass', text: `${formatDuration(duration)} (${MIN_DURATION_SEC}초 이상 권장)` };
}

/** 이벤트를 기다린다. 오류나 시간 초과면 false */
function waitFor(video: HTMLVideoElement, event: string, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    const done = (ok: boolean) => {
      window.clearTimeout(timer);
      video.removeEventListener(event, onOk);
      video.removeEventListener('error', onFail);
      resolve(ok);
    };
    const onOk = () => done(true);
    const onFail = () => done(false);
    const timer = window.setTimeout(onFail, timeoutMs);
    video.addEventListener(event, onOk);
    video.addEventListener('error', onFail);
  });
}

function captureFrame(video: HTMLVideoElement): string | null {
  const scale = Math.min(1, THUMBNAIL_WIDTH / video.videoWidth);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  try {
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.8);
  } catch {
    return null;
  }
}

/**
 * 브라우저는 fps를 직접 알려 주지 않는다. 잠깐 재생하면서 프레임 표시 시각(mediaTime)의
 * 간격을 모아 중앙값으로 추정한다. requestVideoFrameCallback이 없으면 null.
 */
function estimateFps(video: HTMLVideoElement): Promise<number | null> {
  if (!('requestVideoFrameCallback' in video)) return Promise.resolve(null);
  return new Promise((resolve) => {
    const times: number[] = [];
    let finished = false;

    const finish = () => {
      if (finished) return;
      finished = true;
      window.clearTimeout(timer);
      video.pause();
      const gaps = times
        .slice(1)
        .map((t, i) => t - times[i])
        .filter((gap) => gap > 0)
        .sort((a, b) => a - b);
      if (gaps.length < 3) return resolve(null);
      const fps = 1 / gaps[Math.floor(gaps.length / 2)];
      resolve(fps >= 1 && fps <= 240 ? Math.round(fps * 100) / 100 : null);
    };

    const onFrame: VideoFrameRequestCallback = (_now, meta) => {
      if (finished) return;
      times.push(meta.mediaTime);
      if (times.length >= FPS_SAMPLE_FRAMES) finish();
      else video.requestVideoFrameCallback(onFrame);
    };

    const timer = window.setTimeout(finish, FPS_TIMEOUT_MS);
    video.requestVideoFrameCallback(onFrame);
    video.play().catch(finish);
  });
}

/** 영상의 해상도·길이·fps·썸네일을 읽는다. 브라우저가 디코딩하지 못하면 null */
export async function probeVideo(file: File): Promise<VideoProbe | null> {
  const url = URL.createObjectURL(file);
  const video = document.createElement('video');
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  try {
    const loaded = waitFor(video, 'loadedmetadata', LOAD_TIMEOUT_MS);
    video.src = url;
    if (!(await loaded)) return null;

    // MediaRecorder로 녹화한 WebM 등은 길이가 Infinity로 나온다. 끝으로 탐색하면 실제 길이가 채워진다.
    if (!Number.isFinite(video.duration)) {
      const seeked = waitFor(video, 'seeked', SEEK_TIMEOUT_MS);
      video.currentTime = Number.MAX_SAFE_INTEGER;
      await seeked;
    }
    const durationSec = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : null;

    if (video.videoWidth === 0 || video.videoHeight === 0) {
      return { width: null, height: null, durationSec, fps: null, thumbnailUrl: null };
    }

    // 첫 프레임은 검은 화면인 경우가 많아 조금 뒤의 프레임을 썸네일로 쓴다
    const seeked = waitFor(video, 'seeked', SEEK_TIMEOUT_MS);
    video.currentTime = Math.min(1, (durationSec ?? 0) / 4);
    const thumbnailUrl = (await seeked) ? captureFrame(video) : null;
    const fps = await estimateFps(video);

    return { width: video.videoWidth, height: video.videoHeight, durationSec, fps, thumbnailUrl };
  } finally {
    video.pause();
    video.removeAttribute('src');
    video.load();
    URL.revokeObjectURL(url);
  }
}
