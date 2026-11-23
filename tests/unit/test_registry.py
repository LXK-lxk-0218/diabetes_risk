"""组件注册表的行为。"""

from __future__ import annotations

import pytest

from diabetes_risk.core.registry import Registry


# 正常路径：两种登记写法（add 与装饰器）都能用，查表、列名、in、迭代、len 的行为都符合约定
def test_register_and_get() -> None:
    # 测试里用 int 当“组件”就够了：注册表不关心登记的是什么，只关心名字
    reg: Registry[int] = Registry("模型")
    reg.add("logreg", 1)

    # 装饰器写法：定义 _plugin 的同时就登记成 "lightgbm"
    @reg.register("lightgbm")
    def _plugin() -> int:
        return 2

    assert reg.get("logreg") == 1
    # 登记时 logreg 在前，列出来却按字母排序
    assert reg.names() == ["lightgbm", "logreg"]
    assert "logreg" in reg and "xgboost" not in reg
    assert list(reg) == ["lightgbm", "logreg"]
    assert len(reg) == 2
    assert reg.kind == "模型"


# 同一个名字登记两次必须报错。pytest.raises 断言：with 里的代码会抛出这种异常，并且信息匹配 match
def test_duplicate_registration_fails() -> None:
    reg: Registry[int] = Registry("模型")
    reg.add("logreg", 1)
    with pytest.raises(KeyError, match="重复注册"):
        reg.add("logreg", 2)


# 故意把 lightgbm 拼成 lightgmb：报错里要列出全部可选项，写错的人第一秒就知道该写什么
def test_unknown_name_lists_choices() -> None:
    reg: Registry[int] = Registry("模型")
    reg.add("logreg", 1)
    reg.add("lightgbm", 2)
    # match 按正则匹配：方括号在正则里有特殊含义，所以写成 \[ \] 表示字面上的方括号
    with pytest.raises(KeyError, match=r"可选：\['lightgbm', 'logreg'\]"):
        reg.get("lightgmb")


# parametrize：同一个测试函数用五个不同的 bad 各跑一次，pytest 报告里算 5 个测试。
# 空串、大写、数字开头、连字符、空格 —— 都不能当配置值
@pytest.mark.parametrize("bad", ["", "LogReg", "1model", "log-reg", "log reg"])
def test_invalid_names_rejected(bad: str) -> None:
    reg: Registry[int] = Registry("模型")
    with pytest.raises(ValueError, match="注册名不合法"):
        reg.add(bad, 1)
