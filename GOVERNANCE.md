# 治理

项目现在很小，治理写得比实际需要的细是浪费。但**规则要在还没争议的时候定下来**，
等出现分歧再定，定的就是当时谁嗓门大。所以这份文档只写真正会用到的部分。

## 角色

| 角色 | 权限 | 怎么获得 |
|---|---|---|
| **Contributor** | 提 Issue、提 PR | 提一个被合并的 PR 即算 |
| **Reviewer** | 审批 PR（不含合并） | 累计 3 个被合并的 PR，且质量稳定，由 Maintainer 邀请 |
| **Maintainer** | 合并 PR、发布版本、任命 Reviewer | 长期贡献并由现有 Maintainer 一致同意 |

当前 Maintainer：[@MaPleooo9](https://github.com/MaPleooo9)

单人是现状，不是设计。v1.0 之前的目标是把 Maintainer 变成至少两人——
单人维护的项目在「长期发展」上是明确的风险项，这一点不需要粉饰。

## 决策

**默认走懒人共识**：没人反对就通过。以下情况才需要显式表态：

| 变更类型 | 需要什么 |
|---|---|
| 文档、测试、注释、示例 | 1 位 Reviewer 批准 |
| 修 bug、加适配器、加判定规则 | 1 位 Maintainer 批准 |
| **改变指标定义或判定口径** | 2 位 Maintainer 批准 + PR 里前后数据对比 |
| **破坏性 API 变更** | 2 位 Maintainer 批准 + 迁移说明 + 次版本号 |
| 新增运行时依赖 | 需要说明为什么不能用标准库实现 |

第二类之所以门槛最高：指标定义是这整个项目的契约。
口径悄悄变了，所有引用过这份报告的人都得重新理解一遍结论，成本远大于一次代码重构。

分歧无法达成一致时，由 Maintainer 投票，简单多数；平票时由发起人重新提案。
投票过程和理由公开在 Issue 里。

## 发布

- 遵循[语义化版本](https://semver.org/lang/zh-CN/)
- `CHANGELOG.md` 用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 结构
- v1.0 之前不保证 API 稳定，但**每次破坏性变更都会在 CHANGELOG 的 `Changed` 段里明确写出来**

## 响应承诺

| 事项 | 目标 |
|---|---|
| Issue 首次回复 | 7 天内 |
| PR 给出结论 | 14 天内 |
| 安全问题的初次响应 | 72 小时内（见 [SECURITY.md](SECURITY.md)） |

做不到时会明说，不静默挂着。一个挂着不回的 Issue 比明确拒绝更消耗人。

## 行为

参与本项目即视为同意 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。
违规处理由 Maintainer 执行，处理结果在处理记录 Issue 里公开（涉及个人隐私的部分除外）。
