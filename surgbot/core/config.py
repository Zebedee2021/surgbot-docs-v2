"""
core/config.py
==============
全局配置中心。所有参数从 config.toml 加载，不再硬编码在业务代码里。

雄安测试 P0-02：「参数须改代码，无 GUI 配置入口」← 本文件解决这个问题。

使用方式：
    from core.config import cfg

    speed  = cfg.robot.speed          # 机械臂速度
    z_off  = cfg.robot.z_approach_offset  # 夹取点上方安全高度
    thresh = cfg.safety.force_threshold   # 力反馈阈值
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Python 3.11+ 内置 tomllib；旧版本用 tomli（pip install tomli）
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # fallback 到默认值，不报错


# ──────────────────────────────────────────
# 各模块参数 dataclass
# ──────────────────────────────────────────

@dataclass
class RobotConfig:
    """机械臂运动相关参数。"""
    ip: str             = "192.168.144.49"
    dashboard_port: int = 29999
    feed_port: int      = 30005

    speed: int          = 30    # 速度百分比，1~100
    # 雄安问题 #3：Z 轴在不同位置不一致 → 这里集中配置
    z_approach_offset: float = 150.0    # mm，抵达夹取点上方的安全高度
    z_grasp_offset: float    = 1.0      # mm，夹取时相对名义 Z 的偏移

    # 待机姿态（关节角，mode=1）
    reset_pose: list = field(default_factory=lambda: [0.0, 32.6, -129.1, 6.7, 90.0, -90.0, 1])
    # 递送姿态（关节角，mode=1）
    deliver_pose: list = field(default_factory=lambda: [0.0, -50.2, -67.3, 112.5, 90.0, -90.0, 1])


@dataclass
class GripperConfig:
    """夹爪相关参数。雄安问题 #2：夹持力之前须改代码才能调整。"""
    # Modbus RTU 通信参数
    baud_rate: int  = 115200
    parity: str     = "N"
    stop_bits: int  = 1
    slave_id: int   = 1

    # 默认开合速度，10~1000
    default_speed: int = 900

    # 夹爪预设（可在 config.toml 中覆盖）
    # preset_id → {open, close, force}
    # open/close 单位：0~1000（对应开合度）；force：100~1000（夹持力）
    presets: dict = field(default_factory=lambda: {
        -1: {"open": 800, "close": 20,  "force": 800},  # 通用松开
         0: {"open": 400, "close": 20,  "force": 800},  # 刀柄
         1: {"open": 600, "close": 10,  "force": 980},  # 镊子
         2: {"open": 500, "close": 40,  "force": 550},  # 剪刀
         3: {"open": 500, "close": 10,  "force": 800},  # 持针钳
    })


@dataclass
class SafetyConfig:
    """安全约束参数。雄安问题 #8：路径无校验 → 本节提供边界值。"""
    # 工作空间边界（机械臂坐标系，mm）
    x_min: float = -600.0
    x_max: float =  600.0
    y_min: float = -700.0
    y_max: float =  100.0
    z_min: float =  100.0   # 不允许低于托盘面（防撞）
    z_max: float =  550.0

    # 力反馈阈值（N）
    # 雄安问题 #2：之前硬编码为 1.0
    force_threshold: float = 1.0

    # 最大单步移动距离（mm）；超过视为异常轨迹
    max_single_step_dist: float = 400.0


@dataclass
class PerceptionConfig:
    """感知模块参数。"""
    # 最低置信度；低于此值触发 fallback 到名义坐标
    min_confidence: float = 0.70
    # 朝向角最大修正量（°）；超过此值视为识别异常
    max_orientation_correction_deg: float = 45.0
    # ROI 扩展像素（在注册 ROI 基础上向外扩展，提升容错）
    roi_padding_px: int = 10


@dataclass
class NLPConfig:
    """NLP / ASR 模块参数。"""
    # ASR 模型路径（本地 FunASR）
    asr_model_dir: str = "models/funasr"
    # 最低指令置信度
    min_command_confidence: float = 0.60
    # 唤醒词（空表示无需唤醒直接监听）
    wake_word: str = ""


@dataclass
class PathsConfig:
    """文件路径配置。"""
    instrument_registry: str = "data/instrument_registry.json"
    hand_eye_matrix: str     = "data/hand_eye_latest.npy"
    log_dir: str             = "logs"


# ──────────────────────────────────────────
# 主配置类
# ──────────────────────────────────────────

@dataclass
class SurgBotConfig:
    robot:      RobotConfig      = field(default_factory=RobotConfig)
    gripper:    GripperConfig    = field(default_factory=GripperConfig)
    safety:     SafetyConfig     = field(default_factory=SafetyConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    nlp:        NLPConfig        = field(default_factory=NLPConfig)
    paths:      PathsConfig      = field(default_factory=PathsConfig)


# ──────────────────────────────────────────
# 加载逻辑
# ──────────────────────────────────────────

def _apply_toml(cfg: SurgBotConfig, data: dict) -> None:
    """将 TOML dict 中的值覆盖到 cfg 对应字段（只覆盖存在的键）。"""
    section_map = {
        "robot":      cfg.robot,
        "gripper":    cfg.gripper,
        "safety":     cfg.safety,
        "perception": cfg.perception,
        "nlp":        cfg.nlp,
        "paths":      cfg.paths,
    }
    for section_name, section_data in data.items():
        obj = section_map.get(section_name)
        if obj is None:
            continue
        if not isinstance(section_data, dict):
            continue
        for key, value in section_data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)


def load_config(config_path: Optional[str] = None) -> SurgBotConfig:
    """
    加载配置文件，返回 SurgBotConfig 实例。
    找不到文件时使用默认值，不抛异常（方便单元测试和离线开发）。

    优先级（高→低）：
      1. 显式传入的 config_path
      2. 环境变量 SURGBOT_CONFIG
      3. 项目根目录 config.toml
      4. 内置默认值
    """
    cfg = SurgBotConfig()

    if tomllib is None:
        # tomllib / tomli 均未安装，直接返回默认值
        print("[Config] Warning: tomllib/tomli not available, using defaults.")
        return cfg

    candidates = []
    if config_path:
        candidates.append(Path(config_path))
    env_path = os.environ.get("SURGBOT_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    # 向上查找项目根目录的 config.toml
    here = Path(__file__).resolve().parent
    for _ in range(4):
        candidates.append(here / "config.toml")
        here = here.parent

    for p in candidates:
        if p.exists():
            try:
                with open(p, "rb") as f:
                    data = tomllib.load(f)
                _apply_toml(cfg, data)
                print(f"[Config] Loaded from {p}")
                return cfg
            except Exception as e:
                print(f"[Config] Failed to load {p}: {e}")

    print("[Config] No config.toml found, using built-in defaults.")
    return cfg


# ──────────────────────────────────────────
# 全局单例
# ──────────────────────────────────────────

cfg: SurgBotConfig = load_config()
