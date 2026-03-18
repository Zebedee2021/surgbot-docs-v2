"""
hardware/dobot_arm.py
=====================
DobotArm — 高层语义封装，对外提供手术场景所需的动作接口。

设计原则
--------
1. 底层驱动层（RobotControlModule）不动，保留其完整 TCP / 力反馈 / 状态机逻辑。
2. 本层只做三件事：
   a. 从 core/config.py 注入参数（速度、Z 偏移、力反馈阈值），彻底消除硬编码。
   b. 每次执行路径前调用 safety_manager.validate_path()，拒绝超界轨迹。
   c. 提供手术场景语义接口：approach → grasp → lift → deliver → wait_force → reset。

雄安测试直接对应
---------------
  P0-02 参数须改代码   → speed / z_approach_offset / force_threshold 全由 cfg 注入
  P0-03 路径无安全校验 → execute_path() 在发给底层前先过 safety.validate_path()
  P1-02 Z 轴高度不一致 → z_compensation_mm 支持托盘平面标定后的额外偏移

依赖关系
--------
  hardware/dobot_arm.py
      └── 依赖  RobotControlModule  (已有代码，通过 sys.path 引入或直接 copy 到 hardware/)
      └── 依赖  core/config.py      (cfg 单例)
      └── 依赖  core/safety_manager (safety 单例)
      └── 依赖  core/logger.py      (get_logger)

使用方式
--------
    from hardware.dobot_arm import DobotArm

    arm = DobotArm()          # 从 cfg 读取 IP，自动连接
    arm.reset()               # 运动到待机姿态
    arm.approach([x, y, z, rz])    # 移动到夹取点正上方
    arm.grasp([x, y, z, rz])       # 下降并夹取
    arm.deliver()                  # 移动到递送点
    arm.wait_for_handover()        # 等待医生取走（力反馈触发）
    arm.reset()               # 回到待机
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

from core.config import cfg
from core.safety_manager import safety, SafetyError
from core.logger import get_logger, log_motion_start, log_motion_done, log_force_event

log = get_logger("arm")

# ──────────────────────────────────────────
# 引入底层驱动（RobotControlModule）
# 优先从本项目的 hardware/_controller.py 导入；
# 找不到则从原 RobotServer 路径 fallback。
# ──────────────────────────────────────────

def _import_controller():
    """
    尝试导入底层驱动。找不到时静默返回 None（不打印 WARNING），
    由调用方（DobotArm.__init__）根据是否传入 mock=True 决定日志级别。
    """
    try:
        from hardware._controller import RobotControlModule
        return RobotControlModule
    except ImportError:
        pass

    # fallback：从原 RobotServer 目录导入
    original_path = Path(__file__).resolve().parents[2] / "医疗机器人代码" / "RobotServer"
    if original_path.exists():
        sys.path.insert(0, str(original_path))
        try:
            from bitRobot.service.robot_control.controller import RobotControlModule
            log.info(f"[Arm] Loaded RobotControlModule from {original_path}")
            return RobotControlModule
        except ImportError as e:
            log.debug(f"[Arm] Import from {original_path} failed: {e}")

    # 静默返回 None，调用方负责决定如何记录
    return None


RobotControlModule = _import_controller()


# ──────────────────────────────────────────
# Mock（离线开发 / 单元测试用）
# ──────────────────────────────────────────

class _MockRobot:
    """当机械臂未连接时的占位实现，接口与 RobotControlModule 一致。"""

    # 急停计数（供测试查询）
    stop_count: int = 0

    def __init__(self, ip: str, intentional: bool = False, **_):
        """
        intentional=True  → 明确传入 mock=True（演示/测试），用 INFO 级别
        intentional=False → 控制器找不到的自动降级，用 WARNING 级别
        """
        if intentional:
            log.info(f"[Arm] Mock 模式（演示/离线开发）— ip={ip} 未连接")
        else:
            log.warning(f"[Arm] 控制器模块未找到，自动降级为 Mock — 请确认是否需要真实连接 ip={ip}")

    def executePath(self, path):
        log.info(f"[MOCK] executePath {len(path)} points")
        time.sleep(0.05)
        return {"status": "queued", "mock": True}

    def isMoving(self):
        return False

    def stopCurrentMotion(self):
        _MockRobot.stop_count += 1
        log.info("[MOCK] stopCurrentMotion")

    def setSpeed(self, speed):
        log.info(f"[MOCK] setSpeed {speed}")

    def setForceThreshold(self, threshold):
        log.info(f"[MOCK] setForceThreshold {threshold}")

    def startForceDetection(self):
        log.info("[MOCK] startForceDetection")

    def stopForceDetection(self):
        log.info("[MOCK] stopForceDetection")

    def getForceStatus(self):
        return {"is_applied": False, "current_force_torque": [0.0] * 6}

    def open_gripper(self, preset_id):
        log.info(f"[MOCK] open_gripper preset={preset_id}")

    def close_gripper(self, preset_id):
        log.info(f"[MOCK] close_gripper preset={preset_id}")
        return True

    def get_gripper_status(self):
        return True

    def shutdown(self):
        log.info("[MOCK] shutdown")

    isStop = False


# ──────────────────────────────────────────
# DobotArm 封装层
# ──────────────────────────────────────────

class DobotArm:
    """
    手术场景语义封装。

    参数
    ----
    z_compensation_mm : float
        托盘平面标定后的 Z 轴全局补偿量（mm）。
        解决雄安问题 #3：托盘不同位置 Z 高度不一致。
        上机标定后写入 config.toml 的 robot.z_grasp_offset，
        也可在运行时通过 set_z_compensation() 动态调整。

    mock : bool
        True → 强制使用 Mock 实现，无需连接真实机械臂。
    """

    # 等待运动完成的轮询间隔（秒）
    _POLL_INTERVAL = 0.05
    # 等待力反馈的最长时间（秒），超时认为医生已取走
    _FORCE_WAIT_TIMEOUT = 60.0
    # 夹爪动作后等待到位的时间（秒）
    _GRIPPER_SETTLE = 0.3

    def __init__(self,
                 z_compensation_mm: float = 0.0,
                 mock: bool = False,
                 sim: bool = False):

        self._z_comp = z_compensation_mm or cfg.robot.z_grasp_offset
        self._current_instrument_id: str = ""

        # 初始化底层驱动
        if sim:
            # MuJoCo 物理仿真模式
            from hardware.mujoco_robot import MuJoCoRobot
            self._robot = MuJoCoRobot()
            self._is_mock = False
            self._is_sim  = True
            log.info("[Arm] MuJoCo 仿真模式已启动")
        elif mock:
            # 明确要求 mock（演示/单测）→ INFO 级别
            self._robot = _MockRobot(ip=cfg.robot.ip, intentional=True)
            self._is_mock = True
            self._is_sim  = False
        elif RobotControlModule is None:
            # 控制器找不到的被动降级 → WARNING 级别
            self._robot = _MockRobot(ip=cfg.robot.ip, intentional=False)
            self._is_mock = True
            self._is_sim  = False
        else:
            log.info(f"[Arm] Connecting to Dobot @ {cfg.robot.ip} ...")
            self._robot = RobotControlModule(
                ip=cfg.robot.ip,
                dashboard_port=cfg.robot.dashboard_port,
                feed_port=cfg.robot.feed_port,
            )
            self._is_mock = False

        # 注入配置参数
        self._robot.setSpeed(cfg.robot.speed)
        self._robot.setForceThreshold(cfg.safety.force_threshold)
        log.info(
            f"[Arm] Ready  speed={cfg.robot.speed}  "
            f"z_comp={self._z_comp:+.1f}mm  mock={self._is_mock}"
        )

    # ──────────────────────────────────────
    # 配置动态调整（演示时不改代码）
    # ──────────────────────────────────────

    def set_speed(self, speed: int) -> None:
        """运行时调整速度百分比（1~100）。"""
        cfg.robot.speed = max(1, min(100, speed))
        self._robot.setSpeed(cfg.robot.speed)
        log.info(f"[Arm] Speed updated → {cfg.robot.speed}")

    def set_z_compensation(self, offset_mm: float) -> None:
        """运行时更新 Z 补偿量（mm）。无需重启。"""
        self._z_comp = offset_mm
        log.info(f"[Arm] Z compensation → {self._z_comp:+.1f}mm")

    def set_force_threshold(self, threshold_n: float) -> None:
        """运行时调整力反馈触发阈值（N）。"""
        cfg.safety.force_threshold = abs(threshold_n)
        self._robot.setForceThreshold(cfg.safety.force_threshold)
        log.info(f"[Arm] Force threshold → {cfg.safety.force_threshold:.2f}N")

    # ──────────────────────────────────────
    # 核心动作接口
    # ──────────────────────────────────────

    def reset(self) -> None:
        """回到待机姿态（关节角模式，不做笛卡尔边界检查）。"""
        log.info("[Arm] → reset pose")
        t0 = time.time()
        self._safe_execute([cfg.robot.reset_pose], label="reset")
        self._wait_until_idle()
        log_motion_done("reset", (time.time() - t0) * 1000)

    def approach(self, grasp_point: list[float], rz_deg: float) -> None:
        """
        移动到夹取点正上方（安全高度）。

        grasp_point : [x, y, z]，机械臂坐标系 mm
        rz_deg      : 末端旋转角度 °（朝向已由感知层修正）
        """
        x, y, z = grasp_point[0], grasp_point[1], grasp_point[2]
        z_above = z + cfg.robot.z_approach_offset + self._z_comp

        pose = [x, y, z_above, -180.0, 0.0, rz_deg, 0]   # mode=0 笛卡尔
        log.info(f"[Arm] → approach  xyz=({x:.1f},{y:.1f},{z_above:.1f})  rz={rz_deg:.1f}°")
        t0 = time.time()
        self._safe_execute([pose], label="approach")
        self._wait_until_idle()
        log_motion_done("approach", (time.time() - t0) * 1000)

    def grasp(self, grasp_point: list[float], rz_deg: float,
              gripper_preset_id: int = 0) -> bool:
        """
        从当前位置（approach 点）下降到夹取点并闭合夹爪。

        返回 True 表示夹取成功（夹爪闭合检测）。
        """
        x, y, z = grasp_point[0], grasp_point[1], grasp_point[2]
        z_grasp = z + self._z_comp

        pose_down = [x, y, z_grasp, -180.0, 0.0, rz_deg, 0]

        log.info(f"[Arm] → descend to grasp  xyz=({x:.1f},{y:.1f},{z_grasp:.1f})")
        t0 = time.time()
        self._safe_execute([pose_down], label="grasp_descend")
        self._wait_until_idle()

        # 夹爪张开（先确认有足够空间）
        self._robot.open_gripper(gripper_preset_id)
        time.sleep(self._GRIPPER_SETTLE)

        # 闭合夹爪夹取
        log.info(f"[Arm] → close gripper  preset={gripper_preset_id}")
        success = self._robot.close_gripper(gripper_preset_id)
        time.sleep(self._GRIPPER_SETTLE)

        # 检查夹爪是否夹到物体
        gripped = self._robot.get_gripper_status()
        log_motion_done("grasp", (time.time() - t0) * 1000)
        log.info(f"[Arm] Grasp result: gripped={gripped}")
        return bool(gripped)

    def lift(self, grasp_point: list[float], rz_deg: float) -> None:
        """夹取后提升到安全高度（approach 高度），准备移动到递送点。"""
        x, y, z = grasp_point[0], grasp_point[1], grasp_point[2]
        z_above = z + cfg.robot.z_approach_offset + self._z_comp
        pose = [x, y, z_above, -180.0, 0.0, rz_deg, 0]
        log.info(f"[Arm] → lift to ({x:.1f},{y:.1f},{z_above:.1f})")
        t0 = time.time()
        self._safe_execute([pose], label="lift")
        self._wait_until_idle()
        log_motion_done("lift", (time.time() - t0) * 1000)

    def deliver(self) -> None:
        """
        移动到递送点（先经过 reset_pose 中转，再到 deliver_pose）。
        路径：当前位置 → reset_pose → deliver_pose
        """
        log.info("[Arm] → deliver (via reset_pose)")
        t0 = time.time()
        path = [cfg.robot.reset_pose, cfg.robot.deliver_pose]
        self._safe_execute(path, label="deliver")
        self._wait_until_idle()
        log_motion_done("deliver", (time.time() - t0) * 1000)

    def wait_for_handover(self,
                          timeout: float = _FORCE_WAIT_TIMEOUT,
                          gripper_preset_id: int = -1) -> bool:
        """
        在递送点等待医生取走器械（力反馈触发）。

        触发条件：末端受力超过 force_threshold。
        触发后自动松开夹爪。

        返回 True 表示医生已取走，False 表示超时。
        """
        log.info(f"[Arm] Waiting for handover  timeout={timeout:.0f}s ...")
        self._robot.startForceDetection()
        deadline = time.time() + timeout
        taken = False

        while time.time() < deadline:
            if self._robot.isStop:
                log.warning("[Arm] isStop detected during handover wait")
                break

            status = self._robot.getForceStatus()
            if status["is_applied"]:
                force_vals = status["current_force_torque"]
                delta = sum(v ** 2 for v in force_vals[:3]) ** 0.5
                log_force_event(True, delta, cfg.safety.force_threshold)

                # 松开夹爪
                self._robot.open_gripper(gripper_preset_id)
                taken = True
                log.info("[Arm] Instrument taken by doctor — gripper released")
                break

            time.sleep(self._POLL_INTERVAL)

        self._robot.stopForceDetection()

        if not taken:
            if self._is_mock:
                # mock 模式下没有真实医生，超时是预期行为，用 INFO 级别
                log.info(f"[Arm] 等待超时 ({timeout:.0f}s)，自动松夹（真机由医生力反馈触发）")
            else:
                log.warning(f"[Arm] Handover timeout ({timeout:.0f}s) — forcing gripper open")
            self._robot.open_gripper(gripper_preset_id)

        return taken

    # ──────────────────────────────────────
    # 完整递送序列（便捷方法）
    # ──────────────────────────────────────

    def pick_and_deliver(self,
                         grasp_point: list[float],
                         rz_deg: float,
                         gripper_preset_id: int = 0,
                         instrument_id: str = "") -> bool:
        """
        完整拾取递送流程：
          approach → grasp → lift → deliver → wait_for_handover → reset

        返回 True 表示完整流程成功（夹取成功 且 医生已取走）。
        """
        self._current_instrument_id = instrument_id
        log.info(f"[Arm] === pick_and_deliver START  id={instrument_id} ===")
        t0 = time.time()

        # 1. 移到夹取点上方
        self.approach(grasp_point, rz_deg)

        # 2. 下降夹取
        gripped = self.grasp(grasp_point, rz_deg, gripper_preset_id)
        if not gripped:
            log.warning("[Arm] Grasp failed — aborting, returning to reset")
            self.reset()
            return False

        # 3. 提升
        self.lift(grasp_point, rz_deg)

        # 4. 递送
        self.deliver()

        # 5. 等待交接
        taken = self.wait_for_handover(gripper_preset_id=gripper_preset_id)

        # 6. 回到待机
        time.sleep(0.5)
        self.reset()

        elapsed = (time.time() - t0) * 1000
        log.info(f"[Arm] === pick_and_deliver END  gripped={gripped} taken={taken}  {elapsed:.0f}ms ===")
        return gripped and taken

    # ──────────────────────────────────────
    # 急停
    # ──────────────────────────────────────

    def stop(self) -> None:
        """立即停止所有运动（可被 safety_manager.emergency_stop 调用）。"""
        log.warning("[Arm] STOP called")
        self._robot.stopCurrentMotion()

    # ──────────────────────────────────────
    # 内部辅助
    # ──────────────────────────────────────

    def _safe_execute(self, path: list[list[float]], label: str = "") -> None:
        """
        安全执行路径：先过 safety_manager 校验，通过后再调底层。
        SafetyError → 不执行，向上抛出。
        """
        try:
            safety.validate_path(path)
        except SafetyError as e:
            log.error(f"[Arm] Safety BLOCKED [{label}]: {e}")
            raise  # 上层（state_machine）负责处理

        log_motion_start(label, path[0] if path else None,
                         self._current_instrument_id)
        self._robot.executePath(path)

    def _wait_until_idle(self, timeout: float = 30.0) -> None:
        """轮询等待机械臂运动完成。"""
        deadline = time.time() + timeout
        while self._robot.isMoving():
            if self._robot.isStop:
                log.warning("[Arm] isStop during motion wait")
                return
            if time.time() > deadline:
                log.error(f"[Arm] Motion timeout ({timeout:.0f}s) — forcing stop")
                self._robot.stopCurrentMotion()
                return
            time.sleep(self._POLL_INTERVAL)

    # ──────────────────────────────────────
    # 生命周期
    # ──────────────────────────────────────

    def shutdown(self) -> None:
        """安全关闭：先回待机姿态，再断连接。"""
        log.info("[Arm] Shutting down ...")
        try:
            if not self._robot.isMoving():
                self.reset()
        except Exception as e:
            log.warning(f"[Arm] Reset before shutdown failed: {e}")
        try:
            self._robot.shutdown()
        except Exception as e:
            log.warning(f"[Arm] shutdown() error: {e}")
        log.info("[Arm] Shutdown complete")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.shutdown()

    # ──────────────────────────────────────
    # 状态查询
    # ──────────────────────────────────────

    @property
    def is_moving(self) -> bool:
        return self._robot.isMoving()

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    def get_joints(self) -> list[float]:
        """返回当前六轴关节角度（度）。"""
        if hasattr(self._robot, 'getCurrentJoints'):
            return self._robot.getCurrentJoints()
        return [0.0] * 6
