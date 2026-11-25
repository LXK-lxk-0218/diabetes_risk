# AGENTS.md：给编程智能体（和新同事）的规矩

> 只写每次开工都要知道、而且已经存在的东西。每完成一步，在第六节追加这一步留下的规矩；不提前写后面步骤的规则。

## 一、这是什么项目

- 社区糖尿病风险筛查的 MLOps 项目：一个仓库、三个包，用 uv 工作区管理（为什么这样分，见 `docs/adr/0001`、`0002`）。
- `packages/core`（导入名 `diabetes_risk`）：训练和服务都要用的最小集合。
- `packages/training`（`drisk_training`）：数据、训练、评估、命令行。
- `services/api`（`drisk_api`）：推理服务。
- 依赖方向：core 不依赖另外两个；training 与 api 互不依赖（`.importlinter` 检查）。

## 二、怎么算完成

- 唯一标准：`uv run python scripts/ci.py` 全绿（ruff 检查、ruff 格式、mypy、import-linter、pytest + 覆盖率）。
- 跑质量门之前，先 `uv run ruff format .` 和 `uv run ruff check --fix .`，让格式和导入顺序自动对齐。
- 每一步至少留下一条能运行的命令，或一组能运行的测试。
- 交付时贴出命令和输出原文；验证不了的话不写。

## 三、绝对不要做

1. 不降低任何门槛：覆盖率 `fail_under`、ruff 规则、mypy 选项、import-linter 契约。
2. 不改 `tests/architecture/`、`tests/acceptance/` 下的测试，也不改 `docs/specs/` 下的规格卡；不删除、不跳过、不放宽任何已有断言。觉得它们有问题，停下来说明。
3. 不修改 `sys.path`，不调用 `os.chdir`，不在 pytest 配置里加 `pythonpath`。
4. 不改 `baselines/` 下的任何文件；结果对不上基线时，报告差异并停下来。
5. 不写指向未来步骤的占位：TODO、空函数、预留字段、预留配置段。
6. 不写 `# type: ignore`、`# noqa`、`# pragma: no cover` 让检查闭嘴。
7. 契约文件（数据集 manifest、模型包元数据、预测记录 schema、OpenAPI）改动之前先问人。
8. 不创建 `.github/`。

## 四、怎么干活

1. 开工先读：本文件、这一步的说明（`docs/steps/` 或 `docs/specs/`）、对应的验收测试（`tests/acceptance/`）和 `docs/api/`。
2. 先跑一次验收测试，说清哪些红、为什么红；再说计划：要新建、修改哪些文件，每个公开名字的签名，打算怎么证明做对了。等人确认再动手。
3. 每改一轮：`uv run ruff format .` → `uv run ruff check --fix .` → `uv run python scripts/ci.py`。
4. 同一项检查修了三轮还红，停下来报告：贴出失败输出和试过的办法。要改范围以外的文件，也先停下来。
5. 交付顺序：改了哪些文件；`git status --short` 与 `git diff --stat` 的原文；质量门输出的最后几行原文。

## 五、仓库约定

- 三个包：`packages/core`（导入名 `diabetes_risk`）、`packages/training`（`drisk_training`）、`services/api`（`drisk_api`）。
- 运行时依赖用 `uv add --package <发行名> <依赖>`，开发工具用 `uv add --dev <依赖>`；不要手改 `uv.lock`。
- 步骤说明放 `docs/steps/`（每一步的规划与验收数字）；规格卡（若有）放 `docs/specs/`；验收测试放 `tests/acceptance/`：由人维护。公开接口以 `docs/interfaces.md` 为准，不加卡上没有的公开名字（别名、兼容层、预留方法）；为什么这样决定，写在 `docs/adr/`。
- 实现者自己补的测试放 `tests/unit/`：只许加，不许放宽。
- 测试数据在测试里现造，不读 `data/` 下的文件。
- 地基的用法（怎么做、会抛什么、谁在用）写在 `docs/api/`；签名由 `uv run python scripts/api_snapshot.py --write` 生成，不手抄。
- 技能只写在 `.agents/skills/`（Codex、Cursor 等直接读）；`.claude/skills/` 由 `uv run python scripts/sync_agent_files.py` 生成给 Claude Code 读，不要手改。

