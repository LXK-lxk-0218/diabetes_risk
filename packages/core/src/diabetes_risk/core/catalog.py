"""特征目录：字段元数据的唯一来源（configs/features.yaml）。

每个字段只写一次：分组、取值范围、类别、中文名、是否必填；外加禁用字段和派生字段。
下游全部从它派生：配置校验、数据契约、预处理的列分组、API 请求模型、解释模块的中文名。
目录内容的指纹（catalog_hash）会写进数据集 manifest 和模型包，服务加载时比对。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from diabetes_risk.core.errors import DriskError
from diabetes_risk.core.repro import sha256_json

# Literal：分组只能是这三个字符串之一，写成别的（例如 "text"）在校验时就报错
Group = Literal["numeric", "binary", "categorical"]

# 三个分组的固定顺序：模型输入就是按 数值 → 二元 → 类别 排列的
GROUPS: tuple[Group, ...] = ("numeric", "binary", "categorical")


class CatalogError(DriskError):
    """特征目录文件找不到，或内容自相矛盾。"""


# 和配置段一样：多写的键报错（extra="forbid"），加载后不可修改（frozen=True）
class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldSpec(_Spec):
    """一个模型输入字段。"""

    name: str
    group: Group
    display_name: str
    required: bool = False
    range: tuple[float, float] | None = None  # 数值字段的合理取值范围（闭区间）
    categories: tuple[str, ...] | None = None  # 类别字段的全部取值

    @model_validator(mode="after")
    def check_group_rules(self) -> FieldSpec:
        """规则成对检查：该有的必须有，不该有的不能有（二元字段写了 range 就报错）。"""
        if self.group == "numeric":
            if self.range is None or not self.range[0] < self.range[1]:
                raise ValueError(f"数值字段 {self.name} 必须给出 range: [下限, 上限]，且下限 < 上限")
        elif self.range is not None:
            raise ValueError(f"只有数值字段可以写 range：{self.name}")
        if self.group == "categorical":
            # 转成集合后个数变少，说明有重复的取值
            if not self.categories or len(set(self.categories)) != len(self.categories):
                raise ValueError(f"类别字段 {self.name} 必须给出不重复的 categories")
        elif self.categories is not None:
            raise ValueError(f"只有类别字段可以写 categories：{self.name}")
        return self


class DerivedSpec(_Spec):
    """派生字段：不由调用方传入，由特征工程计算（C-L1b）。这里只登记名字和中文名。"""

    name: str
    display_name: str


class CatalogSpec(_Spec):
    """features.yaml 的完整结构。"""

    version: int = Field(ge=1)
    fields: tuple[FieldSpec, ...]
    forbidden: tuple[str, ...]
    derived: tuple[DerivedSpec, ...] = ()

    @model_validator(mode="after")
    def check_consistency(self) -> CatalogSpec:
        # 输入字段和派生字段放在一起查重：派生字段的名字也不能和输入字段撞
        names = [f.name for f in self.fields] + [d.name for d in self.derived]
        # names.count(n) > 1 的就是重复的名字；先用集合去重、再排序，报错信息每次都一样
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(f"字段名重复：{duplicated}")
        # 一个字段不能既是输入、又被禁用：两份清单的交集必须为空
        clash = sorted(set(names) & set(self.forbidden))
        if clash:
            raise ValueError(f"输入或派生字段不能同时是禁用字段：{clash}")
        return self


class FeatureCatalog:
    """对 CatalogSpec 的只读视图，提供下游需要的各种列清单。"""

    # 只读视图：内部存着已经校验过的 CatalogSpec，对外只提供查询方法，不提供任何修改方法
    def __init__(self, spec: CatalogSpec) -> None:
        self._spec = spec
        # 按名字建一个索引，field()、display_name() 查找时不用每次从头遍历
        self._by_name = {f.name: f for f in spec.fields}

    # @classmethod：通过类本身调用，例如 FeatureCatalog.from_yaml(path)，返回一个新对象。
    # 两个入口：from_dict 给测试用（在字典上做破坏），from_yaml 读仓库里的文件
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureCatalog:
        try:
            return cls(CatalogSpec.model_validate(data))
        except ValueError as exc:
            # pydantic 的校验错误是 ValueError，这里统一包成 CatalogError（DriskError 的子类）
            raise CatalogError(f"特征目录不合法：\n{exc}") from exc

    @classmethod
    def from_yaml(cls, path: Path) -> FeatureCatalog:
        if not Path(path).is_file():
            raise CatalogError(f"找不到特征目录：{path}")
        # 读文本时固定 UTF-8：文件里有中文名，不能跟着系统默认编码走
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise CatalogError(f"特征目录顶层必须是映射：{path}")
        return cls.from_dict(data)

    @property
    def version(self) -> int:
        return self._spec.version

    @property
    def fields(self) -> tuple[FieldSpec, ...]:
        return self._spec.fields

    @property
    def input_columns(self) -> list[str]:
        """全部模型输入，按文件里的顺序。"""
        return [f.name for f in self._spec.fields]

    def columns(self, group: Group) -> list[str]:
        """某一组的列名，保持文件里的顺序。"""
        return [f.name for f in self._spec.fields if f.group == group]

    @property
    def forbidden(self) -> tuple[str, ...]:
        return self._spec.forbidden

    @property
    def derived_columns(self) -> list[str]:
        return [d.name for d in self._spec.derived]

    def field(self, name: str) -> FieldSpec:
        try:
            return self._by_name[name]
        except KeyError:
            # from None：去掉内部的 KeyError，报错只说“没有这个字段”
            raise CatalogError(f"特征目录里没有输入字段：{name}") from None

    def display_name(self, name: str) -> str:
        """输入字段或派生字段的中文名。"""
        # 先查输入字段，再查派生字段；都没有才报错
        if name in self._by_name:
            return self._by_name[name].display_name
        for derived in self._spec.derived:
            if derived.name == name:
                return derived.display_name
        raise CatalogError(f"特征目录里没有字段：{name}")

    @property
    def catalog_hash(self) -> str:
        """目录内容指纹：解析后的内容取 SHA256，注释、缩进、换行符都不影响。"""
        # model_dump() 得到解析后的内容（字典），和 YAML 的写法无关：注释、缩进、换行符
        # 都不影响指纹；改一个中文名就会变
        return sha256_json(self._spec.model_dump())
