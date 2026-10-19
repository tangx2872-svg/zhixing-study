"""Showcase data for the "version experience" demo.

Creates one complete, readable story:

    计算机视觉基础 → 实验 03：基于深度学习的图像分类
    张晨：V1 → V2 → V3 → V4（真实代码差异）→ 教师评分 92
    林晓：V1 → V2 → V3（待评分）
    王宇：V1 → V2（待评分）
    周宁：未提交

The command is idempotent: existing accounts, courses, assignments and submissions
are reused or skipped, never overwritten or deleted.
"""
import hashlib
import io
import struct
import zipfile
import zlib
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assignments.models import Assignment, SubmissionAttachment, SubmitAssignment
from courses.models import Course, Enrollment
from users.models import User

RUBRIC = [
    {'title': '代码实现', 'points': 35},
    {'title': '模型设计', 'points': 25},
    {'title': '实验分析', 'points': 25},
    {'title': '报告规范', 'points': 15},
]

ASSIGNMENT_NAME = '实验 03：基于深度学习的图像分类'
COURSE_NAME = '计算机视觉基础'

DESCRIPTION = (
    '使用 PyTorch 完成一个基础图像分类模型，记录模型设计、训练过程与实验结果。\n\n'
    '提交材料：\n'
    '1. 完整源码（ZIP）\n'
    '2. 实验报告（Markdown / PDF）\n'
    '3. 训练结果截图\n'
    '4. README（包含在源码包内）\n\n'
    '（本实验为平台演示数据，用于展示版本提交、代码浏览与版本对比。）'
)

FEEDBACK = (
    '整体完成质量较好，代码结构清晰，能够体现从基础模型到优化版本的完整迭代过程。\n\n'
    '后续可以进一步补充不同优化器的对比实验，并加强实验结果的定量分析。'
)


# --------------------------------------------------------------------------
# 代码快照：四版真实、可读、可产生 diff 的源码
# --------------------------------------------------------------------------

TRAIN_V1 = '''"""训练入口：在 CIFAR-10 子集上训练基础 CNN。"""
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from dataset import build_datasets
from model import SimpleCNN

BATCH_SIZE = 64
EPOCHS = 20


def train_one_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(loader)


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set, _val_set = build_datasets()
    loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True)

    model = SimpleCNN(num_classes=10).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

    for epoch in range(EPOCHS):
        loss = train_one_epoch(model, loader, criterion, optimizer, device)
        print("epoch {} loss {:.4f}".format(epoch + 1, loss))


if __name__ == "__main__":
    main()
'''

TRAIN_V2 = '''"""训练入口：增加验证集评估与最优模型保存。"""
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from dataset import build_datasets
from model import SimpleCNN
from utils import AverageMeter, accuracy, save_checkpoint

BATCH_SIZE = 64
EPOCHS = 20


def train_one_epoch(model, loader, criterion, optimizer, device):
    model.train()
    losses = AverageMeter()
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        losses.update(loss.item(), images.size(0))
    return losses.avg


def evaluate(model, loader, criterion, device):
    model.eval()
    losses, correct, total = AverageMeter(), 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            losses.update(criterion(outputs, labels).item(), images.size(0))
            correct += accuracy(outputs, labels)
            total += labels.size(0)
    return losses.avg, correct / float(total)


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set, val_set = build_datasets()
    train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=BATCH_SIZE, shuffle=False)

    model = SimpleCNN(num_classes=10).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)

    best_acc = 0.0
    for epoch in range(EPOCHS):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        print("epoch {} train {:.4f} val {:.4f} acc {:.3f}".format(
            epoch + 1, train_loss, val_loss, val_acc))
        if val_acc > best_acc:
            best_acc = val_acc
            save_checkpoint(model, optimizer, epoch, "best.pt")
    print("best accuracy: {:.3f}".format(best_acc))


if __name__ == "__main__":
    main()
'''

