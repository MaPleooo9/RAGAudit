# -*- coding: utf-8 -*-
"""消融变体定义。

用法：
    python -m ragaudit ablate -s suite.json -v variants.py
"""

from __future__ import annotations

from retriever import search_v1, search_v2

VARIANTS = [
    ("full（含别名）", search_v1, "线上方案"),
    ("full −alias（关俗称）", search_v2, "验证别名表的净贡献"),
]
