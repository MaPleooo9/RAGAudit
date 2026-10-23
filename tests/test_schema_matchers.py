# -*- coding: utf-8 -*-
"""评估集结构与判定口径的测试。

重点覆盖两类回归：
    1. 子串误判（「大树守卫」命中「龙装大树守卫」）
    2. 口径差异被抹平（换了层命名后 lenient 悄悄退化成 strict）
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ragaudit.matchers import LENIENT, STRICT, Rubric, diagnose, judge
from ragaudit.schema import Case, Doc, Suite, entity_name, load_suite, strip_title


class TestSchema(unittest.TestCase):
    def test_strip_title_removes_quoted_prefix(self):
        self.assertEqual(strip_title("「血王」蒙格"), "蒙格")
        self.assertEqual(strip_title("“满月女王”蕾娜菈"), "蕾娜菈")
        self.assertEqual(strip_title("拉塔恩"), "拉塔恩")

    def test_entity_name_drops_bracket_suffix(self):
        self.assertEqual(entity_name("玛莲妮亚（Boss）"), "玛莲妮亚")
        self.assertEqual(entity_name("玛莲妮亚的追忆"), "玛莲妮亚的追忆")

    def test_expect_layer_accepts_str_and_list(self):
        self.assertEqual(Case("q", "l2").expect_layers, ["l2"])
        self.assertEqual(Case("q", ["l1", "l3"]).expect_layers, ["l1", "l3"])
        # 去重且保序
        self.assertEqual(Case("q", ["l1", "l1", "l3"]).expect_layers, ["l1", "l3"])

    def test_case_id_is_stable_and_content_derived(self):
        a = Case("玛莲妮亚怎么逃课", "l2")
        b = Case("玛莲妮亚怎么逃课", "l2")
        c = Case("拉塔恩怎么逃课", "l2")
        self.assertEqual(a.id, b.id)
        self.assertNotEqual(a.id, c.id)

    def test_layer_only_flag(self):
        self.assertTrue(Case("给我最无脑的打法", "l3").layer_only)
        self.assertFalse(Case("玛莲妮亚怎么逃课", "l2", "玛莲妮亚").layer_only)

    def test_duplicate_query_rejected(self):
        data = {"cases": [
            {"query": "同一句话", "expect_layer": "l1"},
            {"query": "同一句话", "expect_layer": "l2"},
        ]}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_suite(p)

    def test_load_accepts_bare_array(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "s.json"
            p.write_text(json.dumps(
                [{"query": "q1", "expect_layer": "l1"}], ensure_ascii=False),
                encoding="utf-8")
            self.assertEqual(len(load_suite(p)), 1)

    def test_doc_from_any_reads_attributes(self):
        class Dummy:
            layer = "L2"
            target = "「血王」蒙格"
            title = "蒙格"

        d = Doc.from_any(Dummy())
        self.assertEqual(d.layer, "l2")
        self.assertEqual(d.target, "蒙格")

    def test_suite_only_filters_by_layer(self):
        s = Suite([
            Case("a", "l1"), Case("b", "l2"), Case("c", ["l1", "l3"]),
        ])
        self.assertEqual(len(s.only(["l1"])), 2)
        self.assertEqual(len(s.only(["l2"])), 1)


class TestMatchers(unittest.TestCase):
    def test_substring_must_not_count_as_hit(self):
        """「大树守卫」不能命中「龙装大树守卫」，这是最典型的错误命中。"""
        case = Case("大树守卫怎么逃课", "l2", "大树守卫")
        doc = Doc(layer="l2", target="龙装大树守卫")
        self.assertFalse(judge(LENIENT, doc, case))
        self.assertFalse(judge(STRICT, doc, case))

    def test_lenient_vs_strict_differ_on_title_contains(self):
        """标题包含期望名：宽松算命中，严格不算。差值就是虚高。"""
        case = Case("离线部署怎么做", "guide", "离线部署")
        doc = Doc(layer="guide", title="离线部署完整步骤")
        self.assertTrue(judge(LENIENT, doc, case))
        self.assertFalse(judge(STRICT, doc, case))

    def test_rubric_works_regardless_of_layer_naming(self):
        """层名不是 l1/l2/l3 时，两套口径的差异仍然存在。

        早期版本把 contains 写死给 "l1"，换成 guide/faq/ref 之后
        lenient 静默退化成 strict，指标没变但含义全变了。
        """
        case = Case("授权过期怎么续", "faq", "许可证更换")
        doc = Doc(layer="faq", title="许可证更换说明")
        self.assertTrue(judge(LENIENT, doc, case))
        self.assertFalse(judge(STRICT, doc, case))

    def test_layer_mismatch_is_never_hit(self):
        case = Case("玛莲妮亚怎么逃课", "l2", "玛莲妮亚")
        doc = Doc(layer="l3", target="玛莲妮亚")
        self.assertFalse(judge(LENIENT, doc, case))
        self.assertEqual(diagnose(LENIENT, doc, case), "layer_miss")

    def test_layer_only_case_ignores_target(self):
        case = Case("给我最无脑的打法", "l3")
        self.assertTrue(judge(LENIENT, Doc(layer="l3", target="随便什么"), case))

    def test_exact_target_match(self):
        case = Case("蒙格怎么打", "l2", "蒙格")
        self.assertTrue(judge(STRICT, Doc(layer="l2", target="「血王」蒙格"), case))

    def test_diagnose_distinguishes_failure_stage(self):
        case = Case("玛莲妮亚怎么逃课", "l2", "玛莲妮亚")
        wrong_layer = Doc(layer="l1", title="玛莲妮亚")
        wrong_target = Doc(layer="l2", target="拉塔恩")
        self.assertEqual(diagnose(LENIENT, wrong_layer, case), "layer_miss")
        self.assertEqual(diagnose(LENIENT, wrong_target, case), "target_miss")

    def test_unknown_rule_raises(self):
        with self.assertRaises(KeyError):
            Rubric(name="bad", default="no_such_rule").rule_for("l1")


if __name__ == "__main__":
    unittest.main()
