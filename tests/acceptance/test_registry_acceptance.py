"""A2 组件注册表：验收测试（人维护，智能体只读）。出题依据：docs/steps/A2.md、docs/api/core.md。

三层：用法（像后面的人那样调用）→ 契约（名字、参数、返回、异常）→ 性质（对一组系统生成的输入都成立）。
只通过公开入口调用，不碰下划线开头的名字；报错只断言必须出现的关键信息，不逐字比对整句。
"""

from __future__ import annotations

import inspect
import re
from itertools import permutations, product

import pytest

from diabetes_risk.core.errors import DriskError
from diabetes_risk.core.registry import Registry


class LogReg:
    """假装是一个模型类：注册表只关心“按名字登记、按名字取”，不关心登记的是什么。"""


class RandomForest:
    """另一个假装的模型类。"""


def _models() -> Registry[type]:
    """第 0 阶段 v1 里的那个字典 {"lr": ..., "rf": ...}，换成注册表以后的样子。"""
    models: Registry[type] = Registry("模型")
    models.register("logreg")(LogReg)
    models.add("rf", RandomForest)
    return models


# ------------------------------------------------------------------ 第一层：用法


def test_usage_get_by_name_like_a_dict() -> None:
    """按名字取；in、len 像 dict 一样用；names() 排好序。"""
    models = _models()
    assert models.get("rf") is RandomForest
    assert "logreg" in models
    assert "xgb" not in models
    assert len(models) == 2
    assert models.names() == ["logreg", "rf"]


def test_usage_typo_says_kind_name_and_options() -> None:
    """拼错名字，报错说清是哪一类、写的是什么、可选的有哪些。"""
    with pytest.raises(KeyError) as caught:
        _models().get("lgbm")
    message = caught.value.args[0]
    assert "模型" in message
    assert "lgbm" in message
    assert "['logreg', 'rf']" in message


def test_usage_wrong_case_still_lists_options() -> None:
    """get 不先查名字格式。写成 RF 也要看到可选项，而不是一句“名字不合法”。"""
    with pytest.raises(KeyError) as caught:
        _models().get("RF")
    assert "['logreg', 'rf']" in caught.value.args[0]


# ------------------------------------------------------------------ 第二层：契约


def test_constructor_requires_kind() -> None:
    """Registry(kind)，kind 没有默认值；.kind 原样返回。"""
    parameters = inspect.signature(Registry.__init__).parameters
    assert list(parameters) == ["self", "kind"]
    assert parameters["kind"].default is inspect.Parameter.empty
    assert Registry("指标").kind == "指标"


def test_register_is_a_decorator_that_returns_the_object() -> None:
    """@register(name) 登记后原样返回被装饰的类，类在原模块里照常可用。"""
    models: Registry[type] = Registry("模型")

    @models.register("logreg")
    class Model:
        pass

    assert Model is not None
    assert models.get("logreg") is Model


def test_add_returns_the_object() -> None:
    """add(name, obj) 返回 obj，登记和使用可以写在一行。"""
    models: Registry[type] = Registry("模型")
    assert models.add("rf", RandomForest) is RandomForest


def test_names_returns_a_list() -> None:
    """names() 返回 list[str]。"""
    assert isinstance(_models().names(), list)


def test_duplicate_is_rejected_and_the_first_one_stays() -> None:
    """重复注册抛 KeyError，原来登记的不被覆盖；装饰器在创建时就查重。"""
    models = _models()
    with pytest.raises(KeyError) as caught:
        models.add("rf", LogReg)
    assert "模型" in caught.value.args[0] and "rf" in caught.value.args[0]
    assert models.get("rf") is RandomForest
    with pytest.raises(KeyError):
        models.register("rf")


def test_invalid_name_raises_valueerror() -> None:
    """名字不合法抛 ValueError，报错带类别和原样的名字；装饰器创建时就查。"""
    models: Registry[type] = Registry("模型")
    with pytest.raises(ValueError) as caught:
        models.add("Bad", LogReg)
    assert "模型" in caught.value.args[0] and "'Bad'" in caught.value.args[0]
    with pytest.raises(ValueError):
        models.register("Bad")


def test_programmer_errors_are_not_drisk_errors() -> None:
    """重复注册、名字不合法是写代码的人犯的错，不包成 DriskError。"""
    models = _models()
    for action in (lambda: models.add("rf", LogReg), lambda: models.add("Bad", LogReg)):
        with pytest.raises((KeyError, ValueError)) as caught:
            action()
        assert not isinstance(caught.value, DriskError)


# ------------------------------------------------------------------ 第三层：性质


def test_order_is_by_name_for_every_registration_order() -> None:
    """四个名字的 24 种登记顺序，names()、迭代、values() 都按名字排序，且一一对应。"""
    names = ["delta", "alpha", "charlie", "bravo"]
    for order in permutations(names):
        registry: Registry[str] = Registry("组件")
        for name in order:
            registry.add(name, name.upper())
        assert registry.names() == sorted(names), order
        assert list(registry) == sorted(names), order
        assert list(registry.values()) == [n.upper() for n in sorted(names)], order


def test_name_rule_holds_for_every_generated_name() -> None:
    """用 9 个字符拼出长度 1–2 的全部 90 个名字，接受的恰好是规则允许的。"""
    alphabet = ["a", "z", "A", "0", "9", "_", "-", " ", "\n"]
    candidates = [*alphabet, *("".join(pair) for pair in product(alphabet, repeat=2))]
    wrong = []
    for name in candidates:
        registry: Registry[int] = Registry("组件")
        try:
            registry.add(name, 1)
            accepted = True
        except ValueError:
            accepted = False
        if accepted != (re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None):
            wrong.append(name)
    assert not wrong, f"这些名字的判定和规则不一致：{wrong!r}"


@pytest.mark.parametrize("name", [None, 3, b"logreg", "logreg\n", "lögreg"])
def test_unusual_names_are_rejected(name: object) -> None:
    """不是字符串、末尾带换行、非 ASCII 字母，都不合法。"""
    registry: Registry[int] = Registry("组件")
    with pytest.raises(ValueError):
        registry.add(name, 1)
