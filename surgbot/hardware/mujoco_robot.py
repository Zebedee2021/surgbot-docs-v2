"""
hardware/mujoco_robot.py
════════════════════════
MuJoCo 物理仿真后端

用 Panda/UR5 近似几何（mocap body 直接控制末端位置，无需 IK）
走通完整仿真流程，与 _MockRobot / RobotControlModule 接口完全兼容。

使用方式::

    from hardware.dobot_arm import DobotArm

    arm = DobotArm(sim=True)          # 自动使用 MuJoCo 后端
    arm.approach([120.0, -80.0, 181.0], 45.0)
    gripped = arm.grasp(...)
    img = arm.render_camera("overhead")   # RGB 图像 np.ndarray

设计要点
─────────
1. 末端控制：mocap body（data.mocap_pos）→ 直接设笛卡尔坐标，无需 IK
2. 坐标换算：SurgBot 用 mm，MuJoCo 用 m，全部在本模块内换算
3. 器械静态：MVP 阶段器械为 static geom，用等式约束模拟夹取
4. 接触检测：通过 mujoco.mj_contactForce 读取夹爪-托盘/器械接触力
5. 相机渲染：mujoco.Renderer 支持 headless（EGL / OSMesa）
6. 兼容性   ：mujoco >= 3.1，Python 3.10–3.12

依赖::

    pip install mujoco>=3.1

Linux 无 GPU headless 渲染（GitHub Actions）::

    export MUJOCO_GL=osmesa
    pip install pyopengl==3.1.7
"""

from __future__ import annotations

import time
from typing import Optional
import numpy as np

from core.config import cfg
from core.logger import get_logger

log = get_logger("mujoco_robot")

# ──────────────────────────────────────────────
# 场景 MJCF（嵌入式，不依赖外部文件）
# 坐标对应 instrument_registry.json 中的 grasp_point（mm→m）
# ──────────────────────────────────────────────

