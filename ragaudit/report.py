# -*- coding: utf-8 -*-
"""报告渲染。

报告的第一屏必须是**结论**，而不是一堆表。
所以顺序固定为：口径差值 → 难度画像 → 分组 → 失败清单 → 消融 → diff。

理由很实在：评委和同事只会读完第一屏。把「你的分数虚高了多少」
放在最前面，比把 Hit@1 放大加粗有用。
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .ablate import AblationResult
from .diff import DiffResult
from .metrics import Metrics, RunResult
from .profile import (
    LEAK_ALIAS,
    LEAK_EXPLICIT,
    LEAK_IMPLICIT,
    LEAK_PARTIAL,
    Profile,
)

__all__ = ["render_report", "md_table"]

_LEAK_LABEL = {
    LEAK_EXPLICIT: "显式指名",
    LEAK_ALIAS: "俗称",
    LEAK_PARTIAL: "部分同名",
    LEAK_IMPLICIT: "不含实体",
}


def md_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    """渲染 markdown 表格。空表返回空串，避免出现孤立表头。"""
    body = [list(r) for r in rows]
    if not body:
        return ""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in body:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def render_report(
    run: RunResult,
    rubrics: Sequence[str] | None = None,
    profile: Profile | None = None,
    ablation: AblationResult | None = None,
    diff: DiffResult | None = None,
    title: str = "检索评测审计报告",
) -> str:
    """生成完整的 markdown 报告。"""
    # 口径允许传 Rubric 对象或名称，两种都收：调用方常常手里已经有对象了
    rubrics = [getattr(r, "name", str(r)) for r in (rubrics or run.rubrics)]
    metrics = {rb: run.metrics(rb) for rb in rubrics}
    main = metrics[rubrics[0]] if rubrics else Metrics()

    L: list[str] = [f"# {title}\n"]
    L.append(
        f"- 评估集：**{run.suite_name}**（{len(run.cases)} 条，"
        f"{len({c.group for c in run.cases})} 组）\n"
        f"- 判定深度：Top-{run.k}\n"
        f"- 检索方案：`{run.retriever}`\n"
        f"- 运行时间：{run.created_at}\n"
        f"- 判定口径：{', '.join(f'`{r}`' for r in rubrics)}\n"
    )

    # ---- 第一屏：口径差值 ----
    if len(rubrics) >= 2:
        lo, hi = metrics[rubrics[0]], metrics[rubrics[1]]
        gap = (lo.hit1 - hi.hit1) * 100
        L.append("## 结论\n")
        L.append(
            f"**Hit@1 在 `{rubrics[0]}` 口径下 {lo.hit1:.1%}，"
            f"在 `{rubrics[1]}` 口径下 {hi.hit1:.1%}，"
            f"相差 {gap:.1f} 个百分点。**\n"
        )
        if gap >= 3:
            L.append(
                f"这个差值不算小，说明有相当一部分命中依赖宽松匹配"
                f"（同名词页面、标题包含等）。对外引用成绩时应该说明用的是哪套口径，"
                f"否则容易被读成 {lo.hit1:.1%}。\n"
            )
        else:
            L.append(
                "两套口径差距在噪声范围内，说明命中主要靠精确匹配，"
                "这个分数不容易被质疑为口径虚高。\n"
            )

    # ---- 指标表 ----
    L.append("## 整体指标\n")
    L.append(md_table(
        ["口径", "Hit@1", "Hit@3", "Hit@5", "MRR", "层准确率@1"],
        [[f"`{rb}`", f"{m.hit1:.1%}", f"{m.hit3:.1%}", f"{m.hit5:.1%}",
          f"{m.mrr:.3f}", f"{m.layer_acc:.1%}"] for rb, m in metrics.items()],
    ))

    # ---- 难度画像 ----
    if profile is not None:
        L.append("\n## 难度画像\n")
        L.append(
            f"自动判定每道题的信息泄漏程度，不依赖人工分组。"
            f"**显式指名占 {profile.leak_rate:.0%}**，真正有难度的占 "
            f"{profile.hard_rate:.0%}。\n"
        )
        L.append(
            "显式指名的题，问句里直接写着答案实体名，实体匹配就能命中，"
            "测不出语义检索能力；`不含实体` 才是真正考验检索的题型。\n"
        )
        L.append(md_table(
            ["泄漏等级", "含义", "条数", "占比"],
            [[_LEAK_LABEL.get(k, k), _descr(k), n, f"{n / profile.n:.0%}"]
             for k, n in sorted(profile.by_leak.items(),
                                key=lambda x: -x[1])],
        ))
        if profile.by_group_leak:
            L.append("\n按分组的泄漏分布：\n")
            rows = []
            for g, cnt in profile.by_group_leak.items():
                total = sum(cnt.values())
                hard = sum(cnt.get(k, 0) for k in (LEAK_ALIAS, LEAK_PARTIAL, LEAK_IMPLICIT))
                rows.append([g, total, cnt.get(LEAK_EXPLICIT, 0), hard,
                             f"{hard / total:.0%}" if total else "0%"])
            L.append(md_table(
                ["分组", "条数", "显式指名", "有难度", "难度占比"], rows))

    # ---- 分组表现 ----
    if main.by_group:
        L.append(f"\n## 分组表现（`{rubrics[0]}`）\n")
        L.append(md_table(
            ["分组", "条数", "Hit@1", "Hit@5"],
            [[g, s.n, f"{s.hit1_rate:.0%}", f"{s.hit5_rate:.0%}"]
             for g, s in sorted(main.by_group.items(), key=lambda x: -x[1].n)],
        ))

    # ---- 失败清单 ----
    misses = [c for c in run.cases if not int(c.ranks.get(rubrics[0], 0))]
    if misses:
        by_diag: dict[str, int] = {}
        for c in misses:
            d = c.diag.get(rubrics[0], "miss")
            by_diag[d] = by_diag.get(d, 0) + 1
        L.append(f"\n## 未命中 {len(misses)} 条\n")
        L.append(
            f"`layer_miss`（层路由错）= {by_diag.get('layer_miss', 0)} 条，"
            f"`target_miss`（层对但排序错）= {by_diag.get('target_miss', 0)} 条，"
            f"`empty`（一条都没召回）= {by_diag.get('empty', 0)} 条。"
            f"三者修的地方完全不同：分别对应路由规则、排序权重、索引与过滤条件。\n"
        )
        L.append(md_table(
            ["提问", "期望", "Top1 实际", "失败环节"],
            [[_cell(c.query), f"{'/'.join(c.expect_layers)}/{c.expect_target or '任意'}",
              _cell(_top(c)), c.diag.get(rubrics[0], "-")]
             for c in misses[:20]],
        ))
        if len(misses) > 20:
            L.append(f"\n（仅显示前 20 条，共 {len(misses)} 条）")

    # ---- 消融 ----
    if ablation is not None:
        L.append("\n## 消融与归因\n")
        L.append(
            f"在 {ablation.n} 条可比子集上比较，`k={ablation.k}`，"
            f"`{ablation.rubric}` 口径，参照系 `{ablation.reference}`。\n"
        )
        L.append(md_table(
            ["变体", "Hit@1", "ΔHit@1", "Hit@5", "MRR", "层准确率", "说明"],
            [[r.name, f"{r.hit1:.1%}",
              f"{'+' if r.d_hit1 >= 0 else ''}{r.d_hit1:.1f}",
              f"{r.hit5:.1%}", f"{r.mrr:.3f}", f"{r.layer_acc:.1%}", r.note]
             for r in ablation.rows],
        ))
        neg = [r for r in ablation.rows if r.d_hit1 > 0.5 and r.name != ablation.reference]
        if neg:
            L.append(
                "\n**关掉之后反而变好的部件："
                + "、".join(f"`{r.name}`（+{r.d_hit1:.1f}pp）" for r in neg)
                + "**。这类模块要么是负收益，要么其价值无法被当前评估集证明，"
                "两者都该在下一版里重新评估是否保留。\n"
            )

    # ---- diff ----
    if diff is not None:
        L.append("\n## 回归对比\n")
        L.append(
            f"`{diff.before_n}` 条 → `{diff.after_n}` 条，"
            f"Hit@1 {diff.before_hit1:.1%} → {diff.after_hit1:.1%} "
            f"（{diff.delta:+.1f}pp）。"
            f"修好 {len(diff.fixed)} 条，弄坏 {len(diff.broke)} 条，"
            f"净 {diff.net:+d} 条。\n"
        )
        if diff.suspicious:
            L.append(
                f"> 注意：本次运行移除了 {len(diff.removed)} 条题目。"
                f"如果移除的是难例，涨分不代表检索变好。\n"
            )
        if diff.broke:
            L.append("### 退化清单\n")
            L.append(md_table(
                ["提问", "期望", "之前", "现在", "归因"],
                [[_cell(e.query), e.expect_target or "任意",
                  f"rank {e.before_rank}", "未命中",
                  e.shift_hint() or e.after_diag] for e in diff.broke[:20]],
            ))
        if diff.fixed:
            L.append("\n### 修好的\n")
            L.append(md_table(
                ["提问", "期望", "现在排名"],
                [[_cell(e.query), e.expect_target or "任意", f"rank {e.after_rank}"]
                 for e in diff.fixed[:20]],
            ))
        if diff.added:
            L.append(f"\n本次新增 {len(diff.added)} 条题目，"
                     f"新题多为难例，Hit@1 下降不必然是退步。\n")

    L.append("\n---\n")
    L.append("_由 RAGAudit 生成。指标的解读口径见 `docs/metrics.md`。_")
    return "\n".join(L) + "\n"


def _descr(level: str) -> str:
    return {
        LEAK_EXPLICIT: "问句直接写着答案实体名",
        LEAK_ALIAS: "问句用的是登记过的俗称",
        LEAK_PARTIAL: "问句含同名子串，易指向错误实体",
        LEAK_IMPLICIT: "整句不含实体名，只能靠语义",
    }.get(level, "-")


def _cell(s: str, n: int = 28) -> str:
    """表格里的长文本会撑破排版，按字宽截断。"""
    s = (s or "").replace("|", "\\|")
    return s if len(s) <= n else s[: n - 1] + "…"


def _top(c) -> str:
    if not c.retrieved:
        return "-"
    d = c.retrieved[0]
    return f"{d.get('layer') or '-'}/" + (d.get("target") or d.get("title") or "?")
