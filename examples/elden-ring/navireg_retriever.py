# -*- coding: utf-8 -*-
"""把 NaviRAG 的**真实线上检索器**接进 RAGAudit。

这是仓库里唯一一个需要第三方依赖的文件（chromadb + sentence-transformers + torch）。
`ragaudit` 包本身仍然零依赖——审计工具自己不能被依赖污染，
所以重依赖只存在于「被测系统」这一侧，而且只在你要跑真实案例时才需要装。

用法（Windows 示例）::

    set NAVIRAG_HOME=D:\\PROJECT\\NaviRAG
    set PYTHONPATH=examples\\elden-ring
    python -m ragaudit run -s examples/elden-ring/suite.json -r navireg_retriever:search

    # 难度画像带上 NaviRAG 自己的别名表，俗称类才不会被并进 implicit
    python -m ragaudit run -s examples/elden-ring/suite.json -r navireg_retriever:search \
        --alias %NAVIRAG_HOME%\\data\\elden_ring\\aliases.json

NaviRAG 一侧需要：已建好的 `.vectorstore`（本机 8428 条）和本地 embedding 模型。
没有的话先跑一次 `python -m core.retriever "任意问句"`，它会自动建索引。

对外只暴露 `f(query, k) -> list[dict]`，字段是 `layer` / `target` / `title`——
RAGAudit 不关心检索器内部怎么分层、怎么加权，这也是它能审计别人系统的前提。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# 必须赶在 import torch 之前锁线程：多线程 BLAS 的浮点归约顺序不确定，
# 同一条 query 在不同进程里的 embedding 会有微小差异，HNSW 候选边界上的
# 排序就会翻转——报告于是不可复现。NaviRAG 自己的评估脚本也做了同样的处理。
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_HERE = Path(__file__).resolve().parent
_STATE: dict[str, Any] = {}


def _navira_home() -> Path:
    """定位 NaviRAG 源码目录：环境变量优先，其次找同级的 NaviRAG。"""
    cands: list[Path] = []
    env = os.environ.get("NAVIRAG_HOME")
    if env:
        cands.append(Path(env))
    # examples/elden-ring/ → 上两级是仓库根，同级目录里找 NaviRAG
    cands.append(_HERE.parents[1].parent / "NaviRAG")
    for c in cands:
        if (c / "core" / "retriever.py").is_file():
            return c.resolve()
    tried = "、".join(str(c) for c in cands)
    raise RuntimeError(
        "找不到 NaviRAG 源码目录。请设置环境变量 NAVIRAG_HOME 指向 NaviRAG 仓库根。"
        f"已尝试：{tried}"
    )


def _load() -> dict[str, Any]:
    """懒加载：索引与模型只建一次，85 条题共用。"""
    if _STATE:
        return _STATE

    home = _navira_home()
    sys.path.insert(0, str(home))

    from core.retriever import build_index, load_zh2en  # noqa: PLC0415
    from core.retriever import search as navi_search  # noqa: PLC0415

    _client, col, model = build_index()
    _STATE.update(
        navi_search=navi_search,
        col=col,
        model=model,
        zh2en=load_zh2en(),
        home=home,
        n=col.count(),
    )
    return _STATE


def _norm(hits: list[dict]) -> list[dict]:
    """NaviRAG 的 {meta: {...}} → RAGAudit 的 {layer,target,title}。

    L1 wiki 条目没有 target 字段，只能拿标题当实体名；这正是
    「宽松口径能命中同名词页面、严格口径不能」的来源，不是归一化时该抹平的差异。
    """
    out = []
    for h in hits:
        m = h.get("meta") or {}
        out.append({
            "layer": str(m.get("layer") or "").lower(),
            "target": m.get("target") or "",
            # title_zh 优先：中文名是判定用的实体名，英文 title 只是页面标识
            "title": m.get("title_zh") or m.get("title") or "",
            "score": h.get("score"),
            "id": h.get("id") or "",
            "raw_layer_title": m.get("title") or "",
        })
    return out


# ---------------------------------------------------------------- 线上方案

def search(query: str, k: int = 5) -> list[dict]:
    """NaviRAG 线上实际跑的那条链路：术语增强 + 三路分层 + 实体硬置顶 + 别名表。"""
    st = _load()
    hits, _diag = st["navi_search"](
        st["col"], st["model"], query, k=k, zh2en=st["zh2en"], entity_boost=True,
    )
    return _norm(hits)


# ---------------------------------------------------------------- 消融变体
# 每个函数只关掉一个部件，其余全部保持线上配置。归因能成立的前提是
# 「只改一个变量」——手工做这件事最容易忘，所以固化成函数。

def search_no_alias(query: str, k: int = 5) -> list[dict]:
    """关掉手工别名表：俗称提问退化成纯语义匹配。"""
    st = _load()
    hits, _diag = st["navi_search"](
        st["col"], st["model"], query, k=k, zh2en=st["zh2en"],
        entity_boost=True, use_alias=False,
    )
    return _norm(hits)


def search_no_enhance(query: str, k: int = 5) -> list[dict]:
    """关掉官方术语表查询增强（玛莲妮亚 → 玛莲妮亚 Malenia）。"""
    st = _load()
    hits, _diag = st["navi_search"](
        st["col"], st["model"], query, k=k, zh2en=None, entity_boost=True,
    )
    return _norm(hits)


def search_no_entity_boost(query: str, k: int = 5) -> list[dict]:
    """关掉实体硬置顶，只保留分层加权 + 向量相似度。"""
    st = _load()
    hits, _diag = st["navi_search"](
        st["col"], st["model"], query, k=k, zh2en=st["zh2en"], entity_boost=False,
    )
    return _norm(hits)


def search_pure_vector(query: str, k: int = 5) -> list[dict]:
    """最朴素的对照组：一次向量查询、不分层、不增强、不过滤。

    任何 RAG 教程的第一版都长这样。它存在的意义是给出「不用分层设计会怎样」
    的基线——没有这条基线，分层带来的提升只是一句无法验证的话。
    """
    st = _load()
    emb = st["model"].encode([query], normalize_embeddings=True)[0].tolist()
    res = st["col"].query(query_embeddings=[emb], n_results=k,
                          include=["metadatas"])
    out = []
    for m in res["metadatas"][0]:
        out.append({
            "layer": str(m.get("layer") or "").lower(),
            "target": m.get("target") or "",
            "title": m.get("title_zh") or m.get("title") or "",
        })
    return out
