"""A3 配置：验收测试（人维护，智能体只读）。出题依据：docs/steps/A3.md、docs/api/config.md。"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path

import pytest
from pydantic import BaseModel

from diabetes_risk.core.errors import DriskError
from drisk_training.config import ConfigError, Settings, config_hash, deep_merge, load_raw, load_settings, sections
from drisk_training.config.env import EnvSettings

ROOT = Path(__file__).resolve().parents[2]

# 一份和 configs/base.yaml 口径相同的配置；测试在临时目录里改它，不碰仓库里的文件
BASE = """\
project: {name: diabetes-risk, experiment: base, seed: 42}
paths: {data_dir: data}
data: {raw_db: raw/incident.db, as_of: 2025-06-30}
label: {window_days: 90, max_report_lag_days: 30, fpg_pos: 7.0, hba1c_pos: 6.5}
split: {train_end: 2024-06-30, valid_start: 2024-07-01, valid_end: 2024-12-31}
"""


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------------------------------------------ 用法


def test_usage_matches_v2_constants() -> None:
    """第 0 阶段 v2 的每个口径常量，在 Settings 里都有一个名字。"""
    settings = load_settings(ROOT / "configs" / "experiments" / "final15.yaml")
    assert settings.project.experiment == "final15"
    assert settings.label.window_days == 90 and settings.label.max_report_lag_days == 30
    assert settings.label.maturity_days == 120
    assert settings.split.train_end == date(2024, 6, 30)
    assert settings.train_last_visit == date(2024, 3, 2)
    assert settings.raw_db_path(Path("/repo")) == Path("/repo") / "data" / "raw" / "incident.db"


def test_usage_experiment_writes_only_the_difference(tmp_path: Path) -> None:
    """实验配置只写和 base 不同的地方，其余继承。"""
    _write(tmp_path, "base.yaml", BASE)
    child = _write(tmp_path, "experiments/x.yaml", "extends: ../base.yaml\nlabel: {window_days: 60}\n")
    settings = load_settings(child)
    assert settings.label.window_days == 60
    assert settings.label.fpg_pos == 7.0
    assert settings.project.name == "diabetes-risk"


def test_usage_typo_in_key_names_the_key(tmp_path: Path) -> None:
    """键拼错，加载就报 ConfigError，报错里有拼错的键名。"""
    path = _write(tmp_path, "typo.yaml", BASE.replace("window_days", "window_day"))
    with pytest.raises(ConfigError) as caught:
        load_settings(path)
    assert "window_day" in str(caught.value)


# ------------------------------------------------------------------ 契约


def test_config_error_is_a_drisk_error() -> None:
    """ConfigError 继承 DriskError，命令行据此打一句话退出。"""
    assert issubclass(ConfigError, DriskError)


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("missing.yaml", None),
        ("broken.yaml", "label: [unclosed\n"),
        ("list.yaml", "- a\n- b\n"),
        ("future.yaml", BASE + "evaluation: {capacity: 0.15}\n"),
        ("dates.yaml", BASE.replace("valid_start: 2024-07-01", "valid_start: 2024-06-01")),
        ("zero.yaml", BASE.replace("window_days: 90", "window_days: 0")),
    ],
)
def test_every_bad_config_raises_config_error(tmp_path: Path, name: str, text: str | None) -> None:
    """找不到、YAML 写错、顶层不是映射、多出还没实现的段、日期乱序、口径越界，都是 ConfigError。"""
    path = tmp_path / name if text is None else _write(tmp_path, name, text)
    with pytest.raises(ConfigError):
        load_settings(path)


def test_extends_cycle_is_reported(tmp_path: Path) -> None:
    """a 继承 b、b 又继承 a，报 ConfigError 并说“成环”，而不是无限递归。"""
    _write(tmp_path, "a.yaml", "extends: b.yaml\n")
    _write(tmp_path, "b.yaml", "extends: a.yaml\n")
    with pytest.raises(ConfigError, match="成环"):
        load_settings(tmp_path / "a.yaml")


def test_extends_is_relative_to_the_file_not_the_working_directory(tmp_path: Path, monkeypatch) -> None:
    """从别的目录启动，extends 照样找得到。"""
    _write(tmp_path, "configs/base.yaml", BASE)
    child = _write(tmp_path, "configs/experiments/x.yaml", "extends: ../base.yaml\n")
    monkeypatch.chdir(tmp_path.parent)
    assert load_settings(child).project.name == "diabetes-risk"


def test_settings_are_frozen() -> None:
    """加载以后不能再改。"""
    settings = load_settings(ROOT / "configs" / "base.yaml")
    with pytest.raises(ValueError):
        settings.label.window_days = 60


def test_config_hash_only_takes_settings() -> None:
    """config_hash 只收 Settings，不收原始字典。"""
    parameters = inspect.signature(config_hash).parameters
    assert list(parameters) == ["settings"]
    assert parameters["settings"].annotation in (Settings, "Settings")


def test_load_raw_takes_only_a_path() -> None:
    """load_raw(path)，没有给内部递归用的参数。"""
    assert list(inspect.signature(load_raw).parameters) == ["path"]


def test_sections_expose_exactly_six_models() -> None:
    """sections 只公开 6 个配置模型，没有别名、没有预留段。"""
    public = {
        name
        for name, value in vars(sections).items()
        if not name.startswith("_")
        and isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == sections.__name__
    }
    assert public == {"ProjectSection", "PathsSection", "DataSection", "LabelSection", "SplitSection", "Settings"}


def test_env_settings_read_drisk_variables(monkeypatch) -> None:
    """环境参数走 DRISK_ 前缀的环境变量。"""
    monkeypatch.setenv("DRISK_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("DRISK_LOG_FORMAT", "json")
    env = EnvSettings()
    assert env.log_level == "DEBUG" and env.log_format == "json"


# ------------------------------------------------------------------ 性质

MERGE_CASES = [
    ({"a": 1}, {"a": 2}, {"a": 2}),
    ({"a": {"x": 1, "y": 2}}, {"a": {"y": 3}}, {"a": {"x": 1, "y": 3}}),
    ({"a": [1, 2]}, {"a": [3]}, {"a": [3]}),
    ({"a": {"x": 1}}, {"a": 5}, {"a": 5}),
    ({"a": 5}, {"a": {"x": 1}}, {"a": {"x": 1}}),
    ({"a": {"b": {"c": 1, "d": 2}}}, {"a": {"b": {"d": 9}}, "e": 0}, {"a": {"b": {"c": 1, "d": 9}}, "e": 0}),
]


@pytest.mark.parametrize(("base", "override", "expected"), MERGE_CASES)
def test_deep_merge_rule_holds_and_inputs_are_untouched(base: dict, override: dict, expected: dict) -> None:
    """字典逐键递归合并，列表和标量整体替换；传进来的两个字典都不被修改。"""
    base_before, override_before = repr(base), repr(override)
    assert deep_merge(base, override) == expected
    assert repr(base) == base_before and repr(override) == override_before


def test_same_content_same_hash_however_it_is_written(tmp_path: Path) -> None:
    """键的顺序、注释、省略一个等于默认值的键，都不改变指纹。"""
    reference = config_hash(load_settings(_write(tmp_path, "a.yaml", BASE)))
    variants = [
        "\n".join(reversed(BASE.splitlines())) + "\n",
        "# 注释\n" + BASE,
        BASE.replace("paths: {data_dir: data}\n", ""),
        BASE.replace(", seed: 42", ""),
    ]
    for i, text in enumerate(variants):
        assert config_hash(load_settings(_write(tmp_path, f"v{i}.yaml", text))) == reference, text


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("seed: 42", "seed: 7"),
        ("as_of: 2025-06-30", "as_of: 2025-05-31"),
        ("window_days: 90", "window_days: 60"),
        ("max_report_lag_days: 30", "max_report_lag_days: 20"),
        ("fpg_pos: 7.0", "fpg_pos: 6.9"),
        ("hba1c_pos: 6.5", "hba1c_pos: 6.4"),
        ("train_end: 2024-06-30", "train_end: 2024-05-31"),
        ("valid_end: 2024-12-31", "valid_end: 2024-11-30"),
    ],
)
def test_changing_any_value_changes_the_hash(tmp_path: Path, old: str, new: str) -> None:
    """逐个改一个口径值，指纹都会变。"""
    reference = config_hash(load_settings(_write(tmp_path, "a.yaml", BASE)))
    assert config_hash(load_settings(_write(tmp_path, "b.yaml", BASE.replace(old, new)))) != reference
