# 数据集管理

## 目录结构

```
data/
├── instruments/            # 器械图像数据集
│   ├── raw/                # 原始采集图像
│   ├── labeled/            # 标注后数据（YOLO 格式）
│   └── augmented/          # 数据增强后
├── nlp/                    # NLP 训练数据
│   ├── sft_train.jsonl     # SFT 训练集
│   ├── sft_val.jsonl       # 验证集
│   └── dpo_pairs.jsonl     # DPO 偏好对
├── demonstrations/         # 遥操作演示数据（VLA 训练用）
│   ├── sim/                # 仿真采集
│   └── real/               # 真机采集
└── vocabulary/
    └── instrument_vocab.json
```

## 数据标注规范

- 使用 Label Studio 进行 YOLO 格式标注
- 每条数据须包含：器械类别、夹取点、朝向点
- 标注完成后运行验证脚本：`python scripts/validate_labels.py`

## 版本管理

数据集使用 DVC 管理，不直接提交到 Git。

```bash
dvc pull      # 拉取最新数据集
dvc push      # 上传新数据
```

<div class="doc-footer">
  <span>最近更新 2026-03-18</span>
</div>
