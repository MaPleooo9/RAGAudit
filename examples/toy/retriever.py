# -*- coding: utf-8 -*-
"""演示用检索器：纯标准库，不依赖任何向量库。

目的是让任何人 clone 下来就能在 3 秒内看到工具在跑，
而不是先装 2GB 的 embedding 模型。真实项目请换成自己的检索器，
只要它满足 `f(query, k) -> list[dict]` 并且结果里带 layer / title。

两个变体是为了演示同一件事：
    search_v1  带俗称别名表
    search_v2  把别名表关掉
关掉之后，口语描述类题目会退化——这正是「某个部件到底贡献了多少」
要回答的问题，也是 diff 能抓住的回归。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PUNCT = re.compile(r"[\s，。？！、,.?!~～:：;；\"'“”‘’()（）\[\]【】/\\-]+")

# 俗称 → 规范名。真实项目里这张表通常是最脆弱的一环：
# 新实体的俗称没登记，表现立刻退化回纯字面匹配。
ALIASES: dict[str, list[str]] = {
    "离线部署": ["没网", "无外网", "断网", "内网"],
    "许可证更换": ["授权", "续期", "过期"],
    "数据导出": ["导出", "备份出来"],
    "试用期多久": ["免费版", "试用", "免费"],
    "支持哪些数据库": ["mysql", "数据库", "达梦"],
    "配额限制": ["限流", "qps", "多少次", "并发"],
    "鉴权方式": ["鉴权", "token", "认证"],
    "升级迁移": ["升级", "旧版本", "迁移"],
}


def _norm(s: str) -> str:
    return _PUNCT.sub("", (s or "").lower())


def _bigrams(s: str) -> set[str]:
    s = _norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}


def _load_corpus() -> list[dict]:
    data = json.loads((_HERE / "corpus.json").read_text(encoding="utf-8"))
    return data["docs"]


_DOCS = _load_corpus()


def _rank(query: str, k: int, use_alias: bool) -> list[dict]:
    q = _norm(query)
    qg = _bigrams(query)
    scored: list[tuple[float, dict]] = []

    for d in _DOCS:
        hay = f"{d['title']}{d['text']}"
        score = float(len(qg & _bigrams(hay)))

        if use_alias:
            for alias in ALIASES.get(d.get("target", ""), []):
                if _norm(alias) in q:
                    score += 5.0

        # 标题命中的权重高于正文：标题就是实体名本身
        if _norm(d["title"]) and _norm(d["title"]) in q:
            score += 3.0

        scored.append((score, d))

    scored.sort(key=lambda x: -x[0])
    return [
        {"layer": d["layer"], "target": d.get("target", ""), "title": d["title"],
         "score": s, "id": d["id"]}
        for s, d in scored[:k] if s > 0
    ]


def search_v1(query: str, k: int = 5) -> list[dict]:
    """带俗称别名表的版本（线上方案）。"""
    return _rank(query, k, use_alias=True)


def search_v2(query: str, k: int = 5) -> list[dict]:
    """把别名表关掉的版本。用来演示消融与回归检测。"""
    return _rank(query, k, use_alias=False)
