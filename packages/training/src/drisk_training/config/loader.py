"""读取 YAML 配置：先递归处理 extends 并深合并，再交给 pydantic 校验。
规则：
- extends 写相对路径，相对"写 extends 的那个文件"所在目录；可以多层，但不能成环；
- 字典逐键合并，列表与标量整体替换（避免两份列表悄悄拼在一起）；
- 合并完才校验：拼错的键、多出来的段、乱序的日期，都在加载这一步报错。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from diabetes_risk.core.errors import DriskError
from diabetes_risk.core.repro import sha256_json
from drisk_training.config.sections import Settings

EXTENDS = "extends"


class ConfigError(DriskError):
    """配置文件找不到、格式不对、继承成环，或校验不通过。"""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """返回新字典：override 覆盖 base；两边都是字典时递归合并，其余一律整体替换。"""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"找不到配置文件：{path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件顶层必须是映射（键:值）：{path}")
    return data


def load_raw(path: Path, _seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    """读取并展开 extends，返回合并后的原始字典（尚未校验）。"""
    path = Path(path).resolve()
    if path in _seen:
        chain = " → ".join(p.name for p in (*_seen, path))
        raise ConfigError(f"extends 成环：{chain}")
    data = _read_yaml(path)
    parent = data.pop(EXTENDS, None)
    if parent is None:
        return data
    base = load_raw(path.parent / str(parent), (*_seen, path))
    return deep_merge(base, data)


def load_settings(path: Path) -> Settings:
    """读取、合并、校验，返回不可变的 Settings。"""
    raw = load_raw(path)
    try:
        return Settings.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"配置校验失败：{path}\n{exc}") from exc


def config_hash(settings: Settings) -> str:
    """配置指纹：合并、校验之后的完整内容取 SHA256。键的顺序、注释、缩进都不影响它。"""
    return sha256_json(settings.model_dump())
