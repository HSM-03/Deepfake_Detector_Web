"""
부위별 맥박 신호 (사전 등록 6절) — 서비스 추적(analysis.rppg.extract_traces)을 그대로 돌리고, frame_hook으로 같은 프레임·같은 얼굴 윤곽에서
새 부위의 평균 RGB를 함께 기록한다. 서비스 코드를 고치거나 복사하지 않으므로 서비스 ROI·특징 6개·SQI는 서비스와 똑같다.

새 부위 (얼굴 윤곽 = Face Mesh 윤곽 36점, 축소는 윤곽 점들의 평균점을 중심으로):
  inner           안쪽 얼굴: 윤곽을 INNER_SCALE로 줄인 영역 − 눈·눈썹·입술. 얼굴 교체로 합성되는 영역
  upper_forehead  이마 위쪽: 윤곽과 RING_SCALE 윤곽 사이 띠 중 눈썹 맨 위보다 위
  edge            얼굴 가장자리: 같은 띠 중 나머지(관자놀이·볼 바깥·턱선)
  neck            목: 턱 끝(152번) 아래 상자. 폭 = 얼굴 폭 × NECK_WIDTH, 턱에서 얼굴 높이 × NECK_GAP 띄우고 높이 × NECK_HEIGHT
  background      배경(대조군): 얼굴 상자 좌우 바깥 상자 두 개(얼굴 폭 × BG_GAP 띄우고 폭 × BG_WIDTH, 얼굴 중심 높이 ± 높이 × BG_HALF_HEIGHT)
안쪽(INNER_SCALE)과 띠(RING_SCALE~1) 사이는 비워 두 부위가 섞이지 않게 한다. 눈·눈썹·입술은 모든 얼굴 부위에서 뺀다.
목은 서비스 face_skin과 같은 피부색 범위(YCrCb)의 픽셀만 쓴다 — UBFC 확인 그림에서 목 상자에 옷이 많이 들어가서.
얼굴 부위에는 거르지 않는다: 푸른 조명(UBFC subject49)에서 볼·이마 대부분이 범위 밖으로 빠졌다(안쪽 얼굴 5,602 → 1,619px).
띠에 머리카락이 조금 들어가는 것은 감수한다. 배경은 대조군이라 거르지 않는다. (모두 심박 결과를 보기 전, 그림만 보고 정함)
왼볼·오른볼은 서비스 ROI(left_cheek, right_cheek)를 그대로 쓴다. 비율은 결과를 보기 전에 정한 값이다(2026-10-31).
"""
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from analysis import rppg
from analysis.video_meta import VideoMeta, read_video_meta

INNER_SCALE = 0.70
RING_SCALE = 0.85
NECK_WIDTH, NECK_GAP, NECK_HEIGHT = 0.50, 0.05, 0.30
BG_GAP, BG_WIDTH, BG_HALF_HEIGHT = 0.20, 0.40, 0.25

REGION_KEYS = ('inner', 'upper_forehead', 'edge', 'neck', 'background')
_CHIN = rppg._FACE_OVAL.index(152)  # 윤곽 점 순서에서 턱 끝의 위치


def scaled(polygon: np.ndarray, scale: float) -> np.ndarray:
    c = polygon.mean(axis=0)
    return np.round(c + scale * (polygon - c)).astype(np.int32)


def skin_mask(bgr: np.ndarray) -> np.ndarray:
    """서비스 face_skin과 같은 피부색 범위"""
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    return cv2.inRange(ycrcb, (0, rppg._SKIN_CR[0], rppg._SKIN_CB[0]), (255, rppg._SKIN_CR[1], rppg._SKIN_CB[1])) > 0


