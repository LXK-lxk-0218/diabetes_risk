# AGENTS.md：给编程智能体的规则

> 只写已经存在的东西。每完成一步，在第四节追加本步新增的规则；不提前写后面步骤的规则。

## 一、怎么算完成

- 唯一标准：`uv run python scripts/ci.py` 全绿（ruff 检查、ruff 格式、mypy、import-linter、pytest + 覆盖率）。
- 跑质量门之前，先 `uv run ruff format .` 和 `uv run ruff check --fix .`，让格式和导入顺序自动对齐。
- 每一步至少留下一条能运行的命令，或一组能运行的测试。

## 二、绝对不要做

1. 不降低任何门槛：覆盖率 `fail_under`、ruff 规则、mypy 选项、import-linter 契约。
2. 不删除、不跳过、不放宽已有断言来让测试通过。
3. 不修改 `sys.path`，不调用 `os.chdir`，不在 pytest 配置里加 `pythonpath`。
4. 不改 `baselines/` 下的任何文件；结果对不上基线时，报告差异并停下来。
5. 不写指向未来步骤的占位：TODO、空函数、预留字段、预留配置段。
6. 契约文件（数据集 manifest、模型包元数据、预测记录 schema、OpenAPI）改动之前先问人。
7. 不创建 `.github/`。

## 三、仓库约定

- 三个包：`packages/core`（导入名 `diabetes_risk`）、`packages/training`（`drisk_training`）、`services/api`（`drisk_api`）。
- 依赖方向：core 不依赖另外两个；training 与 api 互不依赖。
- 运行时依赖用 `uv add --package <发行名> <依赖>`，开发工具用 `uv add --dev <依赖>`；不要手改 `uv.lock`。
- 测试数据在测试里现造，不依赖 `data/` 下的文件。

## 四、各步骤追加的规则

### A1

- 新增顶层目录之前，先确认它在 `docs/steps/` 的规划里。
- 不改 `data/frozen/` 与 `data/raw/` 下的冻结数据（`tests/test_architecture.py` 守护指纹）。

### A2

- “同类、可替换、会增长”的组件用 `diabetes_risk.core.registry.Registry` 注册；注册名一经发布不再修改。
- 写日志用 `diabetes_risk.observability.log.get_logger(__name__ 或模块名)`；事件名用英文“动词_名词”；日志里不写特征值和居民标识。
- 阶段计时用 `timed()`；耗时发到哪里用 `use_emitter()` 在调用时设置，不要写进装饰器参数。
- 指纹统一用 `diabetes_risk.core.repro`（`sha256_file`、`sha256_json`），不要另写一份。
- 可预期的业务错误继承 `DriskError`。