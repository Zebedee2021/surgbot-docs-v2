# 决策模块

<span class="status-wip">进行中</span> &emsp; **负责人：** 任松（决策/感知全链路）· 谭文韬（仿真部署）

---

## 模块目标

系统的"大脑"，接收视觉感知结果与语言指令，输出机械臂动作序列。

**对外承诺：** 输出符合 [`ActionSequence`](../../design/module_interfaces.md#actionsequence) 接口规范，并在 LIBERO 基准上建立可复现的成功率基线。

---

## 上下游接口

=== "输入"

    | 来源 | 数据 | 说明 |
    |------|------|------|
    | 感知模块 | `GraspTarget` | 夹取点坐标 + 方向 |
    | NLP 模块 | `InstrumentCommand` | 标准化器械名 + 置信度 |
    | Isaac Sim / 真实相机 | RGB 图像帧 | VLA 视觉输入 |

=== "输出"

    | 消费方 | 数据 | 说明 |
    |--------|------|------|
    | 执行模块 | `ActionSequence` | 动作步骤序列，含速度和力控参数 |

---

## 当前状态

| 子功能 | 状态 | 说明 |
|--------|------|------|
| OpenVLA 环境配置 | <span class="status-done">完成</span> | RTX 4090 48GB 单卡运行 |
| LIBERO 链路跑通 | <span class="status-done">完成</span> | libero_spatial 10 任务可评测 |
| 稳定基线建立 | <span class="status-wip">进行中</span> | 排查稳定性 bug，建立可复现结果 |
| Isaac Sim 联调 | <span class="status-todo">待完成</span> | 等第二级仿真环境就绪 |
| 真实机械臂迁移 | <span class="status-todo">待完成</span> | 等 Isaac Sim 验证通过 |

---

## 待决策问题

!!! question "D-02：真机数据采集策略"
    方案 A：先用 Isaac Sim 合成数据微调 OpenVLA，再迁移真机。  
    方案 B：先用真机遥操作采集少量真实数据，直接微调。  
    两种方案的数据成本和迁移效果需要评估。

---

## 已知瓶颈

!!! warning "P1-05：LIBERO 基线尚不稳定"
    `libero_spatial` 评测结果存在随机性，尚未建立可复现的基线成功率。  
    **改进方向：** 固定随机种子，记录每次评测的完整配置，产出基线报告。

---

## 本周行动

- [ ] 任松：固定评测配置（随机种子、episode 数、任务列表），跑出基线报告
- [ ] 任松：整理 OpenVLA 安装文档，保证团队可复现
- [ ] 谭文韬：推进 Isaac Sim 与 OpenVLA 的接口对接方案设计

---

## 技术子页

- [OpenVLA 进展](openvla_progress.md) — 环境配置、已完成工作、评测记录
- [LIBERO 仿真评测](libero_eval.md) — 任务集说明、评测流程、基线结果
- [数据流水线](data_pipeline.md) — 数据采集、格式规范、训练数据管理

<div class="doc-footer">
  <span>负责人：任松 / 谭文韬</span>
  <span>最近更新 2026-03-18</span>
</div>
