# 手术器械护士机器助手

<div class="hero">
  <p>SurgBot — 北京理工大学具身空间智能实验室 × 雄安宣武医院神经外科</p>
</div>

## 快速导航

<div class="grid cards" markdown>

- :material-file-document-outline: **项目背景**

    项目简介、团队成员、硬件平台——写完归档的参考资料

    [:octicons-arrow-right-24: 项目简介](background/introduction.md)

- :material-cog-outline: **系统设计**

    架构、接口定义、人机协同、安全约束——每次开会前先看这里

    [:octicons-arrow-right-24: 总体架构](design/architecture.md)

- :material-puzzle-outline: **模块文档**

    感知 · NLP · 决策 · 执行 · 仿真——统一模板，当前状态一目了然

    [:octicons-arrow-right-24: 感知模块](modules/perception/index.md)

- :material-swap-horizontal: **Sim2Real 状态**

    三级验证进度 · Sim Gap 追踪 · 目标指标——每周更新

    [:octicons-arrow-right-24: 查看面板](sim2real/status.md)

- :material-flag-checkered: **全局追踪**

    跨模块问题、待决策事项、里程碑——聚合所有模块的 P0/P1 问题

    [:octicons-arrow-right-24: 问题追踪](tracker/issues.md)

- :material-book-open-outline: **操作指南**

    环境搭建、Git 规范、文档编写规范——新成员从这里开始

    [:octicons-arrow-right-24: 开始](guides/env_setup.md)

</div>

---

## 当前阶段总览

| 验证级别 | 状态 | 负责人 |
|---------|------|--------|
| **第一级** LIBERO + MuJoCo | :material-check-circle:{ .status-done } 已跑通，正在建立稳定基线 | 任松 |
| **第二级** Isaac Sim 虚拟手术室 | :material-progress-clock:{ .status-wip } 搭建中，CR5 URDF 导入进行中 | 谭文韬 |
| **第三级** 真实 CR5AF 机械臂 | :material-wrench:{ .status-wip } 首轮测试完成，9 类问题改进中 | 全员 |

!!! tip "Sim2Real 面板"
    查看三级验证的详细进度和 Sim Gap 追踪：[:octicons-arrow-right-24: Sim2Real 状态面板](sim2real/status.md)

---

## 核心定位

> **人机协同，而非替代。**
>
> 机器助手处理约 70–80% 的高频标准器械递交任务，器械护士保留决策权与异常处理能力。  
> 交互模式：**触发 → 确认 → 交接**

<div class="doc-footer">
  <span>SurgBot Team — 文档版本 v0.3.0</span>
  <span>最近更新 2026-03-18</span>
</div>
