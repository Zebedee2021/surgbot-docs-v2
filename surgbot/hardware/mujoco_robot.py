"""
hardware/mujoco_robot.py
════════════════════════
MuJoCo 物理仿真后端 — UR5 近似几何机械臂

核心设计
─────────
1. 6-DOF 几何体机械臂（capsule + box，UR5 比例，无需外部 mesh 文件）
2. mocap body + weld 等式约束 → 自动 IK（MuJoCo 约束求解器负责）
3. gravity = "0 0 0"（机器人自身重力补偿，防止关节下垂）
4. 位置执行器随关节角实时更新 setpoint（执行器辅助阻尼，不抗约束）
5. 坐标换算：SurgBot mm ↔ MuJoCo m，全在本模块内

接口与 _MockRobot 完全兼容，可直接注入 DobotArm(sim=True)。

依赖::
    pip install mujoco>=3.1   (Python 3.10–3.12)

headless 渲染（Linux / GitHub Actions）::
    export MUJOCO_GL=egl      # GPU
    export MUJOCO_GL=osmesa   # CPU（需 pip install pyopengl==3.1.7）
"""

from __future__ import annotations

from typing import Optional
import numpy as np

try:
    from core.logger import get_logger
    log = get_logger("mujoco_robot")
except Exception:
    import logging
    log = logging.getLogger("mujoco_robot")

# ─────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────

MM2M = 1e-3
GRASP_FORCE_THRESHOLD_N = 0.05   # N，夹取成功判定阈值
MAX_STEP_M   = 0.005             # m，mocap 每帧最大移动量
CTRL_STEPS   = 400               # 每段运动最大仿真步数
WARMUP_STEPS = 1000              # 初始化热身步数（让臂收敛到 home 姿态）

# ─────────────────────────────────────────────────────
# SCENE_XML
# 坐标系：X 向前（托盘方向），Y 向左，Z 向上
# 机械臂底座位于原点；托盘在 X≈0.28m, Y≈-0.08m
# ─────────────────────────────────────────────────────

