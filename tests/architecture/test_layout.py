"""仓库结构：三个成员都在、按 src 布局真正装进了环境、导入名互不相同；规矩文件在，而且只有一份。"""

from __future__ import annotations

# 动态导入模块，用来验证包是否真的安装成功
import importlib

# 读取已经安装包的元信息（版本号）
import importlib.metadata
from pathlib import Path


def test_workspace_members_match(repo) -> None:
    """① 根 pyproject.toml 登记的工作区成员与约定完全一致。"""
    # 根 pyproject.toml 登记的成员必须正好是这三个目录：多一个、少一个都算错
    members = repo.toml("pyproject.toml")["tool"]["uv"]["workspace"]["members"]
    # 排序再比较：避免顺序不一样导致测试失败
    assert sorted(members) == sorted(directory for directory, _, _ in repo.members)


def test_each_member_is_src_layout_with_marker(repo) -> None:
    """② 每个包都是标准 src 布局：配置里的名字对、文件都放对位置。"""
    for directory, dist, module in repo.members:
        # 1) 配置写对了：发行名、导入名与约定一致
        project = repo.toml(f"{directory}/pyproject.toml")
        assert project["project"]["name"] == dist
        assert project["tool"]["uv"]["build-backend"]["module-name"] == module
        # 2) 文件放对了：src/<导入名>/ 下有 __init__.py 和 py.typed（告诉 mypy“这个包带类型标注”）
        pkg = repo.root / directory / "src" / module
        assert (pkg / "__init__.py").is_file(), f"{pkg} 缺少 __init__.py"
        assert (pkg / "py.typed").is_file(), f"{pkg} 缺少 py.typed"


def test_each_member_is_installed_from_this_repo(repo) -> None:
    """③ 三个包真的被 uv 装进了环境，而且装的就是本仓库 src/ 下的那一份。"""
    for directory, dist, module in repo.members:
        # 测试运行时 src/ 不在搜索路径上：能导入，只能是因为它被 uv sync 装进了环境。
        # 再确认导入的就是本仓库 src/ 下的那一份，而不是别处的同名包
        imported = importlib.import_module(module)
        assert imported.__file__ is not None
        assert Path(imported.__file__).resolve().parent == (repo.root / directory / "src" / module).resolve()
        # 环境里登记的版本要和 pyproject.toml 一致：装进去的就是这一版
        assert importlib.metadata.version(dist) == repo.toml(f"{directory}/pyproject.toml")["project"]["version"]


def test_import_names_are_distinct(repo) -> None:
    """④ 三个包的导入名互不重名，防止命名冲突。"""
    names = [module for _, _, module in repo.members]
    # 转集合自动去重：如果长度变少，说明有重复导入名
    assert len(set(names)) == len(names)


def test_no_github_directory(repo) -> None:
    """⑤ 仓库不出现 .github/ 目录（CI 统一走 scripts/ci.py）。"""
    # 本课程以本机 scripts/ci.py 为唯一质量门
    assert not (repo.root / ".github").exists()


def test_claude_md_imports_agents_md(repo) -> None:
    """⑥ 规矩只有一份（AGENTS.md）：CLAUDE.md 第一行把它引进来，不复制内容。"""
    # 有的工具读 CLAUDE.md，有的读 AGENTS.md；复制成两份，迟早会不一致
    first_line = (repo.root / "CLAUDE.md").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "@AGENTS.md"
    assert (repo.root / "AGENTS.md").is_file()