TRAIN_V3 = '''"""训练入口：加入随机种子与训练日志。"""
import csv
import random

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from dataset import build_datasets
from model import SimpleCNN
from utils import AverageMeter, accuracy, save_checkpoint

BATCH_SIZE = 64
EPOCHS = 25
SEED = 42


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def train_one_epoch(model, loader, criterion, optimizer, device):
    model.train()
    losses = AverageMeter()
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        losses.update(loss.item(), images.size(0))
    return losses.avg


def evaluate(model, loader, criterion, device):
    model.eval()
    losses, correct, total = AverageMeter(), 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            losses.update(criterion(outputs, labels).item(), images.size(0))
            correct += accuracy(outputs, labels)
            total += labels.size(0)
    return losses.avg, correct / float(total)


def main():
    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set, val_set = build_datasets()
    train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=BATCH_SIZE, shuffle=False)

    model = SimpleCNN(num_classes=10).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)

    best_acc = 0.0
    history = []
    for epoch in range(EPOCHS):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        history.append([epoch + 1, round(train_loss, 4), round(val_loss, 4), round(val_acc, 4)])
        print("epoch {} train {:.4f} val {:.4f} acc {:.3f}".format(
            epoch + 1, train_loss, val_loss, val_acc))
        if val_acc > best_acc:
            best_acc = val_acc
            save_checkpoint(model, optimizer, epoch, "best.pt")

    with open("train_log.csv", "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["epoch", "train_loss", "val_loss", "val_acc"])
        writer.writerows(history)
    print("best accuracy: {:.3f}".format(best_acc))


if __name__ == "__main__":
    main()
'''

TRAIN_V4 = '''"""训练入口：切换到 AdamW，并加入余弦退火学习率调度。"""
import csv
import random

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

import config
from dataset import build_datasets
from model import SimpleCNN
from utils import AverageMeter, accuracy, save_checkpoint

BATCH_SIZE = config.BATCH_SIZE
EPOCHS = config.EPOCHS
SEED = 42


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def train_one_epoch(model, loader, criterion, optimizer, device):
    model.train()
    losses = AverageMeter()
    for images, labels in loader:
        images = images.to(device)
        labels = labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()
        losses.update(loss.item(), images.size(0))
    return losses.avg


def evaluate(model, loader, criterion, device):
    model.eval()
    losses, correct, total = AverageMeter(), 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)
            outputs = model(images)
            losses.update(criterion(outputs, labels).item(), images.size(0))
            correct += accuracy(outputs, labels)
            total += labels.size(0)
    return losses.avg, correct / float(total)


def main():
    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set, val_set = build_datasets()
    train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=BATCH_SIZE, shuffle=False)

    model = SimpleCNN(num_classes=10).to(device)
    criterion = nn.CrossEntropyLoss()

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.LEARNING_RATE,
        weight_decay=config.WEIGHT_DECAY,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

    best_acc = 0.0
    history = []
    for epoch in range(EPOCHS):
        train_loss = train_one_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = evaluate(model, val_loader, criterion, device)
        scheduler.step()
        history.append([epoch + 1, round(train_loss, 4), round(val_loss, 4), round(val_acc, 4)])
        print("epoch {} train {:.4f} val {:.4f} acc {:.3f} lr {:.5f}".format(
            epoch + 1, train_loss, val_loss, val_acc, scheduler.get_last_lr()[0]))
        if val_acc > best_acc:
            best_acc = val_acc
            save_checkpoint(model, optimizer, epoch, "best.pt")

    with open("train_log.csv", "w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["epoch", "train_loss", "val_loss", "val_acc"])
        writer.writerows(history)
    print("best accuracy: {:.3f}".format(best_acc))


if __name__ == "__main__":
    main()
'''

MODEL_V1 = '''"""基础卷积网络。"""
import torch.nn as nn


class SimpleCNN(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 8 * 8, 256),
            nn.ReLU(),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        return self.classifier(x)
'''

MODEL_V2 = '''"""三层卷积网络，提升特征表达能力。"""
import torch.nn as nn


class SimpleCNN(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(128 * 4 * 4, 256),
            nn.ReLU(),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        return self.classifier(x)
'''

MODEL_V3 = '''"""加入 BatchNorm 与 Dropout，缓解过拟合。"""
import torch.nn as nn


def conv_block(in_channels, out_channels):
    return nn.Sequential(
        nn.Conv2d(in_channels, out_channels, 3, padding=1, bias=False),
        nn.BatchNorm2d(out_channels),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(2),
    )


class SimpleCNN(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.features = nn.Sequential(
            conv_block(3, 32),
            conv_block(32, 64),
            conv_block(64, 128),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(0.4),
            nn.Linear(128 * 4 * 4, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.2),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        x = self.features(x)
        return self.classifier(x)
'''

DATASET_V1 = '''"""数据集构建。"""
from torchvision import datasets, transforms


def build_datasets(data_dir="data"):
    transform = transforms.Compose([
        transforms.Resize((32, 32)),
        transforms.ToTensor(),
    ])
    train_set = datasets.CIFAR10(root=data_dir, train=True, download=True, transform=transform)
    val_set = datasets.CIFAR10(root=data_dir, train=False, download=True, transform=transform)
    return train_set, val_set
'''

