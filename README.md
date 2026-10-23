# RAGAudit · 检索评测审计台

> 不给你的 RAG 又一个分数，而是审计这个分数能不能信。

一个 RAG 系统报出「Hit@1 94.1%」，这行数字本身不构成任何证据。
它可能是真的，也可能来自：判定口径太松、题库里每题都写着答案、
命中的是手工登记了三个月的俗称表。

RAGAudit 做的是**审计**这件事：查这个数怎么来的、虚高了多少、
哪个部件在起作用、下一次改动弄坏了哪几条。

零运行时依赖，纯标准库，`git clone` 后 3 秒可跑。

---

## 30 秒上手

```bash
git clone https://github.com/MaPleooo9/RAGAudit.git
cd RAGAudit
python examples/toy/run_demo.py
```

不需要 `pip install`，不需要向量库，不需要 embedding 模型。
输出在 `examples/toy/out/` 下，三份报告：跑分、消融、回归对比。

真实输出（toy 演示，10 条题）：

```
v1 含别名       lenient Hit@1 90.0% | strict Hit@1 80.0% | 虚高 10.0pp | MRR 0.900
v2 无别名       lenient Hit@1 80.0% | strict Hit@1 70.0% | 虚高 10.0pp | MRR 0.800

别名表到底贡献了多少：v2 −10.0pp
回归对比：修好 0 条，弄坏 1 条，净 -1
  弄坏：每秒最多调多少次  →  排序：正确结果掉出 Top-K
```

---

## 一个真实案例

拿一个已经上线的本地 RAG 系统做过完整审计（NaviRAG v1.0.1：8428 条三层知识库，
自报 Hit@1 94.1%，85 条人工评估集，原样未改）：

| 问题 | 审计结果 |
|---|---|
| 94.1% 是不是口径撑大的？ | **不是**。两套口径差 1.2pp，而这 1.2pp 还来自本工具的严格口径误判 |
| 这分是谁挣的？ | **76.5pp 来自实体名硬匹配**：关掉它，整条链路只剩 17.6%（纯向量 12.9%） |
| 真实泛化水平？ | 「描述提问」组（整句不含实体名）**Hit@1 只有 50%**，3 条未命中全落在这组 |
| 哪个模块白占位置？ | 术语增强 ΔHit@1 = **±0.0**，MRR 只差 0.004 |
| 哪个部件最脆？ | 手工别名表值 3.5pp，关掉立刻坏 3 条，全部是俗称题 |

**工具独立算出的五个数字，与该项目自评报告逐位吻合**（12.9 / 17.6 / 90.6 / 94.1 / MRR 0.951），
差异全部来自本工具额外提供的信息。完整报告与分析：
[`docs/case-navirag.md`](docs/case-navirag.md)。

---

## 它解决什么

| 你遇到的问题 | 现有做法 | RAGAudit 的做法 |
|---|---|---|
| 这个 94% 可信吗？ | 一个总分，不知道口径 | 宽/严两套口径并列，**差值就是虚高** |
| 分数靠向量还是靠规则？ | 凭感觉，或者手工注释掉代码再跑一遍 | 消融矩阵，**ΔHit@1 直接量化贡献** |
| 题库是不是自己出题自己考？ | 靠自觉 | **自动判定每题的泄漏等级**，给出显式指名占比 |
| 改了一版，分数掉 0.3，坏在哪？ | 只看总分，不知道哪条坏了 | **逐条 diff**，区分修复/弄坏/新增/移除 |
| 悄悄删掉难题也能涨分 | — | **移除题目会单独报出来** |

---

## 四个功能

### 1. 双口径：量化虚高

同一个结果，按两套规则各算一遍：

- `lenient` —— 结果带 `target` 就比 target；没有就看标题是否**包含**期望名
- `strict` —— 结果带 `target` 就比 target；没有就要求**页面主实体完全相等**

差 10 个百分点不是误差，是有 10% 的命中共依赖宽松匹配。
报告永远并列呈现，不挑好看的那个报。

> 口径差异刻意定在「结果自身有没有 target」上，而不是层名上。
> 早期版本按层名分派（给 `l1` 配 contains），换一套层命名
> （`guide` / `faq` / `ref`）之后 lenient 会静默退化成 strict——
> 指标数字没变，含义全变了，而人眼看不出来。

### 2. 消融与归因：这分是谁挣的

把某个部件关掉，再跑一遍：

```python
VARIANTS = [
    ("full（含别名）", search_v1, "线上方案"),
    ("full −alias（关俗称）", search_v2, "验证别名表的净贡献"),
]
```

```bash
ragaudit ablate -s suite.json -v variants.py --layers l2,l3
```

`ΔHit@1` 就是该部件的净贡献。**关掉之后反而变好的部件会被单独标出来**——
负收益模块不该以「还没证明有害」为理由继续留着。

### 3. 难度画像：拆穿自己出题自己考

不需要人工分组，从题面自动判定四条信息泄漏等级：

| 等级 | 含义 | 意味着什么 |
|---|---|---|
| `explicit` | 问句直接写着答案实体名 | 实体匹配就能命中，测不出检索 |
| `alias` | 问句用的是登记过的俗称 | 测的是别名表覆盖度，不是语义 |
| `partial` | 问句含同名子串，易指向错误实体 | 比完全不含实体名更难 |
| `implicit` | 整句不含实体名 | **只有这档才真正考验语义检索** |

