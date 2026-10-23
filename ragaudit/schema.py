# -*- coding: utf-8 -*-
"""评估集与检索结果的数据结构。

设计原则：评估集是**纯数据**，不含任何检索实现细节。
同一份评估集可以喂给任意检索器，跨方案才可比。

这个约束是刻意的。把「评估集长什么样」和「怎么检索」绑在一起，
是所有自制评测脚本最终失去可比性的原因。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "Case",
    "Doc",
    "Suite",
    "case_id",
    "strip_title",
    "entity_name",
    "load_suite",
]

# 「血王」蒙格 → 蒙格。称号用引号包裹，去掉它，否则同一个实体会被算成两个。
_TITLE_RE = re.compile(r"^[“\"「『][^”\"」』]*[”\"」』]\s*")

# 「玛莲妮亚的追忆（道具）」→ 玛莲妮亚的追忆
_BRACKET_RE = re.compile(r"[（(].*$")


def strip_title(s: str) -> str:
    """去掉引号包裹的称号前缀。"""
    return _TITLE_RE.sub("", (s or "").strip()).strip()


def entity_name(s: str) -> str:
    """取页面主实体名：去称号前缀、去括号后缀。

    严格口径靠它区分「玛莲妮亚」本体页和「玛莲妮亚的追忆」物品页。
    不区分的话，标题里只要沾到名字就算命中，指标会被系统性高估。
    """
    return _BRACKET_RE.sub("", strip_title(s)).strip()


def case_id(query: str) -> str:
    """由问句原文派生的稳定 id。

    diff 靠它对齐两次运行里的同一道题。不能用序号：在中间插入一条，
    后面全部错位，diff 会变成一屏噪声。
    """
    return hashlib.sha1(query.strip().encode("utf-8")).hexdigest()[:12]


def _as_layer_list(v: Any) -> list[str]:
    """expect_layer 允许写成 str 或 list，统一成去重后的列表。

    支持列表是因为「正常打法」这类问题命中 l1 或 l3 都算对。
    早期实现里层准确率用 `==` 直接比，遇列表恒为 False，
    于是出现「层准确率 97.2% 低于 Hit@1 98.6%」这种不可能倒挂。
    现在统一入口，从源头上不给这种 bug 留位置。
    """
    if v is None:
        return []
    items = [v] if isinstance(v, str) else list(v)
    out: list[str] = []
    for it in items:
        s = str(it).strip().lower()
        if s and s not in out:
            out.append(s)
    return out


@dataclass
class Case:
    """一道评估题。

    Attributes:
        query:         用户真实问法
        expect_layers: 期望命中的层，可多值（命中任一即算层对）
        expect_target: 期望命中的目标规范名；空串表示「只判层不判目标」
        group:         人工分组，用于看哪类问题最易翻车
        tags:          自由标签
    """

    query: str
    expect_layers: list[str]
    expect_target: str = ""
    group: str = "default"
    tags: list[str] = field(default_factory=list)
    id: str = ""

    def __post_init__(self) -> None:
        self.query = str(self.query).strip()
        self.expect_layers = _as_layer_list(self.expect_layers)
        self.expect_target = strip_title(str(self.expect_target or ""))
        self.group = str(self.group or "default").strip() or "default"
        if not self.query:
            raise ValueError("Case.query 不能为空")
        if not self.id:
            self.id = case_id(self.query)

    @property
    def layer_only(self) -> bool:
        """只判层、不判目标（例如「给我最无脑的打法」没有具体实体）。"""
        return not self.expect_target

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "Case":
        return cls(
            query=d.get("query", ""),
            expect_layers=d.get("expect_layer", d.get("expect_layers", [])),
            expect_target=d.get("expect_target", d.get("target", "")),
            group=d.get("group", "default"),
            tags=list(d.get("tags") or []),
            id=d.get("id", ""),
        )


# 检索结果里各字段可能的键名。不同框架叫法不一，与其强迫用户改代码，
# 不如把映射做成表，允许覆盖。
DEFAULT_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "layer": ("layer", "collection", "type", "kind", "source"),
    "target": ("target", "entity", "canonical"),
    "title": ("title_zh", "title", "name", "label", "doc_name"),
}


@dataclass
class Doc:
    """一条检索结果。

    raw 保留原始对象，自定义 matcher 可能要读额外字段，
    或者想检查「这条结果来自哪个分片」这类审计信息。
    """

    layer: str = ""
    target: str = ""
    title: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # 归一化放在构造器里而不是 from_any 里：
        # 直接 Doc(target="「血王」蒙格") 也必须是干净的，
        # 否则两两相同时会因为一个走工厂一个走构造器而产生误判。
        self.layer = (self.layer or "").strip().lower()
        self.target = strip_title(self.target)
        self.title = (self.title or "").strip()

    @property
    def entity(self) -> str:
        """页面主实体名，严格口径用它比对。"""
        return entity_name(self.target or self.title)

    @classmethod
    def from_any(
        cls,
        obj: Any,
        field_map: Mapping[str, Iterable[str]] | None = None,
    ) -> "Doc":
        """把任意检索器返回的对象归一化成 Doc。

        支持 dict、以及带同名属性的对象（dataclass / 框架的 Document 类）。
        """
        fm = dict(DEFAULT_FIELD_MAP)
        if field_map:
            fm.update({k: tuple(v) for k, v in field_map.items()})

        def pick(key_name: str) -> str:
            for k in fm.get(key_name, ()):
                if isinstance(obj, Mapping):
                    v = obj.get(k)
                else:
                    v = getattr(obj, k, None)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            return ""

        raw: dict[str, Any]
        if isinstance(obj, Mapping):
            raw = dict(obj)
        elif hasattr(obj, "to_dict"):
            try:
                raw = dict(obj.to_dict())
            except Exception:  # 第三方对象的 to_dict 不保证可用
                raw = {}
        else:
            raw = {}

        return cls(
            layer=pick("layer").lower(),
            target=strip_title(pick("target")),
            title=pick("title"),
            raw=raw,
        )


@dataclass
class Suite:
    """一份评估集。"""

    cases: list[Case]
    name: str = "suite"
    about: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.cases)

    def __iter__(self):
        return iter(self.cases)

    @property
    def groups(self) -> list[str]:
        """按样本量从大到小排列的分组名。"""
        seen: dict[str, int] = {}
        for c in self.cases:
            seen[c.group] = seen.get(c.group, 0) + 1
        return sorted(seen, key=lambda g: -seen[g])

    def only(self, layers: Iterable[str]) -> "Suite":
        """取子集：只保留期望层与给定层有交集的用例。

        归因分析必须在可比子集上做。比如「纯规则检索」定位不到
        l1 wiki 页面，拿它跟融合方案在全集上比，结论是假的。
        """
        want = {str(x).lower() for x in layers}
        sub = [c for c in self.cases if want & set(c.expect_layers)]
        return Suite(
            cases=sub,
            name=f"{self.name}[{','.join(sorted(want))}]",
            about=self.about,
            meta={**self.meta, "subset_of": self.name},
        )

    @classmethod
    def load(cls, path: str | Path) -> "Suite":
        return load_suite(path)


def load_suite(path: str | Path) -> Suite:
    """从 JSON 读取评估集。

    兼容两种顶层结构：{"cases": [...]} 和裸数组 [...]。
    兼容 field 名：expect_layer / expect_layers, expect_target / target。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"评估集不存在：{p}")
    data = json.loads(p.read_text(encoding="utf-8"))

    if isinstance(data, list):
        raw_cases, name, about, meta = data, p.stem, "", {}
    elif isinstance(data, dict):
        raw_cases = data.get("cases") or data.get("items") or []
        name = str(data.get("name") or p.stem)
        about = str(data.get("_about") or data.get("about") or "")
        meta = {k: v for k, v in data.items()
                if not k.startswith("_") and k not in ("cases", "items", "name", "about")}
        # _rule 保留下来，报告里可以原样引用判定口径说明
        if "_rule" in data:
            meta["_rule"] = data["_rule"]
    else:
        raise ValueError(f"无法识别的评估集结构：{type(data).__name__}")

    if not raw_cases:
        raise ValueError(f"{p} 里没有任何用例")

    cases = [Case.from_dict(d) for d in raw_cases]
    _check_duplicate_ids(cases)
    return Suite(cases=cases, name=name, about=about, meta=meta)


def _check_duplicate_ids(cases: list[Case]) -> None:
    """重复问句会让 MRR 之类的均值被同一道题重复加权，静默失真。"""
    seen: dict[str, Case] = {}
    for c in cases:
        if c.id in seen:
            raise ValueError(
                f"评估集里有重复问句：{c.query!r}（与 {seen[c.id].query!r} 相同）"
            )
        seen[c.id] = c