SCENE_XML = """
<mujoco model="surgbot_ur5_approx">

  <!--
    gravity=0: 机器人有自身重力补偿，防止各关节在无执行器输出时下垂。
    iterations=150: 提高等式约束收敛精度（对 weld-IK 尤为重要）。
  -->
  <option gravity="0 0 0" timestep="0.002" iterations="150"
          solver="Newton" tolerance="1e-10"/>

  <default>
    <!-- 关节大阻尼：抑制 weld-IK 驱动时的振荡 -->
    <joint damping="12.0" stiffness="0" limited="true" armature="0.01"/>
    <!-- 几何体默认不参与碰撞（臂链接之间不需要碰撞） -->
    <geom contype="0" conaffinity="0"/>
  </default>

  <worldbody>

    <!-- ── 光照 ── -->
    <light name="key"  pos="0.3 -0.4 1.4" dir="-0.1 0.2 -0.9"
           diffuse="0.85 0.85 0.85" specular="0.3 0.3 0.3"/>
    <light name="fill" pos="-0.4 0.5 0.9" dir="0.2 -0.2 -0.6"
           diffuse="0.35 0.38 0.42"/>

    <!-- ── 地面 ── -->
    <geom name="floor" type="plane" size="2 2 0.01"
          rgba="0.20 0.20 0.22 1" contype="1" conaffinity="1"/>

    <!-- ═══════════════════════════════════════════════════
         UR5 近似机械臂（6-DOF，纯几何体，无外部 mesh）
         关节顺序：
           J1 腰转(Z)  →  J2 肩(Y)  →  J3 肘(Y)
           J4 腕1(X)   →  J5 腕2(Y) →  J6 腕3(X)
         ─────────────────────────────────────────────────
         连杆长度（参考 UR5e 官方参数，单位 m）：
           肩偏置  0.131  (link1 pos Y)
           大臂    0.425  (link2→link3)
           前臂    0.392  (link3→link4)
           腕1偏  -0.093  (link4→link5, Y)
           腕2     0.095  (link5→ee_link, X)
         ═══════════════════════════════════════════════════ -->

    <!-- 底座 -->
    <geom name="base_cyl" type="cylinder" size="0.092 0.065"
          pos="0 0 0.065" rgba="0.24 0.24 0.26 1"/>
    <geom name="base_top" type="cylinder" size="0.076 0.012"
          pos="0 0 0.138" rgba="0.28 0.28 0.30 1"/>

    <!-- ─── Link1 / Joint1：腰部绕 Z 轴旋转 ─── -->
    <body name="link1" pos="0 0 0.150">
      <joint name="joint1" axis="0 0 1" range="-3.14159 3.14159"/>
      <geom name="j1_hub" type="cylinder" size="0.058 0.028"
            rgba="0.28 0.30 0.34 1"/>
      <!-- 肩部连接段（沿 Y 轴延伸到 link2 偏置点） -->
      <geom name="l1_shoulder" type="capsule"
            fromto="0 0 0  0 0.131 0" size="0.042"
            rgba="0.22 0.48 0.78 1"/>

      <!-- ─── Link2 / Joint2：肩部绕 Y 轴俯仰 ─── -->
      <body name="link2" pos="0 0.131 0">
        <joint name="joint2" axis="0 1 0" range="-3.14159 1.05"/>
        <geom name="j2_hub" type="sphere" size="0.050"
              rgba="0.28 0.30 0.34 1"/>
        <!-- 大臂（沿 X 延伸 0.425m） -->
        <geom name="l2_upper" type="capsule"
              fromto="0 0 0  0.425 0 0" size="0.037"
              rgba="0.22 0.48 0.78 1"/>

        <!-- ─── Link3 / Joint3：肘部绕 Y 轴弯曲 ─── -->
        <body name="link3" pos="0.425 0 0">
          <joint name="joint3" axis="0 1 0" range="-3.14159 3.14159"/>
          <geom name="j3_hub" type="sphere" size="0.042"
                rgba="0.28 0.30 0.34 1"/>
          <!-- 前臂（沿 X 延伸 0.392m） -->
          <geom name="l3_fore" type="capsule"
                fromto="0 0 0  0.392 0 0" size="0.031"
                rgba="0.30 0.55 0.85 1"/>

          <!-- ─── Link4 / Joint4：腕1 绕 X 轴旋转 ─── -->
          <body name="link4" pos="0.392 0 0">
            <joint name="joint4" axis="1 0 0" range="-3.14159 3.14159"/>
            <geom name="j4_hub" type="cylinder" size="0.032 0.027"
                  rgba="0.28 0.30 0.34 1"/>
            <!-- 腕部1（沿 -Y 偏置 0.093m） -->
            <geom name="l4_wrist1" type="capsule"
                  fromto="0 0 0  0 -0.093 0" size="0.028"
                  rgba="0.35 0.60 0.90 1"/>

            <!-- ─── Link5 / Joint5：腕2 绕 Y 轴旋转 ─── -->
            <body name="link5" pos="0 -0.093 0">
              <joint name="joint5" axis="0 1 0" range="-3.14159 3.14159"/>
              <geom name="j5_hub" type="sphere" size="0.030"
                    rgba="0.28 0.30 0.34 1"/>
              <!-- 腕部2（沿 X 延伸 0.095m） -->
              <geom name="l5_wrist2" type="capsule"
                    fromto="0 0 0  0.095 0 0" size="0.024"
                    rgba="0.38 0.63 0.93 1"/>

              <!-- ─── EE Link / Joint6：腕3 绕 X 轴旋转 ─── -->
              <body name="ee_link" pos="0.095 0 0">
                <joint name="joint6" axis="1 0 0" range="-3.14159 3.14159"/>
                <!-- 末端法兰（橙色球） -->
                <geom name="ee_flange" type="sphere" size="0.028"
                      rgba="1.0 0.55 0.08 1"/>
                <!-- 夹爪底座 -->
                <geom name="grip_base" type="box"
                      pos="0.038 0 0" size="0.014 0.026 0.010"
                      rgba="0.80 0.36 0.10 1"/>
                <!-- 左爪指 -->
                <geom name="grip_l" type="capsule"
                      fromto="0.028  0.020 0  0.088  0.024 0" size="0.009"
                      rgba="0.88 0.40 0.12 1"/>
                <!-- 右爪指 -->
                <geom name="grip_r" type="capsule"
                      fromto="0.028 -0.020 0  0.088 -0.024 0" size="0.009"
                      rgba="0.88 0.40 0.12 1"/>
                <!-- EE 传感器位置（爪指末端中心） -->
                <site name="ee_site" pos="0.090 0 0" size="0.006"
                      rgba="1.0 0.2 0.2 0.8"/>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>

    <!-- ═══════════════════════════════════════════════════
         mocap 目标体（半透明红球）
         data.mocap_pos[0] 直接设置目标坐标 → weld 约束驱动 IK
         ═══════════════════════════════════════════════════ -->
    <body name="ee_mocap" mocap="true" pos="0.280 -0.080 0.360">
      <geom name="target_vis" type="sphere" size="0.018"
            rgba="1.0 0.15 0.15 0.30" contype="0" conaffinity="0"/>
    </body>

    <!-- ═══════════════════════════════════════════════════
         手术器械托盘
         托盘中心：(0.280, -0.080, 0.178) m
         ═══════════════════════════════════════════════════ -->
    <!-- 托盘面 -->
    <geom name="tray_top" type="box"
          pos="0.280 -0.080 0.178" size="0.240 0.068 0.009"
          rgba="0.72 0.68 0.58 1" contype="1" conaffinity="1"/>
    <!-- 四周挡边 -->
    <geom name="tray_rim_f" type="box"
          pos="0.280 -0.148 0.192" size="0.240 0.009 0.016"
          rgba="0.62 0.58 0.48 1"/>
    <geom name="tray_rim_b" type="box"
          pos="0.280 -0.012 0.192" size="0.240 0.009 0.016"
          rgba="0.62 0.58 0.48 1"/>
    <geom name="tray_rim_l" type="box"
          pos="0.040 -0.080 0.192" size="0.009 0.077 0.016"
          rgba="0.62 0.58 0.48 1"/>
    <geom name="tray_rim_r" type="box"
          pos="0.520 -0.080 0.192" size="0.009 0.077 0.016"
          rgba="0.62 0.58 0.48 1"/>
    <!-- 托盘支腿 -->
    <geom name="leg_fl" type="box" pos="0.060 -0.130 0.085" size="0.011 0.011 0.085" rgba="0.55 0.52 0.45 1"/>
    <geom name="leg_fr" type="box" pos="0.060 -0.030 0.085" size="0.011 0.011 0.085" rgba="0.55 0.52 0.45 1"/>
    <geom name="leg_bl" type="box" pos="0.500 -0.130 0.085" size="0.011 0.011 0.085" rgba="0.55 0.52 0.45 1"/>
    <geom name="leg_br" type="box" pos="0.500 -0.030 0.085" size="0.011 0.011 0.085" rgba="0.55 0.52 0.45 1"/>

    <!-- ── 5 个器械（彩色圆柱）坐标对应 instrument_registry.json ── -->
    <!-- slot_01 持针器_大（银灰）  grasp=[120,-80,181] mm -->
    <geom name="ins_01" type="cylinder" size="0.009 0.028"
          pos="0.120 -0.080 0.218" rgba="0.78 0.78 0.82 1"
          contype="1" conaffinity="1"/>
    <!-- slot_02 剪刀（金黄）       grasp=[200,-80,181] mm -->
    <geom name="ins_02" type="cylinder" size="0.009 0.028"
          pos="0.200 -0.080 0.218" rgba="0.88 0.74 0.18 1"
          contype="1" conaffinity="1"/>
    <!-- slot_03 镊子（翠绿）       grasp=[280,-80,181] mm -->
    <geom name="ins_03" type="cylinder" size="0.009 0.028"
          pos="0.280 -0.080 0.218" rgba="0.18 0.74 0.45 1"
          contype="1" conaffinity="1"/>
    <!-- slot_04 刀柄（橙棕）       grasp=[360,-80,181] mm -->
    <geom name="ins_04" type="cylinder" size="0.009 0.028"
          pos="0.360 -0.080 0.218" rgba="0.80 0.44 0.18 1"
          contype="1" conaffinity="1"/>
    <!-- slot_05 持针器_小（紫）    grasp=[440,-80,181] mm -->
    <geom name="ins_05" type="cylinder" size="0.009 0.028"
          pos="0.440 -0.080 0.218" rgba="0.55 0.28 0.80 1"
          contype="1" conaffinity="1"/>

    <!-- 递送区标记 -->
    <geom name="deliver_zone" type="sphere" size="0.025"
          pos="-0.050 -0.250 0.350" rgba="0.10 0.82 0.82 0.35"
          contype="0" conaffinity="0"/>

    <!-- ── 相机 ── -->
    <!-- 俯视：模拟顶置工业相机，对准托盘中心 -->
    <camera name="overhead"
            pos="0.280 -0.080 0.720"
            xyaxes="1 0 0 0 1 0"/>
    <!-- 侧视：斜45°观察整体 -->
    <camera name="side_obs"
            pos="0.800 -0.500 0.600"
            xyaxes="-0.74 0.67 0  0.24 0.27 0.93"/>
    <!-- 正面全景：方便观察机械臂姿态 -->
    <camera name="front_view"
            pos="-0.100 -0.800 0.550"
            xyaxes="1 0 0  0.22 0 0.97"/>

  </worldbody>

  <!-- ═══════════════════════════════════════════════════
       weld 等式约束：ee_link 绑定到 ee_mocap
       移动 data.mocap_pos → 约束求解器自动计算 IK 关节角
       solimp/solref 调大刚度，减少跟踪误差
       ═══════════════════════════════════════════════════ -->
  <equality>
    <weld name="ee_weld"
          body1="ee_link"
          body2="ee_mocap"
          relpose="0 0 0 1 0 0 0"
          solimp="0.95 0.99 0.0005 0.5 2"
          solref="0.01 1"/>
  </equality>

  <!-- ═══════════════════════════════════════════════════
       位置执行器（kp 刚度驱动）
       注：_move_ee_to() 每步将 ctrl[i] 更新为 qpos[i]，
       使执行器跟随当前关节角而非与约束力对抗。
       ═══════════════════════════════════════════════════ -->
  <actuator>
    <position name="act_j1" joint="joint1" kp="500"
              ctrlrange="-3.14 3.14" forcelimited="true" forcerange="-300 300"/>
    <position name="act_j2" joint="joint2" kp="500"
              ctrlrange="-3.14 1.05" forcelimited="true" forcerange="-300 300"/>
    <position name="act_j3" joint="joint3" kp="400"
              ctrlrange="-3.14 3.14" forcelimited="true" forcerange="-200 200"/>
    <position name="act_j4" joint="joint4" kp="300"
              ctrlrange="-3.14 3.14" forcelimited="true" forcerange="-150 150"/>
    <position name="act_j5" joint="joint5" kp="300"
              ctrlrange="-3.14 3.14" forcelimited="true" forcerange="-150 150"/>
    <position name="act_j6" joint="joint6" kp="200"
              ctrlrange="-3.14 3.14" forcelimited="true" forcerange="-100 100"/>
  </actuator>

  <sensor>
    <framepos    name="ee_pos" objtype="site" objname="ee_site"/>
    <framelinvel name="ee_vel" objtype="site" objname="ee_site"/>
  </sensor>

</mujoco>
"""

