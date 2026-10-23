# -*- coding: utf-8 -*-
"""NaviRAG 真实检索器的消融变体。

每个变体只关掉一个部件，其余保持线上配置——归因成立的唯一前提。
参照系是第一个（线上方案），ΔHit@1 为相对它的变化。

用法::

    set NAVIRAG_HOME=D:\\PROJECT\\NaviRAG
    set PYTHONPATH=examples\\elden-ring
    python -m ragaudit ablate -s examples/elden-ring/suite.json -v examples/elden-ring/variants.py
"""

from __future__ import annotations

from navireg_retriever import (
    search,
    search_no_alias,
    search_no_enhance,
    search_no_entity_boost,
    search_pure_vector,
)

VARIANTS = [
    ("full（线上）", search, "术语增强 + 三路分层 + 实体置顶 + 别名表"),
    ("full −alias（关俗称表）", search_no_alias, "手工别名表的净贡献"),
    ("full −enhance（关术语增强）", search_no_enhance, "该模块是否值得继续保留"),
    ("layered −entity（关实体置顶）", search_no_entity_boost, "硬规则的净贡献"),
    ("pure-vector（不分层）", search_pure_vector, "单路向量，教程起点"),
]
