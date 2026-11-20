"""仓库结构：三个成员都在、按 src 布局正常安装、导入名互不相同、依赖方向正确。"""

from __future__ import annotations

# 动态导入模块，用来验证包是否真的安装成功
import importlib

# 读取已经安装包的元信息（版本号）
import importlib.metadata
from pathlib import Path


def test_workspace_members_match(repo) -> None:
    """① 根 pyproject.toml 登记的工作区成员与约定完全一致。"""
    # 读取根 pyproject.toml 里面 uv 工作区登记的成员目录
    members = repo.toml("pyproject.toml")["tool"]["uv"]["workspace"]["members"]
    # 排序再比较：避免顺序不一样导致测试失败；多目录、少目录都会直接断言失败
    assert sorted(members) == sorted(d for d, _, _ in repo.members)


def test_each_member_is_src_layout_with_marker(repo) -> None:
    """② 每个包都是标准 src 布局，并且真的被 uv 安装、可以 import。"""
    # 循环遍历三个包：目录路径、发行包名、导入模块名
    for directory, dist, module in repo.members:
        project = repo.toml(f"{directory}/pyproject.toml")
        # 校验：配置里的包名称必须和约定的发行名一致
        assert project["project"]["name"] == dist
        # 校验：uv 构建配置里的导入模块名必须和约定一致
        assert project["tool"]["uv"]["build-backend"]["module-name"] == module
        # 拼接 src 布局路径：目录 / src / 导入模块名，标准 src 包结构
        pkg = repo.root / directory / "src" / module
        # 校验：必须有 __init__.py，Python 才认定这是一个包
        assert (pkg / "__init__.py").is_file(), f"{pkg} 缺少 __init__.py"
        # 校验：必须有 py.typed，标记这个包对外提供类型注解
        assert (pkg / "py.typed").is_file(), f"{pkg} 缺少 py.typed"
        # 动态导入：pytest 运行时 src 不在默认搜索路径，
        # 能成功 import 说明 uv 已经把包安装进虚拟环境，不是靠当前目录碰巧找到源码
        imported = importlib.import_module(module)
        assert imported.__file__ is not None
        # 校验：导入的源码路径正好是本仓库 src 下的源码，不是别处安装的同名包
        assert Path(imported.__file__).resolve().parent == pkg.resolve(), f"{module} 不是从本仓库 src/ 导入的"
        # 校验：环境里安装的版本号和 pyproject 里写的版本号一致
        assert importlib.metadata.version(dist) == project["project"]["version"]


def test_import_names_are_distinct(repo) -> None:
    """③ 三个包的导入名互不重名，防止命名冲突。"""
    # 取出三个包的导入名字
    names = [module for _, _, module in repo.members]
    # 转集合自动去重：如果长度变少，说明有重复导入名
    assert len(set(names)) == len(names)


def test_core_has_no_internal_dependency(repo) -> None:
    """④ core 核心包不依赖 training、api（依赖只能向下，不能反向依赖上层）。"""
    assert not repo.dependency_names("packages/core/pyproject.toml") & {"drisk-training", "drisk-api"}


def test_service_does_not_depend_on_training(repo) -> None:
    """⑤ api 服务包不依赖 training 训练包（线上部署不带训练的沉重依赖）。"""
    # training 以后会依赖 sklearn、mlflow 等重型库；api 若依赖它，镜像会巨大、启动慢
    assert "drisk-training" not in repo.dependency_names("services/api/pyproject.toml")


def test_no_github_directory(repo) -> None:
    """⑥ 仓库不出现 .github/ 目录（CI 统一走 scripts/ci.py）。"""
    assert not (repo.root / ".github").exists()
