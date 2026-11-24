"""配置的五个段（A3）：project、paths、data、label、split。
每一段都是 extra="forbid" + frozen=True：拼错键立即报错，加载后不可修改。
"配置随功能生长"：还没实现的功能，这里没有它的段，YAML 里也写不进去。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Section(BaseModel):
    """所有配置段的共同父类：extra="forbid" 拼错键报错，frozen=True 加载后不可改。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectSection(_Section):
    """项目元信息。"""

    name: str
    experiment: str = "base"
    seed: int = 42


class PathsSection(_Section):
    """路径段：所有路径都相对仓库根目录。"""

    data_dir: Path = Path("data")
    features: Path = Path("configs/features.yaml")  # 特征目录（A4）


class DataSection(_Section):
    """原始数据段。"""

    raw_db: Path  # 相对 paths.data_dir
    as_of: date  # 原始库的导出日


class LabelSection(_Section):
    """标签口径：四个数字都来自第 0 阶段 v2 的单元 39。Field(gt=0) 表示必须大于 0。"""

    window_days: int = Field(gt=0)  # 随访后多少天内的化验算数
    max_report_lag_days: int = Field(ge=0)  # 报告最晚比采样晚多少天
    fpg_pos: float = Field(gt=0)  # 空腹血糖阳性阈值（mmol/L）
    hba1c_pos: float = Field(gt=0)  # 糖化血红蛋白阳性阈值（%）

    @property
    def maturity_days(self) -> int:
        """标签成熟期 = 观察窗 + 报告缓冲。"""
        return self.window_days + self.max_report_lag_days


class SplitSection(_Section):
    """时间切分：训练集截至训练快照日 train_end，只用那一天已经出了报告的化验。"""

    train_end: date  # 训练快照日
    valid_start: date
    valid_end: date


class Settings(_Section):
    """配置总入口：五个段聚合在一起，加载时校验。"""

    project: ProjectSection
    paths: PathsSection = Field(default_factory=PathsSection)
    data: DataSection
    label: LabelSection
    split: SplitSection

    @model_validator(mode="after")
    def check_dates_in_order(self) -> Settings:
        """校验日期顺序：train_end < valid_start <= valid_end <= as_of。"""
        s = self.split
        if not s.train_end < s.valid_start <= s.valid_end <= self.data.as_of:
            raise ValueError(
                "日期必须满足 train_end < valid_start <= valid_end <= data.as_of，"
                f"现在是 {s.train_end} / {s.valid_start} / {s.valid_end} / {self.data.as_of}"
            )
        return self

    @property
    def train_last_visit(self) -> date:
        """训练随访最晚的一天 = 训练快照日 − 标签成熟期。本项目是 2024-06-30 − 120 天 = 2024-03-02。"""
        return self.split.train_end - timedelta(days=self.label.maturity_days)

    def raw_db_path(self, root: Path) -> Path:
        """原始库的位置。所有相对路径都相对仓库根目录 root。"""
        return root / self.paths.data_dir / self.data.raw_db
