# core：训练和服务共用的地基

`diabetes_risk.core` 是训练和服务都要用的最小集合。签名见 [`docs/interfaces.md`](../interfaces.md) 里的同名模块；这一页只讲调用者需要知道的行为、错误和使用位置。

## `diabetes_risk.core.catalog`

特征目录的只读视图：哪些列能进模型、属于哪一组、范围/类别/中文名。这些元数据只写在 `configs/features.yaml`，训练和服务都从这里取，代码里不另写一份字段清单。

模块还导出三个常量，它们是目录格式的一部分：`Group`（`numeric`、`binary`、`categorical` 三个字面量）、`GROUPS`（固定顺序 numeric → binary → categorical）、`REQUIRED_FORBIDDEN`（`visit_id`、`resident_id`、`visit_date`、`label`，任何目录都必须把它们列进 `forbidden`）。常量不是函数或类，所以不单独成节。

### `CatalogError`

特征目录文件找不到、YAML 写法有错，或目录内容自相矛盾时抛出的异常。

**用法**：由 `FeatureCatalog.from_yaml` 和 `FeatureCatalog.from_dict` 抛出；调用方用 `except CatalogError` 接住，或统一用 `except DriskError` 接住。

**出错抛什么**：它就是 `DriskError` 的子类；`from_dict` 会把 pydantic 的 `ValidationError` 包成它，原始异常留在 `__cause__`。

**谁在用**：预处理、数据契约、API 请求格式、模型包等所有读目录的入口（A4）。

### `CatalogSpec`

`features.yaml` 的完整结构：版本、输入字段、禁用字段、派生字段。

**用法**：通常不直接构造；`FeatureCatalog.from_dict(data)` 把字典交给它校验，`FeatureCatalog` 再提供只读视图。目录版本必须大于等于 1，至少要有一个输入字段。

**出错抛什么**：直接构造不合法时抛 pydantic `ValidationError`；经 `FeatureCatalog` 的两个入口会转成 `CatalogError`。校验包括字段名不重复（含派生字段）、输入字段和派生字段不能同时又出现在 `forbidden`、四个 `REQUIRED_FORBIDDEN` 必须都在 `forbidden` 里、字段按 numeric → binary → categorical 排列。

**谁在用**：目录加载和测试；下游不直接依赖它，用 `FeatureCatalog`。

### `DerivedSpec`

派生字段的登记项：只有名字和中文名，不接收调用方传入的值。

**用法**：`FeatureCatalog.derived_columns` 给出派生字段名，`display_name(name)` 给出中文名；值由特征工程计算（C-L1b）。

**出错抛什么**：直接构造缺字段或多字段时抛 pydantic `ValidationError`；目录加载时统一转成 `CatalogError`。

**谁在用**：特征工程、解释和表单里的中文名。

### `FieldSpec`

一个输入字段的完整规格：名字、分组、中文名、是否必填、数值范围、类别取值。

**用法**：由 `FeatureCatalog.field(name)` 返回。预处理按 `group` 分组；数据契约用 `range` 和 `categories`；API 和解释用 `display_name`。数值字段一定有 `range`，类别字段一定有 `categories`；binary 字段按 0/1 约定，但目录只描述 schema，不校验真实数据。

**出错抛什么**：直接构造不合法时抛 pydantic `ValidationError`；目录加载时转成 `CatalogError`。数值范围必须下限小于上限，类别值不能重复，其他组不能写 `range` 或 `categories`。

**谁在用**：预处理、数据契约、API 请求格式、解释模块（A4）。

### `FeatureCatalog`

对 `CatalogSpec` 的只读视图；下游要的列清单、字段规格、中文名和目录指纹都从这里取。

**用法**：正式读文件用 `from_yaml(Path("configs/features.yaml"))`；测试可直接 `from_dict`。读列用 `input_columns`、`columns(group)`、`derived_columns`；读规格用 `field(name)`、`fields`；读中文名用 `display_name(name)`；读禁用列用 `forbidden`；读指纹用 `catalog_hash`。列顺序就是模型输入顺序；目录指纹由解析后的内容算出，YAML 的注释和缩进不影响它。YAML 里同一层写了两次同一个键会直接报错，不会静默取最后一个。

**出错抛什么**：文件不存在、YAML 错、顶层不是字典、schema 不合法、查不到字段都抛 `CatalogError`；`field` 和 `display_name` 的报错里带字段名。`from_dict` 会把 pydantic 的 `ValidationError` 转成 `CatalogError`。

