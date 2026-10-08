"""
메인 모델 입력용 얼굴 검출·정렬·자르기 — DeepfakeBench 전처리와 같은 방식.

학습 때와 다르게 자르면 정확도가 떨어지므로 DeepfakeBench의 preprocessing/preprocess.py
(get_keypts, extract_aligned_face_dlib)를 그대로 따른다.
  출처: https://github.com/SCLBD/DeepfakeBench  (Copyright (c) 2023, CUHK(SZ)), 라이선스 CC BY-NC 4.0
원본과 다른 점은 하나다: 유사 변환 추정에 scikit-image(SimilarityTransform) 대신 같은 계산(Umeyama 방법)을
NumPy로 직접 구현했다. 상세제안서 스택에 없는 라이브러리를 늘리지 않기 위해서다.
"""
from dataclasses import dataclass

import cv2
import dlib
import numpy as np

# 정렬 기준 5점(왼눈·오른눈·코끝·입 왼쪽·입 오른쪽)의 112×112 기준 위치. ArcFace 계열 정렬에서 쓰는 값
_REFERENCE_5PTS = np.array(
    [
        [30.2946, 51.6963],
        [65.5318, 51.5014],
        [48.0252, 71.7366],
        [33.5493, 92.3655],
        [62.7299, 92.2041],
    ],
    dtype=np.float32,
)
# 얼굴 주변을 얼마나 넓게 자를지. 1.3이면 기준 얼굴 크기보다 30% 넓게 자른다
_CROP_SCALE = 1.3
# 81점 랜드마크 중 정렬에 쓰는 5점의 번호 (DeepfakeBench get_keypts와 같음)
_KEYPOINT_INDEXES = (37, 44, 30, 49, 55)


@dataclass
class FaceAligner:
    """dlib 얼굴 검출기와 81점 랜드마크 모델을 한 번만 불러 두고 프레임마다 쓴다"""

    detector: dlib.fhog_object_detector
    predictor: dlib.shape_predictor

    @classmethod
    def load(cls, landmarks_path) -> 'FaceAligner':
        return cls(dlib.get_frontal_face_detector(), dlib.shape_predictor(str(landmarks_path)))

    def align(self, frame_bgr: np.ndarray, size: int = 256) -> np.ndarray | None:
        """
        프레임(BGR)에서 가장 큰 얼굴을 찾아 size×size로 정렬해 자른 RGB 이미지를 돌려준다.
        얼굴을 못 찾으면 None. DeepfakeBench처럼, 자른 이미지에서 얼굴이 다시 검출되지 않아도 None
        (학습 데이터에도 그런 프레임은 들어가지 않았다).
        """
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        faces = self.detector(rgb, 1)
        if len(faces) == 0:
            return None
        face = max(faces, key=lambda rect: rect.width() * rect.height())

        shape = self.predictor(rgb, face)
        src = np.array([[shape.part(i).x, shape.part(i).y] for i in _KEYPOINT_INDEXES], dtype=np.float32)
        matrix = _similarity_transform(src, _target_points(size))
        cropped = cv2.warpAffine(rgb, matrix, (size, size))

        # 원본은 PNG로 저장할 때 BGR로 바꾼 뒤 다시 검출한다. 검출 결과는 같으므로 RGB 그대로 확인한다
        if len(self.detector(cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR), 1)) == 0:
            return None
        return cropped


def _target_points(size: int) -> np.ndarray:
    """기준 5점을 size×size 출력과 여백(_CROP_SCALE)에 맞게 옮긴다. DeepfakeBench img_align_crop과 같은 계산"""
    dst = _REFERENCE_5PTS.copy()
    dst[:, 0] += 8.0  # 112×96 기준점을 112×112 가운데로
    dst *= size / 112.0
    margin = size * (_CROP_SCALE - 1) / 2.0
    dst += margin
    dst *= size / (size + 2 * margin)
    return dst


def _similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """
    src 점들을 dst 점들에 가장 가깝게 옮기는 유사 변환(회전·균일 확대·이동)의 2×3 행렬.
    Umeyama(1991) 방법 — scikit-image SimilarityTransform.estimate와 같은 계산이다.
    """
    src, dst = src.astype(np.float64), dst.astype(np.float64)
    n = src.shape[0]
    src_mean, dst_mean = src.mean(axis=0), dst.mean(axis=0)
    src_c, dst_c = src - src_mean, dst - dst_mean

    cov = dst_c.T @ src_c / n
    d = np.ones(2, dtype=np.float64)
    if np.linalg.det(cov) < 0:
        d[1] = -1
    u, s, vt = np.linalg.svd(cov)
    if np.linalg.matrix_rank(cov) == 0:
        return np.hstack([np.eye(2), (dst_mean - src_mean)[:, None]]).astype(np.float64)
    rotation = u @ np.diag(d) @ vt

    scale = (s * d).sum() / src_c.var(axis=0).sum()
    translation = dst_mean - scale * rotation @ src_mean
    return np.hstack([scale * rotation, translation[:, None]]).astype(np.float64)
