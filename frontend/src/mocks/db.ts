/**
 * 목 서버의 메모리 DB.
 * 작업(JobRecord)을 저장하고, 경과 시간으로 진행 상태를 계산하며,
 * 시나리오 템플릿에서 status / result / 이력 목록 응답을 만들어 낸다.
 * 새로고침하면 초기 상태로 돌아간다.
 */
import type {
  DoneResult,
  FailedResult,
  HoldResult,
  JobListItem,
  JobLogEntry,
  JobResultResponse,
  JobState,
  JobStatusResponse,
  Review,
  SqiGrade,
  StageKey,
  StageState,
  StageStatus,
} from '@/types/api';
import { reviewStateOf } from '@/lib/verdict';
import { mulberry32 } from './random';
import { SCENARIOS, THRESHOLDS, type ScenarioKey, type ScoredTemplate } from './scenarios';

export interface JobRecord {
  job_id: string;
  scenario: ScenarioKey;
  filename: string;
  size_bytes: number;
  memo: string | null;
  /** 분석 시작 시각 (epoch ms) */
  started_at: number;
  /** 시뮬레이션 배속. 1이면 약 13.5초에 끝난다 */
  speed: number;
  canceled_at: number | null;
  review: Review | null;
  /** 이력 행마다 수치가 조금씩 달라 보이게 하는 편차 */
  jitter: { model: number; rppg: number; sqi: number };
}

/* ───────────── 진행 타임라인 (배속 1 기준, ms) ───────────── */

interface StageDef {
  key: StageKey;
  label: string;
  start: number;
  end: number;
  /** 전체 진행률에서 차지하는 비중(합 100) */
  weight: number;
  running: string;
}

const STAGES: StageDef[] = [
  { key: 'upload', label: '업로드·검증', start: 0, end: 1500, weight: 10, running: '파일 형식·용량을 검증하고 있습니다' },
  { key: 'preprocess', label: '전처리·ROI 추적', start: 1500, end: 5500, weight: 25, running: '프레임을 추출하고 얼굴 ROI를 추적하고 있습니다' },
  { key: 'model', label: '메인 모델 판별', start: 5500, end: 10500, weight: 25, running: '메인 모델과 rPPG 분석을 병렬로 수행하고 있습니다' },
  { key: 'rppg', label: 'rPPG 신호 분석', start: 5500, end: 11500, weight: 25, running: 'rPPG 신호를 분석하고 있습니다' },
  { key: 'fusion', label: '융합 판정', start: 11500, end: 13500, weight: 15, running: 'SQI를 산출하고 두 축을 융합하고 있습니다' },
];
const TOTAL_MS = 13500;
/** 'failed' 시나리오는 전처리 도중 이 시점에 중단된다 */
const FAIL_AT_MS = 4500;

const round3 = (n: number) => Math.round(n * 1000) / 1000;
const clamp01 = (n: number) => Math.min(1, Math.max(0, n));
const iso = (ms: number) => new Date(ms).toISOString();

/* ───────────── 점수 계산 ───────────── */

interface Scores {
  p_model: number;
  p_rppg: number;
  sqi: number;
  w: number;
  gap: number;
  score: number;
}

function sqiGrade(value: number): SqiGrade {
  if (value >= 0.7) return 'good';
  if (value >= THRESHOLDS.sqi_min) return 'fair';
  return 'poor';
}

export function computeScores(record: JobRecord, t: ScoredTemplate): Scores {
  const p_model = round3(clamp01(t.p_model + record.jitter.model));
  const p_rppg = round3(clamp01(t.p_rppg + record.jitter.rppg));
  const sqi = round3(clamp01(t.sqi + record.jitter.sqi));
  const w = round3(THRESHOLDS.alpha * sqi);
  return {
    p_model,
    p_rppg,
    sqi,
    w,
    gap: round3(Math.abs(p_model - p_rppg)),
    // S = (1 − w)·P_model + w·P_rppg
    score: round3((1 - w) * p_model + w * p_rppg),
  };
}

