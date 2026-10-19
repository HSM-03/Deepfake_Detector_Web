"""
SQI(신호품질지수, 상세제안서 기능 6) — rPPG 신호를 믿을 만한 촬영 조건인지 0~1로 낸다. 1에 가까울수록 좋다.

네 항목(API SqiInfo.components)을 각각 0~1로 매기고, **가장 낮은 항목이 SQI**다(가장 약한 고리).
압축이 망가지면 다른 조건이 좋아도 신호가 없으므로 평균으로 합치지 않는다.
  compression   파일 정보(코덱 + 영상 스트림 bpp)로 판단 — 신호(SNR·σ)로 판단하지 않는다(docs/backend-plan.md 4단계)
  face_pixels   얼굴 피부 ROI의 프레임당 평균 픽셀 수
  illumination  피부 평균 밝기와 프레임 간 밝기 변동 — 둘 중 낮은 쪽
  motion        머리 이동과 입·턱 움직임(입 벌림 변화) — 둘 중 낮은 쪽 (화면 문구: "머리·얼굴 움직임")
기준값은 전부 settings.py의 예시값이다.
"""
from dataclasses import dataclass

import numpy as np

from . import dsp, settings
from .rppg import RoiTraces
from .stream_info import StreamInfo


@dataclass
class SqiResult:
    value: float
    grade: str  # 'good' | 'fair' | 'poor'
    components: dict[str, float]  # face_pixels, compression, illumination, motion
    measures: dict[str, float | str | None]  # 점수를 매긴 측정값 (로그·근거 표시용)

    @property
    def weakest(self) -> str:
        return min(self.components, key=self.components.get)


def _ramp(x: float, zero_at: float, one_at: float, log: bool = False) -> float:
    """x가 zero_at이면 0, one_at이면 1인 직선(log=True면 로그 눈금). 방향은 두 값의 크기로 정해진다. 0~1로 자른다"""
    if x is None or not np.isfinite(x):
        return 0.0
    if log:
        if x <= 0:
            return 0.0
        x, zero_at, one_at = np.log(x), np.log(zero_at), np.log(one_at)
    return float(np.clip((x - zero_at) / (one_at - zero_at), 0.0, 1.0))


def compression_score(codec: str, bpp: float | None) -> tuple[float, str]:
    """(점수, 적용한 기준 이름). 무압축이면 1"""
    codec = (codec or '').lower()
    if codec in settings.SQI_LOSSLESS_CODECS:
        return 1.0, 'lossless'
    rule = settings.SQI_CODEC_RULE.get(codec, settings.SQI_CODEC_DEFAULT_RULE)
    zero_at, one_at = settings.SQI_COMPRESSION_BPP[rule]
    return _ramp(bpp, zero_at, one_at, log=True), rule


def measure(traces: RoiTraces, roi: str = settings.RPPG_PRIMARY_ROI) -> dict[str, float]:
    """얼굴 크기·조명·움직임 측정값 (얼굴을 잡은 프레임만)"""
    ok = traces.tracked & (traces.pixels[roi] > 0)
    rgb = traces.rgb[roi][ok]
    luma = rgb @ np.array([0.299, 0.587, 0.114])  # 피부 평균 밝기(BT.601)
    g = {k: v[ok] for k, v in traces.geometry.items()}
    head = mouth = np.nan
    if len(g.get('cx', [])) >= 2:
        # 머리 이동: 프레임 사이 얼굴 중심 이동 거리 ÷ 얼굴 폭의 평균
        step = np.linalg.norm(np.diff(np.stack([g['cx'], g['cy']], axis=1), axis=0), axis=1)
        head = float(np.mean(step / g['width'][1:]))
        # 입·턱 움직임: 프레임 사이 입 벌림(윗입술·아랫입술 안쪽 거리) 변화 ÷ 얼굴 높이의 평균
        mouth = float(np.mean(np.abs(np.diff(g['mouth'])) / g['height'][1:]))
    return {
        'face_pixels': float(np.mean(traces.pixels[roi][ok])) if ok.any() else 0.0,
        'brightness': float(luma.mean()) if len(luma) else 0.0,
        'brightness_cv': float(luma.std() / luma.mean()) if len(luma) and luma.mean() > 0 else np.nan,
        'head_motion': head,
        'mouth_motion': mouth,
        **_inband_lighting(traces, roi),
    }


def _inband_lighting(traces: RoiTraces, roi: str) -> dict[str, float]:
    """
    필터가 걸러 내지 못하는 심박 대역(0.7~4Hz) 안의 밝기 변화 (조명 항목 후보, 2026-10-20 분포 확인용).
      background_inband  배경 밝기(평균으로 나눈 상대값)를 rPPG와 같은 대역통과에 통과시킨 표준편차
      skin_inband        얼굴 피부 밝기를 같은 방식으로 — 맥박 성분도 조금 들어 있다
      lighting_ratio     background_inband ÷ skin_inband (배경의 대역 내 밝기 변화가 피부 신호에 견줘 얼마나 큰지)
    """
    out = {'background_inband': np.nan, 'skin_inband': np.nan, 'lighting_ratio': np.nan}
    fs = traces.fps
    sos = dsp.butter_bandpass_sos(settings.RPPG_FILTER_ORDER, *settings.RPPG_BAND_HZ, fs)
    pad = 3 * (2 * len(sos) + 1)

    def inband(x: np.ndarray) -> float:
        x = np.asarray(x, dtype=np.float64)
        if len(x) <= pad or not np.all(np.isfinite(x)) or x.mean() <= 0:
            return np.nan
        return float(np.std(dsp.sosfiltfilt(sos, x / x.mean() - 1.0)))

    skin = traces.rgb[roi] @ np.array([0.299, 0.587, 0.114])
    out['skin_inband'] = inband(skin)
    if len(traces.background) == len(skin):
        out['background_inband'] = inband(traces.background)
    if np.isfinite(out['background_inband']) and out['skin_inband'] and np.isfinite(out['skin_inband']):
        out['lighting_ratio'] = out['background_inband'] / out['skin_inband']
    return out


def compute(traces: RoiTraces, codec: str, stream: StreamInfo, roi: str = settings.RPPG_PRIMARY_ROI) -> SqiResult:
    m = measure(traces, roi)
    compression, rule = compression_score(codec, stream.bpp)
    face = _ramp(m['face_pixels'], *settings.SQI_FACE_PIXELS, log=True)
    bright = _ramp(m['brightness'], *settings.SQI_BRIGHTNESS)
    if m['brightness'] > settings.SQI_BRIGHTNESS_SATURATION:  # 너무 밝아 피부색이 포화되면 감점
        bright = min(bright, _ramp(m['brightness'], 255.0, settings.SQI_BRIGHTNESS_SATURATION))
    illumination = min(bright, _ramp(m['brightness_cv'], *settings.SQI_BRIGHTNESS_CV))
    motion = min(_ramp(m['head_motion'], *settings.SQI_HEAD_MOTION), _ramp(m['mouth_motion'], *settings.SQI_MOUTH_MOTION))
    components = {'face_pixels': face, 'compression': compression, 'illumination': illumination, 'motion': motion}
    value = min(components.values())
    grade = 'good' if value >= settings.SQI_GOOD_MIN else 'fair' if value >= settings.SQI_MIN else 'poor'
    return SqiResult(value=round(value, 3), grade=grade, components={k: round(v, 3) for k, v in components.items()},
                     measures={**m, 'codec': codec, 'bpp': stream.bpp, 'bpp_source': stream.source, 'compression_rule': rule})
