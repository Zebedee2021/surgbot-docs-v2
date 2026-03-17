# 数据流规范

## 主流程数据流

```
语音输入
   │  ASR 转文字
   ▼
InstrumentCommand（NLP 输出）
   │  instrument_id + confidence
   ▼
┌──────────────────────────────┐
│    交叉验证 validate_cross()  │
│  NLP instrument_id           │
│  == 视觉 instrument_id ？    │
│  && 双方 confidence 达标？   │
└──────────────────────────────┘
   │ 验证通过
   ▼
GraspTarget（感知输出）
   │  grasp_point(3D) + orientation
   ▼
ActionSequence（VLA/规则输出）
   │  steps[]
   ▼
validate_path()（安全校验）
   │ 通过
   ▼
Dobot SDK → CR5AF 执行
```

## 异常路径

| 异常场景 | 行为 |
|----------|------|
| NLP 置信度 < 0.85 | 状态机停留 Parse，请求护士确认 |
| 视觉置信度 < 0.70 | 同上 |
| 交叉验证不一致 | 同上 |
| `validate_path()` 失败 | 拒绝执行，记录原因，通知护士 |
| 执行中力超阈值 | 立即急停，进入 Emergency |

## 日志规范

每条数据流经过的节点均须记录到 `core/logger.py`，格式：

```json
{
  "timestamp": 1710000000.0,
  "stage": "grasp_target",
  "instrument_id": "INS-031",
  "confidence": 0.92,
  "grasp_point": [120.5, -30.2, 180.0],
  "result": "pass"
}
```

<div class="doc-footer">
  <span>最近更新 2026-03-18</span>
</div>