## 六、各步追加的规则

### A1

- 新增顶层目录之前，先确认它写在 `docs/steps/` 的规划里（或本步规格卡里）。
- 不改 `data/frozen/` 与 `data/raw/` 下的冻结数据（`tests/test_architecture.py` 守护指纹）。

### A2

- “同类、可替换、会增长”的组件用 `diabetes_risk.core.registry.Registry` 登记；具体的表在第一个真实实现出现的那一步才建；注册名一经发布不再修改。
- 可预期、要给使用者看的错误（配置写错、文件不合法）继承 `DriskError`；写代码的人犯的错（重复注册、名字不合法）用标准异常，不包进去。
- 指纹统一用 `diabetes_risk.core.repro`（`sha256_file`、`sha256_json`），不另写一份。
- 阶段计时用 `timed()`；耗时发到哪里用 `use_emitter()` 在调用时设置，不要写进装饰器参数。
- 写日志用 `diabetes_risk.observability.log.get_logger(__name__)`；事件名用英文“动词_名词”；日志里不写特征值和居民标识。表示非个人信息的名字不用裸 `name`（写 `model_name`、`file_name`）：任何一层的 `name` 都会被遮住。

### A3

- 口径数字（窗口天数、阈值、日期）只写在 `configs/*.yaml`，代码里从不出现：一律从 `Settings` 读；环境参数走 `DRISK_` 前缀的环境变量；密钥绝不进 Git。
- 新功能需要配置时，在 `sections.py` 新增一段（`extra="forbid"`、`frozen=True`），同时更新 `configs/base.yaml` 和测试；不为还没实现的功能预留段。
- 实验配置用 `extends` 只写差异，不整份复制。

### A4

- 字段的名字、分组、范围、类别、中文名只写在 `configs/features.yaml`；代码里不再另写一份字段清单，一律从 `FeatureCatalog` 取。
- 新增字段只改 `features.yaml` 并补测试；`forbidden` 里的列任何时候都不能当模型输入。
- YAML 里的 `yes`、`no`、`on`、`off` 要加引号，否则会被读成布尔值。
- 目录只描述 schema，不代替数据校验；二元字段按 0/1 约定。

### A5

- 要用地基里的东西，先查 `docs/api/`（怎么用）和 `docs/interfaces.md`（签名）。需要的功能地基里没有，停下来问人：不要自己加别名、兼容层或新函数。
- 地基的公开接口只许新增。在地基的模块里新增了公开函数或类：同一次提交里运行 `uv run python scripts/api_snapshot.py --write`，并在 `docs/api/` 补一节说明；交付时贴出快照的 diff。已有的行被改或被删，先停下来问人。
- 说明里不抄签名，以 `docs/interfaces.md` 为准；`docs/api/` 由智能体起草、人审：每一句都要能在规格卡、验收测试或代码里找到出处。
- `docs/api/` 的示例要能在仓库根目录直接运行，只读 `configs/`，不读 `data/`。

### 加固（2026-11-25）

- 目录的四条硬约束在 `CatalogSpec` 里强制（关键禁用列、非空、组顺序、重复键），任何入口都绕不过；训练侧只把 `CatalogError` 翻成 `ConfigError`，不再另设一套检查。
- `Registry` 的名字判定用 `fullmatch`：末尾带换行的名字不合法。
- 日志脱敏递归到任意深度的字典和列表；`redact` 只写在 `configure_logging` 里。
- 验收测试（`tests/acceptance/`）与 `docs/api/` 的示例是这一步的“考题”，实现不为让它们变绿而改它们。
