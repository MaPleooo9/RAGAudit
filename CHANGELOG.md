# 变更记录

格式参照 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- LangChain / LlamaIndex / Chroma 结果适配器
- HTML 报告输出
- GitHub Action：PR 中自动贴出退化清单
- `--fail-on-regression N` 阈值退出码

## [0.2.0] - 2026-10-24

第一个接上真实系统的版本：从「能跑演示」变成「审计过真实项目」。
本版没有改判定口径，新增的是可验证性——一个真实案例、一份同类对照、一份依赖合规清单。

### Added

**真实案例（NaviRAG）**
- `examples/elden-ring/navireg_retriever.py`：把 NaviRAG 线上检索器接进本工具的适配器，
  含 5 个只改一个变量的消融变体
- 85 条评估集（原样未改，与 NaviRAG 仓库逐字节一致）跑出真实报告、消融、回归 diff
- `docs/case-navirag.md`：审计结论与和原项目自评报告的逐项交叉验证
  （12.9% / 17.6% / 90.6% / 94.1% / MRR 0.951 五项逐位吻合）

**文档**
- `docs/comparison.md`：与 RAGAS / DeepEval 的能力对照、指标口径差异、分工建议
- `docs/licenses.md` + `docs/licenses-deps.txt`：运行时零依赖说明、真实案例 103 个
  传递依赖的许可证清单（机器生成）、无 GPL/AGPL 的合规结论

### Changed
- 项目定位表述统一为「检索评测审计工具」，README、CLI 描述、包文档、`pyproject` 四处一致
- 单元测试由 33 条增至 34 条

### Fixed
- 回归对比报告只渲染 `fixed` / `broke`，`improved` / `worsened`（仍命中但排名变动）
  被算出来后丢弃。真实案例里正好踩中：关掉别名表后 3 条坏掉、1 条 rank 2→1、
  1 条 rank 1→4，后两条原本完全不可见

## [0.1.0] - 2026-10-23

首个可运行版本。核心是四件事：**查口径、查归因、查题库、查退化**。

### Added

**判定口径**
- `Rubric` 机制：口径按「结果自身有无 target 字段」分派，与层命名解耦
- 内置 `lenient` / `strict` 两套口径，报告并列呈现
- `register_rule` 允许注册自定义规则
- 五条内置规则：`lenient` / `strict` / `exact` / `contains` / `entity` / `title_exact` / `any`

**指标**
- Hit@1 / Hit@3 / Hit@5、MRR、层准确率@1，按分组拆分
- 失败归因：区分 `layer_miss`（层路由错）/ `target_miss`（排序错）/ `empty`（零召回）
- 保留逐条结果，支撑后续 diff

**难度画像**
- 自动判定信息泄漏四级：`explicit` / `alias` / `partial` / `implicit`
- 显式指名占比 > 70% 时 `lint` 警告

**评估集自检 `lint`**
- 重复问句
- 分组样本量不足
- 问句含更长同名实体（实体识别必然指向错误目标）
- 整体泄漏率过高
- 缺失 `expect_layer`

**消融与归因**
- `ablate()` 消融矩阵，ΔHit@1 量化部件净贡献
- 可比子集筛选（`layers` 参数），避免把定位不到某些层的方案放在全集上比
- 自动标出「关掉反而更好」的负收益模块

**回归对比**
- 按问句内容哈希对齐，插题不会导致整体错位
- 分类：fixed / broke / improved / worsened / added / **removed**
- 每条退化给出环节归因

**工程**
- CLI 四个子命令：`run` / `lint` / `diff` / `ablate`
- 零运行时依赖，仅标准库
- 33 个单元测试，0.01 秒跑完
- `examples/toy` 端到端演示（10 条题 / 8 条文档 / 2 个检索变体）
- GitHub Actions：多版本测试 + 演示可运行校验 + 演示报告产物

### 已知限制
- 纯串行执行，万级评估集下会慢
- 报告仅 markdown
- 单维护者

[Unreleased]: https://github.com/MaPleooo9/RAGAudit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/MaPleooo9/RAGAudit/releases/tag/v0.2.0
[0.1.0]: https://github.com/MaPleooo9/RAGAudit/releases/tag/v0.1.0
