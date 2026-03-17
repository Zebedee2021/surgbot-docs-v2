# 全局安全约束

!!! danger "硬性边界"
    本页定义整个系统的安全红线。所有模块开发、参数调整均不得违反以下约束。如需修改约束值，须经全组讨论并在此更新，不得单方面在代码中修改。

## 一、运动安全

### 工作空间限制

机械臂末端位姿须始终在以下范围内，由 `safety_manager.py` 在每条指令下发前检查：

```python
WORKSPACE_LIMITS = {
    "x_mm":  (-400,  400),   # 相对机械臂基座
    "y_mm":  (-400,  400),
    "z_mm":  (  50,  600),   # 最低 50mm，防止撞击托盘桌面
    "rx_deg": (-90,   90),
    "ry_deg": (-90,   90),
    "rz_deg": (-180, 180),
}
```

### 速度与力限制

| 参数 | 实验室模式 | 医院现场模式 | 说明 |
|------|-----------|-------------|------|
| 最大速度 | 80% | **40%** | 手术室人员密度高 |
| 夹持力上限 | 8 N | **6 N** | 防止损坏器械 |
| 力控阈值（急停） | 15 N | **10 N** | 接触意外阻力时立即停止 |
| 加速度上限 | 50% | **30%** | 降低惯性冲击 |

!!! warning
    医院现场模式的参数**不得**通过代码直接修改，须通过 GUI 配置界面调整并写入配置文件（现场测试问题 #2）。

---

## 二、急停机制

### 触发条件

以下任一条件触发立即急停，状态机跳转至 `Emergency`：

- 关节力矩超出阈值（见上表）
- 末端位置偏离规划路径 > **20mm**
- 路径安全校验失败（`validate_path()` 返回 False）
- 硬件急停按钮按下
- 软件急停指令（通过 GUI 或脚踏板）

### 响应时间要求

$$T_{stop} \leq 80\text{ ms}$$

此为硬性指标，须在 Isaac Sim 和真机上均通过测试方可进入医院部署。

### 恢复流程

```
Emergency
   │
   ▼
人工确认安全（护士/操作员）
   │
   ▼
手动复位（GUI 按钮）
   │
   ▼
Idle（待机）
```

急停后**不允许**自动恢复，必须经人工确认。

---

## 三、执行前安全校验

每条 `ActionSequence` 下发前，`safety_manager.py` 须执行以下检查序列（现场测试问题 #8）：

```python
def validate_path(sequence: ActionSequence, current_pose: np.ndarray) -> tuple[bool, str]:
    """
    返回 (True, "") 才允许执行；返回 (False, reason) 则拒绝并记录原因。
    """
    for step in sequence.steps:
        # 1. 工作空间检查
        if not in_workspace(step.target_pose):
            return False, f"目标位姿超出工作空间: {step.target_pose}"
        # 2. 奇异点检查
        if near_singularity(step.target_pose):
            return False, f"目标位姿接近奇异点"
        # 3. 碰撞预检（简化包围盒）
        if collision_predicted(current_pose, step.target_pose):
            return False, f"路径碰撞预警"
        # 4. 速度合规检查
        if step.speed > SPEED_LIMIT[SCENE_MODE]:
            return False, f"速度 {step.speed} 超出当前模式上限"
    return True, ""
```

---

## 四、交叉验证约束

见[模块接口定义 — 跨模块验证机制](module_interfaces.md#_4)。

置信度阈值：

| 模块 | 阈值 | 低于阈值时行为 |
|------|------|--------------|
| NLP 器械识别 | 0.85 | 状态机停留在 Parse，请求护士确认 |
| 视觉夹取点 | 0.70 | 同上 |
| 二维码验证（规划中） | 强匹配 | 不一致时拒绝执行 |

---

## 五、禁止行为清单

以下行为在任何代码路径中均被禁止：

- [ ] 绕过 `safety_manager.py` 直接调用 Dobot SDK 的运动接口
- [ ] 在 `Emergency` 状态下自动恢复运动
- [ ] 在置信度不足时跳过交叉验证强制执行
- [ ] 修改医院现场模式的速度/力限制而不更新本文档
- [ ] 未经 `validate_path()` 直接下发 VLA 输出的动作序列

<div class="doc-footer">
  <span>负责人：任松（安全逻辑）/ 全组（约束值审核）</span>
  <span>最近更新 2026-03-18</span>
</div>
