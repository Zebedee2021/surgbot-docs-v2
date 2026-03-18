"""
core/interfaces.py
==================
全系统共用的数据结构定义。
所有模块之间只通过这里的 dataclass 传递数据，不传原始 dict。

层级：
    NLP        → InstrumentCommand
    Perception → GraspTarget
    Decision   → ActionSequence (list[ActionStep])
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────
# NLP 层输出
# ──────────────────────────────────────────

@dataclass
class InstrumentCommand:
    """语音指令经 NLP 解析后的结构化结果。"""
    instrument_id: str          # 器械唯一ID，如 "INS-031"，对应 registry.json 中的 key
    name: str                   # 标准器械名，如 "持针器_大"
    confidence: float           # NLP 置信度，0~1
    source_text: str            # 原始语音文本，用于日志 & 审计
    slot_id: Optional[str] = None   # 预期槽位，如 "slot_01"（可由 registry 反查填入）

    def is_valid(self) -> bool:
        return bool(self.instrument_id) and self.confidence >= 0.0


# ──────────────────────────────────────────
# 感知层输出
# ──────────────────────────────────────────

@dataclass
class GraspTarget:
    """感知模块输出的夹取目标，包含位置、方向与置信度。"""
    slot_id: str                        # 来源槽位，如 "slot_01"
    instrument_id: str                  # 器械 ID
    grasp_point: list[float]            # [x, y, z]，机械臂坐标系，单位 mm
    orientation_deg: float              # 末端 Rz 角度，°，已修正朝向（手柄朝医生）
    confidence: float                   # 视觉置信度，0~1
    is_nominal: bool = False            # True 表示视觉失败、使用了名义坐标兜底
    visual_offset: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    # 视觉相对名义坐标的偏移量 [dx, dy, dz]，用于记录和诊断

    def is_valid(self, min_confidence: float = 0.70) -> bool:
        """置信度达标，或已使用名义坐标兜底（兜底也允许执行）。"""
        return self.is_nominal or self.confidence >= min_confidence

    @property
    def x(self) -> float:
        return self.grasp_point[0]

    @property
    def y(self) -> float:
        return self.grasp_point[1]

    @property
    def z(self) -> float:
        return self.grasp_point[2]


# ──────────────────────────────────────────
# 决策层输出
# ──────────────────────────────────────────

class ActionType(Enum):
    """动作原语枚举，对应执行层的单个运动步骤。"""
    MOVE_APPROACH   = "move_approach"   # 移动到夹取点正上方（z + approach_offset）
    MOVE_GRASP      = "move_grasp"      # 下降到夹取点
    CLOSE_GRIPPER   = "close_gripper"   # 闭合夹爪（夹取）
    MOVE_LIFT       = "move_lift"       # 提升（离开托盘）
    MOVE_DELIVER    = "move_deliver"    # 移动到递送点
    OPEN_GRIPPER    = "open_gripper"    # 松开夹爪（等待医生接取）
    WAIT_FORCE      = "wait_force"      # 等待力反馈触发（医生取走）
    MOVE_RESET      = "move_reset"      # 回到待机姿态
    EMERGENCY_STOP  = "emergency_stop"  # 急停


@dataclass
class ActionStep:
    """单个动作步骤。"""
    action_type: ActionType
    target_pose: Optional[list[float]] = None   # [x,y,z,rx,ry,rz, mode]，MOVE_* 类型使用
    gripper_preset_id: int = -1                 # CLOSE/OPEN_GRIPPER 类型使用
    description: str = ""                       # 可读描述，用于日志

    def __post_init__(self):
        if not self.description:
            self.description = self.action_type.value


@dataclass
class ActionSequence:
    """决策模块输出的完整动作序列。"""
    steps: list[ActionStep]
    instrument_id: str
    instrument_name: str
    grasp_target: GraspTarget
    created_at: float = field(default_factory=__import__('time').time)

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)
