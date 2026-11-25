# 加固：向参考实现对齐（2026-11-25）

- 目标：吸收参考实现里更严的部分：接口说明可执行、验收测试分层、架构测试拆细、智能体规则更严、核心语义更严格。
- 验收：`uv run python scripts/ci.py` 全绿（228 个测试）；覆盖率 98.68%；`final15` 的目录指纹仍是 `ce82b3edbf8b`、配置指纹 `5c77cdcc612b`。
- 不做：派生字段计算；任何读数据的代码；不给卷二以后的模块写说明。

## 代码语义

- `core/registry.py`：名字判定改用 `fullmatch`（`"logreg\n"` 不再合法）；`_check_new` 集中校验；新增 `values()`。
- `core/catalog.py`：拒绝 YAML 重复键（`_UniqueKeyLoader`）；`REQUIRED_FORBIDDEN` 在 `CatalogSpec` 里强制；`fields` 不能为空；字段必须按 numeric → binary → categorical 排列；`FeatureCatalog` 用 `__slots__`。
- `observability/log.py`：脱敏递归到任意深度的字典/列表；时间戳改 UTC（`Z` 结尾）；格式化异常进 `exception` 字段；校验日志格式；`_LazyLogger` 保证先取日志器、后配置也生效。
- `observability/timing.py`：日志写不出去也不拖垮业务；阶段名必须是字符串。
- `config/loader.py`：`deep_merge` 接受任意 `Mapping`；YAML 语法错误包成 `ConfigError`；`extends` 必须是相对路径字符串；`load_raw(path)` 不再暴露内部递归参数。
- `config/catalog.py`：只做定位，把 `CatalogError` 翻成 `ConfigError`；`check_catalog` / `MUST_BE_FORBIDDEN` 移到 core 的强制校验里。
- `config/__init__.py`：门面只导出 YAML 配置相关名字（`EnvSettings` 从 `drisk_training.config.env` 导入）。
- `scripts/ci.py`：`Gate` NamedTuple + `gates()`；`lint-imports --no-logo`。

## 测试

- 新增 `tests/acceptance/`（6 个文件，130 个用例）：用法 → 契约 → 性质三层，只走公开入口。
- 新增 `tests/architecture/test_dependencies.py`（3 个）、`test_quality_gate.py`（2 个）、`test_api_docs.py`（3 个）。
- `tests/architecture/test_layout.py`：拆出“真的装进了环境”的测试；新增 `CLAUDE.md` 引用检查。
- `tests/architecture/test_rules.py`：分层契约检查移到 `test_dependencies.py`，断言不变。

## 文档与规矩

- 新增 `docs/api/`（README + core + observability + config）：每个公开函数/类一节，示例逐段可运行。
- `AGENTS.md` 重构为六节（项目、完成标准、禁止项、干活流程、仓库约定、各步规则），追加 A5 与加固规则。
- 新增 `CLAUDE.md`（第一行 `@AGENTS.md`）。
- `.gitattributes` 标注 `*.parquet`、`*.db` 为二进制；`.gitignore` 增加 `.idea/`。

## 接口变化（快照 diff）

- 新增：`REQUIRED_FORBIDDEN`、`Registry.values`。
- 私有化：`FieldSpec` / `CatalogSpec` 的校验方法、`Processor`、`P`、`R`、`EXTENDS`。
- 移除：`MUST_BE_FORBIDDEN`、`check_catalog`（逻辑上移到 `CatalogSpec` 的强制校验）。
- 签名收紧：`deep_merge` 参数改 `Mapping`；`load_raw(path)` 去掉内部参数。
