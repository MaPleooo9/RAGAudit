# RAGAudit vs RAGAS / DeepEval

> 一句话：**它们量答案，RAGAudit 量分数本身。**
> 三者不是替代关系，RAGAS / DeepEval 回答「答得好不好」，RAGAudit 回答
> 「这个好分数能不能信、是谁挣的、下次改动弄坏了哪条」。

---

## 一、定位差异

| | RAGAudit | RAGAS | DeepEval |
|---|---|---|---|
| 一句话定位 | 检索评测**审计**台 | RAG 端到端**指标**库 | LLM 应用的 **pytest** |
| 评估对象 | 检索层（召回哪一条） | 生成链路（答案 vs 上下文） | 整条链路 + Agent 行为 |
| 判定方式 | **确定性硬指标**：期望层 + 期望目标，命中即对 | LLM-as-judge 打 0–1 分 | LLM-as-judge 为主，含 G-Eval 自定义裁判 |
| 是否需要 LLM 调用 | **不需要** | 默认需要 | 需要（每个用例一次以上推理） |
| 是否需要参考答案 | 需要**期望目标标注**（不是参考答案） | 部分指标需要 reference | 视 metric 而定 |
| 结果可复现性 | 完全相同输入 → 完全相同输出 | 换 judge 模型就换尺子，需冻结并重基线 | 同 |
| 运行时依赖 | **零**（纯标准库） | ragas + datasets（及 judge 客户端） | deepeval（50+ metrics，含模型客户端） |
| 许可证 | Apache-2.0 | Apache-2.0 | Apache-2.0 |

RAGAS 与 DeepEval 的强项是**答案质量**：faithfulness、answer relevancy、
context precision / recall、幻觉检测、G-Eval 自定义评分、Agent 的
tool correctness / task completion。这些 RAGAudit 一概不做，也不打算做——
用 LLM 当裁判去评「召回对不对」，等于在测量仪器里再插一个黑盒，
裁判自己漂了，指标就跟着漂。

---

## 二、能力对照（RAGAudit 独有的部分）

| 能力 | RAGAudit | RAGAS | DeepEval |
|---|---|---|---|
| 双口径并列，**量化虚高** | ✅ `lenient` / `strict` 差值即虚高 | ❌ 一个指标一个数 | ❌ |
| 部件**消融归因** | ✅ `ablate` 内置，ΔHit@1 直接给 | ⚠️ 自己写循环 + 自己保证变量单一 | ⚠️ 同，靠人保证 |
| 题库**信息泄漏画像** | ✅ 自动分 explicit / alias / partial / implicit | ❌（testset generator 反而可能产出「问句里写着答案」的题） | ❌ |
| 逐条**回归 diff** | ✅ 按问句内容哈希对齐，区分 fixed / broke / added / **removed** | ⚠️ 需自建（`to_pandas()` 后自己比） | ⚠️ pytest 报失败，但没有逐条语义归因与移除检测 |
| **删题涨分**检测 | ✅ `removed` 单独报出 | ❌ | ❌ |
| 失败**归因到环节** | ✅ `layer_miss`（路由）/ `target_miss`（排序） | ❌ 只有分数 | ❌ 只有 reason 文本 |
| 零依赖 / 秒级跑完 | ✅ 单测 34 用例 0.01s；85 条真实题热缓存 16s、冷启 60s | ❌ 需 judge 模型，通常分钟级 | ❌ 同 |
| 答案质量（faithfulness 等） | ❌ 不做 | ✅ 核心能力 | ✅ 核心能力 |
| Agent 行为评测 | ❌ 不做 | ⚠️ 有限 | ✅ tool / step / task 指标 |

> 关于耗时：34 用例 0.01s 是 RAGAudit 自己的单元测试；85 条真实题是接 NaviRAG
> 真实检索器的实测（[`docs/case-navirag.md`](case-navirag.md)）。
> RAGAS / DeepEval 的耗时取决于 judge 模型与网络，**未做实测**，只给量级判断。

---

## 三、为什么不用 LLM 当裁判

这不是「LLM 不够聪明」，是**测量学问题**：

1. **不可复现**。同一份数据换 judge 模型、换温度、换版本，分数就变。
   而审计的结论要能被人复核——复核者手上必须有一把不会自己动的尺子。
2. **它会把两个问题混在一起**。「召回错了」和「答得不好」在 LLM 打分里
   是一个数，改完不知道修哪个。RAGAudit 用「期望层 + 期望目标」把
   「召回哪一条」单独拎出来判定。
3. **它自己也可能被判错**。本地小模型（如 qwen3:8b）做裁判时，
   对中文实体名的判定稳定性不足以支撑 0.1 个百分点的差异，
   而回归检测恰恰要看这种小差异。

这也是 RAGAudit 敢说「零依赖」的原因：能被逐行核对的打分逻辑，
才配用来判断别人的系统。

---

## 四、怎么配合用

推荐分工，不是二选一：

```text
检索层（召回了哪几条）      → RAGAudit      确定性、可复现、进 CI 做门禁
生成层（答案好不好、有没有幻觉）→ RAGAS / DeepEval
整条链路的行为断言（Agent）   → DeepEval（pytest 形态最顺手）
```

一个具体做法：**用 RAGAudit 守住检索不退化，用 RAGAS 守住答案不退化。**
前者零成本、秒级、任意 PR 都能跑；后者按天/按版本跑，控制 judge 成本。

---

## 五、诚实说明局限

- RAGAudit **完全不评估生成质量**。一个 Hit@1 94% 的系统照样可能答得一团糟。
- 它要求评估集带**期望层 + 期望目标**标注——没有标注就没有它，
  这比 RAGAS 的 reference-free 用法门槛更高。
- `lenient` / `strict` 两套口径只覆盖「命中判定」这一层，
  不解决「评估集本身写得对不对」。`lint` 能查重复、查泄漏，查不了语义错误。
- 与 RAGAS / DeepEval 的指标**不可直接换算**：RAGAudit 的 Hit@1 与
  RAGAS 的 context precision 问的不是同一件事，不要拿两个数字比大小。

---

## 附：事实核验状态

| 项 | 状态 |
|---|---|
| RAGAS 核心指标构成（faithfulness / answer relevancy / context precision / context recall） | 已核验（官方文档与 2026 年多方评测文一致） |
| RAGAS / DeepEval 许可证 Apache-2.0 | 已核验（各自仓库 LICENSE） |
| DeepEval 50+ metrics、G-Eval、pytest 形态、Agent 指标 | 已核验（官方文档与 2026 年评测文一致） |
| RAGAS testset generator 可能生成泄漏题 | **推断**：生成器从文档反推问题，不保证问句不含实体名；本仓库未做实验验证 |
| 具体耗时/价格数字 | **未核验**，本文不引用任何价格，避免过期误导 |
