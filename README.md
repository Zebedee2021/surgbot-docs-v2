# 🤖 SurgBot 文档站

**手术器械护士机器助手** — 北京理工大学具身空间智能实验室 × 雄安宣武医院神经外科

---

## ▶️ 在线演示（无需安装）

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Zebedee2021/surgbot-docs-v2/blob/main/notebooks/surgbot_demo.ipynb)

点击上方按钮，在 Google Colab 中直接运行完整 Mock 演示：
- 📐 工作空间 + 器械槽位 3D 交互可视化
- 🦾 运动路径轨迹（approach → grasp → lift → deliver）
- 🛡️ 安全校验（工作空间边界、大步长检测）
- 🔄 完整 pick_and_deliver 端到端流程

---

## 📖 文档站

**在线地址**：[https://zebedee2021.github.io/surgbot-docs-v2/](https://zebedee2021.github.io/surgbot-docs-v2/)

### 本地预览

```bash
pip install mkdocs-material
mkdocs serve
# 打开 http://127.0.0.1:8000
```

---

## 📁 仓库结构

```
surgbot-docs-v2/
├── notebooks/
│   └── surgbot_demo.ipynb     # ← Colab 演示 notebook
├── surgbot/                   # 核心代码
│   ├── config.toml            # 全局参数配置（不改代码直接调参）
│   ├── core/
│   │   ├── config.py          # 配置加载
│   │   ├── interfaces.py      # 数据类型定义
│   │   ├── safety_manager.py  # 安全校验
│   │   └── logger.py          # 结构化日志
│   └── hardware/
│       └── dobot_arm.py       # 机械臂语义封装
├── docs/                      # MkDocs 文档源文件
└── mkdocs.yml
```

---

## 🗓️ 五一冲刺计划

| 阶段 | 时间 | 目标 |
|------|------|------|
| Week 1 | 03/16~03/22 | ✅ core/ 骨架 + hardware/dobot_arm |
| Week 2 | 03/23~03/29 | 🔄 硬件对接 + 槽位标定 |
| Week 3 | 03/30~04/05 | ⭕ 感知 ROI + 本地 ASR |
| Week 4 | 04/06~04/12 | ⭕ 状态机集成 |
| Week 5 | 04/13~04/19 | ⭕ 联调稳定 |
| Week 6 | 04/20~04/30 | ⭕ 演示准备 |

详见 [五一冲刺计划](https://zebedee2021.github.io/surgbot-docs-v2/progress/mvp_sprint/)

---

> 文档版本 v0.4.0 · MkDocs Material ≥ 9.5
