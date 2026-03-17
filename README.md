# SurgBot 文档站

**手术器械护士机器助手** — 北京理工大学具身空间智能实验室 × 雄安宣武医院神经外科

## 快速开始

### 本地预览

```bash
pip install mkdocs-material
mkdocs serve
# 打开 http://127.0.0.1:8000
```

### 部署

推送到 `main` 分支后，GitHub Actions 自动构建并发布至 GitHub Pages。

初次使用需在仓库 Settings → Pages 中将 Source 设置为 **GitHub Actions**。

## 文档结构

```
docs/
├── index.md                  # 首页（快速导航 + 阶段总览）
├── background/               # 项目背景（只读）
│   ├── introduction.md
│   ├── team.md
│   └── hardware.md
├── design/                   # 系统设计（活跃决策中心）
│   ├── architecture.md       # 总体架构 + 状态机
│   ├── human_robot_collab.md # 人机协同方案
│   ├── module_interfaces.md  # ★ 跨模块接口定义
│   ├── data_flow.md          # 数据流规范
│   └── safety_constraints.md # ★ 全局安全约束
├── modules/                  # 模块文档（统一模板）
│   ├── perception/           # 感知模块
│   ├── nlp/                  # NLP 模块
│   ├── decision/             # 决策模块
│   ├── execution/            # 执行模块
│   └── simulation/           # 仿真模块
├── sim2real/
│   └── status.md             # ★ Sim2Real 三级验证状态面板
├── tracker/
│   ├── issues.md             # ★ 全局问题与决策追踪
│   └── milestones.md         # 里程碑
├── progress/                 # 项目进展记录
├── meeting/                  # 会议记录
├── testing/                  # 测试记录
├── members/                  # 成员工作
├── references/               # 参考资料
└── guides/                   # 操作指南
    └── doc_convention.md     # ★ 文档编写规范（模板说明）
```

> ★ 标注为本次重构新增的核心页面

## 文档规范

每个模块的 `index.md` 遵循统一的六段模板：

> **模块目标 → 上下游接口 → 当前状态 → 待决策问题 → 已知瓶颈 → 本周行动**

详见 [文档编写规范](docs/guides/doc_convention.md)。

## 版本

- 文档版本：v0.3.0
- MkDocs Material：≥ 9.5
