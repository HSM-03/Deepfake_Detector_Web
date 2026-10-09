"""업로드·검증 단계: 영상 파일을 열어 해상도·fps·길이·프레임 수·코덱을 읽는다 (API VideoMeta)"""
from dataclasses import dataclass
from pathlib import Path

import cv2


@dataclass
class VideoMeta:
    width: int
    height: int
    fps: float
    duration_sec: float
    frame_count: int
    codec: str


def read_video_meta(path: Path) -> VideoMeta | None:
    """영상 정보를 읽는다. 열 수 없거나 프레임을 하나도 읽지 못하면 None (파일 손상으로 본다)"""
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            return None
        ok, _ = cap.read()
        if not ok:
            return None

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if 0 < fps <= _MAX_PLAUSIBLE_FPS and frame_count > 0:
            duration = frame_count / fps
        else:
            # 브라우저로 녹화한 WebM 등은 프레임률을 저장하지 않아 OpenCV가 시간 단위(예: 1000)를 fps로 알려 주고,
            # 프레임 수도 엉뚱하게 나온다. 이때는 끝까지 한 번 넘기며 실제 프레임 수와 마지막 프레임 시각을 재서 계산한다.
            # rPPG(4단계)는 정확한 프레임률이 있어야 심박을 계산할 수 있다
            frame_count, duration = _count_frames(cap)
            fps = frame_count / duration if duration > 0 else 0.0
        return VideoMeta(
            width=width,
            height=height,
            fps=round(fps, 3),
            duration_sec=round(duration, 3),
            frame_count=frame_count,
            codec=_codec_name(cap) or path.suffix.lstrip('.').lower(),
        )
    finally:
        cap.release()


_MAX_PLAUSIBLE_FPS = 240.0  # 이보다 크면 실제 프레임률이 아니라 시간 단위로 본다


def _count_frames(cap: cv2.VideoCapture) -> tuple[int, float]:
    """처음 프레임은 이미 읽었다. 남은 프레임을 넘기며 개수와 마지막 프레임 시각(초)을 잰다"""
    count, first_ms, last_ms = 1, cap.get(cv2.CAP_PROP_POS_MSEC), 0.0
    while cap.grab():
        count += 1
        last_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    # 마지막 프레임 '시작' 시각까지의 길이에 프레임 한 장 길이를 더한다
    span = max(0.0, last_ms - first_ms) / 1000
    duration = span * count / (count - 1) if count > 1 else 0.0
    return count, duration


def _codec_name(cap: cv2.VideoCapture) -> str:
    """OpenCV가 알려 주는 코덱 4글자 코드(FourCC). 예: 'avc1' → 'h264'"""
    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    code = ''.join(chr((fourcc >> (8 * i)) & 0xFF) for i in range(4)).strip('\x00 ').lower()
    aliases = {
        'avc1': 'h264', 'h264': 'h264', 'x264': 'h264', 'hev1': 'h265', 'hvc1': 'h265',
        'vp80': 'vp8', 'vp90': 'vp9', 'fmp4': 'mpeg4', 'mp4v': 'mpeg4', 'xvid': 'mpeg4', 'divx': 'mpeg4',
    }
    return aliases.get(code, code) if code.isprintable() else ''
