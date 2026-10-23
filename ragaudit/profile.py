# -*- coding: utf-8 -*-
"""难度画像与评估集自检。

这是本工具跟"算个分"类评测最大的区别：**先查你的题，再查你的分。**

一份自制评估集最常见的两个毛病：

1. 题是从知识库里反着出的 —— 写题时就知道库里有哪条，问法自然对得上，
   分数必然好看。这类题的共同特征是**问句里直接写着答案实体名**。
2. 题量分布骗人 —— 80% 的题属于同一类低难度的，总分被它拉高。

两者都可以从题面自动检测，不需要人工标注。
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from .schema import Case, Suite

__all__ = [
    "Issue",
    "LEAK_EXPLICIT",
    "LEAK_ALIAS",
    "LEAK_PARTIAL",
    "LEAK_IMPLICIT",
    "leak_level",
    "entity_mentions",
    "profile",
    "lint",
]

LEAK_EXPLICIT = "explicit"    # 问句里直接写着答案实体名
LEAK_ALIAS = "alias"          # 问句里写的是登记过的俗称
LEAK_PARTIAL = "partial"      # 问句里只出现了实体名的一部分
LEAK_IMPLICIT = "implicit"    # 整句不含任何实体名，只能靠语义

LEAK_ORDER = [LEAK_EXPLICIT, LEAK_ALIAS, LEAK_PARTIAL, LEAK_IMPLICIT]
LEAK_RANK = {k: i for i, k in enumerate(LEAK_ORDER)}

_PUNCT_RE = re.compile(r"[\s，。？！、,.?!~～:：;；\"'“”‘’()（）\[\]【】]")


@dataclass
class Issue:
    """自检发现的一个问题。"""

    level: str          # error / warn / info
    code: str
    message: str
    case_id: str = ""
    query: str = ""

    def __str__(self) -> str:
        tag = {"error": "错误", "warn": "警告", "info": "提示"}.get(self.level, self.level)
        where = f"[{self.query}] " if self.query else ""
        return f"{tag} {self.code}: {where}{self.message}"


def entity_mentions(query: str, names: Iterable[str]) -> list[str]:
    """问句里出现了哪些实体名，按匹配长度从长到短排列。

    必须按长度排：问句「龙装大树守卫怎么打」同时包含「龙装大树守卫」
    和「大树守卫」，只取两者中最长的那个，否则会把一次正确的指名
    误判成"命中了错误的实体"。
    """
    hits = [n for n in names if n and n in query]
    return sorted(set(hits), key=len, reverse=True)


def leak_level(
    case: Case,
    all_targets: Sequence[str] = (),
    alias_map: Mapping[str, str] | None = None,
) -> str:
    """判定这道题的信息泄漏等级。

    等级从高到低：explicit > alias > partial > implicit。
    partial 指问句里出现了「某个更长的实体名，而它包含期望名」——
    这种情况实体识别会指向错误目标，比完全不含实体名更难。
    """
    q = case.query
    want = case.expect_target
    if not want:
        return LEAK_IMPLICIT

    if want in q:
        # 出现更长的、以它为子串的其他实体名时，不算干净的显式指名
        longer = [t for t in entity_mentions(q, all_targets) if len(t) > len(want)]
        return LEAK_PARTIAL if longer else LEAK_EXPLICIT

    if alias_map:
        for alias, canonical in alias_map.items():
            if canonical == want and alias and alias in q:
                return LEAK_ALIAS

    # 期望名的一部分出现在问句里（去掉标点后按 2 字滑窗粗查）
    core = _PUNCT_RE.sub("", q)
    if len(want) >= 3 and any(
        want[i:i + 3] in core for i in range(len(want) - 2)
    ):
        return LEAK_PARTIAL

    return LEAK_IMPLICIT


@dataclass
class Profile:
    """评估集的难度画像。"""

    n: int = 0
    by_leak: dict[str, int] = field(default_factory=dict)
    by_group_leak: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def leak_rate(self) -> float:
        """显式指名占比。这个数越高，总分越不值钱。"""
        return (self.by_leak.get(LEAK_EXPLICIT, 0) / self.n) if self.n else 0.0

    @property
    def hard_rate(self) -> float:
        """真正有难度的占比（别名 + 部分 + 隐式）。"""
        if not self.n:
            return 0.0
        hard = sum(self.by_leak.get(k, 0) for k in (LEAK_ALIAS, LEAK_PARTIAL, LEAK_IMPLICIT))
        return hard / self.n

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "leak_rate": self.leak_rate,
            "hard_rate": self.hard_rate,
            "by_leak": dict(self.by_leak),
            "by_group_leak": {g: dict(v) for g, v in self.by_group_leak.items()},
        }


def profile(
    suite: Suite,
    alias_map: Mapping[str, str] | None = None,
) -> Profile:
    """给整份评估集算难度画像。"""
    targets = sorted({c.expect_target for c in suite.cases if c.expect_target})
    p = Profile(n=len(suite.cases))

    for c in suite.cases:
        lv = leak_level(c, targets, alias_map)
        p.by_leak[lv] = p.by_leak.get(lv, 0) + 1
        g = p.by_group_leak.setdefault(c.group, {})
        g[lv] = g.get(lv, 0) + 1

    return p


def lint(
    suite: Suite,
    alias_map: Mapping[str, str] | None = None,
    min_group_size: int = 3,
    max_leak_rate: float = 0.7,
) -> list[Issue]:
    """评估集自检。

    这些检查针对的是「指标看着漂亮但其实测不出东西」的常见成因。
    每一条都对应一次真实踩坑，不是凭空想出来的规范。
    """
    issues: list[Issue] = []
    targets = sorted({c.expect_target for c in suite.cases if c.expect_target})

    # 1. 组太小：n=2 的组算出 100% 也说明不了任何事
    counts: dict[str, int] = defaultdict(int)
    for c in suite.cases:
        counts[c.group] += 1
    for g, n in counts.items():
        if n < min_group_size:
            issues.append(Issue(
                "warn", "small_group",
                f"分组「{g}」只有 {n} 条，该组指标不具备统计意义（建议 ≥{min_group_size}）",
            ))

    # 2. 同一个目标出现在多个期望层：说明层定义有歧义
    target_layers: dict[str, set[str]] = defaultdict(set)
    for c in suite.cases:
        if c.expect_target:
            target_layers[c.expect_target].update(c.expect_layers)
    for t, layers in target_layers.items():
        if len(layers) > 1 and len({c.group for c in suite.cases if c.expect_target == t}) > 1:
            issues.append(Issue(
                "info", "multi_layer_target",
                f"实体「{t}」在不同分组里期望命中 {sorted(layers)}，"
                f"若这是有意的（如既可能命中攻略页也可能命中打法页），可忽略",
            ))

    # 3. 问句里出现了比期望目标更长的其他实体名 —— 实体识别必然指向错的那个
    for c in suite.cases:
        if not c.expect_target:
            continue
        longer = [t for t in entity_mentions(c.query, targets)
                  if len(t) > len(c.expect_target) and t != c.expect_target]
        if longer:
            issues.append(Issue(
                "warn", "longer_entity_present",
                f"问句里同时出现更长的实体名 {longer}，"
                f"实体规则会优先命中它而不是期望的「{c.expect_target}」",
                case_id=c.id, query=c.query,
            ))

    # 4. 整份评估集泄漏率过高 —— 高分可能只是查了词典
    p = profile(suite, alias_map)
    if p.leak_rate > max_leak_rate:
        issues.append(Issue(
            "warn", "high_leak_rate",
            f"{p.leak_rate:.0%} 的题在问句里直接写了答案实体名，"
            f"总分里恐怕有很大一部分来自实体匹配而非语义检索。"
            f"建议补「不含实体名」的描述式提问组",
        ))

    # 5. 期望目标不在本份评估集任何题目的层集合里 —— 多半是打错了
    for c in suite.cases:
        if not c.expect_layers:
            issues.append(Issue(
                "error", "no_expect_layer",
                "缺少 expect_layer，该题无法判定",
                case_id=c.id, query=c.query,
            ))

    return issues
