# 许可证与第三方依赖清单

> 本文件回答一个具体问题：**把 RAGAudit 交出去时，里面有多少别人的代码，
> 各自的许可证允许什么、不允许什么。**
> 所有版本号与许可证字段为机器读取所得（可复现），未经法律审阅。

---

## 一、本项目

| 项 | 值 |
|---|---|
| 本项目许可证 | **Apache-2.0**（见 [LICENSE](../LICENSE)） |
| 运行时依赖 | **无**。`pyproject.toml` 里 `dependencies = []`，全部实现基于 Python 标准库 |
| 分发包内容 | 只有 `ragaudit/` 自身的源码 + 元数据 |
| 开发期依赖 | `pytest>=8`（MIT），仅 `pip install -e ".[dev]"` 时安装，不进入运行时 |
| CI | GitHub Actions：`actions/checkout@v4` / `actions/setup-python@v5` / `actions/upload-artifact@v4`（均 MIT），仅在 GitHub 侧执行 |
| 构建期依赖 | `setuptools>=68`（MIT） |

**结论：`pip install ragaudit` 或直接 clone，都不会把任何第三方代码带进你的项目。**
这不是洁癖——一个要用来判断别人系统可信度的工具，自身链路越短越容易被核对。

---

## 二、可选真实案例的依赖（`examples/elden-ring`）

真实案例要把 NaviRAG 的检索器跑起来，就必须装它那一套。**这些包不属于
ragraudit，也不随本项目分发**，只有你想复现 `docs/case-navirag.md` 时才需要。

### 直接依赖

| 包 | 本次实测版本 | 许可证 | 用途 |
|---|---|---|---|
| chromadb | 1.5.9 | Apache-2.0 | 向量库 |
| sentence-transformers | 6.2.0 | Apache-2.0 | 本地 embedding |
| torch | 2.14.1 | Apache-2.0 / BSD / BSL-1.0（多许可组合） | 推理后端，CPU 版 |
| numpy | 2.5.4 | BSD-3-Clause / 0BSD / MIT / Zlib / CC0-1.0 | 数值计算 |
| requests | 2.34.2 | Apache-2.0 | 数据抓取（NaviRAG 构建期） |

### 传递依赖

共 **103 个包**（含上述直接依赖）。完整清单（包名 / 版本 / 许可证）
见 [`licenses-deps.txt`](licenses-deps.txt)，由 `importlib.metadata` 自动遍历生成。

许可证分布：

| 许可证族 | 数量 | 性质 |
|---|---|---|
| Apache-2.0（含 `Apache Software License` / `Apache 2.0 License` 写法） | 36 | 宽松，含专利授权 |
| MIT | 34 | 宽松 |
| BSD（2/3 条款，含 `3-Clause BSD License` 写法） | 28 | 宽松 |
| PSF-2.0 | 2 | 宽松 |
| ISC | 1 | 宽松 |
| MPL-2.0 | 3 个包参与（certifi、tqdm、orjson） | **文件级** copyleft |
| 多许可组合 | torch / numpy / regex / aiohttp / packaging 等 | 均为宽松许可的组合 |

### 合规结论

- **没有 GPL / AGPL / LGPL 依赖**（已对 103 个包做全文匹配，零命中）。
  因此不存在传染性条款把本项目拖成 GPL。
- **MPL-2.0 的三个包是文件级 copyleft**：只要不修改它们的源文件、
  以未修改形式作为依赖使用，不会影响以 Apache-2.0 分发本项目。
- **本项目不重新分发这些包**：没有 vendored 代码，没有把 wheel 打进仓库。
  使用者自己 `pip install`，许可证关系发生在使用者与各包作者之间。
- `torch` 的许可证是多许可拼接（Apache-2.0 WITH LLVM-exception、BSD-2/3、
  BSL-1.0、MIT），全部为宽松许可，可商用。

> 若要**打包分发**一个含这些依赖的二进制（例如做成单文件 exe），
> 需要另外附上各包的 LICENSE 与 NOTICE。本仓库不做这件事。

---

## 三、数据与内容版权

| 资产 | 来源 | 授权状态 |
|---|---|---|
| `examples/elden-ring/suite.json`（85 条评估集） | NaviRAG 仓库 `data/elden_ring/eval_set.json` | NaviRAG 以 Apache-2.0 发布；本仓库随项目以 Apache-2.0 分发。已核对两者**逐字节一致** |
| `examples/elden-ring/out/*.json`（逐条运行结果） | 本次运行生成 | 本项目产出，Apache-2.0 |
| 报告中出现的 Boss 名、地名、道具名 | 《艾尔登法环》(ELDEN RING) | 名称权利归 FromSoftware / 万代南梦宫。此处仅作**事实性指代**（指明评测对象是哪个实体），不复制游戏文本、不复制 wiki 正文、不收录任何游戏资源文件 |
| `examples/toy/*` | 本项目虚构数据 | Apache-2.0 |

**没有收录**：游戏图片、音频、模型文件、wiki 正文段落。评估集里只有
「问句 + 期望层 + 期望实体名」，属于功能性标注。

---

## 四、核验状态（诚实标注）

| 项 | 状态 |
|---|---|
| 运行时零依赖（`dependencies = []`） | **已验证**：`pip install .` 后 `pip show ragaudit` 无 Requires |
| 103 个包无 GPL/AGPL | **已验证**：对元数据许可证字段全文匹配 `GPL`，零命中 |
| 各包版本号 | **已验证**：本次运行环境实测 |
| 许可证字段与官方仓库一致 | **未逐包比对**。元数据可能滞后或填写不规范（例如 `torch` 只写组合字符串），需要精确结论时请查各包仓库的 LICENSE |
| 法律审阅 | **无**。本文件是工程侧清单，不构成法律意见 |

---

## 五、复现

```bash
# 生成完整依赖清单（在装好真实案例依赖的环境里执行）
python - <<'PY'
import importlib.metadata as im
for d in sorted(im.distributions(), key=lambda x: x.metadata["Name"].lower()):
    m = d.metadata
    lic = (m.get("License-Expression") or "").strip()
    if not lic:
        cls = [c for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
        lic = cls[0].split("::")[-1].strip() if cls else (m.get("License") or "UNKNOWN")
    print(f"{m['Name']}\t{d.version}\t{lic}")
PY
```
