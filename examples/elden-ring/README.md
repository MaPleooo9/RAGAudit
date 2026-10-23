# 真实案例：一个 85 条的人工评估集

这份评估集来自一个真实上线的本地 RAG 问答系统（《艾尔登法环》攻略检索），
**85 条人工标注问法，8 个分组**，是这个项目最初的起点。

放在这里有两个用途：

1. 作为**评估集格式的真实样例**——比 `examples/toy` 那 10 条更能说明问题长什么样
2. 作为 `run` 的**真实输入**——配套适配器 [`navireg_retriever.py`](navireg_retriever.py)
   已经把它接到 NaviRAG 的线上检索器上，跑出来的完整报告在
   [`docs/case-navirag.md`](../../docs/case-navirag.md)

这是一份**未做任何改动**的评估集：与 NaviRAG 仓库里的 `data/elden_ring/eval_set.json`
逐字节一致（已核对）。不改题、不删题，是这份案例能被复核的前提。

## 真实跑分（NaviRAG 线上检索器）

```
lenient  Hit@1 94.1% | Hit@3 96.5% | Hit@5 96.5% | MRR 0.951 | 层准确率 97.6%
strict   Hit@1 92.9% | Hit@3 96.5% | Hit@5 96.5% | MRR 0.945 | 层准确率 97.6%
        口径差 1.2pp（只来自 1 条题，且那条是严格口径误判）
```

消融（各变体只关一个部件）：

| 变体 | Hit@1 | ΔHit@1 | MRR |
|---|---|---|---|
| full（线上） | 94.1% | — | 0.951 |
| −alias 关俗称表 | 90.6% | −3.5 | 0.913 |
| −enhance 关术语增强 | 94.1% | ±0.0 | 0.947 |
| −entity 关实体硬置顶 | 17.6% | −76.5 | 0.210 |
| pure-vector 单路向量 | 12.9% | −81.2 | 0.153 |

完整分析（含与 NaviRAG 自评报告的逐项交叉验证）见
[`docs/case-navirag.md`](../../docs/case-navirag.md)。

## 怎么自己跑一遍

```bash
# 需要 NaviRAG 的依赖与已建好的 .vectorstore
set NAVIRAG_HOME=D:\PROJECT\NaviRAG
set PYTHONPATH=examples\elden-ring

python -m ragaudit run -s examples/elden-ring/suite.json -r navireg_retriever:search ^
    -k 5 --alias %NAVIRAG_HOME%\data\elden_ring\aliases.json ^
    -o examples/elden-ring/out/report.md --json examples/elden-ring/out/run.json
```

`--alias` 指向 NaviRAG 自己的别名表，这样「俗称」才会被判成 `alias` 而不是并进
`implicit`——两种配置的差别见下面的自检输出。

## 分组构成

| 分组 | 条数 | 说明 |
|---|---|---|
| 逃课意图 | 23 | 「XX 怎么逃课」 |
| 常规意图 | 22 | 「XX 怎么正常打」 |
| 口语俗称 | 9 | 用玩家间的俗称提问，不写官方名 |
| 否定表达 | 8 | 「不想硬打」「有没有不用打的」 |
| 知识问答 | 7 | 问设定、问位置 |
| 描述提问 | 6 | **整句不含任何实体名**，只能靠语义 |
| 无脑度意图 | 5 | 问「最无脑的打法」 |
| 等级过滤 | 5 | 带等级/进度条件的问法 |

「口语俗称」和「描述提问」两组是刻意补的难度组：前者测俗称别名覆盖，
后者整句不含实体名，实体硬置顶完全失效——**这两组的分数才代表真实泛化能力**，
前几组的高分是必然的（写题时就知道库里有哪一条，措辞自然对得上）。
实测也印证了这一点：描述提问组 Hit@1 只有 50%，而逃课/等级过滤组是 100%。

## 跑一次自检

```bash
ragaudit lint -s examples/elden-ring/suite.json
```

实际输出（不带别名表）：

```
评估集 suite：85 条，8 组
显式指名 64% | 有难度 36%
| 泄漏等级 | 条数 |
|---|---|
| explicit | 54 |
| implicit | 22 |
| partial  | 9  |
```

加上 NaviRAG 的别名表之后，原先被混进 `implicit` 和 `partial` 的俗称题会被单独识别
出来（`implicit` 22→15，`partial` 9→1，`alias` 15 条）：

```
| explicit | 54 |
| implicit | 15 |
| alias    | 15 |
| partial  | 1  |
```

**64% 的题在问句里直接写着答案实体名。** 这个数不算低，但它诚实地反映了
这份评估集的构成——「逃课意图」「常规意图」这两大组共 45 条，本来就是指名提问。

关键在于：**这个数字被明确写出来了**。评审时可以据此判断
「94.1% 的 Hit@1 里有多少来自实体匹配」，而不是只看一个孤零零的百分比。

（不带别名表时 `partial` 有 9 条——问句里出现了比期望目标更长的同名实体，
比如问「龙装大树守卫」时期望值写成「大树守卫」——这类题在实体硬置顶下
会稳定指向错误目标，`lint` 把它们标出来是为了让人确认期望值没写错。
带上别名表后其中 8 条被判成 `alias`，只剩 1 条真正属于这类。）

> 没提供别名表时，俗称类会被并入 `implicit`。想区分开，加 `--alias alias.json`
> （真实案例里直接指向 NaviRAG 的 `data/elden_ring/aliases.json`）。

## 可以借鉴的写法

这份评估集里有几个处理方式值得抄：

- **`expect_layer` 允许写成数组**。例如「XX 怎么正常打」，命中攻略页和命中打法页都算对，
  写成 `["l1", "l3"]`。（这个特性也正是当年那个「层准确率 < Hit@1」倒挂 bug 的来源，
  见 `docs/metrics.md`。）
- **`expect_target` 留空表示只判层**。像「给我最无脑的打法」没有具体目标，
  硬填一个答案会让指标失真。
- **`_about` / `_rule` 写进评估集文件本身**。半年后回来看，
  没人记得 `group` 字段当时是怎么定义的，写在文件里比写在文档里更不容易丢。

## 来源

评估集由项目作者人工标注，随该项目的开源版本一并发布。
原始项目：[NaviRAG](https://github.com/MaPleooo9/NaviRAG)（Apache-2.0）。
