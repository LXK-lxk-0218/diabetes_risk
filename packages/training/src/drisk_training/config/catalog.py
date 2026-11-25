"""训练侧：按配置找到特征目录（A4）。接口与理由见 docs/api/config.md。"""

from __future__ import annotations

from pathlib import Path

from diabetes_risk.core.catalog import CatalogError, FeatureCatalog
from drisk_training.config.loader import ConfigError
from drisk_training.config.sections import Settings


def load_catalog(settings: Settings, root: Path) -> FeatureCatalog:
    """按配置里的 paths.features 找到特征目录（相对仓库根 root），读进来并做交叉校验。"""
    try:
        return FeatureCatalog.from_yaml(root / settings.paths.features)
    except CatalogError as exc:
        # 训练侧的调用方只处理一种错误：目录的问题也是“配置的问题”。
        # 四个关键禁用列（visit_id、resident_id、visit_date、label）在目录加载时就由 core 强制检查，
        # 训练侧不用再补一遍
        raise ConfigError(f"特征目录有问题：{exc}") from exc