DATASET_V2 = '''"""数据集构建：补充标准化与训练集增强。"""
from torchvision import datasets, transforms

MEAN = (0.4914, 0.4822, 0.4465)
STD = (0.2470, 0.2435, 0.2616)


def build_datasets(data_dir="data"):
    train_transform = transforms.Compose([
        transforms.Resize((32, 32)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomCrop(32, padding=4),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    val_transform = transforms.Compose([
        transforms.Resize((32, 32)),
        transforms.ToTensor(),
        transforms.Normalize(MEAN, STD),
    ])
    train_set = datasets.CIFAR10(root=data_dir, train=True, download=True, transform=train_transform)
    val_set = datasets.CIFAR10(root=data_dir, train=False, download=True, transform=val_transform)
    return train_set, val_set
'''

UTILS_V2 = '''"""训练辅助工具。"""
import torch


class AverageMeter:
    def __init__(self):
        self.total = 0.0
        self.count = 0

    def update(self, value, n=1):
        self.total += value * n
        self.count += n

    @property
    def avg(self):
        return self.total / self.count if self.count else 0.0


def accuracy(outputs, labels):
    predictions = outputs.argmax(dim=1)
    return (predictions == labels).sum().item()


def save_checkpoint(model, optimizer, epoch, path):
    torch.save({
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "epoch": epoch,
    }, path)
'''

DEBUG_UTILS_V2 = '''"""调试辅助：打印单批数据的统计信息。"""


def describe_batch(images, labels):
    print("images", tuple(images.shape), float(images.mean()), float(images.std()))
    print("labels", labels[:8].tolist())
'''

CONFIG_V4 = '''"""实验超参数集中配置。"""

EPOCHS = 30
BATCH_SIZE = 64
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-4
'''

README_V1 = '''# 图像分类实验

基础 CNN 图像分类实验，使用 CIFAR-10 数据集。

## 文件说明

- `train.py`：训练入口
- `model.py`：网络结构
- `dataset.py`：数据加载

## 运行

```bash
python train.py
```
'''

README_V2 = '''# 图像分类实验

基础 CNN 图像分类实验，使用 CIFAR-10 数据集。

## 文件说明

- `train.py`：训练入口，包含验证集评估
- `model.py`：三层卷积网络
- `dataset.py`：数据加载与增强
- `utils.py`：训练辅助函数
- `debug_utils.py`：调试输出

## 运行

```bash
python train.py
```

## 当前结果

- 验证集准确率：0.82
'''

README_V3 = '''# 图像分类实验

基础 CNN 图像分类实验，使用 CIFAR-10 数据集。

## 版本说明

V3 在模型中加入 BatchNorm 与 Dropout，并固定随机种子。

## 文件说明

- `train.py`：训练入口，输出训练日志
- `model.py`：带 BatchNorm / Dropout 的三层卷积网络
- `dataset.py`：数据加载与增强
- `utils.py`：训练辅助函数
- `assets/result.png`：训练结果截图

## 运行

```bash
python train.py
```

## 实验结果

| 版本 | 验证集准确率 |
| --- | --- |
| V2 | 0.82 |
| V3 | 0.88 |

过拟合现象有所缓解，但学习率仍然偏大。
'''

README_V4 = '''# 图像分类实验

基础 CNN 图像分类实验，使用 CIFAR-10 数据集。

## 版本说明

V4 将优化器从 SGD 调整为 AdamW，并加入余弦退火学习率调度。

## 文件说明

- `train.py`：训练入口
- `config.py`：超参数配置
- `model.py`：带 BatchNorm / Dropout 的三层卷积网络
- `dataset.py`：数据加载与增强
- `utils.py`：训练辅助函数
- `assets/result.png`：训练结果截图
- `assets/training_curve.png`：准确率曲线

## 运行

```bash
python train.py
```

## 实验结果

| 版本 | 优化器 | 验证集准确率 |
| --- | --- | --- |
| V2 | SGD | 0.82 |
| V3 | SGD + Momentum | 0.88 |
| V4 | AdamW + Cosine | 0.91 |

## 结论

AdamW 配合余弦退火在相同轮数下收敛更稳定，验证集准确率提升约 3 个百分点。
'''

