# 地基 API 说明

这里说明卷一地基“怎么用、会抛什么、谁在用”，不抄签名。签名以 [`docs/interfaces.md`](../interfaces.md) 为准；那份文件由 `uv run python scripts/api_snapshot.py --write` 从代码生成，并由 `tests/architecture/test_api_snapshot.py` 守住。

## 页面

- [core.md](core.md)：`diabetes_risk.core.catalog`、`diabetes_risk.core.errors`、`diabetes_risk.core.registry`、`diabetes_risk.core.repro`。
- [observability.md](observability.md)：`diabetes_risk.observability.log`、`diabetes_risk.observability.timing`。
- [config.md](config.md)：`drisk_training.config.catalog`、`drisk_training.config.env`、`drisk_training.config.loader`、`drisk_training.config.sections`。

## 每节怎么读

每个公开函数和类都有一节，按“做什么 → 用法 → 出错抛什么 → 谁在用”四部分写。这里只写调用者需要知道的事；参数类型、默认值和返回类型看 `docs/interfaces.md`。

## 示例

页面里的 Python 示例都由 `tests/architecture/test_api_docs.py` 逐段启动独立进程运行，工作目录是仓库根。示例只读仓库里的 `configs/`，并使用已经安装的包；改了地基接口却没有同步改示例，架构测试会红。
