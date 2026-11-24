"""训练侧：按配置找到特征目录，并做配置与目录的交叉校验（A4）。"""

from __future__ import annotations

from pathlib import Path

from diabetes_risk.core.catalog import FeatureCatalog
from drisk_training.config.loader import ConfigError
from drisk_training.config.sections import Settings

# 这些列决定“谁、哪一天、结果是什么”，任何时候都不能当模型输入
MUST_BE_FORBIDDEN: tuple[str, ...] = ("visit_id", "resident_id", "visit_date", "label")


def load_catalog(settings: Settings, root: Path) -> FeatureCatalog:
    """按配置里的 paths.features 找到特征目录（相对仓库根 root），读进来并立刻交叉校验。"""
    catalog = FeatureCatalog.from_yaml(root / settings.paths.features)
    check_catalog(catalog)
    return catalog


def check_catalog(catalog: FeatureCatalog) -> None:
    """交叉校验：必需的禁用列必须在 forbidden 里。"""
    # 列出缺了哪几个，而不是只说“不合格”：报错直接告诉人该往 forbidden 里补什么
    missing = [c for c in MUST_BE_FORBIDDEN if c not in catalog.forbidden]
    if missing:
        raise ConfigError(f"特征目录的 forbidden 必须包含 {list(MUST_BE_FORBIDDEN)}，缺少：{missing}")
