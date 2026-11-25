# config：训练侧配置

训练侧的配置入口：YAML 继承、按段校验、配置指纹、环境参数，以及按配置找特征目录。签名见 [`docs/interfaces.md`](../interfaces.md) 里的同名模块。服务不读这些口径；服务读模型包里记下的东西。

## `drisk_training.config.catalog`

按 `Settings` 里的 `paths.features` 找特征目录，把目录错误翻译成配置错误，训练侧只处理一种异常。

### `load_catalog`

从配置指定的路径读出 `FeatureCatalog`。

**用法**：传 `Settings` 和仓库根目录；它拼出 `root / settings.paths.features`，再交给 `FeatureCatalog.from_yaml`。训练侧读目录都走这里，不自己拼路径。

**出错抛什么**：目录文件不存在、YAML 错、schema 不合法等 `CatalogError` 会被包成 `ConfigError`，消息以“特征目录有问题”开头；调用方只需要接 `ConfigError`。

**谁在用**：预处理 C-L1b 等训练侧读目录的地方。

```python
from pathlib import Path

from diabetes_risk.core.catalog import FeatureCatalog
from drisk_training.config.catalog import load_catalog
from drisk_training.config.loader import ConfigError, load_settings

settings = load_settings(Path("configs/experiments/final15.yaml"))
catalog = load_catalog(settings, Path("."))
direct = FeatureCatalog.from_yaml(Path("configs/features.yaml"))
assert catalog.catalog_hash == direct.catalog_hash
assert catalog.input_columns == direct.input_columns

try:
    load_catalog(settings, Path("no-such-root"))
except ConfigError as exc:
    assert "特征目录" in str(exc)
else:
    raise AssertionError("目录不存在应转成 ConfigError")
```

## `drisk_training.config.env`

环境参数走 `DRISK_` 前缀的环境变量，也可以写在当前目录的 `.env`；密钥不进 Git。

### `EnvSettings`

只从环境读的入口配置，目前是日志级别和日志格式。

**用法**：`EnvSettings()` 读 `DRISK_LOG_LEVEL`（默认 `INFO`）和 `DRISK_LOG_FORMAT`（默认 `console`，可选 `json`）。环境变量优先于 `.env`；不认识的变量忽略，不报错。

**出错抛什么**：`log_format` 不是 `json` / `console` 时抛 pydantic `ValidationError`，消息里带 `log_format`。

**谁在用**：训练侧入口在配置日志前读它；它不从 YAML 读口径。

```python
import os

from drisk_training.config.env import EnvSettings

os.environ["DRISK_LOG_LEVEL"] = "DEBUG"
os.environ["DRISK_LOG_FORMAT"] = "console"
settings = EnvSettings()
assert settings.log_level == "DEBUG"
assert settings.log_format == "console"

try:
    EnvSettings(log_format="xml")
except ValueError as exc:
    assert "log_format" in str(exc)
else:
    raise AssertionError("非法日志格式应抛 ValueError")
```

## `drisk_training.config.loader`

YAML 的继承、深合并、校验和指纹；业务代码只走 `load_settings` 一个入口。

### `ConfigError`

配置文件找不到、YAML 写错、`extends` 断链或成环、字段校验失败时抛出的异常。

**用法**：由 `load_raw`、`load_settings` 和 `load_catalog` 抛出；调用方用 `except ConfigError` 接住，或统一用 `except DriskError`。

**出错抛什么**：它是 `DriskError` 的子类；消息尽量带文件路径和字段名，方便使用者自己改配置。

**谁在用**：命令行入口、训练侧读配置的地方。

### `deep_merge`

把覆盖字典合并到基础字典上：字典递归合并，列表和标量整体替换。

**用法**：返回新字典，不修改传入的两个字典；列表不做逐项合并，这是有意的，避免实验配置只覆盖半张列表。

**出错抛什么**：没有自定义异常；传入的不是字典时由 Python 自己抛。

**谁在用**：`load_raw` 展开 `extends` 时，以及配置测试。

### `load_raw`

读一个 YAML，展开 `extends`，返回还没校验的字典。

**用法**：调试配置继承、或要在校验前看原始结构时用；业务代码不要用它代替 `load_settings`。返回的字典已经合并完，`extends` 键被去掉。