SCENE_XML = """
<mujoco model="surgbot_sim">
  <compiler angle="radian"/>
  <option timestep="0.004" gravity="0 0 -9.81" integrator="RK4"/>

  <default>
    <geom contype="1" conaffinity="1" friction="0.8 0.3 0.3" condim="3"/>
  </default>

  <worldbody>
    <light pos="0.5 0.1 1.5" diffuse=".9 .9 .9" specular=".2 .2 .2"/>
    <light pos="-0.3 0.3 1.0" diffuse=".4 .4 .4"/>
    <geom name="floor" type="plane" size="1.5 1.5 0.01"
          rgba=".95 .95 .92 1" contype="1" conaffinity="1"/>

    <!-- ── 末端执行器（mocap 直接控制，无需 IK）── -->
    <body name="ee_mocap" mocap="true" pos="0.00 -0.08 0.50">
      <geom name="gripper_body" type="box" size="0.018 0.018 0.012"
            pos="0 0 0.012" rgba=".22 .22 .22 1" contype="0" conaffinity="0"/>
      <geom name="finger_l"     type="box" size="0.006 0.005 0.022"
            pos="-0.013 0 0.036" rgba=".45 .45 .45 1" contype="2" conaffinity="2"/>
      <geom name="finger_r"     type="box" size="0.006 0.005 0.022"
            pos=" 0.013 0 0.036" rgba=".45 .45 .45 1" contype="2" conaffinity="2"/>
      <site name="ee_site" pos="0 0 0.058" size="0.006" rgba="1 .1 .1 1"/>
    </body>

    <!-- ── 器械托盘（坐标匹配 SurgBot 注册表，单位 m）── -->
    <body name="tray_body" pos="0 0 0">
      <geom name="tray_surface" type="box" size="0.225 0.058 0.004"
            pos="0.280 -0.080 0.181" rgba=".72 .72 .72 1"/>
      <!-- 槽位隔板 -->
      <geom type="box" size="0.001 0.056 0.010" pos="0.160 -0.080 0.190" rgba=".55 .55 .55 1"/>
      <geom type="box" size="0.001 0.056 0.010" pos="0.240 -0.080 0.190" rgba=".55 .55 .55 1"/>
      <geom type="box" size="0.001 0.056 0.010" pos="0.320 -0.080 0.190" rgba=".55 .55 .55 1"/>
      <geom type="box" size="0.001 0.056 0.010" pos="0.400 -0.080 0.190" rgba=".55 .55 .55 1"/>

      <!-- slot_01 持针器_大（红）  grasp=(120,-80,181) mm -->
      <geom name="ins_01" type="cylinder" size="0.008 0.026"
            pos="0.120 -0.080 0.211" rgba=".85 .15 .15 1"/>
      <!-- slot_02 剪刀（蓝）      grasp=(200,-80,181) mm -->
      <geom name="ins_02" type="cylinder" size="0.007 0.026"
            pos="0.200 -0.080 0.211" rgba=".15 .35 .85 1"/>
      <!-- slot_03 镊子（绿）      grasp=(280,-80,181) mm -->
      <geom name="ins_03" type="cylinder" size="0.006 0.026"
            pos="0.280 -0.080 0.211" rgba=".10 .75 .20 1"/>
      <!-- slot_04 刀柄（橙）      grasp=(360,-80,181) mm -->
      <geom name="ins_04" type="cylinder" size="0.007 0.026"
            pos="0.360 -0.080 0.211" rgba=".90 .50 .10 1"/>
      <!-- slot_05 持针器_小（紫）  grasp=(440,-80,181) mm -->
      <geom name="ins_05" type="cylinder" size="0.007 0.023"
            pos="0.440 -0.080 0.211" rgba=".60 .10 .80 1"/>
    </body>

    <!-- ── 递送区 ── -->
    <body name="deliver_zone" pos="-0.050 -0.250 0.350">
      <geom type="sphere" size="0.022" rgba=".10 .82 .82 .45"
            contype="0" conaffinity="0"/>
    </body>

    <!-- ── 相机 ── -->
    <!-- 俯视（对准托盘中心，Z=0.72m） -->
    <camera name="overhead" pos="0.280 -0.080 0.720" xyaxes="1 0 0 0 1 0"/>
    <!-- 侧观 -->
    <camera name="side_obs" pos="0.700 0.200 0.450"
            xyaxes="-0.857 0.515 0  -0.206 -0.343 0.916"/>
  </worldbody>

  <!-- 传感器 -->
  <sensor>
    <framepos  name="ee_pos"   objtype="site" objname="ee_site"/>
    <framelinvel name="ee_vel" objtype="site" objname="ee_site"/>
  </sensor>
</mujoco>
"""

# ──────────────────────────────────────────────
# 坐标换算
# ──────────────────────────────────────────────

MM2M = 1e-3    # mm → m
M2MM = 1e3     # m → mm


def _mm_to_m(pt: list[float]) -> np.ndarray:
    """SurgBot Cartesian 坐标 (mm, 最多7元素) → MuJoCo 3D 位置 (m)。"""
    return np.array([pt[0] * MM2M, pt[1] * MM2M, pt[2] * MM2M])


# ──────────────────────────────────────────────
# MuJoCo 后端
# ──────────────────────────────────────────────

