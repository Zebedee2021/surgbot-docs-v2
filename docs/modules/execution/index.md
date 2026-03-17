# 执行模块

<span class="status-wip">进行中</span> &emsp; **负责人：** 任松

---

## 模块目标

接收动作序列，经安全校验后控制越疆 CR5AF 机械臂完成器械夹取与递交，全程力控防碰撞。

**硬性约束：** 所有运动指令须经 `safety_manager.py` 的 `validate_path()` 校验，否则拒绝执行。  
完整安全边界见 [全局安全约束](../../design/safety_constraints.md)。

---

## 上下游接口

=== "输入"

    | 来源 | 数据 | 说明 |
    |------|------|------|
    | 决策模块 | `ActionSequence` | 动作步骤序列 |
    | `safety_manager` | 校验结果 | 通过才执行 |

=== "输出"

    | 消费方 | 数据 | 说明 |
    |--------|------|------|
    | CR5AF 机械臂 | 关节角 / 末端位姿 | Dobot SDK TCP 协议 |
    | 状态机 | 执行状态反馈 | 完成 / 中断 / 急停 |

---

## 当前状态

| 子功能 | 状态 | 说明 |
|--------|------|------|
| CR5 SDK 基础封装 | <span class="status-done">完成</span> | `hardware/cr5af_arm.py` 封装完毕 |
| 基础运动控制 | <span class="status-done">完成</span> | 关节运动 + 末端位姿运动可用 |
| 力控夹爪 | <span class="status-wip">进行中</span> | 夹持力参数调试中 |
| 执行前安全校验 | <span class="status-wip">进行中</span> | P0-03，`validate_path()` 开发中 |
| Z 轴高度自适应 | <span class="status-todo">待完成</span> | P1-02，设计中 |
| GUI 参数配置接口 | <span class="status-todo">待完成</span> | P0-02，等 GUI 模块完成 |
| 递送姿态模板 | <span class="status-todo">待完成</span> | 把手朝向医生的标准姿态库 |

---

## 待决策问题

无当前待决策事项。

---

## 已知瓶颈

!!! failure "P0-03：缺少执行前安全校验"
    当前感知模块输出偏差时，机械臂会直接向错误位置运动（现场问题 #8）。  
    **改进方向：** 在 `core/safety_manager.py` 实现 `validate_path()`，包含工作空间检查、碰撞预检、速度合规检查。

!!! warning "P1-02：Z 轴高度不一致"
    真实托盘桌面不平整，不同区域 Z 偏移量差异可达 5–10mm，导致夹取失败（现场问题 #3）。  
    **改进方向：** 执行层增加高度自适应补偿，夹取前先探测实际 Z 高度。

---

## 本周行动

- [ ] 任松：完成 `validate_path()` 工作空间检查部分，单元测试通过
- [ ] 任松：收集夹持力测试数据（不同器械类型），确定力控参数范围
- [ ] 任松：与感知模块对齐 `GraspTarget` 坐标系定义

---

## 技术子页

- [CR5 控制接口](dobot_cr5_control.md) — SDK 封装、通信协议、指令集
- [运动规划](motion_planning.md) — 轨迹规划、笛卡尔路径、关节插值
- [安全策略实现](safety_strategy.md) — `validate_path()` 实现、急停逻辑、力控参数

<div class="doc-footer">
  <span>负责人：任松</span>
  <span>最近更新 2026-03-18</span>
</div>