REPORTS = {
    1: '''# 图像分类实验报告（V1）

## 一、实验目的

完成数据读取与基础 CNN 模型搭建，验证训练流程可以正常启动。

## 二、实现过程

1. 使用 torchvision 加载 CIFAR-10 数据集；
2. 搭建两层卷积 + 全连接的基础网络；
3. 使用 SGD 优化器训练 20 个 epoch。

## 三、结果

训练 loss 可以正常下降，但尚未评估验证集准确率。

## 四、下一步

补充验证集评估与模型保存。
''',
    2: '''# 图像分类实验报告（V2）

## 一、实验目的

在 V1 基础上补充验证集评估、最优模型保存与训练日志。

## 二、实现过程

1. 新增 `evaluate()`，每个 epoch 结束后计算验证集准确率；
2. 增加 `AverageMeter` 与 `accuracy` 工具函数；
3. 网络扩展为三层卷积，保存验证集最优模型。

## 三、结果

| 指标 | 数值 |
| --- | --- |
| 验证集准确率 | 0.82 |
| 最优 epoch | 17 |

## 四、问题分析

训练集准确率明显高于验证集，存在过拟合。
''',
    3: '''# 图像分类实验报告（V3）

## 一、实验目的

通过 BatchNorm 与 Dropout 缓解过拟合，并固定随机种子保证可复现。

## 二、实现过程

1. 将卷积层封装为 `conv_block`，加入 BatchNorm；
2. 分类器加入 Dropout(0.4) 与 Dropout(0.2)；
3. 固定随机种子，训练日志写入 `train_log.csv`。

## 三、结果

| 版本 | 验证集准确率 | 说明 |
| --- | --- | --- |
| V2 | 0.82 | 无归一化 |
| V3 | 0.88 | BatchNorm + Dropout |

![训练结果](assets/result.png)

## 四、问题分析

收敛速度提升明显，但学习率仍然偏大，后期波动较明显。
''',
    4: '''# 图像分类实验报告（V4）

## 一、实验目的

对比不同优化策略对收敛速度与最终准确率的影响。

## 二、实现过程

1. 优化器由 SGD 调整为 AdamW（lr=1e-3, weight_decay=1e-4）；
2. 加入 CosineAnnealingLR 学习率调度；
3. 超参数集中到 `config.py`，训练轮数提升到 30。

## 三、结果

| 版本 | 优化器 | 验证集准确率 |
| --- | --- | --- |
| V2 | SGD | 0.82 |
| V3 | SGD + Momentum | 0.88 |
| V4 | AdamW + Cosine | 0.91 |

![训练曲线](assets/training_curve.png)

## 四、结论

AdamW 配合余弦退火收敛更稳定，验证集准确率提升约 3 个百分点。
建议后续补充不同 weight_decay 的对照实验。
''',
}

LOG_V4 = '''epoch 1   train 1.4821 val 1.2033 acc 0.612
epoch 5   train 0.9134 val 0.8120 acc 0.744
epoch 10  train 0.6420 val 0.6315 acc 0.812
epoch 20  train 0.4012 val 0.5021 acc 0.881
epoch 30  train 0.2887 val 0.4310 acc 0.910
best accuracy: 0.910
'''


