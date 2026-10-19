/**
 * 목 시나리오 5종.
 * 화면 분기(SCR-03 / 06 / 07)와 경고 상태(SQI 낮음)를 모두 확인할 수 있는 최소 집합이다.
 *
 * ※ 여기의 점수·BPM·임계값은 전부 화면 확인용 예시 값이다(화면설계서 5장 주석과 동일).
 */
import type {
  FailureInfo,
  FeatureRow,
  RoiBpm,
  SqiInfo,
  Thresholds,
  VideoMeta,
} from '@/types/api';

export type ScenarioKey = 'real' | 'fake' | 'hold' | 'failed' | 'low_sqi';

/** 판정 임계값 (예시). 실제 값은 성능 평가 실험으로 확정 */
export const THRESHOLDS: Thresholds = {
  score_real_max: 0.4,
  score_fake_min: 0.6,
  conflict_gap: 0.4,
  sqi_min: 0.5,
  alpha: 0.5,
};

export interface ScoredTemplate {
  kind: 'scored';
  label: string;
  video: Omit<VideoMeta, 'filename' | 'size_bytes'>;
  p_model: number;
  p_model_std: number;
  p_rppg: number;
  sqi: number;
  sqi_components: SqiInfo['components'];
  roi_bpm: RoiBpm;
  interpretation: string;
  /** rPPG 신호의 주기성 강도 0~1 (근거 차트 생성용) */
  periodicity: number;
  /** 근거 차트 잡음 크기 */
  noise: number;
  features: FeatureRow[];
}

export interface FailedTemplate {
  kind: 'failed';
  label: string;
  video: Omit<VideoMeta, 'filename' | 'size_bytes'>;
  failure: FailureInfo;
}

export type ScenarioTemplate = ScoredTemplate | FailedTemplate;

const VIDEO_FHD = {
  width: 1920,
  height: 1080,
  fps: 30,
  duration_sec: 24.0,
  frame_count: 720,
  codec: 'h264',
};

function feature(
  key: FeatureRow['key'],
  label: string,
  value: number,
  display: string,
  reference: string,
  judgement: FeatureRow['judgement'],
  conflict_source = false,
): FeatureRow {
  return { key, label, value, display, reference, judgement, conflict_source };
}

