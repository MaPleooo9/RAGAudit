# -*- coding: utf-8 -*-
"""两次运行的逐条对比。

只报总分的评测撑不起回归测试。总分从 94.1% 掉到 93.8% 时，
真正要回答的是「哪几条坏了、坏在哪一环」，否则改下一个版本只能靠猜。

这里按题目 id 对齐（不是按序号，避免插题导致整体错位），
把结果分成六类，其中两类最容易被忽略：

    removed  这次运行里消失的题 —— 悄悄删掉难题也是能涨分的
    added    这次新加的题 —— 新题多为难例，会拉低总分，别误判为退步
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .metrics import CaseOutcome, RunResult

__all__ = [
    "Entry",
    "DiffResult",
    "diff_runs",
    "FIXED",
    "BROKE",
    "IMPROVED",
    "WORSENED",
    "UNCHANGED_HIT",
    "UNCHANGED_MISS",
    "REMOVED",
    "ADDED",
]

FIXED = "fixed"
BROKE = "broke"
IMPROVED = "improved"
WORSENED = "worsened"
UNCHANGED_HIT = "unchanged_hit"
UNCHANGED_MISS = "unchanged_miss"
REMOVED = "removed"
ADDED = "added"

_LABEL = {
    FIXED: "修好",
    BROKE: "弄坏",
    IMPROVED: "排名前移",
    WORSENED: "排名后退",
    UNCHANGED_HIT: "仍然命中",
    UNCHANGED_MISS: "仍然未命中",
    REMOVED: "本次移除",
    ADDED: "本次新增",
}


@dataclass
class Entry:
    """一条变化记录。"""

    id: str
    query: str
    group: str
    status: str
    before_rank: int = 0
    after_rank: int = 0
    before_diag: str = ""
    after_diag: str = ""
    expect_target: str = ""
    top_before: str = ""
    top_after: str = ""

    @property
    def label(self) -> str:
        return _LABEL.get(self.status, self.status)

    def shift_hint(self) -> str:
        """推断这一条是从哪个环节坏的，报告里直接给修的方向。"""
        if self.status == BROKE:
            if self.after_diag == "layer_miss" and self.before_diag != "layer_miss":
                return "层路由：Top1 的层变了"
            if self.before_diag == "layer_miss" and self.after_diag == "target_miss":
                return "层对了但目标排错：排序权重问题"
            return "排序：正确结果掉出 Top-K"
        if self.status == WORSENED:
            return f"仍命中但排名下滑 {self.before_rank}→{self.after_rank}"
        return ""


@dataclass
class DiffResult:
    rubric: str
    fixed: list[Entry] = field(default_factory=list)
    broke: list[Entry] = field(default_factory=list)
    improved: list[Entry] = field(default_factory=list)
    worsened: list[Entry] = field(default_factory=list)
    removed: list[Entry] = field(default_factory=list)
    added: list[Entry] = field(default_factory=list)
    unchanged_hit: int = 0
    unchanged_miss: int = 0
    before_n: int = 0
    after_n: int = 0
    before_hit1: float = 0.0
    after_hit1: float = 0.0

    @property
    def net(self) -> int:
        """净变化条数（修好 − 弄坏）。"""
        return len(self.fixed) - len(self.broke)

    @property
    def delta(self) -> float:
        """Hit@1 变化，单位为百分点。"""
        return (self.after_hit1 - self.before_hit1) * 100

    @property
    def suspicious(self) -> bool:
        """涨分但删了题，或者题目数量减少——需要人工确认不是刷分。"""
        return bool(self.removed)


def _top_summary(c: CaseOutcome) -> str:
    if not c.retrieved:
        return "-"
    d = c.retrieved[0]
    name = d.get("target") or d.get("title") or "?"
    lay = d.get("layer") or "-"
    return f"{lay}/{name}"


def diff_runs(
    baseline: RunResult,
    current: RunResult,
    rubric: str | None = None,
) -> DiffResult:
    """对比两次运行。

    Args:
        baseline: 旧版本结果
        current: 新版本结果
        rubric: 用哪套口径对比，默认两边的第一套（通常是 lenient）
    """
    rb = rubric or (baseline.rubrics[0] if baseline.rubrics else "lenient")

    before = {c.id: c for c in baseline.cases}
    after = {c.id: c for c in current.cases}

    out = DiffResult(
        rubric=rb,
        before_n=len(before),
        after_n=len(after),
        before_hit1=_hit1(baseline, rb),
        after_hit1=_hit1(current, rb),
    )

    for cid, b in before.items():
        a = after.get(cid)
        if a is None:
            out.removed.append(Entry(
                id=cid, query=b.query, group=b.group, status=REMOVED,
                before_rank=int(b.ranks.get(rb, 0)),
                before_diag=b.diag.get(rb, ""),
                expect_target=b.expect_target,
                top_before=_top_summary(b),
            ))
            continue
        _classify(out, b, a, rb)
    for cid, a in after.items():
        if cid not in before:
            out.added.append(Entry(
                id=cid, query=a.query, group=a.group, status=ADDED,
                after_rank=int(a.ranks.get(rb, 0)),
                after_diag=a.diag.get(rb, ""),
                expect_target=a.expect_target,
                top_after=_top_summary(a),
            ))

    return out


def _hit1(run: RunResult, rubric: str) -> float:
    n = len(run.cases)
    if not n:
        return 0.0
    return sum(1 for c in run.cases if int(c.ranks.get(rubric, 0)) == 1) / n


def _classify(out: DiffResult, b: CaseOutcome, a: CaseOutcome, rb: str) -> None:
    """把一条题归入六类之一，直接写进 out。"""
    br = int(b.ranks.get(rb, 0))
    ar = int(a.ranks.get(rb, 0))
    entry = Entry(
        id=a.id,
        query=a.query,
        group=a.group,
        status=UNCHANGED_HIT,
        before_rank=br,
        after_rank=ar,
        before_diag=b.diag.get(rb, ""),
        after_diag=a.diag.get(rb, ""),
        expect_target=a.expect_target,
        top_before=_top_summary(b),
        top_after=_top_summary(a),
    )

    if not br and ar:
        entry.status = FIXED
        out.fixed.append(entry)
    elif br and not ar:
        entry.status = BROKE
        out.broke.append(entry)
    elif br and ar and ar < br:
        entry.status = IMPROVED
        out.improved.append(entry)
    elif br and ar and ar > br:
        entry.status = WORSENED
        out.worsened.append(entry)
    elif br and ar:
        out.unchanged_hit += 1
    else:
        out.unchanged_miss += 1
