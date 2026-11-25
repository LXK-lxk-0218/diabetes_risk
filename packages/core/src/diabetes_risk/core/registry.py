"""组件注册表：配置里写名字，代码里查表。接口与理由见 docs/api/core.md。

只用在“同类、可替换、会增长”的变化点：模型、数据集构建器、指标、决策策略、门禁检查等。
注册表在第一个真实实现出现的那一步才创建，不提前建空表。
"""

# 让类型标注延迟到“需要时”才解析：标注里可以引用还没定义完的名字，
# 导入模块时也不会去执行标注里的表达式。本项目每个 .py 都以这一行开头。
from __future__ import annotations

import re
from collections.abc import Callable, Iterator

# 注册名同时是配置值：小写字母开头，只含小写字母、数字、下划线。
# 用 fullmatch 检查整个字符串；常见写法“match 加 ^…$”会放过末尾带换行的 "logreg\n"
_NAME = re.compile(r"[a-z][a-z0-9_]*")


# [T] 是 Python 3.12 的“类型参数”写法：Registry[int] 里装 int，Registry[ModelSpec] 里装 ModelSpec。
# mypy 因此知道 get() 取出来的是什么类型，用错了在质量门的 mypy 那一道就会报出来。
class Registry[T]:
    """按名字登记同类、可替换的组件。用起来像一个更严格的 dict。"""

    def __init__(self, kind: str) -> None:
        # kind 是给人看的类别名（“模型”“指标”……），只用来拼报错信息
        self._kind = kind
        # 名字 → 组件。对外列名字时一律排序（见 names()），输出不依赖登记的先后
        self._items: dict[str, T] = {}

    # @property：把方法变成只读属性，外面写 MODELS.kind 就能读，但不能赋值修改
    @property
    def kind(self) -> str:
        return self._kind

    def register(self, name: str) -> Callable[[T], T]:
        """装饰器写法：@MODELS.register("logreg")。名字不合法、已被占用，当场报错。"""
        # @MODELS.register("x") 分两步执行：先调用 register("x") 得到 deco，再把下面定义的类交给 deco。
        # 第一步就查名字：写错的名字不用等到类定义完才发现
        self._check_new(name)

        def deco(obj: T) -> T:
            # 两个装饰器先后创建、再先后生效时，名字可能刚被占了：生效这一刻再查一次
            self._check_new(name)
            self._items[name] = obj
            # 原样返回对象：被装饰的类或函数在它自己的模块里照常可用，登记只是顺手记了一笔
            return obj

        return deco

    def add(self, name: str, obj: T) -> T:
        """函数写法：MODELS.add("rf", RandomForest)。和装饰器走同一条路，返回登记的对象。"""
        # 和装饰器走同一条路：先 register(name) 拿到 deco，再立刻 deco(obj)。校验逻辑只写了一份
        return self.register(name)(obj)

    def get(self, name: str) -> T:
        """按名字取；找不到时把可选项全列出来。不先查名字格式：写成 LightGBM 也要看到可选项。"""
        try:
            return self._items[name]
        except KeyError:
            # from None：切断异常链。不写的话，报错会先打印内部那个 KeyError，再打印
            # “During handling of the above exception, another exception occurred”，用户反而找不到重点
            raise KeyError(f"未知{self._kind}：{name}；可选：{self.names()}") from None

    def names(self) -> list[str]:
        # sorted(字典) 得到排好序的键：报错信息和列表输出在任何机器上顺序都一样，测试才能写死期望值
        return sorted(self._items)

    def values(self) -> Iterator[T]:
        """按名字顺序给出登记的组件，和 names() 一一对应。"""
        return (self._items[name] for name in self.names())

    # 下面三个“双下划线方法”让注册表用起来像一个集合：
    #   "logreg" in REG   → 调用 __contains__
    #   for name in REG   → 调用 __iter__（按名字排序）
    #   len(REG)          → 调用 __len__
    # name 标成 object 而不是 str：in 左边可以是任何东西，类型标注要和 Python 的约定一致
    def __contains__(self, name: object) -> bool:
        return name in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self._items)

    def _check_new(self, name: str) -> None:
        """名字不合法、已被占用，都当场报标准异常（写代码的人犯的错，不包成 DriskError）。"""
        if not isinstance(name, str) or _NAME.fullmatch(name) is None:
            raise ValueError(f"{self._kind}注册名不合法：{name!r}（只允许小写字母、数字、下划线，且以字母开头）")
        if name in self._items:
            # 不悄悄覆盖：覆盖意味着同一个名字指向谁，取决于哪个模块后被导入
            raise KeyError(f"{self._kind}重复注册：{name}")
