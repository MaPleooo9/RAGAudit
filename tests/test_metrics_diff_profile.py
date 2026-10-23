# -*- coding: utf-8 -*-
"""指标、diff、难度画像的测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ragaudit.ablate import Variant, ablate, contribution
from ragaudit.diff import diff_runs
from ragaudit.metrics import run_suite
from ragaudit.profile import (
    LEAK_ALIAS,
    LEAK_EXPLICIT,
    LEAK_IMPLICIT,
    LEAK_PARTIAL,
    leak_level,
    lint,
    profile,
)
from ragaudit.schema import Case, Suite


def suite_of(*cases: Case) -> Suite:
    return Suite(cases=list(cases), name="test")


def const_retriever(results_by_query):
    """按问句返回固定结果，用于精确控制排名。"""

    def fn(query, k):
        return list(results_by_query.get(query, []))[:k]

    return fn


class TestMetrics(unittest.TestCase):
    def test_hit_and_mrr(self):
        s = suite_of(
            Case("q1", "l1", "甲"),   # 命中 rank1
            Case("q2", "l1", "乙"),   # 命中 rank2
            Case("q3", "l1", "丙"),   # 未命中
        )
        r = run_suite(s, const_retriever({
            "q1": [{"layer": "l1", "target": "甲"}],
            "q2": [{"layer": "l1", "target": "丁"}, {"layer": "l1", "target": "乙"}],
            "q3": [{"layer": "l1", "target": "戊"}],
        }), k=5)

        m = r.metrics("strict")
        self.assertAlmostEqual(m.hit1, 1 / 3)
        self.assertAlmostEqual(m.hit3, 2 / 3)
        self.assertAlmostEqual(m.mrr, (1 + 0.5) / 3)

    def test_layer_accuracy_is_independent_of_target(self):
        s = suite_of(Case("q", "l2", "甲"))
        r = run_suite(s, const_retriever({
            "q": [{"layer": "l2", "target": "乙"}],
        }), k=5)
        m = r.metrics("strict")
        self.assertEqual(m.hit1, 0.0)      # 目标错
        self.assertEqual(m.layer_acc, 1.0)  # 层对

    def test_group_breakdown(self):
        s = suite_of(
            Case("q1", "l1", "甲", group="A"),
            Case("q2", "l1", "乙", group="B"),
        )
        r = run_suite(s, const_retriever({
            "q1": [{"layer": "l1", "target": "甲"}],
            "q2": [{"layer": "l1", "target": "丙"}],
        }), k=5)
        m = r.metrics("strict")
        self.assertEqual(m.by_group["A"].hit1_rate, 1.0)
        self.assertEqual(m.by_group["B"].hit1_rate, 0.0)

    def test_empty_suite_does_not_crash(self):
        m = run_suite(Suite([]), const_retriever({}), k=5).metrics("strict")
        self.assertEqual(m.n, 0)
        self.assertEqual(m.hit1, 0.0)

    def test_roundtrip_serialization(self):
        s = suite_of(Case("q1", "l1", "甲"))
        r = run_suite(s, const_retriever({
            "q1": [{"layer": "l1", "target": "甲"}],
        }), k=5)
        from ragaudit.metrics import RunResult
        back = RunResult.from_dict(r.to_dict())
        self.assertEqual(back.rubrics, r.rubrics)
        self.assertEqual(back.cases[0].ranks, r.cases[0].ranks)


class TestDiff(unittest.TestCase):
    def _runs(self):
        s = suite_of(
            Case("修好", "l1", "甲"),
            Case("弄坏", "l1", "乙"),
            Case("不变", "l1", "丙"),
            Case("消失", "l1", "丁"),
        )
        before = run_suite(s, const_retriever({
            "修好": [{"layer": "l1", "target": "错"}],
            "弄坏": [{"layer": "l1", "target": "乙"}],
            "不变": [{"layer": "l1", "target": "丙"}],
            "消失": [{"layer": "l1", "target": "丁"}],
        }), k=5)
        after = run_suite(s.only(["l1"]) if False else Suite(s.cases[:3]), const_retriever({
            "修好": [{"layer": "l1", "target": "甲"}],
            "弄坏": [{"layer": "l1", "target": "错"}],
            "不变": [{"layer": "l1", "target": "丙"}],
        }), k=5)
        return before, after

    def test_classification(self):
        before, after = self._runs()
        d = diff_runs(before, after)
        self.assertEqual([e.query for e in d.fixed], ["修好"])
        self.assertEqual([e.query for e in d.broke], ["弄坏"])
        self.assertEqual([e.query for e in d.removed], ["消失"])
        self.assertEqual(d.net, 0)

    def test_removed_questions_are_flagged(self):
        """删题也能涨分，必须显式报出来。"""
        before, after = self._runs()
        d = diff_runs(before, after)
        self.assertTrue(d.suspicious)

    def test_broke_hint_points_at_stage(self):
        before, after = self._runs()
        d = diff_runs(before, after)
        self.assertIn("排序", d.broke[0].shift_hint())


class TestProfile(unittest.TestCase):
    def test_leak_levels(self):
        targets = ["大树守卫", "龙装大树守卫", "玛莲妮亚"]
        self.assertEqual(
            leak_level(Case("玛莲妮亚怎么逃课", "l2", "玛莲妮亚"), targets),
            LEAK_EXPLICIT)
        self.assertEqual(
            leak_level(Case("龙装大树守卫怎么打", "l2", "大树守卫"), targets),
            LEAK_PARTIAL)
        self.assertEqual(
            leak_level(Case("雪山上那个巨人怎么打", "l3", "火焰巨人"), targets),
            LEAK_IMPLICIT)

    def test_alias_leak(self):
        case = Case("授权过期怎么续", "faq", "许可证更换")
        self.assertEqual(
            leak_level(case, ["许可证更换"], {"授权": "许可证更换"}),
            LEAK_ALIAS)

    def test_profile_rates(self):
        s = suite_of(
            Case("玛莲妮亚怎么逃课", "l2", "玛莲妮亚"),
            Case("雪山上那个巨人怎么打", "l3", "火焰巨人"),
        )
        p = profile(s)
        self.assertEqual(p.n, 2)
        self.assertAlmostEqual(p.leak_rate, 0.5)

    def test_lint_flags_small_group(self):
        s = suite_of(Case("唯一一条", "l1", "甲", group="单例组"))
        codes = {i.code for i in lint(s)}
        self.assertIn("small_group", codes)

    def test_lint_flags_missing_expect_layer(self):
        # 构造一个层为空的用例（绕过 __post_init__ 的校验不现实，
        # 所以直接改属性模拟从脏数据加载进来的情况）
        c = Case("没有层", "l1", "甲")
        c.expect_layers = []
        codes = {i.code for i in lint(Suite([c]))}
        self.assertIn("no_expect_layer", codes)


class TestAblate(unittest.TestCase):
    def test_delta_relative_to_first_variant(self):
        s = suite_of(Case("q1", "l1", "甲"), Case("q2", "l1", "乙"))
        good = const_retriever({
            "q1": [{"layer": "l1", "target": "甲"}],
            "q2": [{"layer": "l1", "target": "乙"}],
        })
        bad = const_retriever({
            "q1": [{"layer": "l1", "target": "甲"}],
            "q2": [{"layer": "l1", "target": "错"}],
        })
        res = ablate(s, [Variant("full", good), Variant("full -x", bad)], k=5)
        self.assertAlmostEqual(res.rows[1].d_hit1, -50.0)

    def test_layers_subset_is_enforced(self):
        s = suite_of(Case("a", "l1", "甲"), Case("b", "l2", "乙"))
        fn = const_retriever({})
        res = ablate(s, [Variant("v", fn)], k=5, layers=["l2"])
        self.assertEqual(res.n, 1)

    def test_contribution_sign(self):
        s = suite_of(Case("q1", "l1", "甲"))
        good = const_retriever({"q1": [{"layer": "l1", "target": "甲"}]})
        bad = const_retriever({"q1": [{"layer": "l1", "target": "错"}]})
        res = ablate(s, [Variant("full", good), Variant("off", bad)], k=5)
        c = contribution(res.rows[0], res.rows[1])
        self.assertGreater(c["hit1"], 0)


if __name__ == "__main__":
    unittest.main()
