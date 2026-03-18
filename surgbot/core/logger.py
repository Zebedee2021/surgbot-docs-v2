"""
core/logger.py
==============
结构化日志。基于 loguru（现有代码已在用），增加手术场景专用的上下文字段。

每条日志都携带：
    time / level / module / session_id / message + 业务字段（instrument_id 等）

日志同时输出到：
    - 控制台（彩色，INFO 及以上）
    - logs/surgbot_YYYYMMDD.log（DEBUG 及以上，自动按日轮转）
    - logs/surgbot_errors.log（ERROR 及以上，保留 30 天）
"""

from __future__ import annotations

import sys
import uuid
import time
from pathlib import Path
from typing import Optional

from loguru import logger as _loguru_logger

from core.config import cfg


# ──────────────────────────────────────────
# 初始化（只执行一次）
# ──────────────────────────────────────────

_initialized = False
_session_id: str = uuid.uuid4().hex[:8]   # 每次启动生成一个 8 位会话 ID


def _setup_logger() -> None:
    global _initialized
    if _initialized:
        return

    log_dir = Path(cfg.paths.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 移除 loguru 默认 handler
    _loguru_logger.remove()

    # 控制台：彩色，INFO+
    _loguru_logger.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[module]: <12}</cyan> | "
            "{message}"
        ),
    )

    # 文件：DEBUG+，按日轮转，保留 14 天
    _loguru_logger.add(
        log_dir / "surgbot_{time:YYYYMMDD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "session={extra[session_id]} | "
            "mod={extra[module]: <12} | "
            "{message}"
        ),
    )

    # 错误文件：ERROR+，保留 30 天
    _loguru_logger.add(
        log_dir / "surgbot_errors.log",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "session={extra[session_id]} | "
            "mod={extra[module]: <12} | "
            "{message}\n{exception}"
        ),
    )

    _initialized = True


# ──────────────────────────────────────────
# 公共接口
# ──────────────────────────────────────────

def get_logger(module: str = "core"):
    """
    获取绑定了 module 和 session_id 的 logger。

    用法：
        log = get_logger("perception")
        log.info("YOLO detected instrument")
        log.warning("confidence low: 0.62")
    """
    _setup_logger()
    return _loguru_logger.bind(module=module, session_id=_session_id)


# ──────────────────────────────────────────
# 业务专用日志函数（结构化字段）
# ──────────────────────────────────────────

def log_command(instrument_id: str, name: str, confidence: float,
                source_text: str, module: str = "nlp") -> None:
    """记录 NLP 识别到的器械指令。"""
    log = get_logger(module)
    log.info(
        f"CMD instrument_id={instrument_id} name={name!r} "
        f"conf={confidence:.2f} text={source_text!r}"
    )


def log_grasp_target(slot_id: str, instrument_id: str,
                     point: list, orientation: float,
                     confidence: float, is_nominal: bool,
                     module: str = "perception") -> None:
    """记录感知层输出的夹取目标。"""
    log = get_logger(module)
    tag = "[NOMINAL]" if is_nominal else f"[conf={confidence:.2f}]"
    log.info(
        f"GRASP {tag} slot={slot_id} id={instrument_id} "
        f"xyz=({point[0]:.1f},{point[1]:.1f},{point[2]:.1f}) "
        f"rz={orientation:.1f}°"
    )


def log_motion_start(action_type: str, target_pose: Optional[list],
                     instrument_id: str = "", module: str = "execution") -> None:
    """记录开始执行某个动作步骤。"""
    log = get_logger(module)
    pose_str = (f"({target_pose[0]:.1f},{target_pose[1]:.1f},{target_pose[2]:.1f})"
                if target_pose and len(target_pose) >= 3 else "N/A")
    log.info(f"MOTION_START action={action_type} pose={pose_str} id={instrument_id}")


def log_motion_done(action_type: str, elapsed_ms: float,
                    module: str = "execution") -> None:
    """记录动作步骤完成。"""
    log = get_logger(module)
    log.info(f"MOTION_DONE  action={action_type} elapsed={elapsed_ms:.0f}ms")


def log_safety_event(event: str, detail: str, module: str = "safety") -> None:
    """记录安全相关事件（急停、工作空间违规等）。"""
    log = get_logger(module)
    log.warning(f"SAFETY {event}: {detail}")


def log_force_event(is_applied: bool, delta_n: float,
                    threshold: float, module: str = "execution") -> None:
    """记录力反馈事件。"""
    log = get_logger(module)
    if is_applied:
        log.info(f"FORCE_DETECTED delta={delta_n:.2f}N threshold={threshold:.2f}N → releasing gripper")
    else:
        log.debug(f"FORCE_CHECK delta={delta_n:.2f}N threshold={threshold:.2f}N → no action")


# ──────────────────────────────────────────
# 便捷：直接作为模块使用
# ──────────────────────────────────────────

# 默认 logger，给懒得 get_logger 的地方用
log = get_logger("core")