def region_masks(frame: np.ndarray, oval: np.ndarray, excludes: list[np.ndarray]) -> tuple[dict[str, np.ndarray], tuple[int, int]]:
    """얼굴 부위 세 개(inner, upper_forehead, edge)의 마스크. 윤곽의 경계 사각형 안에서만 만들고 (마스크, 사각형 왼쪽 위)를 돌려준다"""
    shape = frame.shape[:2]
    x, y, w, h = cv2.boundingRect(oval)
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, shape[1]), min(y + h, shape[0])
    if x1 <= x0 or y1 <= y0:
        return {}, (x0, y0)
    size = (y1 - y0, x1 - x0)
    off = np.array([x0, y0])

    def fill(poly):
        m = np.zeros(size, dtype=np.uint8)
        cv2.fillPoly(m, [poly - off], 255)
        return m

    holes = np.zeros(size, dtype=np.uint8)
    for poly in excludes:
        cv2.fillConvexPoly(holes, poly - off, 255)
    keep = holes == 0
    inner = (fill(scaled(oval, INNER_SCALE)) > 0) & keep
    ring = (fill(oval) > 0) & (fill(scaled(oval, RING_SCALE)) == 0) & keep
    brow_top = min(int(p.reshape(-1, 2)[:, 1].min()) for p in excludes[:2]) - y0  # 눈·눈썹 영역 두 개 중 맨 위(convexHull은 (N, 1, 2))
    above = np.zeros(size, dtype=bool)
    above[:max(brow_top, 0)] = True
    return {'inner': inner, 'upper_forehead': ring & above, 'edge': ring & ~above}, (x0, y0)


def region_boxes(shape: tuple[int, int], oval: np.ndarray) -> dict[str, list[tuple[int, int, int, int]]]:
    """목·배경 상자 (x0, y0, x1, y1). 프레임 밖은 잘라 낸다"""
    (fx0, fy0), (fx1, fy1) = oval.min(axis=0), oval.max(axis=0)
    fw, fh = fx1 - fx0, fy1 - fy0
    chin_x, chin_y = oval[_CHIN]
    cy = (fy0 + fy1) / 2

    def clip(a, b, c, d):
        a, c = max(int(a), 0), min(int(c), shape[1])
        b, d = max(int(b), 0), min(int(d), shape[0])
        return (a, b, c, d) if c > a and d > b else None

    neck = clip(chin_x - fw * NECK_WIDTH / 2, chin_y + fh * NECK_GAP, chin_x + fw * NECK_WIDTH / 2, chin_y + fh * (NECK_GAP + NECK_HEIGHT))
    left = clip(fx0 - fw * (BG_GAP + BG_WIDTH), cy - fh * BG_HALF_HEIGHT, fx0 - fw * BG_GAP, cy + fh * BG_HALF_HEIGHT)
    right = clip(fx1 + fw * BG_GAP, cy - fh * BG_HALF_HEIGHT, fx1 + fw * (BG_GAP + BG_WIDTH), cy + fh * BG_HALF_HEIGHT)
    return {'neck': [b for b in (neck,) if b], 'background': [b for b in (left, right) if b]}


@dataclass
class _Collector:
    """extract_traces의 frame_hook. 프레임마다 새 부위의 BGR 합과 픽셀 수를 쌓는다"""

    sums: dict[str, list] = field(default_factory=lambda: {k: [] for k in REGION_KEYS})
    counts: dict[str, list] = field(default_factory=lambda: {k: [] for k in REGION_KEYS})
    preview: callable = None

    def __call__(self, index: int, frame: np.ndarray, polygons: dict) -> None:
        face = polygons.get('face')
        values = {k: (np.zeros(3), 0) for k in REGION_KEYS}
        masks, origin, boxes = {}, (0, 0), {}
        if face is not None:
            oval, excludes = face
            masks, origin = region_masks(frame, oval, excludes)
            x0, y0 = origin
            for key, m in masks.items():
                crop = frame[y0:y0 + m.shape[0], x0:x0 + m.shape[1]]
                n = int(np.count_nonzero(m))
                if n:
                    values[key] = (crop[m].sum(axis=0).astype(np.float64), n)
            boxes = region_boxes(frame.shape[:2], oval)
            for key, rects in boxes.items():
                total, n = np.zeros(3), 0
                for a, b, c, d in rects:
                    patch = frame[b:d, a:c]
                    keep = skin_mask(patch) if key == 'neck' else np.ones(patch.shape[:2], dtype=bool)
                    total = total + patch[keep].sum(axis=0)
                    n += int(np.count_nonzero(keep))
                values[key] = (total, n)
        for key, (total, n) in values.items():
            self.sums[key].append(total)
            self.counts[key].append(n)
        if self.preview:
            self.preview(index, frame, polygons, masks, origin, boxes)