**谁在用**：预处理 C-L1b、数据契约 B-L1、API 请求格式 E-L1b、模型包 D-L1（A4）。

```python
from pathlib import Path

from diabetes_risk.core.catalog import CatalogError, FeatureCatalog, FieldSpec

catalog = FeatureCatalog.from_yaml(Path("configs/features.yaml"))

assert catalog.version >= 1
assert len(catalog.columns("numeric")) == 8
assert len(catalog.columns("binary")) == 7
assert len(catalog.columns("categorical")) == 4
assert len(catalog.input_columns) == 19
assert len(catalog.forbidden) == 10
assert "resident_id" in catalog.forbidden
assert catalog.derived_columns == [
    "bmi",
    "waist_height_ratio",
    "pulse_pressure",
    "symptom_count",
]
assert catalog.field("smoking_status").categories == ("never", "former", "current")
assert catalog.display_name("bmi") == "BMI"
assert catalog.catalog_hash[:12] == "ce82b3edbf8b"
assert isinstance(catalog.fields[0], FieldSpec)

try:
    catalog.field("不存在")
except CatalogError as exc:
    assert "不存在" in str(exc)
else:
    raise AssertionError("未知字段应抛 CatalogError")
```

## `diabetes_risk.core.errors`

项目统一的可预期错误基类。它把“使用者能自己改正的错误”和“程序缺陷”分开：前者可以被一层 `except DriskError` 接住，后者照常带堆栈抛出。

### `DriskError`

所有“可预期、要给使用者看”的错误的基类。

**用法**：具体模块定义子类（`ConfigError`、`CatalogError`），命令行或服务入口用 `except DriskError` 统一处理；不要在业务代码里把 `KeyError`、`TypeError` 包成它。

**出错抛什么**：它本身不主动抛出；子类实例就是它，捕获后可用 `str(exc)` 取中文说明。

**谁在用**：命令行入口、服务层；A3 的 `ConfigError` 和 A4 的 `CatalogError`。

```python
from diabetes_risk.core.catalog import CatalogError
from diabetes_risk.core.errors import DriskError
from drisk_training.config.loader import ConfigError

assert issubclass(ConfigError, DriskError)
assert issubclass(CatalogError, DriskError)
assert not issubclass(KeyError, DriskError)

try:
    raise ConfigError("配置文件写错了")
except DriskError as exc:
    assert str(exc) == "配置文件写错了"
else:
    raise AssertionError("ConfigError 应能被 DriskError 接住")
```

## `diabetes_risk.core.registry`

按名字登记同类、可替换的组件：配置里写名字，代码里查表；名字写错时，报错列出可选的名字。

### `Registry`

一张“名字 → 组件”的登记表，用起来像一个更严格的字典。

**用法**：先 `Registry("模型")` 建表；`kind` 只用于报错，不能改。定义处用 `@MODELS.register("logreg")`，改不了源码的类用 `MODELS.add("rf", RandomForest)`；取用 `MODELS.get(name)`；`names()`、`values()`、`in`、`len()`、`for` 都按名字排序。不支持 `MODELS["rf"]`、删除和覆盖。

**出错抛什么**：名字不合法（不是 `[a-z][a-z0-9_]*`，或不是字符串、末尾带换行）抛 `ValueError`；重复注册抛 `KeyError`；`get` 找不到抛 `KeyError`，消息含表名、写错的名字和排序后的可选项。它们都不是 `DriskError`：前两种是写代码的人犯的错，找不到由知道名字来源的那一层翻译（读配置处会转成 `ConfigError`）。

**谁在用**：C-L1b 的第一张真实表 `MODELS`；训练和服务按配置取模型或组件。

```python
from diabetes_risk.core.registry import Registry

MODELS: Registry[type] = Registry("模型")


@MODELS.register("logreg")
class LogReg:
    pass


class RandomForest:
    pass


MODELS.add("rf", RandomForest)

assert MODELS.kind == "模型"
assert MODELS.names() == ["logreg", "rf"]
assert "rf" in MODELS
assert len(MODELS) == 2
assert MODELS.get("logreg") is LogReg
assert list(MODELS) == ["logreg", "rf"]
assert list(MODELS.values()) == [LogReg, RandomForest]

try:
    MODELS.get("lgbm")
except KeyError as exc:
    message = str(exc)
    assert "未知模型" in message
    assert "lgbm" in message
    assert "['logreg', 'rf']" in message
else:
    raise AssertionError("未知模型应抛 KeyError")

try:
    MODELS.register("Bad")
except ValueError as exc:
    assert "模型注册名不合法" in str(exc)
else:
    raise AssertionError("非法名字应抛 ValueError")

try:
    MODELS.register("logreg")
except KeyError as exc:
    assert "模型重复注册" in str(exc)
else:
    raise AssertionError("重复注册应抛 KeyError")
```

