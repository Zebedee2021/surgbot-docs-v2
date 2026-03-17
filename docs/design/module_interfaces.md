# 模块接口定义

!!! warning "活跃文档"
    本页是系统设计的核心约定。任何模块修改输出格式前，须先在此更新接口定义并通知上下游负责人。

## 接口总览

各模块之间通过明确定义的 Python 数据结构传递信息，不直接引用对方的内部实现。

```
语音输入
   │
   ▼
[NLP 模块] ──→ InstrumentCommand
   │
[感知模块] ──→ GraspTarget
   │        ↘
   └──────→ [决策模块 / VLA] ──→ ActionSequence
                                       │
                                  [执行模块]
                                       │
                                  CR5AF 机械臂
```

---

## 接口定义

### `InstrumentCommand`
**来源：** NLP 模块 &emsp; **消费方：** 决策模块

```python
@dataclass
class InstrumentCommand:
    instrument_name: str      # 标准化器械名，来自词库（如 "持针器_大"）
    instrument_id: str        # 词库编号（如 "INS-031"）
    confidence: float         # 识别置信度，< 0.85 时触发二次确认
    raw_text: str             # ASR 原始文本，用于调试
    timestamp: float          # Unix 时间戳
```

**约束：**

- `instrument_name` 必须是 [`instrument_vocab.json`](../modules/nlp/instrument_vocab.md) 中的合法值，不允许自由文本
- `confidence < 0.85` 时决策模块应暂停并请求护士确认，不得直接执行

---

### `GraspTarget`
**来源：** 感知模块 &emsp; **消费方：** 决策模块、执行模块

```python
@dataclass
class GraspTarget:
    instrument_name: str      # 与 InstrumentCommand 对齐
    instrument_id: str        # 与 InstrumentCommand 对齐，用于交叉验证
    grasp_point: np.ndarray   # shape (3,)，机械臂坐标系下的夹取点 [x, y, z]，单位 mm
    grasp_orientation: float  # 夹爪旋转角，单位 deg，范围 [0, 180]
    delivery_side: str        # "handle_to_doctor"（把手朝向医生）| "tip_to_doctor"
    confidence: float         # 检测置信度
    bbox: list                # [x1, y1, x2, y2]，图像像素坐标，调试用
    depth_mm: float           # 目标中心点深度，单位 mm
    timestamp: float
```

**约束：**

- `grasp_point` 须经过手眼标定矩阵变换，**不得**直接使用像素坐标
- `delivery_side` 默认 `"handle_to_doctor"`，特殊器械（如剪刀）由词库配置覆盖
- 执行前须检查 `grasp_point` 是否在机械臂工作空间内（见[全局安全约束](safety_constraints.md)）

---

### `ActionSequence`
**来源：** 决策模块 &emsp; **消费方：** 执行模块

```python
@dataclass
class ActionStep:
    action_type: str          # "move_to" | "grasp" | "release" | "home"
    target_pose: np.ndarray   # shape (6,)，[x, y, z, rx, ry, rz]，单位 mm / deg
    speed: float              # 速度百分比，范围 (0, 1]，默认 0.3
    force_threshold: float    # 力控阈值，单位 N，超出则触发急停

@dataclass
class ActionSequence:
    steps: list[ActionStep]
    source: str               # "vla" | "rule_based"（规则兜底路径）
    estimated_duration: float # 预估总时长，单位 s
    timestamp: float
```

**约束：**

- `speed` 在医院现场模式下上限为 `0.4`，实验室模式为 `0.8`（由 `config.py` 中 `SCENE_MODE` 控制）
- `force_threshold` 默认 `5.0N`，夹取金属器械时不得超过 `8.0N`
- VLA 输出的动作序列须经执行模块的**路径安全校验**（见[全局安全约束](safety_constraints.md)）后才可下发

---

## 跨模块验证机制

感知模块与 NLP 模块的输出须进行交叉验证，防止误识别导致错误执行：

```python
def validate_cross_module(cmd: InstrumentCommand, target: GraspTarget) -> bool:
    """
    返回 False 时状态机进入 Parse 状态重新确认，不进入 Execute。
    """
    if cmd.instrument_id != target.instrument_id:
        return False                           # 语音识别与视觉识别的器械不一致
    if cmd.confidence < 0.85 or target.confidence < 0.7:
        return False                           # 任一置信度不足
    if not workspace_check(target.grasp_point):
        return False                           # 夹取点超出工作空间
    return True
```

!!! note "二维码增强验证（规划中）"
    现场测试问题 #6 提出在器械上打印二维码，届时增加第三重验证：  
    `qr_code_id == cmd.instrument_id == target.instrument_id`

---

## 变更记录

| 日期 | 变更内容 | 影响模块 | 责任人 |
|------|----------|----------|--------|
| 2026-03-18 | 初版接口定义，统一 `instrument_id` 字段 | 全部 | 任松 |

<div class="doc-footer">
  <span>负责人：任松（接口规范）</span>
  <span>最近更新 2026-03-18</span>
</div>
