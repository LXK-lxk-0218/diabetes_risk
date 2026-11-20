"""结构测试：校验项目骨架、src布局、依赖方向、包导入规则"""
import importlib
import sys
from pathlib import Path

def test_package_register(repo):
    """测试1：三个包信息登记数量正确"""
    assert len(repo.packages) == 3, "项目必须登记3个包：core、training、api"

def test_src_layout_and_import(repo):
    """测试2：src布局正确，并且包成功安装、可导入，源码路径在本仓库src下"""
    for pkg in repo.packages:
        # 校验目录必须存在 src/导入名
        src_entry = pkg.dir / "src" / pkg.import_name
        assert src_entry.exists() and src_entry.is_dir(), f"{pkg.dist_name} 缺少标准src布局：{src_entry}"
        # 动态导入包
        mod = importlib.import_module(pkg.import_name)
        # 拿到包的源码文件路径
        mod_path = Path(mod.__file__).resolve()
        # 校验导入的文件，确实在当前仓库src下面，不是别的环境同名包
        assert repo.root.resolve() in mod_path.parents, f"{pkg.import_name} 不是本仓库源码包"

def test_import_name_unique(repo):
    """测试3：三个包导入名互不重复，防止命名冲突"""
    import_names = [pkg.import_name for pkg in repo.packages]
    assert len(set(import_names)) == len(import_names), "包导入名字重复！"

def test_core_not_depend_others(repo):
    """测试4：core核心包，不依赖training、api"""
    core_pkg = next(p for p in repo.packages if p.dist_name == "drisk-core")
    toml = repo.read_toml(core_pkg.dir)
    deps = toml.get("project", {}).get("dependencies", [])
    # 核心包不能依赖另外两个业务包
    assert "drisk-training" not in deps
    assert "drisk-api" not in deps

def test_api_not_depend_training(repo):
    """测试5：api推理服务包，不依赖training训练包（线上推理和训练解耦）"""
    api_pkg = next(p for p in repo.packages if p.dist_name == "drisk-api")
    toml = repo.read_toml(api_pkg.dir)
    deps = toml.get("project", {}).get("dependencies", [])
    assert "drisk-training" not in deps, "推理服务不可以依赖训练包"

def test_no_github_dir(repo):
    """测试6：根目录禁止存在.github文件夹（规范约束）"""
    github_dir = repo.root / ".github"
    assert not github_dir.exists(), "仓库禁止放置 .github 目录"