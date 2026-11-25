"""A4 特征目录：验收测试（人维护，智能体只读）。出题依据：docs/steps/A4.md、docs/api/core.md。

用法测试拿第 0 阶段 v2 的列清单当标准答案：那几张列清单是验收、冻结过的，目录给出的必须和它们一模一样。
"""

from __future__ import annotations

import copy
from itertools import permutations
from pathlib import Path
from typing import Any

import pytest
import yaml

from diabetes_risk.core.catalog import REQUIRED_FORBIDDEN, CatalogError, FeatureCatalog
from diabetes_risk.core.errors import DriskError
from drisk_training.config import ConfigError, load_settings
from drisk_training.config.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[2]

# ---- 第 0 阶段 v2 的列清单：照 data/frozen/FROZEN.json 和验收口径原样抄过来 ----
NUM_COLS = ["age", "height_cm", "weight_kg", "waist_cm", "sbp", "dbp", "exercise_min_week", "sleep_hours"]
BIN_COLS = ["veg_fruit_daily", "hypertension_dx", "hyperlipidemia_dx", "gdm_history",
            "polyuria", "polydipsia", "weight_loss_unexplained"]  # fmt: skip
CAT_COLS = ["gender", "smoking_status", "drinking_freq", "family_history_dm"]
META_COLS = ["visit_id", "resident_id", "visit_date", "district", "education", "income_level"]
ENUMS = {"gender": ["M", "F"], "smoking_status": ["never", "former", "current"],
         "drinking_freq": ["never", "occasional", "frequent"], "family_history_dm": ["yes", "no", "unknown"]}  # fmt: skip
RANGES = {"height_cm": (120, 210), "weight_kg": (30, 200), "sbp": (60, 260), "dbp": (30, 150),
          "exercise_min_week": (0, 3000), "sleep_hours": (2, 14), "waist_cm": (50, 150), "age": (18, 100)}  # fmt: skip

# 一份最小的合格目录：三组各一个字段、四个关键禁用列、一个派生字段。性质测试在它上面逐处改
MINI: dict[str, Any] = {
    "version": 1,
    "fields": [
        {"name": "age", "group": "numeric", "range": [18, 100], "display_name": "年龄"},
        {"name": "polyuria", "group": "binary", "display_name": "多尿"},
        {"name": "gender", "group": "categorical", "categories": ["M", "F"], "display_name": "性别"},
    ],
    "forbidden": list(REQUIRED_FORBIDDEN),
    "derived": [{"name": "bmi", "display_name": "BMI"}],
}


@pytest.fixture(scope="module")
def catalog() -> FeatureCatalog:
    return FeatureCatalog.from_yaml(ROOT / "configs" / "features.yaml")


