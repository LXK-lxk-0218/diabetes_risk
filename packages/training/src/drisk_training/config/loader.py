"""读取 YAML 配置：先展开 extends 并深合并，再交给 pydantic 校验，最后可以算配置指纹。

接口与理由见 docs/api/config.md。规则：
- extends 写相对路径，相对“写 extends 的那个文件”所在目录；可以多层，但不能成环；
- 字典逐键合并，列表与标量整体替换（避免两份列表悄悄拼在一起）；
- 合并完才校验：拼错的键、多出来的段、乱序的日期，都在加载这一步报错。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from diabetes_risk.core.errors import DriskError
from diabetes_risk.core.repro import sha256_json
from drisk_training.config.sections import Settings

# 继承用的键名只写这一处
_EXTENDS = "extends"


class ConfigError(DriskError):
    """配置文件找不到、YAML 写错、继承断链或成环，或校验不通过。"""


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """返回新字典：override 覆盖 base；两边都是字典时递归合并，其余（列表、数字、字符串）整体替换。"""
    # 先复制一份：不修改调用方传进来的字典（base 可能还在别处用）
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        # 两边都是字典才往下合并。例：base 里 x: [1, 2]，override 里 x: [3]，结果是 [3]，不是 [1, 2, 3]
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"找不到配置文件：{path}")
    try:
        # safe_load 只构造普通的字典、列表、字符串、数字、日期，不执行 YAML 里的任何代码；
        # 空文件读出来是 None，用 or {} 统一成空字典
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        # YAML 语法错也包成 ConfigError：调用方只需要接一种错误，报错里带文件名
        raise ConfigError(f"YAML 写法有错：{path}\n{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是“键: 值”：{path}")
    return data


def _load_chain(path: Path, seen: tuple[Path, ...]) -> dict[str, Any]:
    # seen 是这条 extends 链上已经走过的文件；又碰到其中一个，说明 a 继承 b、b 又继承了 a
    if path in seen:
        raise ConfigError(f"extends 成环：{' → '.join(p.name for p in (*seen, path))}")
    data = _read_yaml(path)
    parent = data.pop(_EXTENDS, None)
    if parent is None:
        return data
    # extends 的值必须是相对路径字符串：写成数字、列表或者空串，都是配置写错了
    if not isinstance(parent, str) or not parent.strip():
        raise ConfigError(f"extends 必须写一个相对路径：{path}")
    # 相对“写 extends 的这个文件”所在目录，不相对当前工作目录：从哪里启动结果都一样（防 E1）
    base = _load_chain((path.parent / parent).resolve(), (*seen, path))
    return deep_merge(base, data)


def load_raw(path: Path) -> dict[str, Any]:
    """读取并展开 extends，返回合并后的原始字典（还没校验）。排查“配置最后合并成了什么”时用。"""
    # resolve() 转成绝对路径：同一个文件不论从哪条相对路径找到，都是同一个值，成环检测才可靠
    return _load_chain(Path(path).resolve(), ())


def load_settings(path: Path) -> Settings:
    """读配置的唯一入口：展开、合并、校验。任何问题都抛 ConfigError，报错里带文件名和出错的键。"""
    raw = load_raw(path)
    try:
        # model_validate：按 Settings 的定义逐段检查类型、取值范围、多余的键，最后跑日期顺序校验
        return Settings.model_validate(raw)
    except ValueError as exc:
        # pydantic 的 ValidationError 是 ValueError 的子类；转成 ConfigError，命令行就能打一句话退出
        raise ConfigError(f"配置校验失败：{path}\n{exc}") from exc


def config_hash(settings: Settings) -> str:
    """配置指纹：合并、校验之后的完整内容（含默认值）取 SHA256。只收 Settings，不收原始字典。

    口径相同，指纹就相同：键的顺序、注释、省略一个等于默认值的键，都不影响。
    代价：以后新增一个带默认值的字段，所有配置的指纹都会变，要在步骤说明里记下新值。
    """
    return sha256_json(settings.model_dump())
