# 规格卡 A5：接口快照（`scripts/api_snapshot.py`、`docs/interfaces.md`）

## 概要

1. **定位**：把地基的公开接口写进仓库，由测试守着：改了已有接口，质量门就红。
2. **输出**：`scripts/api_snapshot.py`（不带参数时和代码比对；`--write` 重新生成；`--compare <仓库>` 和另一个仓库对照）；`docs/interfaces.md`；架构测试 `tests/architecture/test_api_snapshot.py`。
3. **使用者与用法**：卷二起的每一步。开工前查 `docs/interfaces.md`；新增了公开接口，同一次提交里由人运行 `uv run python scripts/api_snapshot.py --write`，交付时贴出它的 diff。
4. **输入与依赖**：只用标准库（`importlib`、`inspect`、`pkgutil`）；读三个包的源码目录。
5. **分量**：高。从这一步起，地基接口“只许新增、不许改”由机器检查。可一步回退。
   路线：全部八步（② 调研：卷一用的仓库外工具 `tools/snapshot_api.py`）。计划档位：P2。
6. **边界**：不列文档字符串和私有名字；不判断是不是破坏性变更，只判断变没变；不改地基的任何代码。
7. **成功的样子**：
   - `docs/interfaces.md` 和代码逐行一致；改一个签名，质量门变红；
   - `--compare` 的每一处差异都带上所属的类名；
   - 模块按固定顺序自动找到，不用手工列清单。
8. **未决问题**：无。

## 精确决定

### 接口

| 命令 | 约定 |
|---|---|
| `uv run python scripts/api_snapshot.py` | 和代码比对；一致时打印“接口快照：和代码一致”，不一致时退出码 1 并打印差异 |
| `--write` | 重新生成 `docs/interfaces.md`，只由人运行 |
| `--compare <仓库>` | 和另一个仓库的快照对照；差异行带上所属的类名 |

### 不变量

1. 只列公开名字的签名，不列文档字符串：全班的说明写法不同，签名相同才算接口相同。
2. 模块按包内路径排序，输出与导入顺序无关。

### 错误与报错文字

- 不一致时说明：以 `-` 开头的是标准里有、你没有的；以 `+` 开头的是你多出来或写得不一样的。

### 位置与依赖方向

- `scripts/api_snapshot.py`；`docs/interfaces.md`；测试在 `tests/architecture/`。

### 证明

- `uv run pytest tests/architecture/test_api_snapshot.py`：全绿
- 变异测试：快照漏列一个模块、把私有名字列进去、差异行不带类名 …… 每一种都让测试变红

### 升级条件

- 快照里出现你没打算公开的名字：改代码（加下划线），不要删快照里的行。

### 审查项

- `--write` 由人运行，不让智能体顺手运行。