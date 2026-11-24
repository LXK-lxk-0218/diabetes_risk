"""接口记录的签名部分（A5 ①）：快照脚本怎么读代码，以及快照必须和代码一致。

第一条是守卫：接口变了它就红。新增的接口由人确认后运行 --write 更新快照；
已有的行被改或被删，说明改了已有接口 —— 停下来，先问人。
后三条考脚本本身：在临时目录里现造几个小模块，看快照列了什么、没列什么。
"""

from __future__ import annotations

import difflib
from pathlib import Path


def _module(root: Path, relpath: str, text: str) -> None:
    """在临时“仓库”的核心包源码目录下写一个模块。"""
    path = root / "packages" / "core" / "src" / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_interfaces_snapshot_matches_the_code(repo) -> None:
    snapshot = repo.load_script("api_snapshot")
    expected = snapshot.render(repo.root)
    path = repo.root / snapshot.SNAPSHOT
    actual = path.read_text(encoding="utf-8") if path.is_file() else ""
    diff = list(difflib.unified_diff(actual.splitlines(), expected.splitlines(), "快照", "代码", lineterm="", n=0))
    # 失败时把前 30 行差异打出来：- 是快照里有、代码里没有（已有接口变了），+ 是新增
    assert not diff, "公开接口和 docs/interfaces.md 不一致：\n" + "\n".join(diff[:30])


def test_snapshot_lists_signatures_but_not_private_names_or_docstrings(repo, tmp_path: Path) -> None:
    snapshot = repo.load_script("api_snapshot")
    _module(
        tmp_path,
        "pkg/tools.py",
        '"""模块说明。"""\n\nLIMIT: int = 3\n\n\n'
        'def area(width: float, height: float = 1.0) -> float:\n    """说明文字。"""\n    return width * height\n\n\n'
        "def _helper() -> None: ...\n\n\n"
        "class Box:\n    size: int = 0\n\n    def __init__(self, size: int) -> None: ...\n\n"
        "    def grow(self, by: int) -> int: ...\n\n    def _secret(self) -> None: ...\n\n"
        "    def __repr__(self) -> str: ...\n",
    )
    lines = snapshot.render(tmp_path).splitlines()
    for expected in (
        "## `pkg.tools`",
        "- `LIMIT: int = 3`",
        "- `def area(width: float, height: float=1.0) -> float`",
        "- `class Box`",
        "  - `size: int = 0`",
        "  - `def __init__(self, size: int) -> None`",
        "  - `def grow(self, by: int) -> int`",
    ):
        assert expected in lines
    text = "\n".join(lines)
    for hidden in ("_helper", "_secret", "__repr__", "说明文字", "模块说明"):
        assert hidden not in text  # 私有名字、除 __init__/__call__ 以外的双下划线方法、文档字符串都不进快照


def test_modules_are_found_automatically_in_a_fixed_order(repo, tmp_path: Path) -> None:
    snapshot = repo.load_script("api_snapshot")
    _module(tmp_path, "pkg/zeta.py", "def z() -> None: ...\n")
    _module(tmp_path, "pkg/alpha.py", "def a() -> None: ...\n")
    _module(tmp_path, "pkg/_private.py", "def p() -> None: ...\n")
    _module(tmp_path, "pkg/empty.py", "_X = 1\n")
    headings = [line for line in snapshot.render(tmp_path).splitlines() if line.startswith("## ")]
    # 新模块不用登记就会出现；下划线开头的模块、没有公开内容的模块不出现；顺序按模块名
    assert headings == ["## `pkg.alpha`", "## `pkg.zeta`"]


def test_compare_names_the_class_of_each_difference(repo, tmp_path: Path) -> None:
    snapshot = repo.load_script("api_snapshot")
    mine, other = tmp_path / "mine", tmp_path / "other"
    _module(mine, "pkg/registry.py", "class Registry:\n    def __init__(self, kind: str) -> None: ...\n")
    _module(other, "pkg/registry.py", "class Registry:\n    def __init__(self) -> None: ...\n")
    assert snapshot.compare(mine, mine) == []
    lines = snapshot.compare(mine, other)
    assert lines[0] == "## pkg.registry"
    assert "  - 这里有、那里没有   Registry 里：`def __init__(self, kind: str) -> None`" in lines
    assert "  + 那里有、这里没有   Registry 里：`def __init__(self) -> None`" in lines