function axisText(scenario: ScenarioKey, s: Scores): string {
  const f = (n: number) => n.toFixed(2);
  if (scenario === 'low_sqi') {
    return `SQI(${f(s.sqi)})가 하한(${f(THRESHOLDS.sqi_min)}) 미만이라 rPPG 축 기여도가 0에 근접합니다(w = ${f(s.w)}). 본 판정은 사실상 메인 모델 단독 결과입니다.`;
  }
  if (scenario === 'hold') {
    return `메인 모델은 진짜 쪽(${f(s.p_model)}), rPPG 축은 가짜 쪽(${f(s.p_rppg)})으로 평가했습니다. 축 간 차이 ${f(s.gap)}로 상충 임계(${f(THRESHOLDS.conflict_gap)}) 이상이며 SQI(${f(s.sqi)})는 하한(${f(THRESHOLDS.sqi_min)})을 넘습니다.`;
  }
  const level = scenario === 'fake' ? '높게' : '낮게';
  return `두 축 모두 조작 가능성을 ${level} 평가했습니다. 축 간 차이 ${f(s.gap)}로 상충 임계(${f(THRESHOLDS.conflict_gap)}) 미만입니다.`;
}

/** 근거 화면(SCR-04)의 '두 축 대조 요약' */
export function buildAxisSummary(record: JobRecord, t: ScoredTemplate) {
  const s = computeScores(record, t);
  return { p_model: s.p_model, p_rppg: s.p_rppg, w: s.w, sqi: s.sqi, text: axisText(record.scenario, s) };
}

/* ───────────── 저장소 ───────────── */

const records = new Map<string, JobRecord>();

const NO_JITTER = { model: 0, rppg: 0, sqi: 0 };
const HOUR = 3600_000;
const DAY = 24 * HOUR;

/** 고정 ID 목 작업. URL로 바로 열어 볼 수 있다(CLAUDE.md 참고). */
export const FIXTURE_IDS = {
  real: 'job-real-0001',
  fake: 'job-fake-0002',
  hold: 'job-hold-0003',
  failed: 'job-failed-0004',
  low_sqi: 'job-lowsqi-0005',
  running: 'job-running-0006',
} as const;

function seed() {
  const now = Date.now();
  const fixed: Array<[string, ScenarioKey, string, number, number, string | null, number]> = [
    [FIXTURE_IDS.real, 'real', 'interview_original.mp4', 48_300_000, 2 * HOUR, '원본 인터뷰 영상', 1],
    [FIXTURE_IDS.fake, 'fake', 'suspicious_clip.mp4', 31_900_000, 5 * HOUR, '제보 영상 — SNS 유포본', 1],
    [FIXTURE_IDS.hold, 'hold', 'press_conference_cut.mov', 72_400_000, 1 * DAY, '기자회견 편집본', 1],
    [FIXTURE_IDS.failed, 'failed', 'landscape_drone.mp4', 120_800_000, 1 * DAY + 3 * HOUR, null, 1],
    [FIXTURE_IDS.low_sqi, 'low_sqi', 'messenger_forward_240p.mp4', 2_100_000, 2 * DAY, '메신저 전달본(저화질)', 1],
    // 이력 화면의 '진행 중' 행 확인용: 아주 느리게(약 5분) 진행된다
    [FIXTURE_IDS.running, 'real', 'live_stream_capture.webm', 88_000_000, 60_000, null, 0.045],
  ];
  for (const [job_id, scenario, filename, size_bytes, ago, memo, speed] of fixed) {
    records.set(job_id, {
      job_id,
      scenario,
      filename,
      size_bytes,
      memo,
      started_at: now - ago,
      speed,
      canceled_at: null,
      review: null,
      jitter: NO_JITTER,
    });
  }

  // 검색·필터·페이지네이션 확인용 추가 이력 18건
  const rand = mulberry32(20260930);
  const cycle: ScenarioKey[] = ['real', 'fake', 'real', 'hold', 'fake', 'low_sqi', 'real', 'failed', 'fake'];
  for (let i = 0; i < 18; i++) {
    const scenario = cycle[i % cycle.length];
    const job_id = `job-sample-${String(i + 7).padStart(4, '0')}`;
    const j = () => round3((rand() - 0.5) * 0.06);
    records.set(job_id, {
      job_id,
      scenario,
      filename: `sample_${String(i + 1).padStart(2, '0')}_${scenario}.mp4`,
      size_bytes: Math.round(10_000_000 + rand() * 90_000_000),
      memo: i % 4 === 0 ? `검증 요청 #${100 + i}` : null,
      started_at: now - (3 + i * 1.5) * DAY - Math.round(rand() * 8 * HOUR),
      speed: 1,
      canceled_at: null,
      // 보류 건 셋의 검토 상태를 하나씩 다르게 둔다: job-hold-0003은 검토 대기,
      // 이 중 하나(i=3)는 검토 완료, 다른 하나(i=12)는 추가 검토 필요
      review:
        scenario === 'hold' && i === 3
          ? { decision: 'fake', reason: '원본 출처 확인 결과 합성본으로 판명', reviewed_at: iso(now - 2 * DAY) }
          : scenario === 'hold' && i === 12
            ? { decision: 'needs_more_review', reason: '원본 영상 확보 후 다시 판단', reviewed_at: iso(now - 1 * DAY) }
            : null,
      jitter: { model: j(), rppg: j(), sqi: j() },
    });
  }
}
seed();

