"""
modules/perception/position_registry.py
────────────────────────────────────────
器械槽位注册表：从 instrument_registry.json 加载槽位信息，
提供按名称/alias/slot_id 的快速查询接口。

设计要点
- 单例：PositionRegistry.get_instance() 避免重复 IO
- 支持模糊 alias 匹配（精确优先，再做子串）
- 运行时支持热重载（reload()）——更新标定点后不需重启进程
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config import cfg
from core.logger import get_logger

log = get_logger("position_registry")

# surgbot 包根目录（无论从哪里运行都能正确定位 data/）
# modules/perception/position_registry.py → parents[2] = surgbot/
_SURGBOT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_registry_path() -> Path:
    """
    优先级：
    1. cfg.paths.data_dir 如果是绝对路径 → 直接用
    2. cfg.paths.data_dir 是相对路径 → 相对于 surgbot 包根目录
    3. 兜底 → surgbot/data/instrument_registry.json
    """
    data_dir = Path(cfg.paths.data_dir)
    if data_dir.is_absolute():
        return data_dir / "instrument_registry.json"
    # 相对路径：先试 surgbot 根目录，再试当前目录
    candidate = _SURGBOT_ROOT / data_dir / "instrument_registry.json"
    if candidate.exists():
        return candidate
    # 最后回退：当前工作目录（兼容直接 cd 到 surgbot 运行的情况）
    return data_dir / "instrument_registry.json"


# ──────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────

@dataclass
class SlotInfo:
    slot_id: str
    instrument_id: str
    name: str
    aliases: list[str]
    grasp_point: list[float]        # [x, y, z, rx, ry, rz] or [x, y, z]
    orientation_deg: float
    gripper_preset_id: int
    roi: dict                       # {"x1", "y1", "x2", "y2"} pixel coords
    enabled: bool
    notes: str = ""

    @property
    def all_names(self) -> list[str]:
        """全部可匹配名称（含主名称）"""
        return [self.name] + self.aliases


# ──────────────────────────────────────────────
# 注册表
# ──────────────────────────────────────────────

class PositionRegistry:
    """
    器械槽位注册表（单例）。

    用法::

        from modules.perception.position_registry import registry

        slot = registry.find("持针器")      # → SlotInfo | None
        slot = registry.get_by_id("slot_01")
        all_slots = registry.enabled_slots()
    """

    _instance: Optional["PositionRegistry"] = None

    def __init__(self, json_path: Optional[Path] = None) -> None:
        self._path = json_path or _resolve_registry_path()
        self._slots: dict[str, SlotInfo] = {}          # slot_id → SlotInfo
        self._deliver_point: list[float] = []
        self._reset_pose: list[float] = []
        self.load()

    @classmethod
    def get_instance(cls) -> "PositionRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── I/O ──────────────────────────────────

    def load(self) -> None:
        """从 JSON 文件加载（或热重载）。"""
        if not self._path.exists():
            log.warning(f"instrument_registry.json 不存在: {self._path}，使用空注册表")
            return

        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)

        self._slots = {}
        for s in data.get("slots", []):
            info = SlotInfo(
                slot_id=s["slot_id"],
                instrument_id=s["instrument_id"],
                name=s["name"],
                aliases=s.get("aliases", []),
                grasp_point=s["grasp_point"],
                orientation_deg=s.get("orientation_deg", 0.0),
                gripper_preset_id=s.get("gripper_preset_id", 1),
                roi=s.get("roi", {}),
                enabled=s.get("enabled", True),
                notes=s.get("notes", ""),
            )
            self._slots[info.slot_id] = info

        self._deliver_point = data.get("deliver_point", [])
        self._reset_pose = data.get("reset_pose", [])

        log.info(f"注册表加载完成：{len(self._slots)} 个槽位  path={self._path}")

    def reload(self) -> None:
        """标定更新后热重载，无需重启进程。"""
        log.info("重载槽位注册表...")
        self.load()

    def save(self) -> None:
        """将当前状态写回 JSON（用于标定工具更新坐标）。"""
        slots_data = []
        for s in self._slots.values():
            slots_data.append({
                "slot_id": s.slot_id,
                "instrument_id": s.instrument_id,
                "name": s.name,
                "aliases": s.aliases,
                "grasp_point": s.grasp_point,
                "orientation_deg": s.orientation_deg,
                "gripper_preset_id": s.gripper_preset_id,
                "roi": s.roi,
                "enabled": s.enabled,
                "notes": s.notes,
            })
        out = {
            "_version": "0.2.0",
            "slots": slots_data,
            "deliver_point": self._deliver_point,
            "reset_pose": self._reset_pose,
        }
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        log.info(f"注册表已保存: {self._path}")

    # ── 查询接口 ─────────────────────────────

    def get_by_id(self, slot_id: str) -> Optional[SlotInfo]:
        """按 slot_id 精确查询。"""
        return self._slots.get(slot_id)

    def get_by_instrument_id(self, instrument_id: str) -> Optional[SlotInfo]:
        """按器械编号查询。"""
        for s in self._slots.values():
            if s.instrument_id == instrument_id and s.enabled:
                return s
        return None

    def find(self, name: str) -> Optional[SlotInfo]:
        """
        按名称/alias 查找（大小写不敏感，优先精确匹配）。

        匹配顺序：
        1. 精确匹配主名称
        2. 精确匹配任意 alias
        3. 子串匹配（name 包含 query 或 query 包含 name）
        """
        query = name.strip()

        # 精确匹配
        for s in self._slots.values():
            if not s.enabled:
                continue
            if s.name == query or query in s.aliases:
                return s

        # 子串匹配（大小写不敏感）
        q_lower = query.lower()
        best: Optional[SlotInfo] = None
        best_score = 0
        for s in self._slots.values():
            if not s.enabled:
                continue
            for alias in s.all_names:
                a_lower = alias.lower()
                if q_lower in a_lower or a_lower in q_lower:
                    # 越长的别名匹配得越具体
                    score = min(len(q_lower), len(a_lower))
                    if score > best_score:
                        best_score = score
                        best = s
        return best

    def enabled_slots(self) -> list[SlotInfo]:
        """返回所有已启用槽位（按 slot_id 排序）。"""
        return sorted(
            [s for s in self._slots.values() if s.enabled],
            key=lambda s: s.slot_id,
        )

    def all_slots(self) -> list[SlotInfo]:
        return sorted(self._slots.values(), key=lambda s: s.slot_id)

    # ── 标定辅助 ────────────────────────────

    def update_grasp_point(
        self,
        slot_id: str,
        grasp_point: list[float],
        orientation_deg: Optional[float] = None,
        auto_save: bool = True,
    ) -> None:
        """标定工具调用：更新夹取点坐标并可选自动保存。"""
        slot = self._slots.get(slot_id)
        if slot is None:
            raise KeyError(f"slot_id 不存在: {slot_id}")
        slot.grasp_point = grasp_point
        if orientation_deg is not None:
            slot.orientation_deg = orientation_deg
        log.info(f"更新夹取点: {slot_id}  pt={grasp_point}  rz={orientation_deg}")
        if auto_save:
            self.save()

    @property
    def deliver_point(self) -> list[float]:
        return self._deliver_point

    @property
    def reset_pose(self) -> list[float]:
        return self._reset_pose

    def __len__(self) -> int:
        return len(self._slots)

    def __repr__(self) -> str:
        return f"<PositionRegistry slots={len(self._slots)} path={self._path}>"


# ── 全局单例 ─────────────────────────────────

registry = PositionRegistry.get_instance()