def _png(width, height, pixels):
    """Minimal RGB PNG encoder (no Pillow dependency)."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(pixels[y * width * 3:(y + 1) * width * 3])

    def chunk(tag, data):
        payload = tag + data
        return struct.pack('>I', len(data)) + payload + struct.pack('>I', zlib.crc32(payload) & 0xffffffff)

    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def _chart_png(points, width=520, height=260):
    """Lightweight line chart used for the demo screenshots."""
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend((247, 250, 249))
    for x in range(40, width - 20):
        pixels[(height - 40) * width * 3 + x * 3:(height - 40) * width * 3 + x * 3 + 3] = b'\xdc\xe5\xe3'
    for y in range(24, height - 40):
        pixels[y * width * 3 + 40 * 3:y * width * 3 + 40 * 3 + 3] = b'\xdc\xe5\xe3'

    values = list(points)
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    coords = []
    for index, value in enumerate(values):
        x = 40 + int((width - 70) * index / max(1, len(values) - 1))
        y = (height - 45) - int((height - 80) * (value - low) / span)
        coords.append((x, y))
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        steps = max(abs(x2 - x1), abs(y2 - y1), 1)
        for step in range(steps + 1):
            x = x1 + (x2 - x1) * step // steps
            y = y1 + (y2 - y1) * step // steps
            for dx in (0, 1):
                for dy in (0, 1):
                    pos = ((y + dy) * width + (x + dx)) * 3
                    pixels[pos:pos + 3] = b'\x1f\x6f\x5c'
    for x, y in coords:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                pos = ((y + dy) * width + (x + dx)) * 3
                pixels[pos:pos + 3] = b'\x2f\x8c\x72'
    return _png(width, height, pixels)


def code_files(version):
    """Return the complete source snapshot for one version."""
    files = {
        'train.py': {1: TRAIN_V1, 2: TRAIN_V2, 3: TRAIN_V3, 4: TRAIN_V4}[version],
        'model.py': {1: MODEL_V1, 2: MODEL_V2, 3: MODEL_V3, 4: MODEL_V3}[version],
        'dataset.py': {1: DATASET_V1, 2: DATASET_V2, 3: DATASET_V2, 4: DATASET_V2}[version],
        'README.md': {1: README_V1, 2: README_V2, 3: README_V3, 4: README_V4}[version],
    }
    if version >= 2:
        files['utils.py'] = UTILS_V2
    if version == 2:
        files['debug_utils.py'] = DEBUG_UTILS_V2
    if version >= 3:
        files['assets/result.png'] = _chart_png([0.42, 0.61, 0.70, 0.79, 0.84, 0.86, 0.88])
    if version >= 4:
        files['config.py'] = CONFIG_V4
        files['assets/training_curve.png'] = _chart_png(
            [0.61, 0.69, 0.74, 0.78, 0.81, 0.85, 0.87, 0.89, 0.905, 0.91])
    return files


def zip_files(version):
    """ZIP payload; text files are UTF-8 and images are raw PNG bytes."""
    files = code_files(version)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content if isinstance(content, bytes) else content.encode('utf-8')
            archive.writestr('image-classifier/' + name, data)
    return buffer.getvalue()


class Command(BaseCommand):
    help = '创建"版本迭代展示"用的连贯演示数据（可重复执行，不覆盖真实数据）。'

    def add_arguments(self, parser):
        parser.add_argument('--skip-supporting', action='store_true',
                            help='只创建主展示故事，不补其他课程数据。')

    @transaction.atomic
    def handle(self, *args, **options):
        self.now = timezone.now()
        self.created = []
        teacher = self._user('demo_teacher_chen', 'demo_teacher', '陈', '老师', 2, teacher=True)
        zhang = self._user('demo_student_zhang', 'demo_zhang', '张', '晨', 1)
        lin = self._user('demo_student_lin', 'demo_lin', '林', '晓', 1)
        wang = self._user('demo_student_wang', 'demo_wang', '王', '宇', 1)
        zhou = self._user('demo_student_zhou', 'demo_zhou', '周', '宁', 1)

        if not options.get('skip_supporting') and not Course.objects.filter(course_name='Python 程序设计').exists():
            call_command('seed_demo_data', verbosity=0)
            self.created.append('其他课程与作业（seed_demo_data）')

        # 按课程名唯一确定主展示课程；若历史上由其他演示教师创建，则接管为陈老师，
        # 避免同一门课出现两条同名记录。
        course = Course.objects.filter(course_name=COURSE_NAME).first()
        if course is not None and course.teacher_id != teacher.pk:
            course.teacher = teacher
            course.save(update_fields=['teacher'])
        if course is None:
            course = Course.objects.create(
                course_name=COURSE_NAME, teacher=teacher,
                course_description='图像处理基础、边缘与特征提取、目标检测入门。用于平台功能展示的示例课程。',
            )
            self.created.append('课程 ' + COURSE_NAME)
        for student in (zhang, lin, wang, zhou):
            Enrollment.objects.get_or_create(course=course, student=student)

        assignment = Assignment.objects.filter(course=course, assignment_name=ASSIGNMENT_NAME).first()
        if assignment is None:
            assignment = Assignment.objects.create(
                course=course, assignment_name=ASSIGNMENT_NAME,
                assignment_description=DESCRIPTION,
                start_date=self.now - timedelta(days=14),
                due_date=self.now + timedelta(days=8),
                submission_mode='individual',
                required_materials=['code', 'report', 'screenshots'],
                rubric=RUBRIC,
            )
            self.created.append('实验 ' + ASSIGNMENT_NAME)

        self._build_story(zhang, assignment, last_version=4, graded=True)
        self._build_story(lin, assignment, last_version=3, graded=False)
        self._build_story(wang, assignment, last_version=2, graded=False)

        self.stdout.write(self.style.SUCCESS(
            '主展示故事就绪：{} / {} / 张晨 V1-V4 / 林晓 V1-V3 / 王宇 V1-V2 / 周宁未提交'.format(
                COURSE_NAME, ASSIGNMENT_NAME)))
        if self.created:
            self.stdout.write('同时创建：' + '，'.join(self.created))
        if assignment.question.exists():
            self.stdout.write('已有提交：{} 条（重复执行不会重复创建）'.format(assignment.question.count()))
        self.stdout.write(self.style.WARNING('演示账号默认不可登录；如需登录请使用 seed_demo_data --enable-login。'))

    def _user(self, primary, fallback, last_name, first_name, user_type, teacher=False):
        user = User.objects.filter(username__in=[primary, fallback]).first()
        if user is None:
            user = User.objects.create_user(fallback, password=None, last_name=last_name,
                                            first_name=first_name, user_type=user_type,
                                            email='{}@example.com'.format(fallback))
            self.created.append('账号 {}（{}）'.format(fallback, str(user)))
        elif user.username.startswith('demo_') and (user.last_name, user.first_name) != (last_name, first_name):
            user.last_name, user.first_name = last_name, first_name
            user.save(update_fields=['last_name', 'first_name'])
        return user

    # ---------------- 版本故事 ----------------

    def _build_story(self, student, assignment, last_version, graded):
        if SubmitAssignment.objects.filter(author=student, assignment_ques=assignment).exists():
            return
        storage = SubmissionAttachment._meta.get_field('file').storage
        previous = None
        for version in range(1, last_version + 1):
            topic = {1: 'V1 · 初始模型实现', 2: 'V2 · 完善训练流程',
                     3: 'V3 · 优化模型结构', 4: 'V4 · 调整优化策略'}[version]
            description = {
                1: '完成数据读取与基础 CNN 模型，能够正常启动训练。',
                2: '增加验证集评估，补充模型保存与训练日志。',
                3: '加入 BatchNorm 与 Dropout，降低过拟合并补充实验结果。',
                4: '将 SGD 调整为 AdamW，降低学习率并加入学习率调度器，最终验证集准确率得到提升。',
            }[version]
            files = self._attachments(student, assignment, version, storage)
            submission = SubmitAssignment.objects.create(
                author=student, assignment_ques=assignment,
                topic=topic, description=description + '（演示数据）',
                assignment_file=files[0]['path'], current_slot=None,
                version_number=version, rubric_snapshot=assignment.rubric,
                participant_snapshot=[{'id': student.pk, 'username': student.username, 'name': str(student)}],
                submitted_date=self.now - timedelta(days=(last_version - version) * 2 + 1),
            )
            SubmissionAttachment.objects.bulk_create([
                SubmissionAttachment(submission=submission, file=item['path'], name=item['name'],
                                     category=item['category'], size=item['size'], checksum=item['checksum'])
                for item in files
            ])
            from assignments.code_review import manifest
            manifest(submission)  # 早失败：确保 ZIP 可被在线浏览与对比
            previous = submission
        if previous is not None:
            previous.current_slot = 1
            previous.save(update_fields=['current_slot'])
            if graded:
                previous.grade_assignment(
                    92, FEEDBACK, grader=assignment.course.teacher,
                    breakdown=[
                        {'title': '代码实现', 'points': 35, 'score': 33},
                        {'title': '模型设计', 'points': 25, 'score': 23},
                        {'title': '实验分析', 'points': 25, 'score': 22},
                        {'title': '报告规范', 'points': 15, 'score': 14},
                    ],
                )

    def _attachments(self, student, assignment, version, storage):
        items = []
        zip_data = zip_files(version)
        items.append(self._store(storage, student, version, 'source_code.zip', zip_data, 'code'))
        report = REPORTS[version].encode('utf-8')
        items.append(self._store(storage, student, version, '实验报告.md', report, 'report'))
        if version >= 3:
            shot = _chart_png([0.42, 0.61, 0.70, 0.79, 0.84, 0.86, 0.88])
            items.append(self._store(storage, student, version, '训练结果.png', shot, 'screenshots'))
        if version >= 4:
            log = LOG_V4.encode('utf-8')
            items.append(self._store(storage, student, version, '训练日志.txt', log, 'test_report'))
        return items

    def _store(self, storage, student, version, name, data, category):
        path = storage.save('experiments/showcase/{}-v{}/{}'.format(student.pk, version, name),
                            ContentFile(data, name=name))
        return {'path': path, 'name': name, 'category': category,
                'size': len(data), 'checksum': hashlib.sha256(data).hexdigest()}
