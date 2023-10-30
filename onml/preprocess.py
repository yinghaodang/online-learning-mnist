# 数据预处理模块

# 此demo中使用的是 MNIST 数据集, 原数据集(每张图片)是  28 * 28 的 数组
# 在kafka中存储的格式是摊平之后的list
# 此模块需要做的事情
# 1. 将 list 转化为 Tensor 格式
# 2. 将 Tensor 格式转化为可训练 的维度，如 1 * 1 * 28 * 28

# to do:
# 1. 支持批处理
import numpy as np
import torch
from torchvision import transforms


def preprocess(image: list) -> torch.Tensor:
    image = np.array(image).reshape(28, 28).astype(np.float32)

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])
    image = transform(image)

    return image.unsqueeze(1)