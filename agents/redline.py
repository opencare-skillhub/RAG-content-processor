"""风险红线检测器。

一期只做本地预筛：关键词 + 正则。
命中结果交给 RubricConfig.evaluate_result 做降级/拒绝等处理。
"""
from __future__ import annotations

import re
from typing import Any

from agents.rubric import RubricConfig


class RedlineChecker:
    """根据 rubric.risk_redlines 检测内容风险。"""

    def __init__(self, rubric: RubricConfig):
        self.rubric = rubric
        self.rules = rubric.data.get("risk_redlines", [])

    def check(self, content: str) -> list[dict[str, Any]]:
        """返回命中的红线列表。"""
        if not content:
            return []

        hits = []
        for rule in self.rules:
            matched_keywords = self._match_keywords(content, rule.get("keywords", []))
            matched_patterns = self._match_patterns(content, rule.get("patterns", []))
            if matched_keywords or matched_patterns:
                hit = {
                    "id": rule.get("id"),
                    "name": rule.get("name"),
                    "action": rule.get("action", "downgrade"),
                    "max_grade": rule.get("max_grade"),
                    "matched_keywords": matched_keywords,
                    "matched_patterns": matched_patterns,
                }
                hits.append(hit)
        return hits

    @staticmethod
    def _match_keywords(content: str, keywords: list[str]) -> list[str]:
        return [kw for kw in keywords if kw and kw in content]

    @staticmethod
    def _match_patterns(content: str, patterns: list[str]) -> list[str]:
        hits = []
        for pattern in patterns:
            if not pattern:
                continue
            try:
                if re.search(pattern, content):
                    hits.append(pattern)
            except re.error:
                # 配置里如果写了无效正则，不让检测器崩溃
                continue
        return hits