@dataclass
class RegionTraces:
    service: rppg.RoiTraces  # 서비스와 같은 추적 결과(forehead·cheeks·face·face_skin·all, geometry, background 밝기)
    rgb: dict[str, np.ndarray]  # 새 부위 → (프레임 수, 3) R·G·B 평균. 놓친 프레임은 서비스와 같이 선형 보간
    pixels: dict[str, np.ndarray]


def extract(path: Path, meta: VideoMeta | None = None, max_frames: int | None = None, preview=None) -> RegionTraces:
    meta = meta or read_video_meta(path)
    collector = _Collector(preview=preview)
    service = rppg.extract_traces(path, meta, frame_hook=collector, max_frames=max_frames)
    rgb, pixels = {}, {}
    for key in REGION_KEYS:
        s = np.array(collector.sums[key], dtype=np.float64).reshape(-1, 3)
        c = np.array(collector.counts[key], dtype=np.float64)
        pixels[key] = c
        rgb[key] = rppg._fill_gaps(s[:, ::-1] / np.maximum(c, 1)[:, None], c > 0)
    return RegionTraces(service=service, rgb=rgb, pixels=pixels)


def save_npz(traces: RegionTraces, path: Path) -> None:
    """맥박 지도(부위 × 시간)를 만들 수 있는 원자료. 얼굴 이미지는 저장하지 않는다"""
    s = traces.service
    arrays = {'fps': np.float64(s.fps), 'tracked': s.tracked, 'background_luma': s.background.astype(np.float32)}
    for key, value in {**s.rgb, **traces.rgb}.items():
        arrays[f'rgb_{key}'] = value.astype(np.float32)
    for key, value in {**s.pixels, **traces.pixels}.items():
        arrays[f'pixels_{key}'] = value.astype(np.int32)
    for key, value in s.geometry.items():
        arrays[f'geom_{key}'] = value.astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


# 확인용 그림 색 (BGR)
PREVIEW_COLORS = {'inner': (0, 200, 0), 'upper_forehead': (255, 120, 0), 'edge': (0, 160, 255),
                  'neck': (200, 0, 200), 'background': (128, 128, 128)}


def draw_preview(frame: np.ndarray, polygons: dict, masks: dict, origin: tuple[int, int], boxes: dict) -> np.ndarray:
    """부위를 반투명 색으로 칠한 그림(확인용 — 얼굴이 담기므로 backend/out/에만 두고 확인 뒤 지운다)"""
    out = frame.copy()
    overlay = frame.copy()
    x0, y0 = origin
    for key, m in masks.items():
        region = overlay[y0:y0 + m.shape[0], x0:x0 + m.shape[1]]
        region[m] = PREVIEW_COLORS[key]
    for key, rects in boxes.items():
        for a, b, c, d in rects:
            patch = overlay[b:d, a:c]
            patch[skin_mask(frame[b:d, a:c]) if key == 'neck' else slice(None)] = PREVIEW_COLORS[key]
    for key in ('left_cheek', 'right_cheek'):
        if key in polygons:
            cv2.polylines(out, [polygons[key]], True, (0, 255, 255), 1)
    return cv2.addWeighted(overlay, 0.45, out, 0.55, 0)
