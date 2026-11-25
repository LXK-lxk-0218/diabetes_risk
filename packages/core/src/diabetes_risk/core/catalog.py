"""特征目录：字段元数据的唯一来源（configs/features.yaml）。接口与理由见 docs/api/core.md。

每个字段只写一次：分组、取值范围、类别、中文名、是否必填；外加禁用字段和派生字段。
下游全部从它取：预处理的列分组、数据契约、API 请求格式、解释模块的中文名、模型包里的目录指纹。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from yaml.constructor import ConstructorError

from diabetes_risk.core.errors import DriskError
from diabetes_risk.core.repro import sha256_json

# Literal：分组只能是这三个字符串之一，写成别的（例如 "text"）在校验时就报错
Group = Literal["numeric", "binary", "categorical"]

# 三个分组的固定顺序：模型输入就是按 数值 → 二元 → 类别 排列的
GROUPS: tuple[Group, ...] = ("numeric", "binary", "categorical")

# 这四列决定“谁、哪一天、结果是什么”：任何一份目录都必须把它们列为禁用，哪个入口都绕不过
REQUIRED_FORBIDDEN: tuple[str, ...] = ("visit_id", "resident_id", "visit_date", "label")


class CatalogError(DriskError):
    """特征目录文件找不到、YAML 写错，或内容自相矛盾。"""


class _UniqueKeyLoader(yaml.SafeLoader):
    """safe_load 的“重复键报错”版本：同一层出现两次同一个键就报错，不静默取最后一个。"""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        # 逐对看键节点：同一个映射里重复出现的键，即使后一个值合法也报错——
        # 否则改了前一个等于没改，人还以为改生效了
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConstructorError(None, None, f"重复的键：{key!r}", key_node.start_mark)
            seen.add(key)
        return cast(dict[Any, Any], super().construct_mapping(node, deep=deep))


# 和配置段一样：多写的键报错（extra="forbid"），加载后不可修改（frozen=True）
class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldSpec(_Spec):
    """一个模型输入字段。binary 字段约定编码为 0/1；目录只描述 schema，不校验真实数据的值。"""

    name: str
    group: Group
    display_name: str
    required: bool = False
    range: tuple[float, float] | None = None  # 数值字段的合理取值范围（闭区间）
    categories: tuple[str, ...] | None = None  # 类别字段的全部取值

    @model_validator(mode="after")
    def _check_group_rules(self) -> FieldSpec:
        # 成对检查：该有的必须有（数值要 range，类别要 categories），不该有的不能有
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
    def _check_consistency(self) -> CatalogSpec:
        if not self.fields:
            raise ValueError("fields 至少要有一个输入字段")
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
        # 四个关键禁用列：写在这里，from_yaml、from_dict、直接构造，哪个入口都绕不过
        missing = [name for name in REQUIRED_FORBIDDEN if name not in self.forbidden]
        if missing:
            raise ValueError(f"forbidden 必须包含 {list(REQUIRED_FORBIDDEN)}，缺少：{missing}")
        # 输入顺序是模型契约的一部分：只允许 numeric → binary → categorical 单调前进（允许缺组，不允许回退）
        last = -1
        for field in self.fields:
            index = GROUPS.index(field.group)
            if index < last:
                raise ValueError(
                    f"字段必须按 {' → '.join(GROUPS)} 排列：{field.name}（{field.group}）出现在后面的组之后"
                )
            last = index
        return self


class FeatureCatalog:
    """对 CatalogSpec 的只读视图：下游要的各种列清单，都从这里取。"""

    __slots__ = ("_spec", "_by_name", "_derived_by_name")

    # 只读视图：内部存着已经校验过的 CatalogSpec，对外只提供查询方法，不提供任何修改方法
    def __init__(self, spec: CatalogSpec) -> None:
        self._spec = spec
        # 按名字建索引：field()、display_name() 查找时不用每次从头遍历
        self._by_name = {f.name: f for f in spec.fields}
        self._derived_by_name = {d.name: d for d in spec.derived}

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
        try:
            # 固定 UTF-8 读：文件里有中文名，不能跟着系统默认编码走。自定义 Loader 让重复键报错
            data = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
        except yaml.YAMLError as exc:
            raise CatalogError(f"特征目录的 YAML 写法有错：{path}\n{exc}") from exc
        if not isinstance(data, dict):
            raise CatalogError(f"特征目录顶层必须是“键: 值”：{path}")
        return cls.from_dict(data)

    @property
    def version(self) -> int:
        return self._spec.version

    @property
    def fields(self) -> tuple[FieldSpec, ...]:
        return self._spec.fields

    @property
    def input_columns(self) -> list[str]:
        """全部模型输入，按文件里的顺序（就是 numeric → binary → categorical）。"""
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
        """一个输入字段的完整规格（范围、类别、中文名……）。"""
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
        if name in self._derived_by_name:
            return self._derived_by_name[name].display_name
        raise CatalogError(f"特征目录里没有字段：{name}")

    @property
    def catalog_hash(self) -> str:
        """目录内容指纹：解析后的内容取 SHA256。注释、缩进、键的顺序都不影响；改一个中文名就会变。"""
        # model_dump() 得到解析后的内容（字典），和 YAML 的写法无关
        return sha256_json(self._spec.model_dump())
