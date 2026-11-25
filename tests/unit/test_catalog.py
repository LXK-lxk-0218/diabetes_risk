"""特征目录：仓库里的目录符合约定；自相矛盾的目录在加载时就报错。"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from diabetes_risk.core.catalog import CatalogError, FeatureCatalog
from drisk_training.config import ConfigError, load_settings
from drisk_training.config.catalog import load_catalog

# 仓库根目录与仓库里的特征目录。本文件既测仓库里那份真实的目录，也测各种被故意改坏的目录
REPO = Path(__file__).resolve().parents[2]
CATALOG = REPO / "configs" / "features.yaml"


# 读出仓库里 features.yaml 的原始字典（还没校验）；测试在它的深拷贝上“做破坏”
@pytest.fixture
def raw() -> dict[str, Any]:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


# 仓库里的目录：19 个输入（8 数值、7 二元、4 类别），顺序与第 0 阶段 v2 一致
def test_repository_catalog_has_19_inputs_in_order() -> None:
    catalog = FeatureCatalog.from_yaml(CATALOG)
    assert len(catalog.input_columns) == 19
    assert len(catalog.columns("numeric")) == 8
    assert len(catalog.columns("binary")) == 7
    assert len(catalog.columns("categorical")) == 4
    assert catalog.input_columns[:3] == ["age", "height_cm", "weight_kg"]
    assert catalog.input_columns[-1] == "family_history_dm"


# 输入与禁用不重叠
def test_inputs_and_forbidden_do_not_overlap() -> None:
    catalog = FeatureCatalog.from_yaml(CATALOG)
    assert not set(catalog.input_columns) & set(catalog.forbidden)
    assert {"known_diabetes", "chronic_mgmt_tag", "district"} <= set(catalog.forbidden)


# 每个输入和派生字段都有中文名（.strip() 防止只写了空格）；查一个不存在的名字要报错
def test_every_input_and_derived_field_has_a_display_name() -> None:
    catalog = FeatureCatalog.from_yaml(CATALOG)
    for name in catalog.input_columns + catalog.derived_columns:
        assert catalog.display_name(name).strip()
    with pytest.raises(CatalogError, match="没有字段"):
        catalog.display_name("nonexistent")


# 同样的内容（从字典重建）指纹不变；改一个中文名，指纹就变
def test_catalog_hash_ignores_formatting_but_not_content(raw: dict[str, Any]) -> None:
    original = FeatureCatalog.from_yaml(CATALOG).catalog_hash
    assert FeatureCatalog.from_dict(copy.deepcopy(raw)).catalog_hash == original
    changed = copy.deepcopy(raw)
    changed["fields"][0]["display_name"] = "年纪"
    assert FeatureCatalog.from_dict(changed).catalog_hash != original


# 每一行是一种“自相矛盾”的目录：mutate 对原始字典做一处破坏，message 是报错里必须出现的文字。
# lambda d: … 是写在一行里的小函数，参数 d 就是那份字典
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["fields"].append(dict(d["fields"][0])), "字段名重复"),
        (lambda d: d["forbidden"].append("age"), "不能同时是禁用字段"),
        (lambda d: d["fields"][0].pop("range"), "必须给出 range"),
        (lambda d: d["fields"][0].update(range=[100, 18]), "下限 < 上限"),
        # fields[15] 是 gender（第一个类别字段），去掉它的 categories
        (lambda d: d["fields"][15].pop("categories"), "categories"),
        # fields[8] 是 veg_fruit_daily（第一个二元字段），给它加上 range
        (lambda d: d["fields"][8].update(range=[0, 1]), "只有数值字段"),
        (lambda d: d["fields"][0].update(group="text"), "group"),
        # 多写一个模型里没定义的键：extra="forbid" 拦下
        (lambda d: d["fields"][0].update(unit="岁"), "unit"),
    ],
)
def test_inconsistent_catalogs_are_rejected(raw: dict[str, Any], mutate: Any, message: str) -> None:
    # 先深拷贝再破坏，夹具给的字典不被改动；from_dict 必须抛 CatalogError，并且信息里有 message
    data = copy.deepcopy(raw)
    mutate(data)
    with pytest.raises(CatalogError, match=message):
        FeatureCatalog.from_dict(data)


# 端到端：从实验配置出发，经 paths.features 找到目录，并通过交叉校验
def test_settings_point_to_the_catalog_and_cross_check() -> None:
    settings = load_settings(REPO / "configs" / "experiments" / "final15.yaml")
    catalog = load_catalog(settings, REPO)
    assert catalog.version == 1


# 从禁用清单里拿掉 label：目录加载时就拦下（core 的 REQUIRED_FORBIDDEN），任何入口都绕不过
def test_missing_required_forbidden_is_rejected_at_load(raw: dict[str, Any]) -> None:
    data = copy.deepcopy(raw)
    data["forbidden"].remove("label")
    with pytest.raises(CatalogError, match=r"缺少：\['label'\]"):
        FeatureCatalog.from_dict(data)


# 训练侧只抛 ConfigError：目录的问题也被包成“配置的问题”
def test_load_catalog_turns_catalog_errors_into_config_errors(tmp_path: Path) -> None:
    settings = load_settings(REPO / "configs" / "experiments" / "final15.yaml")
    with pytest.raises(ConfigError, match="特征目录"):
        load_catalog(settings, tmp_path)
