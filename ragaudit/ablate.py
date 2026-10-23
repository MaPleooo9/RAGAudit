# -*- coding: utf-8 -*-
"""消融矩阵与归因。

一个 94% 的 Hit@1 说明不了任何事，除非你能回答：
**这 94% 里，有多少是规则捞的、多少是向量排的、多少是手工别名表顶上来的？**

做法很朴素：把某个部件关掉，再跑一遍，差值就是它的贡献。
问题在于手工做这件事很容易出错——忘了固定其他变量、在不同子集上比、
口径混用。所以把它做成代码。

两个必须遵守的约束（写进 API 而不是写进文档，因为写进文档没人看）：

    1. 所有变体必须在同一份评估集、同一个 k、同一套口径下跑
    2. 涉及「定位到具体条目」的变体，必须在所有变体都能给出结果的子集上比
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .metrics import RunResult, run_suite
from .schema import Suite

__all__ = ["Variant", "AblationRow", "AblationResult", "ablate", "contribution"]

Retriever = Callable[[str, int], Sequence]


@dataclass
class Variant:
    """一个消融变体。

    name 建议带上「关掉了什么」，因为报告里的每一行都靠它读：
    `full` / `full -alias` / `pure-vector` 比 `v1 v2 v3` 有用得多。
    """

    name: str
    retriever: Retriever
    note: str = ""


@dataclass
class AblationRow:
    name: str
    hit1: float
    hit3: float
    hit5: float
    mrr: float
    layer_acc: float
    note: str = ""
    d_hit1: float = 0.0     # 相对参照变体的变化（百分点）
    d_mrr: float = 0.0

    def to_row(self) -> dict[str, str]:
        sign = "+" if self.d_hit1 >= 0 else ""
        return {
            "变体": self.name,
            "Hit@1": f"{self.hit1:.1%}",
            "ΔHit@1": f"{sign}{self.d_hit1:.1f}",
            "Hit@5": f"{self.hit5:.1%}",
            "MRR": f"{self.mrr:.3f}",
            "层准确率": f"{self.layer_acc:.1%}",
            "说明": self.note,
        }


@dataclass
class AblationResult:
    rubric: str
    k: int
    n: int
    subset: str
    rows: list[AblationRow] = field(default_factory=list)
    reference: str = ""

    def ranked(self) -> list[AblationRow]:
        """按对参照变体的影响从大到小排。

        正数 = 关掉它之后变好了（说明这个部件是负收益），
        负数 = 关掉它变差了（说明它在起作用）。
        """
        return sorted(self.rows, key=lambda r: -abs(r.d_hit1))

    def best(self) -> AblationRow | None:
        return max(self.rows, key=lambda r: (r.hit1, r.mrr)) if self.rows else None


def ablate(
    suite: Suite,
    variants: Iterable[Variant],
    k: int = 5,
    rubric: str = "lenient",
    layers: Iterable[str] | None = None,
    reference: str = "",
    top_n: int = 3,
) -> AblationResult:
    """跑消融矩阵。

    Args:
        suite: 评估集
        variants: 变体列表，第一个默认为参照系
        k: Top-K
        rubric: 用哪套口径比较（归因只看一套，否则口径混用会让归因失效）
        layers: 只在这些期望层上比较。给「纯规则」这类定位不到某些层的
                变体时必须传，否则它在全集上比会显得很蠢，结论是假的
        reference: 参照变体名，默认为第一个
        top_n: 保留每条结果的前 n 条（归因不需要看太深）
    """
    from .matchers import Rubric, default_rubrics

    vs = list(variants)
    if not vs:
        raise ValueError("至少需要一个变体")

    rubrics = {r.name: r for r in default_rubrics()}
    rb: Rubric = rubrics.get(rubric) or Rubric(name=rubric)

    sub = suite.only(layers) if layers else suite
    if len(sub) == 0:
        raise ValueError(f"在层 {list(layers or [])} 上筛不出任何用例，无法比较")

    ref_name = reference or vs[0].name
    ref_metrics = None
    rows: list[AblationRow] = []

    for v in vs:
        run: RunResult = run_suite(
            sub, v.retriever, k=k, rubrics=[rb], top_n=top_n,
            retriever_name=v.name,
        )
        m = run.metrics(rb.name)
        if v.name == ref_name:
            ref_metrics = m
        rows.append(AblationRow(
            name=v.name, hit1=m.hit1, hit3=m.hit3, hit5=m.hit5,
            mrr=m.mrr, layer_acc=m.layer_acc, note=v.note,
        ))

    for r in rows:
        if ref_metrics is not None:
            r.d_hit1 = (r.hit1 - ref_metrics.hit1) * 100
            r.d_mrr = r.mrr - ref_metrics.mrr

    return AblationResult(
        rubric=rb.name, k=k, n=len(sub),
        subset=sub.name, rows=rows, reference=ref_name,
    )


def contribution(full: AblationRow, without: AblationRow) -> dict[str, float]:
    """某个部件的净贡献。

    正值表示它有用（关掉会掉），负值表示它是负收益（关掉反而更好）。
    负收益的模块在工程上应该考虑直接删掉而不是保留——
    「没被证明有用」和「有害」之间，多数团队会选前者作为保留理由，
    但数据说它有害的时候，保留就是在给链路增加维护成本。
    """
    return {
        "hit1": (full.hit1 - without.hit1) * 100,
        "hit5": (full.hit5 - without.hit5) * 100,
        "mrr": full.mrr - without.mrr,
    }
