/**
 * SCR-04 판정 근거 상세용 목 데이터 생성기.
 * 시나리오의 주기성(periodicity)·잡음(noise) 값으로 rPPG 파형과 스펙트럼을 합성한다.
 * 실제 신호처리 결과가 아니라 차트 모양을 확인하기 위한 값이다.
 */
import type {
  EvidenceResponse,
  ModelSegment,
  PsdPoint,
  RoiKey,
  RoiSelector,
  SignalPoint,
  WindowBpm,
} from '@/types/api';
import { buildAxisSummary, computeScores, type JobRecord } from './db';
import { hashString, mulberry32 } from './random';
import { THRESHOLDS, type ScoredTemplate } from './scenarios';

const HR_BAND: [number, number] = [0.7, 4.0];
const ROI_KEYS: RoiKey[] = ['forehead', 'left_cheek', 'right_cheek'];
const round = (n: number, digits = 4) => Number(n.toFixed(digits));

function mean(values: number[]): number {
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function std(values: number[]): number {
  const m = mean(values);
  return Math.sqrt(mean(values.map((v) => (v - m) ** 2)));
}

export function buildEvidence(record: JobRecord, t: ScoredTemplate, roi: RoiSelector): EvidenceResponse {
  const rand = mulberry32(hashString(`${record.job_id}:${roi}`));
  const noise = () => (rand() - 0.5) * 2;

  const fs = t.video.fps;
  const duration = Math.min(t.video.duration_sec, 20);
  const validBpm = ROI_KEYS.map((k) => t.roi_bpm[k]).filter((v): v is number => v !== null);
  const bpm = roi === 'all' ? mean(validBpm) : t.roi_bpm[roi];
  const hz = (bpm ?? 0) / 60;
  const amp = bpm === null ? 0 : t.periodicity;

  /* 원신호: 느린 밝기 변동(드리프트) + 맥파 + 잡음 / 필터 후: 드리프트 제거 */
  const raw_signal: SignalPoint[] = [];
  const filtered_signal: SignalPoint[] = [];
  const total = Math.round(duration * fs);
  for (let i = 0; i < total; i++) {
    const time = i / fs;
    const pulse = amp * Math.sin(2 * Math.PI * hz * time);
    const drift = 0.8 * Math.sin(2 * Math.PI * 0.08 * time) + 0.3 * Math.sin(2 * Math.PI * 0.21 * time);
    raw_signal.push({ t: round(time, 3), v: round(pulse + drift + t.noise * 0.5 * noise()) });
    filtered_signal.push({ t: round(time, 3), v: round(pulse + t.noise * 0.22 * noise()) });
  }

  /* Welch 스펙트럼: 바닥 잡음 + 심박 피크(주기성이 약하면 여러 개의 작은 봉우리) */
  const lumps = Array.from({ length: 4 }, () => ({ hz: 0.8 + rand() * 3, power: 0.1 + rand() * 0.25 }));
  const psd: PsdPoint[] = [];
  for (let f = 0; f <= 5.0001; f += 0.05) {
    let power = 0.04 + 0.03 * rand() + 0.12 * t.noise * Math.exp(-f / 1.5) * rand();
    power += amp * amp * Math.exp(-((f - hz) ** 2) / (2 * 0.06 ** 2));
    if (t.periodicity < 0.5) {
      for (const lump of lumps) power += lump.power * t.noise * Math.exp(-((f - lump.hz) ** 2) / (2 * 0.12 ** 2));
    }
    psd.push({ hz: round(f, 2), power: round(power) });
  }
  const inBand = psd.filter((p) => p.hz >= HR_BAND[0] && p.hz <= HR_BAND[1]);
  const top = inBand.reduce((a, b) => (b.power > a.power ? b : a));
  const peak = bpm === null ? null : { hz: top.hz, bpm: Math.round(top.hz * 60), power: top.power };

  /* 8초 슬라이딩 윈도우 BPM (1초 간격) */
  const spread = t.periodicity >= 0.5 ? 1.5 : 22;
  const window_bpm: WindowBpm[] = [];
  for (let start = 0; start + 8 <= duration; start++) {
    window_bpm.push({ t_start: start, bpm: bpm === null ? null : Math.round(bpm + spread * noise()) });
  }

  /* 메인 모델 구간별 프로파일 (2초 구간) */
  const { p_model } = computeScores(record, t);
  const model_profile: ModelSegment[] = [];
  for (let start = 0; start < duration; start += 2) {
    const p = Math.min(1, Math.max(0, p_model + t.p_model_std * 1.2 * noise()));
    model_profile.push({ t_start: start, t_end: Math.min(start + 2, duration), p: round(p, 3) });
  }

  const axis_summary = buildAxisSummary(record, t);

  return {
    job_id: record.job_id,
    roi,
    fs,
    raw_signal,
    filtered_signal,
    psd,
    hr_band: HR_BAND,
    peak,
    roi_bpm: t.roi_bpm,
    roi_bpm_std: validBpm.length >= 2 ? round(std(validBpm), 1) : null,
    window_bpm,
    model_profile,
    features: t.features,
    axis_summary,
    rppg_low_contribution: axis_summary.sqi < THRESHOLDS.sqi_min,
  };
}
