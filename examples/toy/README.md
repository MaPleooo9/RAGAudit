# toy 演示

10 条题 / 8 条文档 / 2 个检索变体，纯标准库，跑完不到 1 秒。

目的是让人**在决定要不要用之前**就能看到工具在做什么，
而不是先装 2GB 的 embedding 模型。

## 跑

```bash
python examples/toy/run_demo.py
```

输出在 `out/`：`report.md`（跑分）、`ablation.md`（消融）、`diff.md`（回归）。

## 文件

| 文件 | 是什么 |
|---|---|
| `corpus.json` | 语料（虚构产品的文档库，与该领域无关，说明工具是通用的） |
| `suite.json` | 评估集，10 条，混了显式指名 / 俗称 / 纯描述 |
| `alias.json` | 俗称表，用于难度画像区分「俗称」和「完全不含实体名」 |
| `retriever.py` | 两个检索变体：`search_v1` 含别名表、`search_v2` 关掉 |
| `variants.py` | 消融定义，供 `ragaudit ablate -v` 使用 |
| `run_demo.py` | 一键跑完全部四件事 |

## 想只跑某一步

```bash
cd examples/toy

ragaudit lint   -s suite.json
ragaudit run    -s suite.json -r retriever:search_v1 --alias alias.json -o out/r.md
ragaudit ablate -s suite.json -v variants.py
ragaudit diff   --base out/v1.json --cur out/v2.json
```

`-r retriever:search_v1` 能在当前目录直接导入，是因为 `retriever.py` 就在 cwd 下。
换成自己的项目时，写完整路径如 `mypkg.retr:search`。

## 下面这些是刻意造的

`corpus.json` 里 `离线部署完整步骤` 这条**没有 `target` 字段**，标题还带了个后缀。
不是懒，是为了让 `lenient`（标题包含）和 `strict`（主实体相等）产生分歧——
演示里那 10 个百分点的虚高就来自它。真实的 wiki 库里这种标题很常见。
