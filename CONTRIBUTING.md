# 贡献指南

谢谢你想改这个项目。这份文档只写**真的会被检查的东西**，
省掉那些「请保持友善」之外的套话（友善那条在 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)）。

## 环境

```bash
git clone https://github.com/MaPleooo9/RAGAudit.git
cd RAGAudit
python -m unittest discover -s tests -p "test_*.py"
python examples/toy/run_demo.py
```

不需要装任何依赖。项目刻意保持零运行时依赖，**提交的 PR 也不应该引入新的运行时依赖**——
评估工具本身要是黑盒，它的结论就没法用来判断别人。开发工具（pytest、build）不受此限。

## 提交之前

三件事，缺一不可：

1. `python -m unittest discover -s tests -p "test_*.py"` 全绿
2. `python examples/toy/run_demo.py` 能跑完并生成三份报告
3. 改了判定口径、指标定义或报告结构 → **同步更新 `docs/metrics.md`**

第 3 条最容易漏。指标口径变了但文档没变，等于给后来的人埋了一个
「数字对不上」的坑，而这类问题在评测工具里是致命的。

## 提交什么最有价值

按优先级：

| 类型 | 例子 |
|---|---|
| **新的判定规则** | 领域专用的匹配逻辑（编号归一化、单位换算） |
| **适配器** | 接 LangChain / LlamaIndex / Chroma 的结果格式 |
| **评估集质量问题** | lint 能发现但当前没覆盖的坏味道 |
| **报告可读性** | 结论不清楚、表格放不下的地方 |
| 性能 | 万级评估集下的耗时（当前是纯串行） |

**不建议提交**：引入 LLM 打分的功能。这不是技术难度问题，是定位问题——
这个项目测的是「召回哪一条」，用 LLM 当裁判会把两个问题混在一起，
且结果不可复现。需要 LLM 打分的场景请用 RAGAS / DeepEval。

## 新增一条判定规则

```python
# ragaudit/matchers.py
@register_rule("my_rule")
def _my_rule(doc: Doc, case: Case) -> bool:
    """一句话说明这条规则在什么情况下比内置规则更合适。"""
    return ...
```

然后：

1. 在 `tests/test_schema_matchers.py` 补一个用例，**至少要有一个 false 的断言**
   （只测命中不测不命中，规则写反了也测不出来）
2. 在 `docs/metrics.md` 说明它和 `lenient` / `strict` 的关系

## 提交信息

中文，一句话说清改了什么，不要写 `update`、`fix bug`。

```
新增 unit_normalize 判定规则，解决「100QPS」与「100 qps」判不中的问题
修正 by_group 在空分组下除零
```

## PR

- 一个 PR 只做一件事。顺手改的无关代码会让 review 变成猜谜。
- 描述里写**为什么**，diff 已经说明了**是什么**。
- 涉及指标口径变化的 PR，请在描述里贴出 toy 演示前后的两组数字。

## 报告问题

用 [Issue 模板](.github/ISSUE_TEMPLATE/) 提。判断类问题请附：

- 评估集里的那一条（`query` / `expect_layer` / `expect_target`）
- 检索器实际返回的前 3 条
- 你期望的判定结果和实际结果

没有这三样，判断类 bug 基本无法复现。

## 流程

1. Fork → 新分支（`feat/xxx` 或 `fix/xxx`）
2. 改代码 + 补测试
3. 提 PR，等 CI 绿
4. 至少一位 Maintainer 批准后合并

响应时间目标：Issue 7 天内首次回复，PR 14 天内给出结论。
做不到的时候会在 Issue 里明说，而不是静默挂着。

## 许可证

提交即表示同意以 [Apache-2.0](LICENSE) 授权你的贡献。
