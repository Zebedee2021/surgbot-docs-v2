# 开发环境搭建

## 文档站本地预览

```bash
# 安装依赖
pip install mkdocs-material

# 本地启动
mkdocs serve

# 浏览器打开
open http://127.0.0.1:8000
```

## VLA 评测环境（第一级 LIBERO）

参考 `modules/decision/openvla_progress.md` 中的详细安装步骤。

**硬件要求：** RTX 4090 48GB（单卡）

```bash
# 基础依赖
pip install torch torchvision
pip install transformers flash-attn
pip install libero robosuite mujoco
```

## Isaac Sim 环境（第二级仿真）

参考 `modules/simulation/isaac_sim_setup.md`。

**硬件要求：** RTX 级 GPU，建议 24GB+

1. 安装 NVIDIA Omniverse Launcher
2. 通过 Launcher 安装 Isaac Sim
3. 配置 ROS2 Bridge（可选）

<div class="doc-footer">
  <span>最近更新 2026-03-18</span>
</div>
