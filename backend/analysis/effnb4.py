"""
메인 모델: EfficientNet-B4 딥페이크 판별기 (추론 전용)

DeepfakeBench의 training/networks/efficientnetb4.py와 training/detectors/efficientnetb4_detector.py에서
추론에 필요한 부분만 옮겼다. 학습 코드·손실 함수·지표 계산은 뺐다.
  출처: https://github.com/SCLBD/DeepfakeBench  (Copyright (c) 2023, CUHK(SZ))
  라이선스: CC BY-NC 4.0 — 비상업적 이용, 출처 표시 (https://creativecommons.org/licenses/by-nc/4.0/)
  가중치: 같은 저장소 릴리스 v1.0.1의 effnb4_best.pth
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from efficientnet_pytorch import EfficientNet


class EfficientNetB4(nn.Module):
    """DeepfakeBench 설정(efficientnetb4.yaml)과 같은 구조: 입력 3채널, 출력 2칸(진짜/가짜), 드롭아웃 없음"""

    def __init__(self):
        super().__init__()
        # 학습된 가중치로 통째로 덮어쓰므로 ImageNet 사전학습 가중치는 받지 않는다
        self.efficientnet = EfficientNet.from_name('efficientnet-b4')
        # DeepfakeBench가 첫 층과 마지막 층을 바꿔서 학습했으므로 똑같이 바꿔야 가중치가 맞는다
        self.efficientnet._conv_stem = nn.Conv2d(3, 48, kernel_size=3, stride=2, bias=False)
        self.efficientnet._fc = nn.Identity()
        self.last_layer = nn.Linear(1792, 2)

    def forward(self, x):
        x = self.efficientnet.extract_features(x)
        x = F.adaptive_avg_pool2d(x, (1, 1)).flatten(1)
        return self.last_layer(x)


def load_model(weights_path) -> EfficientNetB4:
    """effnb4_best.pth를 불러 추론 모드로 돌려준다. 구조가 다르면 여기서 오류가 난다"""
    state = torch.load(weights_path, map_location='cpu', weights_only=True)
    # 저장된 이름이 'backbone.efficientnet…', 'backbone.last_layer…' 형태라 앞의 'backbone.'을 뗀다
    state = {key.removeprefix('backbone.'): value for key, value in state.items()}
    model = EfficientNetB4()
    model.load_state_dict(state, strict=True)  # strict: 이름·모양이 하나라도 다르면 오류
    model.eval()
    return model


def to_input_tensor(faces_rgb: list[np.ndarray]) -> torch.Tensor:
    """
    정렬된 얼굴(RGB, uint8, 256×256) 목록 → 모델 입력 (N, 3, 256, 256).
    DeepfakeBench와 같이 0~1로 바꾼 뒤 평균 0.5·표준편차 0.5로 정규화해 [-1, 1] 범위로 만든다.
    """
    batch = np.stack(faces_rgb).astype(np.float32) / 255.0
    batch = (batch - 0.5) / 0.5
    return torch.from_numpy(batch).permute(0, 3, 1, 2).contiguous()


@torch.no_grad()
def predict_fake_prob(model: EfficientNetB4, faces: torch.Tensor) -> torch.Tensor:
    """
    faces: to_input_tensor로 만든 (N, 3, 256, 256) 텐서.
    반환: 프레임별 조작(가짜) 확률. DeepfakeBench에서 라벨 1이 가짜이고 softmax의 1번 칸을 쓰므로,
          우리 P_model과 같은 방향(1에 가까울수록 가짜)이다.
    """
    return torch.softmax(model(faces), dim=1)[:, 1]