# ─────────────────────────────────────────────────────
# 坐标工具
# ─────────────────────────────────────────────────────

def _mm_to_m(pt: list[float]) -> np.ndarray:
    """SurgBot 坐标 (mm, 最多7元素) → MuJoCo 3D 位置 (m)。"""
    return np.array([pt[0] * MM2M, pt[1] * MM2M, pt[2] * MM2M])


# ─────────────────────────────────────────────────────
# 初始关节角（家位：臂伸向托盘中心上方）
# 通过正运动学验证：约在 (0.28, -0.08, 0.36) 附近
# ─────────────────────────────────────────────────────
_HOME_QPOS = np.array([
    -0.28,   # J1：腰部偏向 -Y 方向（atan2(-0.08, 0.28) ≈ -0.28 rad）
    -0.45,   # J2：肩部向下倾
     0.90,   # J3：肘部弯曲
     0.00,   # J4：腕1 中立
    -0.45,   # J5：腕2 向下
     0.00,   # J6：腕3 中立
], dtype=float)


# ─────────────────────────────────────────────────────
# MuJoCo 后端
# ─────────────────────────────────────────────────────

class MuJoCoRobot:
    """
    MuJoCo 物理仿真后端，接口与 _MockRobot / RobotControlModule 完全兼容。

    额外能力
    ─────────
    render(camera)          → RGB np.ndarray (H, W, 3)
    get_ee_pos()            → EE 世界坐标 (m)
    get_contact_force()     → 夹爪最大接触力 (N)
    trajectory_record(...)  → (positions_m, forces_N)
    sim_steps               → 累计仿真步数
    """

    GRASP_FORCE_THRESHOLD_N: float = GRASP_FORCE_THRESHOLD_N
    MAX_STEP_M:   float = MAX_STEP_M
    stop_count:   int   = 0

    def __init__(self) -> None:
        try:
            import mujoco
            self._mj = mujoco
        except ImportError as e:
            raise ImportError(
                "MuJoCo 未安装。运行: pip install mujoco>=3.1\n"
                "（Python 3.10–3.12 支持；3.13+ 尚不支持）"
            ) from e

        log.info("[Sim] 加载 MuJoCo 场景（UR5 近似几何臂）...")
        self._model = self._mj.MjModel.from_xml_string(SCENE_XML)
        self._data  = self._mj.MjData(self._model)

        # 设置家位关节角
        n_joints = min(len(_HOME_QPOS), self._model.nq)
        self._data.qpos[:n_joints] = _HOME_QPOS[:n_joints]
        self._data.ctrl[:n_joints] = _HOME_QPOS[:n_joints]
        self._mj.mj_forward(self._model, self._data)

        # 热身：让臂在约束驱动下收敛到家位
        for i in range(WARMUP_STEPS):
            self._sync_ctrl()          # 执行器跟随关节角（不对抗约束）
            self._mj.mj_step(self._model, self._data)

        self._renderer: Optional[object] = None
        self._force_detect = False
        self._is_moving    = False
        self.isStop        = False
        self.sim_steps     = WARMUP_STEPS

        ee = self.get_ee_pos()
        log.info(
            f"[Sim] MuJoCo {self._mj.__version__} 就绪 | "
            f"bodies={self._model.nbody}  geoms={self._model.ngeom} | "
            f"EE home=({ee[0]*1e3:.1f},{ee[1]*1e3:.1f},{ee[2]*1e3:.1f}) mm"
        )

    # ── _MockRobot 兼容接口 ───────────────────────────────────

    def executePath(self, path: list[list[float]]) -> dict:
        """沿路径点列表移动 EE，每步物理仿真。"""
        self._is_moving = True
        total_steps = 0
        for wp in path:
            if len(wp) >= 7 and int(wp[6]) == 1:
                log.debug("[Sim] 关节角模式路径点，跳过")
                continue
            steps = self._move_ee_to(_mm_to_m(wp))
            total_steps += steps
        self._is_moving = False
        log.info(f"[Sim] executePath {len(path)} 点  sim_steps={total_steps}")
        return {"status": "done", "sim_steps": total_steps}

    def isMoving(self) -> bool:
        return self._is_moving

    def stopCurrentMotion(self) -> None:
        MuJoCoRobot.stop_count += 1
        self._is_moving = False
        log.info("[Sim] stopCurrentMotion")

    def setSpeed(self, speed: int) -> None:
        self.MAX_STEP_M = 0.001 + (speed / 100.0) * 0.009
        log.info(f"[Sim] setSpeed {speed}% → max_step={self.MAX_STEP_M*1e3:.1f} mm/step")

    def setForceThreshold(self, threshold: float) -> None:
        self.GRASP_FORCE_THRESHOLD_N = max(0.01, threshold)

    def open_gripper(self, preset_id: int) -> None:
        log.info(f"[Sim] open_gripper preset={preset_id}")

    def close_gripper(self, preset_id: int) -> bool:
        """闭合夹爪，运行若干步后判断是否夹取成功（接触力 > 阈值）。"""
        log.info(f"[Sim] close_gripper preset={preset_id}")
        for _ in range(60):
            self._sync_ctrl()
            self._mj.mj_step(self._model, self._data)
        self.sim_steps += 60
        force   = self.get_contact_force()
        success = force > self.GRASP_FORCE_THRESHOLD_N
        log.info(f"[Sim] 接触力={force:.4f}N  {'✅ 夹取成功' if success else '❌ 力不足'}")
        return success

    def get_gripper_status(self) -> bool:
        """EE 是否接近某个器械槽位（距离 < 18 mm）。"""
        ee = self.get_ee_pos()
        for x in [0.120, 0.200, 0.280, 0.360, 0.440]:
            if np.linalg.norm(ee - np.array([x, -0.080, 0.218])) < 0.018:
                return True
        return False

    def startForceDetection(self) -> None:
        self._force_detect = True

    def stopForceDetection(self) -> None:
        self._force_detect = False

    def getForceStatus(self) -> dict:
        return {"is_applied": False, "current_force_torque": [0.0] * 6}

    def shutdown(self) -> None:
        if self._renderer is not None:
            try:
                self._renderer.close()
            except Exception:
                pass
            self._renderer = None
        log.info("[Sim] 已关闭")

    # close() 是 shutdown() 的别名（Notebook 中常用）
    def close(self) -> None:
        self.shutdown()

    # ── MuJoCo 专有能力 ──────────────────────────────────────

    def get_ee_pos(self) -> np.ndarray:
        """EE site 当前世界坐标（m）。"""
        sid = self._model.site("ee_site").id
        return self._data.site_xpos[sid].copy()

    def get_contact_force(self) -> float:
        """所有活跃接触点的最大合力（N）。"""
        max_f = 0.0
        cf = np.zeros(6)
        for i in range(self._data.ncon):
            self._mj.mj_contactForce(self._model, self._data, i, cf)
            f = float(np.linalg.norm(cf[:3]))
            if f > max_f:
                max_f = f
        return max_f

    def render(
        self,
        camera_name: str = "overhead",
        width:  int = 640,
        height: int = 480,
    ) -> np.ndarray:
        """
        用指定相机渲染 RGB 图像，返回 np.ndarray (height, width, 3) uint8。

        需要设置 MUJOCO_GL=egl（GPU）或 MUJOCO_GL=osmesa（CPU）。
        """
        if (self._renderer is None
                or self._renderer.width  != width
                or self._renderer.height != height):
            if self._renderer is not None:
                self._renderer.close()
            self._renderer = self._mj.Renderer(
                self._model, height=height, width=width)

        self._renderer.update_scene(self._data, camera=camera_name)
        return self._renderer.render().copy()

    def trajectory_record(
        self,
        waypoints_mm: list,
        steps_per_segment: int = 40,
    ) -> tuple:
        """
        仿真轨迹并记录 EE 位置与接触力。

        参数
        ────
        waypoints_mm    路径点列表，mm 单位
        steps_per_segment  每两点间的仿真步数

        返回
        ────
        positions  np.ndarray (N, 3)  单位 m
        forces     np.ndarray (N,)    单位 N
        """
        positions: list = []
        forces:    list = []

        for wp in waypoints_mm:
            if hasattr(wp, '__len__') and len(wp) >= 7 and int(wp[6]) == 1:
                continue
            target_m = _mm_to_m(wp)
            start    = self._data.mocap_pos[0].copy()

            for k in range(steps_per_segment):
                t = (k + 1) / steps_per_segment
                self._data.mocap_pos[0] = start + t * (target_m - start)
                self._sync_ctrl()
                self._mj.mj_step(self._model, self._data)
                self.sim_steps += 1
                positions.append(self.get_ee_pos().copy())
                forces.append(self.get_contact_force())

        return np.array(positions), np.array(forces)

    # ── 内部辅助 ─────────────────────────────────────────────

    def _sync_ctrl(self) -> None:
        """
        将执行器设定点同步到当前关节角。
        关键：防止位置执行器与 weld 约束力对抗，
        使约束可以自由驱动 IK 而执行器只提供阻尼。
        """
        nq = min(self._model.nq, len(self._data.ctrl))
        self._data.ctrl[:nq] = self._data.qpos[:nq]

    def _move_ee_to(self, target_m: np.ndarray, max_iter: int = CTRL_STEPS) -> int:
        """
        分小步移动 mocap_pos 到目标位置，每步运行仿真。
        weld 约束驱动关节角跟随（自动 IK）。
        返回累计仿真步数。
        """
        steps = 0
        for _ in range(max_iter):
            current = self._data.mocap_pos[0].copy()
            delta   = target_m - current
            dist    = float(np.linalg.norm(delta))
            if dist < 5e-4:
                break
            step = min(dist, self.MAX_STEP_M)
            self._data.mocap_pos[0] = current + (delta / dist) * step
            self._sync_ctrl()
            self._mj.mj_step(self._model, self._data)
            self.sim_steps += 1
            steps += 1
        return steps
