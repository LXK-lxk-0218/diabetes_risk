"""规则本身不能被悄悄改掉：这些测试专门拦“为了让 CI 变绿而绕过规则”的改动。"""

from __future__ import annotations

import re

# 门槛下限：pyproject 里的值只能比这里高，不能低
COVERAGE_FLOOR = 85
REQUIRED_RUFF_RULES = {"E", "F", "W", "I", "B", "UP"}

# 拼出来的正则，避免本文件自己命中
_SYS_PATH = re.compile(r"\bsys\." + r"path\.(insert|append|extend)\b|\bsys\." + r"path\s*\+?=")
_CHDIR = re.compile(r"\bos\." + r"chdir\s*\(")


def test_no_sys_path_hacks_or_chdir(repo) -> None:
    """禁止修改导入搜索路径、禁止切换工作目录：这是“在我机器上能跑”的来源（E1）。"""
    # 按文本扫描仓库里自己写的每个 .py，注释也算。宁可误报，不可放过：
    # 改导入搜索路径、切换工作目录，都是“在我机器上能跑”的来源（E1）。
    offenders = []
    for path in repo.python_files():
        text = path.read_text(encoding="utf-8")
        if _SYS_PATH.search(text) or _CHDIR.search(text):
            offenders.append(path.relative_to(repo.root).as_posix())
    assert not offenders, f"禁止修改 sys.path 或 os.chdir：{offenders}"


def test_pytest_config_has_no_pythonpath(repo) -> None:
    """pytest 配置里不能加 pythonpath，绕过“包必须被正常安装”的规则。"""
    # pythonpath 是 pytest 自带的“改搜索路径”开关：加上它，没装好的包也能被测试找到，
    # 测试是绿的，换个目录或者真正部署时却导入失败。
    ini = repo.toml("pyproject.toml")["tool"]["pytest"]["ini_options"]
    assert "pythonpath" not in ini, "不要用 pythonpath 让测试“找到”代码：包应当被正常安装"


def test_coverage_floor_not_lowered(repo) -> None:
    """覆盖率门槛只能调高，不能调低。"""
    # 只许调高，不许调低：85 改成 90 可以，改成 0 这里就红
    fail_under = repo.toml("pyproject.toml")["tool"]["coverage"]["report"]["fail_under"]
    assert fail_under >= COVERAGE_FLOOR, f"覆盖率门槛不能低于 {COVERAGE_FLOOR}"


def test_quality_rules_not_reduced(repo) -> None:
    """ruff 规则只能增加不能减少，mypy 必须保持强制类型标注。"""
    tool = repo.toml("pyproject.toml")["tool"]
    # <= 是子集判断：规则只能比下限多，不能少
    assert REQUIRED_RUFF_RULES <= set(tool["ruff"]["lint"]["select"])
    assert tool["mypy"]["disallow_untyped_defs"] is True