export const SCENARIOS: Record<ScenarioKey, ScenarioTemplate> = {
  /* ① 진짜 — 두 축이 모두 낮은 조작 확률, SQI 양호 */
  real: {
    kind: 'scored',
    label: '진짜',
    video: VIDEO_FHD,
    p_model: 0.22,
    p_model_std: 0.05,
    p_rppg: 0.12,
    sqi: 0.82,
    sqi_components: { face_pixels: 0.91, compression: 0.78, illumination: 0.84, motion: 0.75 },
    roi_bpm: { forehead: 72, left_cheek: 73, right_cheek: 71 },
    interpretation:
      '시각 아티팩트가 거의 없고, 세 ROI에서 일관된 심박 신호(약 72 BPM)가 검출되었습니다. 실제 촬영 영상일 가능성이 높습니다.',
    periodicity: 1,
    noise: 0.25,
    features: [
      feature('hr_in_range', '심박수 생리학적 범위', 1, '72 BPM', '45~180 BPM', 'ok'),
      feature('snr', '주 피크 SNR', 8.4, '8.4 dB', '≥ 3 dB', 'ok'),
      feature('spectral_entropy', '스펙트럼 엔트로피', 0.41, '0.41', '≤ 0.60', 'ok'),
      feature('roi_bpm_std', 'ROI 간 심박수 일치도', 0.8, 'σ = 0.8 BPM', 'σ ≤ 5 BPM', 'ok'),
      feature('phase_consistency', 'ROI 간 신호 일치도(위상 일관성)', 0.88, '0.88', '≥ 0.70', 'ok'),
      feature('window_bpm_var', '윈도우별 BPM 변동성', 1.6, 'σ = 1.6 BPM', 'σ ≤ 6 BPM', 'ok'),
    ],
  },

  /* ② 가짜 — 두 축이 모두 높은 조작 확률, ROI 간 심박 불일치 */
  fake: {
    kind: 'scored',
    label: '가짜',
    video: VIDEO_FHD,
    p_model: 0.71,
    p_model_std: 0.11,
    p_rppg: 0.88,
    sqi: 0.76,
    sqi_components: { face_pixels: 0.88, compression: 0.71, illumination: 0.79, motion: 0.66 },
    roi_bpm: { forehead: 64, left_cheek: 97, right_cheek: 118 },
    interpretation:
      '얼굴 경계에서 합성 흔적이 관찰되고, 세 ROI의 추정 심박이 서로 크게 다릅니다(64 / 97 / 118 BPM). 합성 영상일 가능성이 높습니다.',
    periodicity: 0.12,
    noise: 0.9,
    features: [
      feature('hr_in_range', '심박수 생리학적 범위', 1, '93 BPM', '45~180 BPM', 'ok'),
      feature('snr', '주 피크 SNR', 0.9, '0.9 dB', '≥ 3 dB', 'bad'),
      feature('spectral_entropy', '스펙트럼 엔트로피', 0.87, '0.87', '≤ 0.60', 'bad'),
      feature('roi_bpm_std', 'ROI 간 심박수 일치도', 22.2, 'σ = 22.2 BPM', 'σ ≤ 5 BPM', 'bad'),
      feature('phase_consistency', 'ROI 간 신호 일치도(위상 일관성)', 0.31, '0.31', '≥ 0.70', 'bad'),
      feature('window_bpm_var', '윈도우별 BPM 변동성', 19.5, 'σ = 19.5 BPM', 'σ ≤ 6 BPM', 'bad'),
    ],
  },

  /* ③ 판단 보류 — SQI는 충분한데 두 축이 크게 상충 */
  hold: {
    kind: 'scored',
    label: '판단 보류',
    video: VIDEO_FHD,
    p_model: 0.21,
    p_model_std: 0.06,
    p_rppg: 0.83,
    sqi: 0.79,
    sqi_components: { face_pixels: 0.9, compression: 0.74, illumination: 0.81, motion: 0.72 },
    roi_bpm: { forehead: 58, left_cheek: 104, right_cheek: 131 },
    interpretation:
      '신호 품질은 충분하지만 메인 모델은 진짜 쪽, rPPG 축은 가짜 쪽으로 판단해 두 축이 크게 상충합니다. 임의로 한쪽을 택하지 않고 판단을 보류합니다.',
    periodicity: 0.18,
    noise: 0.8,
    features: [
      feature('hr_in_range', '심박수 생리학적 범위', 1, '98 BPM', '45~180 BPM', 'ok'),
      feature('snr', '주 피크 SNR', 1.4, '1.4 dB', '≥ 3 dB', 'bad', true),
      feature('spectral_entropy', '스펙트럼 엔트로피', 0.79, '0.79', '≤ 0.60', 'warn'),
      feature('roi_bpm_std', 'ROI 간 심박수 일치도', 30.1, 'σ = 30.1 BPM', 'σ ≤ 5 BPM', 'bad', true),
      feature('phase_consistency', 'ROI 간 신호 일치도(위상 일관성)', 0.36, '0.36', '≥ 0.70', 'bad', true),
      feature('window_bpm_var', '윈도우별 BPM 변동성', 12.8, 'σ = 12.8 BPM', 'σ ≤ 6 BPM', 'warn'),
    ],
  },

  /* ④ 분석 불가 — 전처리 단계에서 얼굴 미검출로 중단 */
  failed: {
    kind: 'failed',
    label: '분석 불가',
    video: VIDEO_FHD,
    failure: {
      code: 'FACE_NOT_DETECTED',
      title: '영상에서 얼굴을 충분히 검출하지 못했습니다',
      stopped_stage: 'preprocess',
      stopped_stage_index: 2,
      checks: [
        { label: '얼굴 검출 프레임 비율', measured: '5.3%', criterion: '80% 이상', passed: false },
        { label: '평균 얼굴 크기', measured: '42×48px', criterion: '80×80px 이상', passed: false },
        { label: '영상 길이', measured: '24.0초', criterion: '10초 이상', passed: true },
      ],
      suggestions: [
        '정면 얼굴이 10초 이상 연속으로 나오는 구간을 사용해 주세요.',
        '720p 이상 해상도의 영상을 권장합니다.',
        '얼굴이 화면에서 충분히 크게 보이도록 잘라낸 뒤 다시 업로드해 주세요.',
      ],
    },
  },

  /* ⑤ SQI 낮음 — w≈0, 사실상 메인 모델 단독 판정 */
  low_sqi: {
    kind: 'scored',
    label: '가짜 (SQI 낮음)',
    video: { width: 426, height: 240, fps: 24, duration_sec: 18.5, frame_count: 444, codec: 'h264' },
    p_model: 0.68,
    p_model_std: 0.14,
    p_rppg: 0.35,
    sqi: 0.18,
    sqi_components: { face_pixels: 0.12, compression: 0.15, illumination: 0.31, motion: 0.22 },
    roi_bpm: { forehead: 88, left_cheek: null, right_cheek: 141 },
    interpretation:
      '화질이 낮아 생체신호 축의 신뢰도가 떨어집니다. rPPG 기여도 낮음 — 메인 모델 중심 판정입니다.',
    periodicity: 0.25,
    noise: 1.4,
    features: [
      feature('hr_in_range', '심박수 생리학적 범위', 1, '88 BPM', '45~180 BPM', 'ok'),
      feature('snr', '주 피크 SNR', 1.1, '1.1 dB', '≥ 3 dB', 'bad'),
      feature('spectral_entropy', '스펙트럼 엔트로피', 0.91, '0.91', '≤ 0.60', 'bad'),
      feature('roi_bpm_std', 'ROI 간 심박수 일치도', 26.5, 'σ = 26.5 BPM', 'σ ≤ 5 BPM', 'bad'),
      feature('phase_consistency', 'ROI 간 신호 일치도(위상 일관성)', 0.44, '0.44', '≥ 0.70', 'warn'),
      feature('window_bpm_var', '윈도우별 BPM 변동성', 15.2, 'σ = 15.2 BPM', 'σ ≤ 6 BPM', 'bad'),
    ],
  },
};

/** 업로드 파일명에 들어 있는 키워드로 시나리오를 고른다(목 전용 규칙). 해당 없으면 'real' */
export function scenarioFromFilename(filename: string): ScenarioKey {
  const name = filename.toLowerCase();
  if (name.includes('lowsqi') || name.includes('low_sqi')) return 'low_sqi';
  if (name.includes('fake')) return 'fake';
  if (name.includes('hold')) return 'hold';
  if (name.includes('fail') || name.includes('noface')) return 'failed';
  return 'real';
}
