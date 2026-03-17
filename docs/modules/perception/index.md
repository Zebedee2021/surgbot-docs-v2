# 感知模块

<span class="status-wip">进行中</span> &emsp; **负责人：** 李淑雅

---

## 模块目标

感知模块是系统的"眼睛"，负责将相机图像转化为机械臂可执行的夹取坐标。

**对外承诺：** 输出符合 [`GraspTarget`](../../design/module_interfaces.md#grasptarget) 接口规范的数据结构，置信度 ≥ 0.70。

---

## 上下游接口

=== "输入"

    | 来源 | 数据 | 说明 |
    |------|------|------|
    | 双目摄像头（RGB-D） | 640×480 彩色图 + 深度图 | 30fps，USB/GigE |
    | `InstrumentCommand` | 器械名称、`instrument_id` | 来自 NLP 模块，用于交叉验证 |

=== "输出"

    | 消费方 | 数据 | 说明 |
    |--------|------|------|
    | 决策模块 / 执行模块 | `GraspTarget` | 夹取点坐标 + 方向 + 置信度 |

完整字段定义见 [模块接口定义](../../design/module_interfaces.md#grasptarget)。

---

## 当前状态

| 子功能 | 状态 | 说明 |
|--------|------|------|
| YOLO 器械检测 | <span class="status-wip">进行中</span> | 基本可用，误识别率偏高（托盘外物体） |
| 手眼标定 | <span class="status-wip">进行中</span> | 流程可行但繁琐（约1h/次），半自动化开发中 |
| 夹取点修正算法 | <span class="status-wip">进行中</span> | 朝向识别偏差大，修正算法设计中 |
| 二维码验证 | <span class="status-todo">规划中</span> | 待 D-04 决策后启动 |

---

## 待决策问题

!!! question "D-01：托盘布局与摄像头方案"
    双摄像头装在同一结构件 vs 分离安装，影响整体器械台布局方案。  
    **需要全组会议决策。** 见[问题追踪 D-01](../../tracker/issues.md#_2)

!!! question "D-04：二维码验证引入时机"
    是否在第二级仿真阶段同步引入二维码识别，还是等真机阶段再加。

---

## 已知瓶颈

!!! failure "P0-01：手眼标定每次约 1 小时"
    每次换场景或重新部署都需要重新标定，严重影响现场效率。  
    **改进方向：** `hardware/hand_eye_calib.py` 加入半自动流程，按钮触发自动记录标定点。

!!! warning "P1-01：夹取点识别偏差"
    YOLO 输出的中心点直接用作夹取点时偏差约 10–20mm，导致夹取失败。  
    **改进方向：** 结合识别框、夹取点标注、朝向点，用算法修正到实际夹持位置。

---

## 本周行动

- [ ] 李淑雅：完成手眼标定半自动化工具原型，可在界面按钮触发
- [ ] 李淑雅：整理当前 YOLO 误识别样本，制作 hard negative 数据集
- [ ] 李淑雅 + 任松：确认 `GraspTarget` 接口字段，与执行模块对齐

---

## 技术子页

- [YOLO 器械检测](yolo_detection.md) — 模型选型、训练数据、评测结果
- [相机标定](camera_calibration.md) — 手眼标定流程、标定矩阵管理
- [夹取点算法](grasp_algorithm.md) — 修正算法设计、测试记录

<div class="doc-footer">
  <span>负责人：李淑雅</span>
  <span>最近更新 2026-03-18</span>
</div>
