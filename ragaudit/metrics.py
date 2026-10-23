# -*- coding: utf-8 -*-
"""指标计算与运行结果的数据结构。

一次运行 = 一份评估集 × 一个检索器 × k。

结果里保留**逐条**的排名和检索到的前 k 条，而不是只留汇总数字。
这是整个工具的立场：只留总分的评测，事后无法回答
「掉了 0.3 分是哪几条坏掉的」，也就没法当回归测试用。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from .matchers import Rubric, diagnose, judge
from .schema import Case, Doc, Suite

__all__ = [
    "CaseOutcome",
    "RunResult",
    "Metrics",
    "GroupMetrics",
    "run_suite",
    "summarize",
]

# 保留在结果里的 Top-N 条概要。存全部没有意义，diff 只需要看头部
# 发生了什么；留 5 条跟默认 k 对齐，够定位也够小。
KEEP_TOP = 5


@dataclass
class CaseOutcome:
    """一道题在一次运行里的结果。"""

    id: str
    query: str
    group: str
    expect_layers: list[str]
    expect_target: str
    retrieved: list[dict[str, str]] = field(default_factory=list)
    ranks: dict[str, int] = field(default_factory=dict)
    diag: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "group": self.group,
            "expect_layers": self.expect_layers,
            "expect_target": self.expect_target,
            "retrieved": self.retrieved,
            "ranks": self.ranks,
            "diag": self.diag,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "CaseOutcome":
        return cls(
            id=d["id"],
            query=d["query"],
            group=d.get("group", "default"),
            expect_layers=list(d.get("expect_layers") or []),
            expect_target=d.get("expect_target", ""),
            retrieved=list(d.get("retrieved") or []),
            ranks=dict(d.get("ranks") or {}),
            diag=dict(d.get("diag") or {}),
        )


@dataclass
class RunResult:
    """一次完整运行。可序列化，用于跨版本 diff。"""

    suite_name: str
    k: int
    rubrics: list[str]
    cases: list[CaseOutcome]
    retriever: str = "unknown"
    created_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _dt.datetime.now().isoformat(timespec="seconds")

    def metrics(self, rubric: str) -> "Metrics":
        return summarize(self.cases, rubric)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "k": self.k,
            "rubrics": self.rubrics,
            "retriever": self.retriever,
            "created_at": self.created_at,
            "meta": self.meta,
            "cases": [c.to_dict() for c in self.cases],
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "RunResult":
        return cls(
            suite_name=d.get("suite_name", "suite"),
            k=int(d.get("k", 5)),
            rubrics=list(d.get("rubrics") or []),
            cases=[CaseOutcome.from_dict(c) for c in d.get("cases") or []],
            retriever=d.get("retriever", "unknown"),
            created_at=d.get("created_at", ""),
            meta=dict(d.get("meta") or {}),
        )


@dataclass
class GroupMetrics:
    n: int = 0
    hit1: int = 0
    hit5: int = 0

    @property
    def hit1_rate(self) -> float:
        return self.hit1 / self.n if self.n else 0.0

    @property
    def hit5_rate(self) -> float:
        return self.hit5 / self.n if self.n else 0.0


@dataclass
class Metrics:
    rubric: str = ""
    n: int = 0
    hit1: float = 0.0
    hit3: float = 0.0
    hit5: float = 0.0
    mrr: float = 0.0
    layer_acc: float = 0.0
    by_group: dict[str, GroupMetrics] = field(default_factory=dict)

    def to_row(self) -> dict[str, str]:
        return {
            "rubric": self.rubric,
            "Hit@1": f"{self.hit1:.1%}",
            "Hit@3": f"{self.hit3:.1%}",
            "Hit@5": f"{self.hit5:.1%}",
            "MRR": f"{self.mrr:.3f}",
            "层准确率@1": f"{self.layer_acc:.1%}",
        }


def summarize(cases: Sequence[CaseOutcome], rubric: str) -> Metrics:
    """按给定口径汇总逐条结果。"""
    n = len(cases)
    if n == 0:
        return Metrics(rubric=rubric)

    hit1 = hit3 = hit5 = 0
    mrr = 0.0
    layer_ok = 0
    by_group: dict[str, GroupMetrics] = {}

    for c in cases:
        rank = int(c.ranks.get(rubric, 0))
        g = by_group.setdefault(c.group, GroupMetrics())
        g.n += 1

        if rank:
            mrr += 1.0 / rank
            if rank == 1:
                hit1 += 1
                g.hit1 += 1
            if rank <= 3:
                hit3 += 1
            if rank <= 5:
                hit5 += 1
                g.hit5 += 1

        # 层准确率与命中判定分开统计：层判错比排错更严重，
        # 但两者混在一个数里就看不出来了。
        if c.retrieved:
            top_layer = c.retrieved[0].get("layer", "")
            if top_layer in c.expect_layers:
                layer_ok += 1

    return Metrics(
        rubric=rubric,
        n=n,
        hit1=hit1 / n,
        hit3=hit3 / n,
        hit5=hit5 / n,
        mrr=mrr / n,
        layer_acc=layer_ok / n,
        by_group=by_group,
    )


def run_suite(
    suite: Suite,
    retriever: Any,
    k: int = 5,
    rubrics: Sequence[Rubric] | None = None,
    top_n: int = KEEP_TOP,
    retriever_name: str = "",
) -> RunResult:
    """跑一次评估。

    Args:
        suite: 评估集
        retriever: 任何接收 (query, k) 并返回结果列表的可调用对象。
                   结果可以是 dict，也可以是带 layer/target/title 属性的对象。
        k: 取前 k 条判定
        rubrics: 判定口径，默认 [lenient, strict]
        top_n: 结果里保留前 n 条的概要
        retriever_name: 报告里显示的名字
    """
    from .matchers import default_rubrics

    rubrics = list(rubrics or default_rubrics())
    outcomes: list[CaseOutcome] = []

    for case in suite.cases:
        raw = retriever(case.query, k) or []
        docs = [Doc.from_any(r) for r in raw]
        top = docs[:k]

        ranks: dict[str, int] = {}
        diags: dict[str, str] = {}
        for rb in rubrics:
            rank = 0
            first_diag = ""
            for i, d in enumerate(top, 1):
                if judge(rb, d, case):
                    rank = i
                    break
                if not first_diag:
                    first_diag = diagnose(rb, d, case)
            ranks[rb.name] = rank
            if rank:
                diags[rb.name] = "hit"
            elif not top:
                # 一条都没检索到，跟前两条失败原因不同：
                # 不是排错了，是压根没召回，修的地方在索引或过滤条件。
                diags[rb.name] = "empty"
            else:
                diags[rb.name] = first_diag or "miss"

        outcomes.append(
            CaseOutcome(
                id=case.id,
                query=case.query,
                group=case.group,
                expect_layers=list(case.expect_layers),
                expect_target=case.expect_target,
                retrieved=[
                    {
                        "layer": d.layer,
                        "target": d.target,
                        "title": d.title,
                    }
                    for d in docs[:top_n]
                ],
                ranks=ranks,
                diag=diags,
            )
        )

    return RunResult(
        suite_name=suite.name,
        k=k,
        rubrics=[rb.name for rb in rubrics],
        cases=outcomes,
        retriever=retriever_name or getattr(retriever, "__name__", "retriever"),
        meta={"about": suite.about} if suite.about else {},
    )