**出错抛什么**：文件不存在、YAML 语法错、`extends` 不是字符串、断链或成环、顶层不是字典，都抛 `ConfigError`。

**谁在用**：`load_settings` 和配置测试；命令行不直接用它。

### `load_settings`

读配置的正式入口：展开 `extends`、深合并、按 `Settings` 校验，返回配置对象。

**用法**：`load_settings(Path("configs/experiments/final15.yaml"))`；训练侧所有命令都从这里拿 `Settings`，不自己读 YAML。

**出错抛什么**：任何读文件、继承或校验问题都转成 `ConfigError`；pydantic 的 `ValidationError` 不会漏给调用方。

**谁在用**：`prepare`、`train` 等训练侧入口。

### `config_hash`

给校验后的 `Settings` 算配置指纹。

**用法**：只接受 `Settings`；按合并、校验后包含默认值的 `model_dump()` 算 SHA256，返回 64 位小写十六进制。写进 manifest 或训练记录，用来回答“这次训练用的是哪份配置”。

**出错抛什么**：没有自定义异常；传入的不是 `Settings` 时按对象自身行为抛。

**谁在用**：manifest、训练记录。

```python
from pathlib import Path

from drisk_training.config.loader import (
    ConfigError,
    config_hash,
    deep_merge,
    load_raw,
    load_settings,
)

assert deep_merge({"a": {"x": 1}, "b": [1, 2]}, {"a": {"y": 2}, "b": [3]}) == {
    "a": {"x": 1, "y": 2},
    "b": [3],
}

raw = load_raw(Path("configs/experiments/final15.yaml"))
assert raw["project"]["experiment"] == "final15"
assert raw["label"]["window_days"] == 90
assert "extends" not in raw

config_path = Path("configs/experiments/final15.yaml")
settings = load_settings(config_path)
fingerprint = config_hash(settings)
assert fingerprint == config_hash(load_settings(config_path))
assert len(fingerprint) == 64

try:
    load_settings(Path("configs/features.yaml"))
except ConfigError as exc:
    assert "project" in str(exc)
else:
    raise AssertionError("不是训练配置的 YAML 应抛 ConfigError")

try:
    load_settings(Path("no-such-config.yaml"))
except ConfigError as exc:
    assert "找不到配置文件" in str(exc)
else:
    raise AssertionError("文件不存在应抛 ConfigError")
```

## `drisk_training.config.sections`

配置的五个段和根对象：`ProjectSection`（项目名、实验名、种子）、`PathsSection`（数据目录、特征目录）、`DataSection`（原始库、截止日期）、`LabelSection`（窗口、报告延迟、阳性阈值）、`SplitSection`（训练/验证边界）。每段都是 `extra="forbid"` 且冻结，配置随功能生长；没实现的段不预留。

### `Settings`

校验后的整份配置，训练侧所有口径都从这里读。

**用法**：由 `load_settings` 返回；按 `project`、`paths`、`data`、`label`、`split` 五段读。`train_last_visit` 是 `split.train_end` 往前推 `label.maturity_days`（窗口加最大报告延迟）得到的最后就诊日；`raw_db_path(root)` 把 `paths.data_dir` 和 `data.raw_db` 拼到根目录下。日期必须满足 `train_end < valid_start <= valid_end <= data.as_of`。

**出错抛什么**：加载时不满足字段约束、日期顺序、多余字段，抛 pydantic `ValidationError`，由 `load_settings` 转成 `ConfigError`；拿到 `Settings` 后再赋值会抛 `ValidationError`（对象是冻结的，消息含 frozen）。

**谁在用**：训练侧所有命令。

```python
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from drisk_training.config.loader import load_settings

settings = load_settings(Path("configs/experiments/final15.yaml"))
assert settings.project.experiment == "final15"
assert settings.label.window_days == 90
assert settings.label.maturity_days == 120
assert settings.train_last_visit == date(2024, 3, 2)

root = Path("repo-root")
assert settings.raw_db_path(root) == root / "data" / "raw" / "incident.db"

try:
    settings.label.window_days = 60
except ValidationError as exc:
    assert "frozen" in str(exc).lower()
else:
    raise AssertionError("配置段是冻结的，赋值应抛 ValidationError")
```
