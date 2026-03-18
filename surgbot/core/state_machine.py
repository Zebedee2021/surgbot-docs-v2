"""
core/state_machine.py
──────────────────────
SurgBot 主状态机

将 NLP → 感知 → 安全校验 → 规划 → 执行 串联成完整流程。

状态图::

    IDLE
      │ 收到语音触发
      ▼
    RECOGNIZING  (NLP 关键词匹配)
      │ 匹配成功
      ▼
    PERCEIVING   (感知模块：ROI YOLO)
      │ 目标确认
      ▼
    PLANNING     (RulePlanner 生成动作序列)
      │
      ▼
    EXECUTING    (DobotArm 逐步执行)
      │ 完成
      ▼
    DELIVERING   (等待医生接取)
      │ 力反馈 / 超时
      ▼
    RESETTING    → IDLE

    任意状态发生错误 → ERROR → IDLE（急停后）

MVP 阶段感知模块为 mock（直接读注册表名义坐标），
可通过 set_perception_fn() 注入真实感知结果。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

from core.config import cfg
from core.interfaces import ActionType, GraspTarget, InstrumentCommand
from core.logger import get_logger
from core.safety_manager import safety
from hardware.dobot_arm import DobotArm
from modules.decision.rule_planner import planner
from modules.nlp.keyword_matcher import matcher
from modules.perception.position_registry import registry

log = get_logger("state_machine")


# ──────────────────────────────────────────────
# 状态枚举
# ──────────────────────────────────────────────

class State(Enum):
    IDLE        = auto()
    RECOGNIZING = auto()
    PERCEIVING  = auto()
    PLANNING    = auto()
    EXECUTING   = auto()
    DELIVERING  = auto()
    RESETTING   = auto()
    ERROR       = auto()


# ──────────────────────────────────────────────
# 运行结果
# ──────────────────────────────────────────────

@dataclass
class RunResult:
    success: bool
    instrument_name: str = ""
    slot_id: str = ""
    elapsed_s: float = 0.0
    error: str = ""
    state_trace: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# 状态机
# ──────────────────────────────────────────────

PerceptionFn = Callable[[InstrumentCommand], Optional[GraspTarget]]


class SurgBotStateMachine:
    """
    SurgBot 主状态机（单实例）。

    用法（mock 模式，无需真实硬件）::

        sm = SurgBotStateMachine(mock=True)
        result = sm.run("递持针器")
        print(result)

    注入真实感知函数::

        sm.set_perception_fn(my_yolo_grasp_fn)
    """

    def __init__(self, mock: bool = False) -> None:
        self._state = State.IDLE
        self._arm = DobotArm(mock=mock)
        self._perception_fn: PerceptionFn = self._nominal_perception
        self._mock = mock

    # ── 外部接口 ─────────────────────────────

    def set_perception_fn(self, fn: PerceptionFn) -> None:
        """注入感知函数（替代 mock 名义坐标）。"""
        self._perception_fn = fn
        log.info("感知函数已注入（真实视觉模式）")

    def run(
        self,
        text: str,
        *,
        handover_timeout: float = 60.0,
    ) -> RunResult:
        """
        接收语音文本，执行完整流程。

        :param text: ASR 识别结果（中文）
        :param handover_timeout: 等待医生接取的超时（秒）
        :returns: RunResult
        """
        t0 = time.time()
        trace: list[str] = []

        try:
            # ① NLP 匹配
            self._transition(State.RECOGNIZING, trace)
            cmd = matcher.match(text)
            if cmd is None:
                return self._error(f"未识别到有效器械指令: '{text}'", t0, trace)

            log.info(f"NLP: {cmd.name}  conf={cmd.confidence:.2f}  slot={cmd.slot_id}")

            # ② 感知
            self._transition(State.PERCEIVING, trace)
            grasp = self._perception_fn(cmd)
            if grasp is None:
                return self._error(f"感知失败，无法确定夹取目标: {cmd.name}", t0, trace)

            log.info(
                f"感知: slot={grasp.slot_id}  "
                f"pt={grasp.grasp_point}  "
                f"conf={grasp.confidence:.2f}  "
                f"nominal={grasp.is_nominal}"
            )

            # ③ 规划
            self._transition(State.PLANNING, trace)
            seq = planner.plan(cmd, grasp)
            log.info(f"规划: {len(seq.steps)} 步")

            # ④ 执行
            self._transition(State.EXECUTING, trace)
            self._execute_sequence(seq, grasp, handover_timeout)

            self._transition(State.IDLE, trace)
            elapsed = time.time() - t0
            log.info(f"完整流程完成: {cmd.name}  耗时={elapsed:.1f}s")

            return RunResult(
                success=True,
                instrument_name=cmd.name,
                slot_id=grasp.slot_id,
                elapsed_s=round(elapsed, 2),
                state_trace=trace,
            )

        except Exception as exc:
            log.exception(f"状态机异常: {exc}")
            try:
                safety.emergency_stop(self._arm._robot, reason=str(exc))
            except Exception:
                pass
            self._transition(State.IDLE, trace)
            return self._error(str(exc), t0, trace)

    def shutdown(self) -> None:
        """关闭机械臂连接。"""
        self._arm.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()

    # ── 内部执行 ─────────────────────────────

    def _execute_sequence(self, seq, grasp: GraspTarget, handover_timeout: float) -> None:
        """逐步执行 ActionSequence。"""
        from core.interfaces import ActionType as AT

        arm = self._arm
        rz = grasp.orientation_deg
        gp = seq.steps[0].gripper_preset_id if seq.steps else 1  # fallback

        for step in seq.steps:
            log.debug(f"执行步骤: [{step.action_type.value}] {step.description}")

            t = step.action_type
            pt = step.target_pose

            if t == AT.MOVE_APPROACH:
                arm.approach(pt, step.orientation_deg or rz)

            elif t == AT.VISUAL_CONFIRM:
                # MVP: 打印日志，真实版本调用感知模块重新识别
                log.info("视觉确认步骤（MVP mock：跳过，使用已有目标）")

            elif t == AT.MOVE_GRASP:
                arm.grasp(pt, step.orientation_deg or rz,
                          gripper_preset_id=step.gripper_preset_id)

            elif t == AT.CLOSE_GRIPPER:
                # grasp() 内部已包含夹爪操作，此步骤在 DobotArm 中已处理
                pass

            elif t == AT.MOVE_LIFT:
                arm.lift(pt, step.orientation_deg or rz)

            elif t == AT.MOVE_DELIVER:
                self._transition(State.DELIVERING, [])
                arm.deliver()

            elif t == AT.WAIT_FORCE:
                arm.wait_for_handover(
                    timeout=handover_timeout,
                    gripper_preset_id=step.gripper_preset_id,
                )

            elif t == AT.MOVE_RESET:
                self._transition(State.RESETTING, [])
                arm.reset()

            elif t == AT.EMERGENCY_STOP:
                safety.emergency_stop(arm._robot, reason="序列中包含 EMERGENCY_STOP 步骤")
                raise RuntimeError("EMERGENCY_STOP triggered in sequence")

    # ── 名义感知（MVP mock）─────────────────

    def _nominal_perception(self, cmd: InstrumentCommand) -> Optional[GraspTarget]:
        """
        MVP 阶段感知：直接读取注册表中的名义坐标。
        slot_id 由 NLP 层填入；若为 None 则按名称查找。
        """
        slot_id = cmd.slot_id
        slot = registry.get_by_id(slot_id) if slot_id else registry.find(cmd.name)

        if slot is None:
            log.warning(f"注册表中找不到: slot_id={slot_id}  name={cmd.name}")
            return None

        return GraspTarget(
            slot_id=slot.slot_id,
            instrument_id=slot.instrument_id,
            grasp_point=list(slot.grasp_point),
            orientation_deg=slot.orientation_deg,
            confidence=0.90,        # 名义坐标，固定置信度
            is_nominal=True,
        )

    # ── 状态转换 ─────────────────────────────

    def _transition(self, new_state: State, trace: list[str]) -> None:
        log.debug(f"状态: {self._state.name} → {new_state.name}")
        self._state = new_state
        trace.append(new_state.name)

    def _error(self, msg: str, t0: float, trace: list[str]) -> RunResult:
        self._transition(State.ERROR, trace)
        self._transition(State.IDLE, trace)
        return RunResult(
            success=False,
            error=msg,
            elapsed_s=round(time.time() - t0, 2),
            state_trace=trace,
        )

    @property
    def state(self) -> State:
        return self._state