## `diabetes_risk.core.repro`

可复现与谱系：固定全局随机数，给文件、对象和 git 版本算“说得清从哪来”的指纹。配置指纹、目录指纹、数据文件指纹和 manifest 都用它。

### `set_global_seed`

固定 Python 的 `random`，装了 NumPy 也固定 NumPy 的全局随机数。

**用法**：训练或实验入口调用一次；种子来自 `ProjectSection.seed` 时，这里只负责设进去。模型自己的 `random_state` 仍要单独传。它不返回结果。

**出错抛什么**：没有自定义异常；不接受的种子值由标准库自己抛。

**谁在用**：训练入口、实验入口。

### `sha256_bytes`

对一段字节算 SHA256，返回 64 位小写十六进制。

**用法**：适合配置文本、目录 JSON 这类已经在内存里的内容；`b""` 也可以算。不要用它代替大文件的 `sha256_file`。

**出错抛什么**：传入非字节类型时由标准库抛 `TypeError`。

**谁在用**：`sha256_json`、`config_hash`、`catalog_hash` 和测试。

### `sha256_file`

分块读文件算 SHA256，大文件不会一次读进内存。

**用法**：默认块大小 1 MiB；`chunk_size` 只影响读法，不影响结果，同一文件换块大小应得到同一个值。

**出错抛什么**：文件不存在或没有读权限时抛 `FileNotFoundError` / `PermissionError`，不包成 `DriskError`。

**谁在用**：原始库、冻结集和 manifest 的文件指纹。

### `canonical_json`

把对象写成规范 JSON：键排序、紧凑分隔符、中文原样、日期用 ISO、`Path` 用正斜杠。

**用法**：在算指纹或写调试输出前调用；同一个对象不论键序和缩进都得到同一个字符串。

**出错抛什么**：遇到不认识的对象类型抛 `TypeError`，消息以“无法规范化为 JSON”开头。

**谁在用**：`sha256_json`、`config_hash`、`catalog_hash`。

### `sha256_json`

先把对象规范化为 JSON，再算 SHA256；键序和缩进不影响结果。

**用法**：配置、目录、清单的指纹都用它；返回值是 64 位小写十六进制。

**出错抛什么**：对象无法规范化时抛 `TypeError`（来自 `canonical_json`）。

**谁在用**：A3 的 `config_hash`、A4 的 `catalog_hash`，以及后面的 manifest。

### `git_sha`

取当前工作目录 HEAD 的提交号。

**用法**：训练记录里写“代码从哪来”；不在 git 仓库、没有 git 命令或命令失败时返回 `None`，不抛异常。

**出错抛什么**：不主动抛；无法判断时返回 `None`。

**谁在用**：训练记录、实验追踪。

### `git_dirty`

判断当前工作区是否有未提交的改动。

**用法**：训练记录里写“代码是否干净”；返回布尔值，无法判断时返回 `None`。

**出错抛什么**：不主动抛；无法判断时返回 `None`。

**谁在用**：训练记录、实验追踪。

把这一组串起来：

```python
import hashlib
import random
from pathlib import Path

from diabetes_risk.core.repro import (
    canonical_json,
    git_dirty,
    git_sha,
    set_global_seed,
    sha256_bytes,
    sha256_file,
    sha256_json,
)

assert canonical_json({"b": 1, "a": "年龄"}) == '{"a":"年龄","b":1}'
assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
assert sha256_json({"b": 1, "a": "年龄"}) == sha256_json({"a": "年龄", "b": 1})

path = Path("pyproject.toml")
assert sha256_file(path) == sha256_file(path, chunk_size=3)
assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()

sha = git_sha(Path("."))
assert sha is None or len(sha) == 40
dirty = git_dirty(Path("."))
assert dirty is None or isinstance(dirty, bool)

set_global_seed(42)
first = random.random()
set_global_seed(42)
assert random.random() == first

try:
    canonical_json(object())
except TypeError as exc:
    assert "无法规范化为 JSON" in str(exc)
else:
    raise AssertionError("无法序列化的对象应抛 TypeError")
```
