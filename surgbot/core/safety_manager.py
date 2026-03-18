"""
core/safety_manager.py
======================
执行前安全校验。所有路径点必须通过本模块校验才能发给机械臂。

雄安测试 P0-03：「路径无安全校验，机械臂会向错误位置运动，曾撞摄像头」
← 本文件直接解决这个问题。

使用方式：
    from core.safety_manager import safety, SafetyError

    try:
        safety.validate_path(path_points)
        safety.validate_grasp(grasp_target)
    except SafetyError as e:
        logger.error(f"Safety check failed: {e}")
        # 不执行，提示操作者
"""

from __future__ import annotations

import math
import time
from typing import Optional, TYPE_CHECKING

from core.config import cfg
from core.interfaces import GraspTarget

if TYPE_CHECKING:
    # 避免循环导入，只在类型注解时引用
    from hardware.dobot_arm import DobotArm


# ──────────────────────────────────────────
# 异常类
# ──────────────────────────────────────────

class SafetyError(Exception):
    """安全校验失败，禁止执行运动。"""
    pass


class WorkspaceViolation(SafetyError):
    """目标点超出工作空间边界。"""
    pass


class ConfidenceTooLow(SafetyError):
    """感知置信度低于阈值，拒绝执行。"""
    pass


class LargeStepDetected(SafetyError):
    """单步移动距离过大，疑似错误轨迹。"""
    pass


# ──────────────────────────────────────────
# 工作空间边界（从 cfg 读取，运行时可重载）
# ──────────────────────────────────────────

def _in_workspace(x: float, y: float, z: float) -> bool:
    s = cfg.safety
    return (s.x_min <= x <= s.x_max and
            s.y_min <= y <= s.y_max and
            s.z_min <= z <= s.z_max)


def _point_dist(p1: list[float], p2: list[float]) -> float:
    """笛卡尔两点欧氏距离（只用前3维 x,y,z）。"""
    return math.sqrt(sum((p1[i] - p2[i]) ** 2 for i in range(3)))


# ──────────────────────────────────────────
# 核心校验类
# ──────────────────────────────────────────

class SafetyManager:
    """
    单例安全管理器。
    提供三类校验：
      1. validate_point    — 单个坐标点是否在工作空间内
      2. validate_path     — 路径序列中每个点都合法，且单步不超过最大距离
      3. validate_grasp    — GraspTarget 置信度是否达标
    以及急停接口：
      4. emergency_stop    — 立即停止机械臂并记录日志
    """

    def __init__(self):
        self._stop_count = 0
        self._last_stop_time: Optional[float] = None

    # --------------------------------------------------
    # 1. 单点校验
    # --------------------------------------------------
    def validate_point(self, point: list[float], label: str = "") -> None:
        """
        校验单个路径点（pose 模式：[x,y,z,rx,ry,rz,mode] 或 [x,y,z,...]）。
        只校验前三维 x/y/z。
        抛出 WorkspaceViolation 则不允许执行。
        """
        if len(point) < 3:
            raise SafetyError(f"Invalid point format (len={len(point)}): {point}")

        x, y, z = point[0], point[1], point[2]

        # mode=1 表示关节角模式，不做笛卡尔边界检查
        if len(point) >= 7 and int(point[6]) == 1:
            return  # 关节角模式跳过笛卡尔边界检查

        if not _in_workspace(x, y, z):
            s = cfg.safety
            tag = f"[{label}] " if label else ""
            raise WorkspaceViolation(
                f"{tag}Point ({x:.1f}, {y:.1f}, {z:.1f}) outside workspace "
                f"X[{s.x_min},{s.x_max}] Y[{s.y_min},{s.y_max}] Z[{s.z_min},{s.z_max}]"
            )

    # --------------------------------------------------
    # 2. 路径校验
    # --------------------------------------------------
    def validate_path(self, path: list[list[float]],
                      current_pos: Optional[list[float]] = None) -> None:
        """
        校验完整路径序列。
        - 每个点都必须在工作空间内（关节角模式跳过）
        - 相邻两点的笛卡尔距离不超过 max_single_step_dist
        - 路径不能为空

        current_pos: 当前末端坐标（用于检查第一步的移动距离）
        """
        if not path:
            raise SafetyError("Path is empty, refusing to execute.")

        prev = current_pos
        for i, point in enumerate(path):
            self.validate_point(point, label=f"point[{i}]")

            # 只对 pose 模式（mode=0）做步长检查
            if len(point) >= 7 and int(point[6]) == 1:
                prev = None  # 关节角切换后，下一步不做距离连续性检查
                continue

            if prev is not None and len(prev) >= 3:
                mode_prev = int(prev[6]) if len(prev) >= 7 else 0
                if mode_prev == 0:  # 两点都是 pose 模式才检查距离
                    dist = _point_dist(point, prev)
                    if dist > cfg.safety.max_single_step_dist:
                        raise LargeStepDetected(
                            f"Step [{i-1}→{i}] distance {dist:.1f}mm exceeds "
                            f"limit {cfg.safety.max_single_step_dist}mm. "
                            f"Possible bad coordinate. Refusing to execute."
                        )
            prev = point

    # --------------------------------------------------
    # 3. 感知置信度校验
    # --------------------------------------------------
    def validate_grasp(self, target: GraspTarget) -> None:
        """
        校验 GraspTarget 是否满足执行条件。
        名义坐标兜底（is_nominal=True）始终允许执行。
        """
        if target.is_nominal:
            return  # 已经是兜底坐标，允许执行

        min_conf = cfg.perception.min_confidence
        if target.confidence < min_conf:
            raise ConfidenceTooLow(
                f"GraspTarget confidence {target.confidence:.2f} < "
                f"threshold {min_conf:.2f} for slot={target.slot_id}. "
                f"Ask operator to confirm instrument placement."
            )

    # --------------------------------------------------
    # 4. 急停
    # --------------------------------------------------
    def emergency_stop(self, robot=None, reason: str = "manual") -> None:
        """
        触发急停：
        1. 调用机械臂 stopCurrentMotion()
        2. 记录急停日志
        3. 累计急停次数（用于监控）
        """
        self._stop_count += 1
        self._last_stop_time = time.time()

        # 延迟 import 避免循环依赖
        try:
            from core.logger import get_logger
            log = get_logger("safety")
            log.warning(
                f"[EMERGENCY STOP #{self._stop_count}] reason={reason} "
                f"at {time.strftime('%H:%M:%S')}"
            )
        except Exception:
            print(f"[EMERGENCY STOP #{self._stop_count}] reason={reason}")

        if robot is not None:
            try:
                robot.stop()
            except Exception as e:
                print(f"[Safety] stop() failed: {e}")

    # --------------------------------------------------
    # 辅助
    # --------------------------------------------------
    @property
    def stop_count(self) -> int:
        return self._stop_count

    def workspace_info(self) -> dict:
        """返回当前工作空间配置，供 UI/调试查看。"""
        s = cfg.safety
        return {
            "x": [s.x_min, s.x_max],
            "y": [s.y_min, s.y_max],
            "z": [s.z_min, s.z_max],
            "force_threshold": s.force_threshold,
            "max_step_dist_mm": s.max_single_step_dist,
        }


# ──────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────

safety = SafetyManager()
