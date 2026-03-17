# 仿真模块

<span class="status-wip">搭建中</span> &emsp; **负责人：** 谭文韬

---

## 模块目标

构建高保真虚拟手术室，在真机测试前完成感知-决策-执行全链路的闭环验证，并产出用于模型训练的仿真数据。

**核心作用：** 三级验证体系的第二级，是 sim2real 迁移的缓冲层。  
详见 [Sim2Real 状态面板](../../sim2real/status.md)。

---

## 上下游接口

=== "提供给其他模块"

    | 消费方 | 数据 | 说明 |
    |--------|------|------|
    | 决策模块 | 仿真 RGB 图像帧 | OpenVLA 视觉输入 |
    | 感知模块 | 仿真 RGB-D 数据 | 用于算法测试，不依赖真实相机 |
    | 数据流水线 | 示教演示数据 | `(图像, 动作)` 对，用于 VLA 微调 |

=== "依赖的输入"

    | 来源 | 数据 | 说明 |
    |------|------|------|
    | 核心控制层 | 状态机指令 | 通过 Python SDK 接入 |
    | 执行模块 | 关节角指令 | ROS2 Bridge 转发 |

---

## 当前状态

| 子功能 | 状态 | 说明 |
|--------|------|------|
| Isaac Sim 安装 + 基础场景 | <span class="status-done">完成</span> | Omniverse Launcher 安装完成 |
| CR5 URDF 导入 | <span class="status-wip">进行中</span> | 机械臂模型导入，夹爪配置中 |
| 手术室场景建模 | <span class="status-wip">进行中</span> | 手术床、无菌台建模中 |
| 器械 3D 模型 | <span class="status-todo">待完成</span> | Top-10 器械 CAD 导入 |
| 传感器仿真配置 | <span class="status-todo">待完成</span> | RGB-D 相机 + ToF 接近检测 |
| ROS2 Bridge 联调 | <span class="status-todo">待完成</span> | 与执行模块对接 |
| 状态机全流程联调 | <span class="status-todo">待完成</span> | 等传感器仿真完成 |
| 仿真数据采集流水线 | <span class="status-todo">待完成</span> | 等场景稳定后启动 |

---

## 待决策问题

!!! question "D-02（关联）：仿真数据采集时机"
    Isaac Sim 数据采集是否在场景搭建完成后立即启动，还是等真机遥操作数据采集方案确定后再决策？  
    见[问题追踪 D-02](../../tracker/issues.md#_2)

---

## 已知瓶颈

!!! warning "Isaac Sim 搭建进度影响全链路"
    第二级验证环境未完成，导致决策模块无法在手术室场景下做系统评测，VLA 的 sim2real 迁移也无法启动。此项是当前最关键的进度风险。

---

## 本周行动

- [ ] 谭文韬：完成 CR5 URDF + 夹爪在 Isaac Sim 中的配置，可执行基础关节运动
- [ ] 谭文韬：手术台 + 无菌台 3D 建模完成
- [ ] 谭文韬：调研 Isaac Sim 中 RGB-D 相机传感器配置方式，输出配置文档

---

## 技术子页

- [Isaac Sim 环境搭建](isaac_sim_setup.md) — 安装步骤、机械臂 URDF 导入、传感器配置
- [虚拟手术室方案](surgery_room_sim.md) — 场景分层设计、评测指标、Sim2Real 策略

<div class="doc-footer">
  <span>负责人：谭文韬</span>
  <span>最近更新 2026-03-18</span>
</div>
