"""配置系统：继承合并、拼错即报错、日期顺序、成环、指纹、环境参数。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from drisk_training.config import ConfigError, config_hash, deep_merge, load_raw, load_settings
from drisk_training.config.env import EnvSettings

REPO = Path(__file__).resolve().parents[2]

# 测试专用的最小配置，写成字符串，由下面的夹具写进临时目录。它只用来测"加载规则"，
# 和仓库里真实的 configs/base.yaml 无关：以后改真实配置的某个值，这些测试不会跟着变红。
BASE = """\
project: {name: demo, experiment: base, seed: 42}
paths: {data_dir: data}
data: {raw_db: raw/x.db, as_of: 2025-06-30}
label: {window_days: 90, max_report_lag_days: 30, fpg_pos: 7.0, hba1c_pos: 6.5}
split: {train_end: 2024-06-30, valid_start: 2024-07-01, valid_end: 2024-12-31}
"""


@pytest.fixture
def configs(tmp_path: Path) -> Path:
    (tmp_path / "base.yaml").write_text(BASE, encoding="utf-8")
    (tmp_path / "experiments").mkdir()
    return tmp_path


def _experiment(configs: Path, body: str, name: str = "exp.yaml") -> Path:
    path = configs / "experiments" / name
    path.write_text(body, encoding="utf-8")
    return path


def test_extends_deep_merges_only_the_difference(configs: Path) -> None:
    path = _experiment(configs, "extends: ../base.yaml\nproject: {experiment: exp}\nlabel: {window_days: 60}\n")
    settings = load_settings(path)
    assert settings.project.experiment == "exp"
    assert settings.project.name == "demo"  # 没写的键沿用 base
    assert settings.label.window_days == 60
    assert settings.label.max_report_lag_days == 30


def test_deep_merge_replaces_lists() -> None:
    assert deep_merge({"a": {"x": [1, 2], "y": 1}}, {"a": {"x": [3]}}) == {"a": {"x": [3], "y": 1}}


def test_misspelled_key_fails_at_load(configs: Path) -> None:
    path = _experiment(configs, "extends: ../base.yaml\nlabel: {window_day: 60}\n")
    with pytest.raises(ConfigError, match="window_day"):
        load_settings(path)


def test_section_of_unbuilt_feature_cannot_be_written(configs: Path) -> None:
    path = _experiment(configs, "extends: ../base.yaml\nevaluation: {capacity: 0.15}\n")
    with pytest.raises(ConfigError, match="evaluation"):
        load_settings(path)


def test_dates_out_of_order_fail(configs: Path) -> None:
    path = _experiment(configs, "extends: ../base.yaml\nsplit: {valid_start: 2024-06-01}\n")
    with pytest.raises(ConfigError, match="train_end < valid_start"):
        load_settings(path)


def test_extends_cycle_and_missing_file(configs: Path) -> None:
    _experiment(configs, "extends: b.yaml\n", "a.yaml")
    _experiment(configs, "extends: a.yaml\n", "b.yaml")
    with pytest.raises(ConfigError, match="成环"):
        load_raw(configs / "experiments" / "a.yaml")
    with pytest.raises(ConfigError, match="找不到配置文件"):
        load_raw(configs / "experiments" / "nope.yaml")


def test_config_hash_is_stable_and_sensitive(configs: Path) -> None:
    a = load_settings(_experiment(configs, "extends: ../base.yaml\nproject: {seed: 42, experiment: e}\n", "a.yaml"))
    b = load_settings(_experiment(configs, "extends: ../base.yaml\nproject: {experiment: e, seed: 42}\n", "b.yaml"))
    c = load_settings(_experiment(configs, "extends: ../base.yaml\nproject: {experiment: e, seed: 7}\n", "c.yaml"))
    assert config_hash(a) == config_hash(b)
    assert config_hash(a) != config_hash(c)


def test_settings_are_frozen_and_derive_train_last_visit(configs: Path) -> None:
    settings = load_settings(_experiment(configs, "extends: ../base.yaml\n"))
    assert settings.train_last_visit == date(2024, 3, 2)
    assert settings.raw_db_path(Path("/repo")) == Path("/repo/data/raw/x.db")
    with pytest.raises(ValueError):
        # frozen=True：赋值会抛 ValidationError（ValueError 的子类）
        settings.project.seed = 1


# 唯一一条读真实 configs/ 的测试：保证仓库里的配置文件一直能加载
def test_repository_configs_load() -> None:
    settings = load_settings(REPO / "configs" / "experiments" / "final15.yaml")
    assert settings.project.experiment == "final15"
    assert settings.train_last_visit == date(2024, 3, 2)


def test_env_settings_use_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRISK_LOG_FORMAT", "json")
    assert EnvSettings().log_format == "json"
