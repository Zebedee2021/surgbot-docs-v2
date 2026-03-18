"""
modules/nlp/keyword_matcher.py
────────────────────────────────
关键词 → InstrumentCommand 映射器

MVP 阶段不使用大模型，直接用正则/关键词匹配；
未来可无缝替换为 Qwen2.5 SFT 输出（接口不变）。

设计要点
- 从 PositionRegistry 自动导入所有别名，无需手动维护词表
- 支持优先级：精确 > 最长子串 > 模糊
- 返回 InstrumentCommand，含置信度
- confidence 低于阈值时返回 None，由调用方决定是否重新询问
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from core.config import cfg
from core.interfaces import InstrumentCommand
from core.logger import get_logger
from modules.perception.position_registry import registry, SlotInfo

log = get_logger("keyword_matcher")


# ──────────────────────────────────────────────
# 匹配结果
# ──────────────────────────────────────────────

@dataclass
class MatchResult:
    slot: SlotInfo
    confidence: float
    matched_keyword: str
    match_type: str          # "exact" | "alias_exact" | "substring" | "fuzzy"


# ──────────────────────────────────────────────
# 匹配器
# ──────────────────────────────────────────────

class KeywordMatcher:
    """
    关键词匹配器（单例）。

    用法::

        from modules.nlp.keyword_matcher import matcher

        cmd = matcher.match("递持针器")     # → InstrumentCommand | None
        cmd = matcher.match("给我剪刀")
    """

    # 动词前缀（忽略，只看器械名）
    _VERB_PREFIXES = re.compile(
        r"^(请|帮我|递|给我|给|传|来一个|来个|要|拿|需要|准备|换|换一个|换个)+"
    )

    def __init__(self) -> None:
        self._threshold = cfg.nlp.keyword_confidence_threshold if hasattr(cfg, "nlp") else 0.6
        self._refresh()

    def _refresh(self) -> None:
        """从注册表重建匹配表（注册表热重载后调用）。"""
        self._slots = registry.enabled_slots()
        log.debug(f"KeywordMatcher 刷新：{len(self._slots)} 个槽位")

    # ── 核心接口 ─────────────────────────────

    def match(self, text: str, source_text: Optional[str] = None) -> Optional[InstrumentCommand]:
        """
        从 ASR 文本中匹配器械指令。

        :param text: ASR 识别结果（中文自然语言）
        :param source_text: 原始 ASR 文本（可选，用于日志）
        :returns: InstrumentCommand，置信度不足时返回 None
        """
        result = self._do_match(text)
        if result is None:
            log.warning(f"未匹配到器械: '{text}'")
            return None

        if result.confidence < self._threshold:
            log.warning(
                f"匹配置信度过低: '{text}' → {result.slot.name} "
                f"({result.confidence:.2f} < {self._threshold})"
            )
            return None

        cmd = InstrumentCommand(
            instrument_id=result.slot.instrument_id,
            name=result.slot.name,
            confidence=result.confidence,
            source_text=source_text or text,
            slot_id=result.slot.slot_id,
        )
        log.info(
            f"匹配成功: '{text}' → {cmd.name} ({cmd.slot_id})  "
            f"type={result.match_type}  conf={cmd.confidence:.2f}"
        )
        return cmd

    def match_all(self, text: str) -> list[MatchResult]:
        """返回所有候选匹配（含置信度），用于调试/审计。"""
        cleaned = self._clean(text)
        candidates: list[MatchResult] = []
        for slot in self._slots:
            r = self._score(cleaned, slot)
            if r is not None:
                candidates.append(r)
        return sorted(candidates, key=lambda r: -r.confidence)

    # ── 内部 ─────────────────────────────────

    def _do_match(self, text: str) -> Optional[MatchResult]:
        candidates = self.match_all(text)
        return candidates[0] if candidates else None

    def _clean(self, text: str) -> str:
        """去除动词前缀、标点、空格。"""
        t = text.strip()
        t = self._VERB_PREFIXES.sub("", t)
        t = re.sub(r"[，。！？,.!? ]", "", t)
        return t

    def _score(self, cleaned_query: str, slot: SlotInfo) -> Optional[MatchResult]:
        """对单个槽位打分，返回最佳 MatchResult 或 None。"""
        q = cleaned_query

        # 1. 精确匹配主名称
        if slot.name == q:
            return MatchResult(slot, 0.98, q, "exact")

        # 2. 精确匹配 alias
        for alias in slot.aliases:
            if alias == q:
                return MatchResult(slot, 0.95, alias, "alias_exact")

        # 3. 子串匹配
        best_score = 0.0
        best_kw = ""
        for kw in slot.all_names:
            kw_l = kw.lower()
            q_l = q.lower()
            if kw_l in q_l or q_l in kw_l:
                # 匹配长度占被搜索串的比例
                ratio = len(min(kw_l, q_l, key=len)) / max(len(kw_l), len(q_l), 1)
                score = 0.6 + 0.3 * ratio          # 0.60 – 0.90
                if score > best_score:
                    best_score = score
                    best_kw = kw

        if best_score > 0:
            return MatchResult(slot, round(best_score, 3), best_kw, "substring")

        return None


# ── 全局单例 ─────────────────────────────────

matcher = KeywordMatcher()
