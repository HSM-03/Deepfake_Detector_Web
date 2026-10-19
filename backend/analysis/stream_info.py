"""
영상 스트림 비트레이트와 픽셀당 비트(bpp) — SQI 압축 항목의 입력 (docs/backend-plan.md 4단계).

bpp = 영상 스트림 비트레이트 / (가로 × 세로 × fps)

비트레이트는 다음 순서로 구한다(오디오가 섞이면 저화질 영상일수록 bpp가 부풀려지므로 영상 스트림만 센다):
  1. MP4·MOV: 파일 안 트랙별 표본 크기 표(stsz)를 직접 읽어 영상 트랙의 바이트 수 ÷ 영상 트랙 길이 — 'track'
  2. 그 밖(WebM·AVI 등) 또는 1이 안 되면: 파일 크기 ÷ 길이에서 오디오 트랙 비트레이트(읽을 수 있으면)를 뺀 값 — 'file'
     오디오를 못 읽으면 빼지 못하므로 bpp가 조금 높게(관대하게) 나올 수 있다 — 'file_with_audio'
"""
import struct
from dataclasses import dataclass
from pathlib import Path

from .video_meta import VideoMeta

_CONTAINERS = {b'moov', b'trak', b'mdia', b'minf', b'stbl', b'edts'}


@dataclass
class StreamInfo:
    video_kbps: float | None
    audio_kbps: float | None  # 오디오 트랙이 없으면 None
    total_kbps: float  # 파일 크기 ÷ 길이
    bpp: float | None
    source: str  # 'track' | 'file' | 'file_with_audio'

    @property
    def audio_share(self) -> float | None:
        """파일 전체 비트레이트 중 오디오 비중"""
        return self.audio_kbps / self.total_kbps if self.audio_kbps and self.total_kbps else None


def stream_info(path: Path, meta: VideoMeta) -> StreamInfo:
    path = Path(path)
    total = path.stat().st_size * 8 / 1000 / meta.duration_sec if meta.duration_sec > 0 else 0.0
    tracks = _mp4_tracks(path) if path.suffix.lower() in ('.mp4', '.mov', '.m4v') else {}
    video, audio = tracks.get('vide'), tracks.get('soun')
    if video:
        kbps, source = video, 'track'
    elif audio is not None:
        kbps, source = total - audio, 'file'
    else:
        kbps, source = total, 'file_with_audio' if path.suffix.lower() not in ('.mp4', '.mov', '.m4v') else 'file'
    pixels_per_sec = meta.width * meta.height * meta.fps
    return StreamInfo(video_kbps=video, audio_kbps=audio, total_kbps=total,
                      bpp=kbps * 1000 / pixels_per_sec if pixels_per_sec > 0 and kbps > 0 else None, source=source)


def _boxes(data: bytes, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack('>I4s', data[pos:pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack('>Q', data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            return
        yield kind, pos + header, pos + size
        pos += size


def _mp4_tracks(path: Path) -> dict[str, float]:
    """MP4·MOV의 트랙 종류('vide', 'soun')별 비트레이트(kbps). moov 상자만 읽는다(영상 데이터는 건너뜀)"""
    out: dict[str, float] = {}
    try:
        with open(path, 'rb') as f:
            size = path.stat().st_size
            pos = 0
            moov = None
            while pos + 8 <= size:  # 맨 위 상자들을 건너뛰며 moov만 찾는다
                f.seek(pos)
                head = f.read(16)
                box_size, kind = struct.unpack('>I4s', head[:8])
                header = 8
                if box_size == 1:
                    box_size, header = struct.unpack('>Q', head[8:16])[0], 16
                elif box_size == 0:
                    box_size = size - pos
                if kind == b'moov':
                    f.seek(pos)
                    moov = f.read(box_size)
                    break
                if box_size < header:
                    break
                pos += box_size
        if moov is None:
            return out
        for kind, body, end in _boxes(moov, 8, len(moov)):
            if kind != b'trak':
                continue
            info: dict = {}
            _walk(moov, body, end, info)
            handler, seconds, total_bytes = info.get('handler'), info.get('seconds'), info.get('bytes')
            if handler in (b'vide', b'soun') and seconds and total_bytes:
                out.setdefault(handler.decode(), total_bytes * 8 / 1000 / seconds)
    except (OSError, struct.error):
        return {}
    return out


def _walk(data: bytes, start: int, end: int, info: dict) -> None:
    for kind, body, stop in _boxes(data, start, end):
        if kind in _CONTAINERS:
            _walk(data, body, stop, info)
        elif kind == b'hdlr':
            info['handler'] = data[body + 8:body + 12]
        elif kind == b'mdhd':
            if data[body] == 1:
                timescale, duration = struct.unpack('>IQ', data[body + 20:body + 32])
            else:
                timescale, duration = struct.unpack('>II', data[body + 12:body + 20])
            info['seconds'] = duration / timescale if timescale else None
        elif kind == b'stsz':
            sample_size, count = struct.unpack('>II', data[body + 4:body + 12])
            if sample_size:
                info['bytes'] = sample_size * count
            else:
                info['bytes'] = sum(struct.unpack(f'>{count}I', data[body + 12:body + 12 + 4 * count]))