class MuJoCoRobot:
    """
    MuJoCo 物理仿真后端，接口与 _MockRobot 兼容。

    额外能力（超出 _MockRobot）
    ──────────────────────────
    - render(camera_name)  → RGB np.ndarray (H, W, 3)
    - get_ee_pos()         → 当前 EE 世界坐标 (m)
    - get_contact_force()  → 夹爪最大接触力 (N)
    - sim_steps            → 已累计仿真步数
    """

    # 接触力超过此值认为夹取成功
    GRASP_FORCE_THRESHOLD_N: float = 0.05
    # 单步 mocap 移动量上限（m）
    MAX_STEP_M: float = 0.005
    # 力反馈检测间隔（s）
    POLL_INTERVAL: float = 0.004
    # 急停计数
    stop_count: int = 0

    def __init__(self) -> None:
        try:
            import mujoco
            self._mj = mujoco
        except ImportError as e:
            raise ImportError(
                "MuJoCo 未安装。请运行: pip install mujoco>=3.1\n"
                "注意：Python 3.14 尚不支持，建议使用 Python 3.12。"
            ) from e

        log.info("[Sim] 加载 MuJoCo 场景...")
        self._model = self._mj.MjModel.from_xml_string(SCENE_XML)
        self._data  = self._mj.MjData(self._model)

        # 暖机：让物理稳定
        for _ in range(100):
            self._mj.mj_step(self._model, self._data)

        self._renderer: Optional[object] = None
        self._force_detect = False
        self._is_moving    = False
        self.isStop        = False
        self.sim_steps     = 100

        log.info(
            f"[Sim] MuJoCo {self._mj.__version__} 就绪 | "
            f"bodies={self._model.nbody}  geoms={self._model.ngeom}  "
            f"sensors={self._model.nsensor}"
        )

    # ── 兼容接口（与 _MockRobot 完全一致）────────────────────

    def executePath(self, path: list[list[float]]) -> dict:
        """沿路径列表移动 mocap EE，每步进行物理仿真。"""
        self._is_moving = True
        total_steps = 0

        for waypoint in path:
            # 跳过关节角模式（mode=1）——直接置 mocap 在当前位置
            if len(waypoint) >= 7 and int(waypoint[6]) == 1:
                log.debug("[Sim] 关节角模式路径点，跳过笛卡尔移动")
                continue

            target_m = _mm_to_m(waypoint)
            steps = self._move_ee_to(target_m)
            total_steps += steps

        self._is_moving = False
        log.info(f"[Sim] executePath {len(path)} 点  仿真步数={total_steps}")
        return {"status": "done", "sim_steps": total_steps}

    def isMoving(self) -> bool:
        return self._is_moving

    def stopCurrentMotion(self) -> None:
        MuJoCoRobot.stop_count += 1
        self._is_moving = False
        log.info("[Sim] stopCurrentMotion")

    def setSpeed(self, speed: int) -> None:
        # 速度映射：speed% → MAX_STEP_M 比例
        self.MAX_STEP_M = 0.001 + (speed / 100.0) * 0.009
        log.info(f"[Sim] setSpeed {speed}% → max_step={self.MAX_STEP_M*1000:.1f}mm/step")

    def setForceThreshold(self, threshold: float) -> None:
        self.GRASP_FORCE_THRESHOLD_N = max(0.01, threshold)
        log.info(f"[Sim] setForceThreshold {threshold:.3f}N")

    def open_gripper(self, preset_id: int) -> None:
        log.info(f"[Sim] open_gripper preset={preset_id}")
        # 张开：finger_l 向左偏，finger_r 向右偏（修改 geom body 偏移模拟）
        # MVP 阶段仅日志记录，不修改 geom 位置

    def close_gripper(self, preset_id: int) -> bool:
        """闭合夹爪并判断是否夹取成功（基于接触力）。"""
        log.info(f"[Sim] close_gripper preset={preset_id}")
        # 多步仿真让接触稳定
        for _ in range(50):
            self._mj.mj_step(self._model, self._data)
        self.sim_steps += 50

        force = self.get_contact_force()
        success = force > self.GRASP_FORCE_THRESHOLD_N
        log.info(f"[Sim] 接触力={force:.4f}N  夹取={'✅成功' if success else '❌失败'}")
        return success

    def get_gripper_status(self) -> bool:
        """夹爪是否有物体（EE 与最近器械距离 < 15mm）。"""
        ee_pos = self.get_ee_pos()
        for slot_x in [0.120, 0.200, 0.280, 0.360, 0.440]:
            dist = np.linalg.norm(ee_pos - np.array([slot_x, -0.080, 0.211]))
            if dist < 0.015:
                return True
        return False

    def startForceDetection(self) -> None:
        self._force_detect = True
        log.info("[Sim] startForceDetection")

    def stopForceDetection(self) -> None:
        self._force_detect = False
        log.info("[Sim] stopForceDetection")

    def getForceStatus(self) -> dict:
        """返回末端接触力状态（模拟医生取走动作）。"""
        # 仿真中力反馈始终为 0（无医生），依赖超时机制
        return {
            "is_applied": False,
            "current_force_torque": [0.0] * 6,
        }

    def shutdown(self) -> None:
        if self._renderer is not None:
            try:
                self._renderer.close()
            except Exception:
                pass
            self._renderer = None
        log.info("[Sim] MuJoCo 仿真已关闭")

    # ── 扩展能力（MuJoCo 专有）──────────────────────────────

    def get_ee_pos(self) -> np.ndarray:
        """返回当前 EE 世界坐标（m）。"""
        site_id = self._model.site("ee_site").id
        return self._data.site_xpos[site_id].copy()

    def get_contact_force(self) -> float:
        """计算所有活跃接触的最大合力（N）。"""
        max_force = 0.0
        contact_force = np.zeros(6)
        for i in range(self._data.ncon):
            self._mj.mj_contactForce(self._model, self._data, i, contact_force)
            f = np.linalg.norm(contact_force[:3])
            if f > max_force:
                max_force = f
        return float(max_force)

    def render(
        self,
        camera_name: str = "overhead",
        width: int = 640,
        height: int = 480,
    ) -> np.ndarray:
        """
        渲染指定相机的 RGB 图像。

        返回 np.ndarray (height, width, 3)，uint8。
        需要 MuJoCo 渲染支持（MUJOCO_GL=egl 或 osmesa）。
        """
        if self._renderer is None or \
           self._renderer.width != width or self._renderer.height != height:
            if self._renderer is not None:
                self._renderer.close()
            self._renderer = self._mj.Renderer(self._model, height=height, width=width)

        self._renderer.update_scene(self._data, camera=camera_name)
        return self._renderer.render().copy()

    def trajectory_record(
        self,
        waypoints_mm: list[list[float]],
        steps_per_segment: int = 30,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        仿真一段轨迹并记录 EE 位置 & 接触力。

        返回:
            positions  np.ndarray (N, 3) 单位 m
            forces     np.ndarray (N,)   单位 N
        """
        positions: list[np.ndarray] = []
        forces:    list[float]      = []

        for wp in waypoints_mm:
            if len(wp) >= 7 and int(wp[6]) == 1:
                continue
            target_m = _mm_to_m(wp)

            # 在当前位置和目标之间插值
            start = self._data.mocap_pos[0].copy()
            for k in range(steps_per_segment):
                t = (k + 1) / steps_per_segment
                self._data.mocap_pos[0] = start + t * (target_m - start)
                self._mj.mj_step(self._model, self._data)
                self.sim_steps += 1
                positions.append(self.get_ee_pos().copy())
                forces.append(self.get_contact_force())

        return np.array(positions), np.array(forces)

    # ── 内部辅助 ─────────────────────────────────────────────

    def _move_ee_to(self, target_m: np.ndarray, max_iter: int = 300) -> int:
        """
        把 mocap EE 移动到目标位置（分小步移动，保持物理稳定）。
        返回累计仿真步数。
        """
        steps = 0
        for _ in range(max_iter):
            current = self._data.mocap_pos[0].copy()
            delta = target_m - current
            dist  = np.linalg.norm(delta)
            if dist < 1e-4:
                break
            step = min(dist, self.MAX_STEP_M)
            self._data.mocap_pos[0] = current + (delta / dist) * step
            self._mj.mj_step(self._model, self._data)
            self.sim_steps += 1
            steps += 1
        return steps
