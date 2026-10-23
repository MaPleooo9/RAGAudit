# -*- coding: utf-8 -*-
"""判定口径。

「命中没命中」不是自然事实，是**口径选择**。
同一份检索结果，换个判定规则就能从 94% 掉到 89%——
差值不是误差，是这个指标虚高的部分。

所以这里不写死一套规则，而是把口径做成可组合的 Rubric：
默认给 lenient / strict 两套，用户可以给自己的数据再加一套。
报告永远并列呈现，绝不只报最好看的那一个。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

from .schema import Case, Doc, entity_name

__all__ = [
    "Rubric",
    "LENIENT",
    "STRICT",
    "default_rubrics",
    "register_rule",
    "judge",
    "diagnose",
    "LAYER_MISS",
    "TARGET_MISS",
    "HIT",
]

HIT = "hit"
LAYER_MISS = "layer_miss"
TARGET_MISS = "target_miss"

Rule = Callable[[Doc, Case], bool]
RULES: dict[str, Rule] = {}


def register_rule(name: str) -> Callable[[Rule], Rule]:
    """注册一条判定规则，供 Rubric 按名引用。"""

    def deco(fn: Rule) -> Rule:
        RULES[name] = fn
        return fn

    return deco


@register_rule("lenient")
def _lenient(doc: Doc, case: Case) -> bool:
    """宽松：有 target 字段就比 target，没有就退化成「标题包含」。

    差异点刻意定在**结果自身有没有 target** 上，而不是层名上。
    早期版本按层名分派（给 l1 配 contains），结果是换个层命名规则
    （guide / faq / ref）就整体退化到严格口径，而人眼看不出来——
    指标看着还是那个数，只是解读完全变了。
    """
    if doc.target:
        return doc.target == case.expect_target
    hay = f"{doc.title}{doc.target}"
    return bool(case.expect_target) and case.expect_target in hay


@register_rule("strict")
def _strict(doc: Doc, case: Case) -> bool:
    """严格：有 target 比 target，没有就要求页面主实体完全相等。

    同名词页面（「玛莲妮亚的追忆」）在宽松口径下算命中「玛莲妮亚」，
    严格口径下不算。两套口径的差值就是可量化的虚高。
    """
    if doc.target:
        return doc.target == case.expect_target
    return doc.entity == case.expect_target


@register_rule("exact")
def _exact(doc: Doc, case: Case) -> bool:
    """规范名精确相等。

    用 `in` 会让「大树守卫」误判命中「龙装大树守卫」，
    这类子串误判在实体名上极常见，所以这里一律用等号。
    """
    return (doc.target or doc.entity) == case.expect_target


@register_rule("entity")
def _entity(doc: Doc, case: Case) -> bool:
    """页面主实体完全相等（去称号、去括号后缀）。"""
    return doc.entity == case.expect_target


@register_rule("title_exact")
def _title_exact(doc: Doc, case: Case) -> bool:
    """标题完全相等，不做任何归一化。最保守的口径。"""
    return doc.title.strip() == case.expect_target


@register_rule("any")
def _any(doc: Doc, case: Case) -> bool:
    """层对就算命中，不判目标。只用于「只判层」的题。"""
    return True


@dataclass(frozen=True)
class Rubric:
    """一套判定口径：每层用哪种规则。

    Attributes:
        name:        口径名，报告里作为列名
        by_layer:    layer 名 → 规则名，未列出的层用 default
        default:     兜底规则
    """

    name: str
    by_layer: Mapping[str, str] = field(default_factory=dict)
    default: str = "exact"

    def rule_for(self, layer: str) -> Rule:
        rule_name = self.by_layer.get(layer, self.default)
        if rule_name not in RULES:
            raise KeyError(
                f"口径 {self.name} 引用了未注册的规则 {rule_name!r}，"
                f"可用：{sorted(RULES)}"
            )
        return RULES[rule_name]


def _lite(layer: str, rule_name: str) -> Rubric:  # 便于构造单层口径
    return Rubric(name=layer, by_layer={layer: rule_name})


# 两套内置口径。名字刻意不用「宽松/严格」的中文直译，避免报告里
# 读者以为 strict 是"更正确"的那一个——它们只是两个不同的问题：
# 「排第一的是不是它本人」和「排第一的是不是它相关的页面」。
LENIENT = Rubric(name="lenient", by_layer={}, default="lenient")

STRICT = Rubric(name="strict", by_layer={}, default="strict")


def default_rubrics() -> list[Rubric]:
    """默认并列呈现的口径，顺序即报告列序。"""
    return [LENIENT, STRICT]


def judge(rubric: Rubric, doc: Doc, case: Case) -> bool:
    """单条结果在给定口径下是否命中。"""
    if doc.layer not in case.expect_layers:
        return False
    if case.layer_only:
        return True
    return rubric.rule_for(doc.layer)(doc, case)


def diagnose(rubric: Rubric, doc: Doc, case: Case) -> str:
    """没命中时说明是哪一环断了。

    区分「层判错」和「层对但目标错」很重要：前者是路由问题，
    后者是排序或实体识别问题，修的地方完全不同。
    """
    if doc.layer not in case.expect_layers:
        return LAYER_MISS
    if case.layer_only:
        return HIT
    return HIT if rubric.rule_for(doc.layer)(doc, case) else TARGET_MISS
