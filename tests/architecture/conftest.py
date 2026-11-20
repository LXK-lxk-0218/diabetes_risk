"""架构测试共用的夹具：仓库根、三个成员、读 TOML。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

# conftest.py 在 tests/architecture/，往上两级就是仓库根。
# 和 ci.py 一样用文件位置定位，不看当前目录：
# 当前文件 → parents[0]=architecture、parents[1]=tests、parents[2]=仓库根
ROOT = Path(__file__).resolve().parents[2]


class Repo:
    """对仓库的只读视图。测试通过它读配置，不直接拼路径。"""

    # 把根路径绑定到类上
    root = ROOT

    # 三个工作区成员：(相对仓库根的目录路径, uv 发行包名, import 导入名)
    # 发行包名：drisk-core；导入名：import diabetes_risk
    members: tuple[tuple[str, str, str], ...] = (
        ("packages/core", "drisk-core", "diabetes_risk"),
        ("packages/training", "drisk-training", "drisk_training"),
        ("services/api", "drisk-api", "drisk_api"),
    )

    # 按相对仓库根的路径读一个 TOML 文件，返回字典。
    # tomllib 是 Python 3.11 起自带的 TOML 解析器（只读）
    def toml(self, relpath: str) -> dict[str, Any]:
        return tomllib.loads((self.root / relpath).read_text(encoding="utf-8"))

    def dependency_names(self, relpath: str) -> set[str]:
        """一个 pyproject 的 [project].dependencies 里的发行名（去掉版本约束与 extra）。"""
        names: set[str] = set()
        for dep in self.toml(relpath)["project"].get("dependencies", []):
            # 依赖写法举例："pydantic>=2.6"、"uvicorn[standard]"、"x; python_version<'3.13'"
            # 第一步：切掉 ; 后面的环境标记（x; python_version<3.13 → x）
            # 第二步：切掉方括号里的 extra（uvicorn[standard] → uvicorn）
            name = dep.split(";")[0].split("[")[0]
            # 第三步：依次在版本比较符号或空格处截断，只保留包名
            for sep in ("<", ">", "=", "!", "~", " "):
                name = name.split(sep)[0]
            # 发行包名不区分大小写，统一小写，避免 Drisk-Core 和 drisk-core 判断不相等
            names.add(name.strip().lower())
        return names

    def python_files(self) -> list[Path]:
        """仓库里自己写的全部 .py（不含虚拟环境、缓存和数据目录）。"""
        skip = {".venv", ".git", "data", "runs", "mlruns", "node_modules", "__pycache__"}
        return [p for p in self.root.rglob("*.py") if not skip & set(p.relative_to(self.root).parts)]


# scope="session"：整个测试会话只创建一次 Repo 实例
# 它只读不写，所有测试用例共用这一个对象，没有冲突，节省性能
@pytest.fixture(scope="session")
def repo() -> Repo:
    return Repo()
