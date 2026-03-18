"""
modules/decision/rule_planner.py
──────────────────────────────────
规则动作规划器（MVP 阶段）

输入: InstrumentCommand + GraspTarget（已通过安全校验）
输出: ActionSequence（可直接交给 DobotArm 执行）

设计要点
- 纯规则，无学习，确定性强，便于调试
- 动作序列：approach → grasp → lift → deliver → wait_handover → reset
- 可选择在 grasp 前插入"视觉确认"步骤（confidence 高时跳过）
- 每步插入安全校验点（path 中间点），防止大步长
- 未来替换为 VLA 时只需实现相同 plan() 接口
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.config import cfg
from core.interfaces import (
    ActionSequence, ActionStep, ActionType,
    GraspTarget, InstrumentCommand,
)
from core.logger import get_logger
from core.safety_manager import safety
from modules.perception.position_registry import registry

log = get_logger("rule_planner")


# ──────────────────────────────────────────────
# 规划器
# ──────────────────────────────────────────────

class RulePlanner:
    """
    确定性规则规划器。

    用法::

        from modules.decision.rule_planner import planner

        seq = planner.plan(cmd, grasp)
        # seq.steps → List[ActionStep]
    """

    def plan(
        self,
        cmd: InstrumentCommand,
        grasp: GraspTarget,
        *,
        skip_visual_confirm: Optional[bool] = None,
    ) -> ActionSequence:
        """
        生成完整动作序列。

        :param cmd: NLP 输出的器械指令
        :param grasp: 感知模块输出的夹取目标
        :param skip_visual_confirm: None → 根据置信度自动决定
        :returns: ActionSequence（含所有 ActionStep）
        """
        # 安全前置校验
        safety.validate_grasp(grasp)

        slot = registry.get_by_id(grasp.slot_id)
        if slot is None:
            raise ValueError(f"slot_id 未注册: {grasp.slot_id}")

        pt   = grasp.grasp_point          # [x, y, z] 或 [x, y, z, rx, ry, rz]
        rz   = grasp.orientation_deg
        z_ap = pt[2] + cfg.robot.z_approach_offset   # approach 高度
        gp   = slot.gripper_preset_id

        # approach 点（Z 高）
        pt_approach = _with_z(pt, z_ap)
        # 递送点
        pt_deliver  = list(registry.deliver_point) or cfg.robot.deliver_pose
        # 复位点
        pt_reset    = list(registry.reset_pose) or cfg.robot.reset_pose

        # 路径校验（approach → grasp → lift → deliver → reset）
        path_to_validate = [pt_approach, pt, pt_approach, pt_deliver, pt_reset]
        safety.validate_path(path_to_validate)

        # ── 构建步骤列表 ──────────────────────

        steps: list[ActionStep] = []

        # ① 移到 approach 点
        steps.append(ActionStep(
            action_type=ActionType.MOVE_APPROACH,
            target_pose=pt_approach,
            orientation_deg=rz,
            description=f"移至 approach 点 ({pt_approach[0]:.0f},{pt_approach[1]:.0f},{pt_approach[2]:.0f})",
        ))

        # ② 可选：视觉确认（低置信度时触发重新识别）
        if skip_visual_confirm is None:
            skip_visual_confirm = grasp.confidence >= cfg.perception.confidence_threshold_high
        if not skip_visual_confirm:
            steps.append(ActionStep(
                action_type=ActionType.VISUAL_CONFIRM,
                target_pose=pt_approach,
                orientation_deg=rz,
                description="视觉二次确认（置信度偏低）",
            ))

        # ③ 下降到夹取点
        steps.append(ActionStep(
            action_type=ActionType.MOVE_GRASP,
            target_pose=pt,
            orientation_deg=rz,
            description=f"下降至夹取点 ({pt[0]:.0f},{pt[1]:.0f},{pt[2]:.0f}) Rz={rz}°",
        ))

        # ④ 关闭夹爪
        steps.append(ActionStep(
            action_type=ActionType.CLOSE_GRIPPER,
            target_pose=pt,
            gripper_preset_id=gp,
            description=f"关闭夹爪 preset={gp}",
        ))

        # ⑤ 上升（lift）
        steps.append(ActionStep(
            action_type=ActionType.MOVE_LIFT,
            target_pose=pt_approach,
            orientation_deg=rz,
            description=f"上升至 lift 点 Z={z_ap:.0f} mm",
        ))

        # ⑥ 移到递送点
        steps.append(ActionStep(
            action_type=ActionType.MOVE_DELIVER,
            target_pose=pt_deliver,
            description=f"移至递送点 ({pt_deliver[0]:.0f},{pt_deliver[1]:.0f},{pt_deliver[2]:.0f})",
        ))

        # ⑦ 等待医生接取（力反馈触发或超时）
        steps.append(ActionStep(
            action_type=ActionType.WAIT_FORCE,
            target_pose=pt_deliver,
            gripper_preset_id=-1,           # -1 = 完全打开
            description="等待医生接取（力反馈触发）",
        ))

        # ⑧ 复位
        steps.append(ActionStep(
            action_type=ActionType.MOVE_RESET,
            target_pose=pt_reset,
            description="复位至待机姿态",
        ))

        seq = ActionSequence(
            steps=steps,
            instrument_id=cmd.instrument_id,
            instrument_name=cmd.name,
            slot_id=grasp.slot_id,
        )

        log.info(
            f"规划完成: {cmd.name} ({grasp.slot_id})  "
            f"steps={len(steps)}  "
            f"visual_confirm={not skip_visual_confirm}"
        )
        return seq


# ── 工具函数 ─────────────────────────────────

def _with_z(pt: list[float], new_z: float) -> list[float]:
    """替换坐标列表的 Z 值（保留 rx, ry, rz 如有）。"""
    out = list(pt)
    out[2] = new_z
    return out


# ── 全局单例 ─────────────────────────────────

planner = RulePlanner()