显式指名占比超过 70% 时，`lint` 会直接警告：这个总分大概率是查词典查出来的。

### 4. 逐条回归：坏在哪一环

按题目内容哈希对齐（不是按序号，中间插一条不会让后面全部错位）：

- `fixed` / `broke` / `improved` / `worsened` / `added` / **`removed`**
- 每条退化还会给出归因：层路由错了、还是排序掉了

`removed` 是审计视角的关键：删掉难例同样能让总分上涨。

---

## 接入你自己的检索器

只要满足 `f(query, k) -> list[结果]`，结果里带 `layer` / `target` / `title`：

```python
# mypkg/retr.py
def search(query: str, k: int = 5) -> list[dict]:
    return [
        {"layer": "l2", "target": "玛莲妮亚", "title": "玛莲妮亚跳崖"},
        ...
    ]
```

```bash
ragaudit run -s my_suite.json -r mypkg.retr:search -o report.md --json run.json
```

返回对象也支持：dict、dataclass、任何带同名属性的对象都能被自动归一化。
字段名不一样时，用 `Doc.from_any(obj, field_map=...)` 指定映射。

需要连真实向量库和 embedding 模型的接入样例，看
[`examples/elden-ring/navireg_retriever.py`](examples/elden-ring/navireg_retriever.py)
——它连着 ChromaDB，`ragaudit` 侧仍然零依赖，重依赖只出现在被测系统那一侧。

### 评估集格式

```json
{
  "cases": [
    {"query": "玛莲妮亚怎么逃课", "expect_layer": "l2",
     "expect_target": "玛莲妮亚", "group": "逃课意图"}
  ]
}
```

- `expect_layer` 可以是字符串或数组（命中任一即算层对）
- `expect_target` 留空表示「只判层不判目标」
- 顶层结构也接受裸数组

---

## 命令

| 命令 | 作用 |
|---|---|
| `ragaudit lint -s suite.json` | 评估集自检（先查题） |
| `ragaudit run -s suite.json -r mod:fn` | 跑分并生成报告 |
| `ragaudit ablate -s suite.json -v variants.py` | 消融与归因 |
| `ragaudit diff --base v1.json --cur v2.json` | 两次运行逐条对比 |

`run` 加 `--json` 保存原始结果，它同时是 `diff` 的输入——
这意味着**把它挂进 CI，每次提交都能拿到一份退化清单**。

---

## 设计取舍

**为什么不用 LLM 打分。** 检索层的问题在「召回哪一条」，不在「话说得好不好」。
用 LLM 当裁判会把两个问题混在一起，而且本地小模型打分不可靠、
每次跑结果还不一样。这里用可判定的硬指标：期望层 + 期望目标，命中就算对。

**为什么零运行时依赖。** 评估工具本身要是黑盒，它的结论就没法用来判断别人。
纯标准库意味着任何人拿到代码都能核对每一行打分逻辑。

**为什么保留逐条结果。** 只留总分的评测撑不起回归测试。
总分掉 0.3 时，你需要知道是哪几条、坏在哪一环。

---

## 和 RAGAS / DeepEval 的关系

它们是量**答案**的，这里量**分数本身**。不替代，可叠加：

| | RAGAudit | RAGAS | DeepEval |
|---|---|---|---|
| 判定方式 | 确定性硬指标，**不调 LLM** | LLM-as-judge | LLM-as-judge（含 G-Eval） |
| 看什么 | 召回哪一条 | 答案是否有据、是否切题 | 整条链路 + Agent 行为 |
| 可复现 | 完全相同输入 → 完全相同输出 | 换 judge 就换尺子 | 同 |
| 依赖 | **零** | ragas / datasets | deepeval |
| 双口径量虚高 | ✅ | ❌ | ❌ |
| 题库泄漏画像 | ✅ | ❌ | ❌ |
| 删题涨分检测 | ✅ | ❌ | ❌ |

推荐分工：**RAGAudit 守检索不退化（秒级、可进 CI），RAGAS / DeepEval 守答案不退化。**
完整对照（含各框架的指标口径差异与「为什么不用 LLM 打分」）见
[`docs/comparison.md`](docs/comparison.md)。

---

## 开发

```bash
python -m unittest discover -s tests -p "test_*.py"
```

34 个用例，零依赖，0.01 秒跑完。CI 见 `.github/workflows/ci.yml`。

文档：

| 文件 | 内容 |
|---|---|
| [`docs/metrics.md`](docs/metrics.md) | 每个指标怎么算、为什么这么算 |
| [`docs/architecture.md`](docs/architecture.md) | 模块划分与数据流 |
| [`docs/case-navirag.md`](docs/case-navirag.md) | 真实案例：审计一个 94.1% 的系统 |
| [`docs/comparison.md`](docs/comparison.md) | vs RAGAS / DeepEval |
| [`docs/licenses.md`](docs/licenses.md) | 依赖许可证清单与合规结论 |

---

## 许可证

[Apache-2.0](LICENSE)，运行时零第三方依赖（清单见 [`docs/licenses.md`](docs/licenses.md)）。
贡献前请读 [CONTRIBUTING.md](CONTRIBUTING.md)，长期规划见 [ROADMAP.md](ROADMAP.md)。