export function getRecord(jobId: string): JobRecord | undefined {
  return records.get(jobId);
}

export function createRecord(input: {
  scenario: ScenarioKey;
  filename: string;
  size_bytes: number;
  memo: string | null;
}): JobRecord {
  const job_id = `job-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
  const record: JobRecord = {
    job_id,
    ...input,
    started_at: Date.now(),
    speed: 1,
    canceled_at: null,
    review: null,
    jitter: NO_JITTER,
  };
  records.set(job_id, record);
  return record;
}

export function deleteRecord(jobId: string): boolean {
  return records.delete(jobId);
}

/* ───────────── status ───────────── */

function stageLog(record: JobRecord, key: StageKey): string {
  const t = SCENARIOS[record.scenario];
  const v = t.video;
  switch (key) {
    case 'upload':
      return `업로드·검증 완료 — ${v.codec.toUpperCase()}, ${v.width}×${v.height}, ${v.fps}fps, ${v.duration_sec.toFixed(1)}초`;
    case 'preprocess':
      return `전처리 완료 — ${v.frame_count}프레임, 얼굴 검출률 98.6%, ROI 3개 추적`;
    case 'model':
      return t.kind === 'scored'
        ? `메인 모델 판별 완료 — P_model = ${computeScores(record, t).p_model.toFixed(2)}`
        : '메인 모델 판별 완료';
    case 'rppg':
      return t.kind === 'scored'
        ? `rPPG 분석 완료 — P_rppg = ${computeScores(record, t).p_rppg.toFixed(2)}`
        : 'rPPG 분석 완료';
    case 'fusion':
      return t.kind === 'scored'
        ? `융합 판정 완료 — SQI = ${computeScores(record, t).sqi.toFixed(2)}, w = ${computeScores(record, t).w.toFixed(2)}`
        : '융합 판정 완료';
  }
}

export function computeStatus(record: JobRecord, now = Date.now()): JobStatusResponse {
  const willFail = record.scenario === 'failed';
  const endMs = willFail ? FAIL_AT_MS : TOTAL_MS;
  const canceled = record.canceled_at !== null;
  const elapsed = ((record.canceled_at ?? now) - record.started_at) * record.speed;
  const t = Math.min(elapsed, endMs);
  const finished = !canceled && elapsed >= endMs;

  let state: JobState = 'running';
  if (canceled) state = 'canceled';
  else if (finished) state = willFail ? 'failed' : record.scenario === 'hold' ? 'hold' : 'done';

  const logs: JobLogEntry[] = [];
  let progress = 0;
  let current: StageDef | null = null;

  const stages: StageStatus[] = STAGES.map((def) => {
    const p = clamp01((t - def.start) / (def.end - def.start));
    progress += def.weight * p;

    let stageState: StageState = p >= 1 ? 'done' : p > 0 ? 'running' : 'waiting';
    if (stageState === 'running') {
      if (canceled) stageState = 'canceled';
      else if (finished && willFail) stageState = 'failed';
      else current ??= def;
    }
    if (stageState === 'done') {
      logs.push({ at: iso(record.started_at + def.end / record.speed), stage: def.key, message: stageLog(record, def.key) });
    }
    if (stageState === 'failed') {
      logs.push({
        at: iso(record.started_at + FAIL_AT_MS / record.speed),
        stage: def.key,
        message: '얼굴 검출 프레임 5.3% < 기준 80% — 분석을 중단합니다',
      });
    }
    return { key: def.key, label: def.label, state: stageState, progress: Math.round(p * 100) };
  });
  logs.sort((a, b) => a.at.localeCompare(b.at));

  const running = current as StageDef | null;
  let message = running?.running ?? '';
  if (state === 'canceled') message = '분석이 취소되었습니다';
  else if (state === 'failed') message = '분석을 계속할 수 없어 중단했습니다';
  else if (state === 'done' || state === 'hold') message = '분석이 완료되었습니다';

  return {
    job_id: record.job_id,
    filename: record.filename,
    created_at: iso(record.started_at),
    state,
    progress: Math.round(progress),
    current_stage: running?.key ?? null,
    message,
    stages,
    logs,
    eta_seconds: state === 'running' ? Math.ceil((endMs - t) / record.speed / 1000) : null,
    result_type: state === 'done' || state === 'failed' || state === 'hold' ? state : null,
  };
}

/** 진행 중이면 취소하고 true. 이미 종료된 작업이면 false */
export function cancelRecord(record: JobRecord): boolean {
  if (computeStatus(record).state !== 'running') return false;
  record.canceled_at = Date.now();
  return true;
}

/* ───────────── result ───────────── */

/** 분석이 끝난 작업의 결과. 아직 진행 중이거나 취소된 작업이면 null */
export function buildResult(record: JobRecord): JobResultResponse | null {
  const status = computeStatus(record);
  if (status.result_type === null) return null;

  const t = SCENARIOS[record.scenario];
  const endMs = t.kind === 'failed' ? FAIL_AT_MS : TOTAL_MS;
  const base = {
    job_id: record.job_id,
    created_at: iso(record.started_at),
    completed_at: iso(record.started_at + endMs / record.speed),
    video: { ...t.video, filename: record.filename, size_bytes: record.size_bytes },
    memo: record.memo,
  };

  if (t.kind === 'failed') {
    const failed: FailedResult = { ...base, result_type: 'failed', failure: t.failure };
    return failed;
  }

  const s = computeScores(record, t);
  const scored = {
    p_model: s.p_model,
    p_model_std: t.p_model_std,
    p_rppg: s.p_rppg,
    p_rppg_provisional: false, // 목 시나리오는 P_rppg가 따로 있다
    w: s.w,
    sqi: { value: s.sqi, grade: sqiGrade(s.sqi), components: t.sqi_components },
    roi_bpm: t.roi_bpm,
    thresholds: THRESHOLDS,
    interpretation: t.interpretation,
  };

  if (record.scenario === 'hold') {
    const hold: HoldResult = {
      ...base,
      ...scored,
      result_type: 'hold',
      verdict: 'hold',
      score: null,
      axis_gap: s.gap,
      review: record.review,
    };
    return hold;
  }

  const done: DoneResult = {
    ...base,
    ...scored,
    result_type: 'done',
    verdict: s.score >= THRESHOLDS.score_fake_min ? 'fake' : 'real',
    score: s.score,
    rppg_low_contribution: s.sqi < THRESHOLDS.sqi_min,
  };
  return done;
}

/* ───────────── 이력 목록 ───────────── */

export function toListItem(record: JobRecord): JobListItem {
  const status = computeStatus(record);
  const result = buildResult(record);
  const item: JobListItem = {
    job_id: record.job_id,
    filename: record.filename,
    created_at: status.created_at,
    state: status.state,
    verdict: null,
    score: null,
    p_model: null,
    p_rppg: null,
    sqi: null,
    review_state: 'none',
    memo: record.memo,
    progress: status.progress,
  };
  if (result && result.result_type !== 'failed') {
    item.verdict = result.verdict;
    item.score = result.score;
    item.p_model = result.p_model;
    item.p_rppg = result.p_rppg;
    item.sqi = result.sqi.value;
    if (result.result_type === 'hold') {
      item.review_state = reviewStateOf(result.review);
    }
  }
  return item;
}

/** 최신순 전체 이력 */
export function listItems(): JobListItem[] {
  return [...records.values()].map(toListItem).sort((a, b) => b.created_at.localeCompare(a.created_at));
}