def _yaml(tmp_path: Path, data: Any, name: str = "features.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------ 用法：和 v2 的列清单对账


def test_usage_column_lists_match_v2(catalog: FeatureCatalog) -> None:
    """NUM_COLS / BIN_COLS / CAT_COLS 和它们拼起来的输入顺序。"""
    assert catalog.columns("numeric") == NUM_COLS
    assert catalog.columns("binary") == BIN_COLS
    assert catalog.columns("categorical") == CAT_COLS
    assert catalog.input_columns == NUM_COLS + BIN_COLS + CAT_COLS


def test_usage_value_rules_match_v2(catalog: FeatureCatalog) -> None:
    """ENUMS、RANGES 都从 field(name) 取。"""
    for name, allowed in ENUMS.items():
        assert list(catalog.field(name).categories or ()) == allowed, name
    for name, (low, high) in RANGES.items():
        assert catalog.field(name).range == (low, high), name


def test_usage_forbidden_covers_meta_and_leaks(catalog: FeatureCatalog) -> None:
    """元数据列、K1/K2 的泄漏列、标签都不能进模型。"""
    assert set(META_COLS + ["known_diabetes", "chronic_mgmt_tag", "label"]) <= set(catalog.forbidden)
    assert not set(catalog.input_columns) & set(catalog.forbidden)


def test_usage_display_names_and_derived(catalog: FeatureCatalog) -> None:
    """中文名（输入字段、派生字段都能查）和派生字段清单。"""
    assert catalog.display_name("age") == "年龄"
    assert catalog.display_name("bmi") == "BMI"
    assert catalog.derived_columns == ["bmi", "waist_height_ratio", "pulse_pressure", "symptom_count"]


def test_usage_training_side_finds_the_same_catalog(catalog: FeatureCatalog) -> None:
    """训练侧按配置找到的，就是同一份目录。"""
    settings = load_settings(ROOT / "configs" / "experiments" / "final15.yaml")
    assert load_catalog(settings, ROOT).catalog_hash == catalog.catalog_hash


# ------------------------------------------------------------------ 契约


def test_errors_are_drisk_errors() -> None:
    """CatalogError 继承 DriskError。"""
    assert issubclass(CatalogError, DriskError)


def test_fields_and_version(catalog: FeatureCatalog) -> None:
    """fields 是全部输入字段的规格，顺序和 input_columns 一致；version 是文件版本号。"""
    assert [f.name for f in catalog.fields] == catalog.input_columns
    assert catalog.field("age").required is True and catalog.field("sbp").required is False
    assert catalog.version == 1


def test_unknown_field_raises_catalog_error(catalog: FeatureCatalog) -> None:
    """查一个不存在的字段，抛 CatalogError，报错里有这个名字。"""
    with pytest.raises(CatalogError, match="nonexistent"):
        catalog.field("nonexistent")
    with pytest.raises(CatalogError, match="nonexistent"):
        catalog.display_name("nonexistent")


@pytest.mark.parametrize(
    "text",
    [
        None,  # 文件不存在
        "fields: [unclosed\n",  # YAML 写错
        "- a\n- b\n",  # 顶层不是映射
    ],
)
def test_bad_files_raise_catalog_error(tmp_path: Path, text: str | None) -> None:
    """文件找不到、YAML 写错、顶层不是“键: 值”，都抛 CatalogError。"""
    path = tmp_path / "features.yaml"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    with pytest.raises(CatalogError):
        FeatureCatalog.from_yaml(path)


def test_duplicate_key_is_rejected_even_if_the_last_value_is_valid(tmp_path: Path) -> None:
    """同一层写了两次同一个键，即使后一个值完全合法也报错——否则改了前一个等于没改。"""
    path = _yaml(tmp_path, MINI)
    path.write_text(path.read_text(encoding="utf-8") + "version: 2\n", encoding="utf-8")
    with pytest.raises(CatalogError, match="version"):
        FeatureCatalog.from_yaml(path)


def test_training_side_turns_catalog_errors_into_config_errors(tmp_path: Path) -> None:
    """训练侧只抛 ConfigError，调用方只处理一种错误。"""
    settings = load_settings(ROOT / "configs" / "experiments" / "final15.yaml")
    with pytest.raises(ConfigError):
        load_catalog(settings, tmp_path)


# ------------------------------------------------------------------ 性质


@pytest.mark.parametrize("required", REQUIRED_FORBIDDEN)
def test_every_entry_rejects_a_missing_required_forbidden(tmp_path: Path, required: str) -> None:
    """四个关键禁用列少任何一个，from_dict 和 from_yaml 两个入口都拒绝。"""
    data = copy.deepcopy(MINI)
    data["forbidden"].remove(required)
    with pytest.raises(CatalogError, match=required):
        FeatureCatalog.from_dict(data)
    with pytest.raises(CatalogError, match=required):
        FeatureCatalog.from_yaml(_yaml(tmp_path, data))


def test_only_numeric_binary_categorical_order_is_accepted() -> None:
    """三个字段的 6 种排列里，只有 numeric → binary → categorical 能加载。"""
    accepted = []
    for order in permutations(MINI["fields"]):
        data = {**copy.deepcopy(MINI), "fields": list(order)}
        try:
            FeatureCatalog.from_dict(data)
            accepted.append([f["group"] for f in order])
        except CatalogError:
            pass
    assert accepted == [["numeric", "binary", "categorical"]]


BROKEN_FIELDS = {
    "数值字段没有 range": {"name": "x", "group": "numeric", "display_name": "x"},
    "数值字段下限不小于上限": {"name": "x", "group": "numeric", "range": [5, 5], "display_name": "x"},
    "二元字段写了 range": {"name": "x", "group": "binary", "range": [0, 1], "display_name": "x"},
    "二元字段写了 categories": {"name": "x", "group": "binary", "categories": ["0", "1"], "display_name": "x"},
    "类别字段没有 categories": {"name": "x", "group": "categorical", "display_name": "x"},
    "类别字段取值重复": {"name": "x", "group": "categorical", "categories": ["a", "a"], "display_name": "x"},
    "未知的分组": {"name": "x", "group": "text", "display_name": "x"},
    "多写了一个键": {"name": "x", "group": "binary", "display_name": "x", "unit": "kg"},
}


@pytest.mark.parametrize("label", list(BROKEN_FIELDS))
def test_every_broken_field_is_rejected(label: str) -> None:
    """字段规格“该有的必须有、不该有的不能有”，每一种违反都拒绝。"""
    data = copy.deepcopy(MINI)
    broken = BROKEN_FIELDS[label]
    # 放在它那一组该在的位置上：只考这一条规则，不让“顺序不对”抢先报错
    data["fields"].insert({"numeric": 1, "binary": 2}.get(broken["group"], 3), broken)
    with pytest.raises(CatalogError):
        FeatureCatalog.from_dict(data)


@pytest.mark.parametrize(
    "change",
    ["输入字段重名", "派生字段和输入字段重名", "输入字段同时被禁用", "派生字段同时被禁用", "没有输入字段"],
)
def test_every_inconsistency_is_rejected(change: str) -> None:
    """名字重复、既是输入又被禁用、一个输入都没有，都拒绝。"""
    data = copy.deepcopy(MINI)
    if change == "输入字段重名":
        data["fields"].insert(1, copy.deepcopy(data["fields"][0]))
    elif change == "派生字段和输入字段重名":
        data["derived"].append({"name": "age", "display_name": "年龄2"})
    elif change == "输入字段同时被禁用":
        data["forbidden"].append("polyuria")
    elif change == "派生字段同时被禁用":
        data["forbidden"].append("bmi")
    else:
        data["fields"] = []
    with pytest.raises(CatalogError):
        FeatureCatalog.from_dict(data)


def test_unquoted_yes_no_is_rejected(tmp_path: Path) -> None:
    """YAML 把裸写的 yes/no 读成布尔值；加引号才是字符串。没加引号的当场报错。"""
    text = _yaml(tmp_path, MINI).read_text(encoding="utf-8").replace("- M\n", "- yes\n").replace("- F\n", "- no\n")
    path = tmp_path / "trap.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(CatalogError):
        FeatureCatalog.from_yaml(path)
    path.write_text(text.replace("- yes\n", "- 'yes'\n").replace("- no\n", "- 'no'\n"), encoding="utf-8")
    assert FeatureCatalog.from_yaml(path).field("gender").categories == ("yes", "no")


def test_hash_ignores_how_the_file_is_written(tmp_path: Path) -> None:
    """注释、缩进、键的顺序都不影响目录指纹。"""
    reference = FeatureCatalog.from_dict(copy.deepcopy(MINI)).catalog_hash
    reordered = {key: MINI[key] for key in reversed(list(MINI))}
    text = "# 注释\n" + yaml.safe_dump(reordered, allow_unicode=True, sort_keys=False, indent=4)
    path = tmp_path / "other.yaml"
    path.write_text(text, encoding="utf-8")
    assert FeatureCatalog.from_yaml(path).catalog_hash == reference


def test_changing_any_display_name_changes_the_hash() -> None:
    """任何一个字段（包括派生字段）的中文名改了，目录指纹都变。"""
    reference = FeatureCatalog.from_dict(copy.deepcopy(MINI)).catalog_hash
    for section in ("fields", "derived"):
        for i in range(len(MINI[section])):
            data = copy.deepcopy(MINI)
            data[section][i]["display_name"] += "（改）"
            assert FeatureCatalog.from_dict(data).catalog_hash != reference, (section, i)
