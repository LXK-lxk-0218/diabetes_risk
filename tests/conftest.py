
"""pytest全局夹具：项目仓库只读信息，所有layout测试共用"""
from pathlib import Path
import tomllib
from dataclasses import dataclass

# 定义一个数据类，用来描述一个本地包的信息
@dataclass(frozen=True)  # frozen=True：只读，测试里不能意外修改
class PackageInfo:
    dir: Path        # 包所在文件夹路径，packages/core
    dist_name: str   # uv发行包名，drisk-core
    import_name: str # import名字，diabetes_risk

# pytest全局fixture，名字叫repo，所有测试函数可以直接接收这个参数
import pytest
@pytest.fixture(scope="session")  # session级别：整个测试会话只加载一次，性能更好
def repo():
    # 获取仓库根目录，conftest.py放在项目根目录
    root = Path(__file__).parent
    # 登记我们三个包：core、training、api
    packages = [
        PackageInfo(
            dir=root / "packages" / "core",
            dist_name="drisk-core",
            import_name="diabetes_risk"
        ),
        PackageInfo(
            dir=root / "packages" / "training",
            dist_name="drisk-training",
            import_name="drisk_training"
        ),
        PackageInfo(
            dir=root / "services" / "api",
            dist_name="drisk-api",
            import_name="drisk_api"
        ),
    ]

    # 工具函数：读取某个包下pyproject.toml
    def read_toml(pkg_dir: Path):
        toml_path = pkg_dir / "pyproject.toml"
        with toml_path.open("rb") as f:
            return tomllib.load(f)

    # 打包成只读对象返回给测试
    class Repo:
        root = root
        packages = packages
        read_toml = read_toml
    return Repo()