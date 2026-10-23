# -*- coding: utf-8 -*-
"""命令行入口。

    python -m ragaudit run    -s suite.json -r mypkg.retr:search -o report.md
    python -m ragaudit lint   -s suite.json
    python -m ragaudit diff   --base v1.json --cur v2.json
    python -m ragaudit ablate -s suite.json -v variants.py

设计上刻意不做配置文件：一个命令能跑完的事，不该让人先去写 YAML。
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .ablate import Variant, ablate
from .diff import diff_runs
from .matchers import Rubric, default_rubrics
from .metrics import RunResult, run_suite
from .profile import profile as build_profile, lint as lint_suite
from .report import md_table, render_report
from .schema import Suite, load_suite

__all__ = ["main"]


def _fix_console() -> None:
    """Windows 控制台默认 cp936，中文报告直接 print 会炸。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def _load_callable(spec: str) -> Any:
    """'pkg.mod:func' 或 'pkg.mod.func' → 对象。"""
    if ":" in spec:
        mod_name, attr = spec.split(":", 1)
    else:
        mod_name, _, attr = spec.rpartition(".")
    if not mod_name:
        raise SystemExit(f"检索器必须写成 module:function，收到 {spec!r}")
    mod = importlib.import_module(mod_name)
    if not hasattr(mod, attr):
        raise SystemExit(f"{mod_name} 里没有 {attr!r}")
    return getattr(mod, attr)


def _load_variants(path: str) -> list[Variant]:
    """从 python 文件加载变体定义。

    文件里需要一个 VARIANTS = [("名字", 可调用对象, "说明"), ...]，
    也接受 [Variant(...), ...]。
    """
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"变体文件不存在：{p}")
    spec = importlib.util.spec_from_file_location("_ragaudit_variants", p)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载 {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(p.parent.resolve()))
    spec.loader.exec_module(mod)

    raw = getattr(mod, "VARIANTS", None)
    if not raw:
        raise SystemExit(f"{p} 里没有定义 VARIANTS")

    out: list[Variant] = []
    for item in raw:
        if isinstance(item, Variant):
            out.append(item)
        else:
            name, fn = item[0], item[1]
            note = item[2] if len(item) > 2 else ""
            out.append(Variant(name=name, retriever=fn, note=note))
    return out


def _build_rubrics(names: str | None) -> list[Rubric]:
    builtin = {r.name: r for r in default_rubrics()}
    if not names:
        return list(builtin.values())
    out = []
    for n in [x.strip() for x in names.split(",") if x.strip()]:
        if n not in builtin:
            raise SystemExit(f"未知口径 {n!r}，可用：{sorted(builtin)}")
        out.append(builtin[n])
    return out


def _load_alias(path: str | None) -> dict[str, str] | None:
    """别名表：{俗称: 规范名} 或 {规范名: [俗称...]}，两种都接受。"""
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    flat: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue  # 允许在别名表里写 _about 之类的说明字段
        if isinstance(v, list):
            for a in v:
                flat[str(a)] = str(k)
        else:
            flat[str(k)] = str(v)
    return flat


