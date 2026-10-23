# -*- coding: utf-8 -*-
"""一键演示：跑分 + 自检 + 消融 + 回归对比。

    python examples/toy/run_demo.py

输出写在 examples/toy/out/ 下。全程只用标准库，无需安装任何依赖。
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from ragaudit.ablate import Variant, ablate  # noqa: E402
from ragaudit.diff import diff_runs  # noqa: E402
from ragaudit.metrics import run_suite  # noqa: E402
from ragaudit.profile import lint, profile  # noqa: E402
from ragaudit.report import md_table, render_report  # noqa: E402
from ragaudit.schema import load_suite  # noqa: E402

sys.path.insert(0, str(HERE))
from retriever import ALIASES, search_v1, search_v2  # noqa: E402

OUT = HERE / "out"


def title(s: str) -> None:
    print(f"\n{'=' * 60}\n{s}\n{'=' * 60}")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    suite = load_suite(HERE / "suite.json")
    alias_map = {a: t for t, alist in ALIASES.items() for a in alist}

    # ---- 1. 先查题，再查分 ----
    title("1. 评估集自检（先查题）")
    prof = profile(suite, alias_map)
    print(f"{len(suite)} 条题 / {len(suite.groups)} 组")
    print(f"显式指名 {prof.leak_rate:.0%}，有难度 {prof.hard_rate:.0%}")
    print(md_table(["泄漏等级", "条数"],
                   [[k, v] for k, v in sorted(prof.by_leak.items(), key=lambda x: -x[1])]))
    issues = lint(suite, alias_map)
    if issues:
        print("\n自检发现：")
        for it in issues:
            print(f"  - {it}")
    else:
        print("\n自检未发现问题。")

    # ---- 2. 跑分 ----
    title("2. 跑分：两个版本并列")
    run_v1 = run_suite(suite, search_v1, k=5, retriever_name="search_v1")
    run_v2 = run_suite(suite, search_v2, k=5, retriever_name="search_v2")

    for name, run in (("v1 含别名", run_v1), ("v2 无别名", run_v2)):
        m_lo, m_hi = run.metrics("lenient"), run.metrics("strict")
        print(f"{name:<12} lenient Hit@1 {m_lo.hit1:5.1%} | "
              f"strict Hit@1 {m_hi.hit1:5.1%} | 虚高 {(m_lo.hit1 - m_hi.hit1) * 100:4.1f}pp | "
              f"MRR {m_lo.mrr:.3f}")

    # ---- 3. 归因 ----
    title("3. 别名表到底贡献了多少")
    ab = ablate(
        suite,
        [
            Variant("v1 含别名", search_v1, "线上方案"),
            Variant("v2 无别名", search_v2, "关掉俗称映射"),
        ],
        k=5,
        rubric="lenient",
    )
    print(md_table(["变体", "Hit@1", "ΔHit@1", "Hit@5", "MRR"],
                   [[r.name, f"{r.hit1:.1%}", f"{r.d_hit1:+.1f}",
                     f"{r.hit5:.1%}", f"{r.mrr:.3f}"] for r in ab.rows]))

    # ---- 4. 回归 ----
    title("4. 回归对比：v1 → v2 弄坏了哪几条")
    d = diff_runs(run_v1, run_v2)
    print(f"修好 {len(d.fixed)} 条，弄坏 {len(d.broke)} 条，净 {d.net:+d}")
    for e in d.broke:
        print(f"  弄坏：{e.query}  →  {e.shift_hint() or e.after_diag}")

    # ---- 5. 出报告 ----
    (OUT / "report.md").write_text(
        render_report(run_v1, profile=prof), encoding="utf-8")
    (OUT / "ablation.md").write_text(
        render_report(run_v1, ablation=ab, title="消融与归因报告"), encoding="utf-8")
    (OUT / "diff.md").write_text(
        render_report(run_v2, diff=d, title="回归对比报告"), encoding="utf-8")

    title("完成")
    print(f"报告已写入 {OUT}")
    for f in ("report.md", "ablation.md", "diff.md"):
        print(f"  - {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