def cmd_run(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    retriever = _load_callable(args.retriever)
    rubrics = _build_rubrics(args.rubrics)

    run = run_suite(
        suite, retriever, k=args.k, rubrics=rubrics,
        retriever_name=args.name or args.retriever,
    )

    prof = build_profile(suite, _load_alias(args.alias)) if args.profile else None
    md = render_report(run, [r.name for r in rubrics], profile=prof)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md, encoding="utf-8")
        print(f"报告已写入 {out}")
    else:
        print(md)

    if args.json:
        jp = Path(args.json)
        jp.parent.mkdir(parents=True, exist_ok=True)
        jp.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"原始结果已写入 {jp}（可用于 ragaudit diff）")

    m = run.metrics(rubrics[0].name)
    print(f"\nHit@1 {m.hit1:.1%} | Hit@5 {m.hit5:.1%} | MRR {m.mrr:.3f} | n={m.n}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    issues = lint_suite(suite, _load_alias(args.alias))
    prof = build_profile(suite, _load_alias(args.alias))

    print(f"评估集 {suite.name}：{len(suite)} 条，{len(suite.groups)} 组")
    print(f"显式指名 {prof.leak_rate:.0%} | 有难度 {prof.hard_rate:.0%}")
    print(md_table(
        ["泄漏等级", "条数"],
        [[k, v] for k, v in sorted(prof.by_leak.items(), key=lambda x: -x[1])],
    ))
    print()

    if not issues:
        print("未发现问题。")
        return 0

    for it in issues:
        print(f"- {it}")

    errors = sum(1 for i in issues if i.level == "error")
    warns = sum(1 for i in issues if i.level == "warn")
    print(f"\n共 {len(issues)} 项：error {errors} / warn {warns}")
    return 1 if errors else 0


def cmd_diff(args: argparse.Namespace) -> int:
    base = RunResult.from_dict(json.loads(Path(args.base).read_text(encoding="utf-8")))
    cur = RunResult.from_dict(json.loads(Path(args.cur).read_text(encoding="utf-8")))
    d = diff_runs(base, cur, args.rubric)

    md = render_report(cur, cur.rubrics, diff=d, title="回归对比报告")
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        print(md)
    return 0


def cmd_ablate(args: argparse.Namespace) -> int:
    suite = load_suite(args.suite)
    variants = _load_variants(args.variants)
    layers = [x.strip() for x in args.layers.split(",")] if args.layers else None

    res = ablate(
        suite, variants, k=args.k, rubric=args.rubric,
        layers=layers, reference=args.reference,
    )

    md = render_report(
        run_suite(suite.only(layers) if layers else suite,
                  variants[0].retriever, k=args.k,
                  rubrics=_build_rubrics(args.rubrics),
                  retriever_name=variants[0].name),
        _build_rubrics(args.rubrics),
        ablation=res,
        title="消融与归因报告",
    )
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        print(md)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="ragaudit",
        description="检索评测审计台：查你的分，而不是给你一个分。",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("-s", "--suite", required=True, help="评估集 JSON")
        p.add_argument("-k", type=int, default=5, help="Top-K，默认 5")
        p.add_argument("--rubrics", default=None,
                       help="口径列表，逗号分隔，默认 lenient,strict")
        p.add_argument("--alias", default=None, help="别名表 JSON（用于难度画像）")
        p.add_argument("-o", "--out", default=None, help="报告输出路径（.md）")

    p_run = sub.add_parser("run", help="跑一次评估")
    common(p_run)
    p_run.add_argument("-r", "--retriever", required=True,
                       help="检索器，格式 module:function")
    p_run.add_argument("--name", default=None, help="报告里显示的方案名")
    p_run.add_argument("--json", default=None, help="原始结果输出路径（供 diff 用）")
    p_run.add_argument("--no-profile", dest="profile", action="store_false",
                       help="跳过难度画像")
    p_run.set_defaults(func=cmd_run, profile=True)

    p_lint = sub.add_parser("lint", help="评估集自检")
    p_lint.add_argument("-s", "--suite", required=True)
    p_lint.add_argument("--alias", default=None)
    p_lint.set_defaults(func=cmd_lint)

    p_diff = sub.add_parser("diff", help="两次运行对比")
    p_diff.add_argument("--base", required=True, help="旧结果 JSON")
    p_diff.add_argument("--cur", required=True, help="新结果 JSON")
    p_diff.add_argument("--rubric", default=None, help="用哪套口径对比")
    p_diff.add_argument("-o", "--out", default=None)
    p_diff.set_defaults(func=cmd_diff)

    p_abl = sub.add_parser("ablate", help="消融与归因")
    common(p_abl)
    p_abl.add_argument("-v", "--variants", required=True, help="变体定义 .py")
    p_abl.add_argument("--layers", default=None,
                       help="只在这些期望层上比较，如 l2,l3")
    p_abl.add_argument("--reference", default=None, help="参照变体名")
    p_abl.add_argument("--rubric", default="lenient", help="归因用单一口径")
    p_abl.set_defaults(func=cmd_ablate)

    return ap


def main(argv: Sequence[str] | None = None) -> int:
    _fix_console()
    ap = build_parser()
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
