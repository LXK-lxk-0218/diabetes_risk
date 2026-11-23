"""
基线只读：baselines/ 下每个子目录都必须与它的 SHA256SUMS 一致。
这个是 pytest 架构测试，CI 流水线自动执行，用来守住基线不被私自篡改。
"""

# 向前兼容类型注解写法
from __future__ import annotations

# importlib.util：动态从文件加载 Python 模块，解决 scripts 不是包无法直接 import 的问题
import importlib.util

# 导入模块类型，标注返回值类型
from types import ModuleType


def _load_freeze_script(repo) -> ModuleType:
    """scripts/ 不是包，按文件路径加载它（不改搜索路径）。

    测试直接复用脚本里的 check()、write()：校验逻辑只有一份，
    命令行跑 --check 和测试里跑，得到的结论不可能不一样。
    """
    # 拼接脚本完整路径：仓库根目录 /scripts/freeze_baseline.py
    path = repo.root / "scripts" / "freeze_baseline.py"
    # 根据文件路径创建模块描述信息，模块名字叫 freeze_baseline
    spec = importlib.util.spec_from_file_location("freeze_baseline", path)
    # 断言：模块描述和加载器必须存在，文件不存在直接测试失败
    assert spec is not None and spec.loader is not None
    # 根据模块描述，新建一个空模块对象
    module = importlib.util.module_from_spec(spec)
    # 执行这个 py 文件，把里面的函数、变量加载进 module 对象
    spec.loader.exec_module(module)
    # 返回加载好的模块，后面就可以调用 module.check()、module.write()
    return module


def test_every_baseline_matches_its_checksums(repo) -> None:
    """真实基线校验：baselines/ 下每个子目录都必须和 SHA256SUMS 指纹匹配。"""
    # A1 阶段 baselines/ 里面只有 README.md，没有子基线目录，循环不会执行，测试直接通过
    # 后续放入第一份基线文件夹后，循环开始遍历基线，正式校验
    # baselines 目录必须存在（靠 README 提交到 git），否则 iterdir() 会报文件找不到错误
    # 加载 freeze_baseline.py 脚本，拿到里面的函数
    freeze = _load_freeze_script(repo)
    # 定义列表，用来收集所有基线的报错信息
    problems = []
    # 遍历 baselines 目录下所有内容，只保留文件夹，并且排序，保证顺序稳定
    for directory in sorted(p for p in (repo.root / "baselines").iterdir() if p.is_dir()):
        # 调用 freeze.check() 校验当前基线目录，把报错信息带上基线名字，放进 problems 列表
        problems += [f"{directory.name}: {msg}" for msg in freeze.check(directory)]
    # 如果 problems 不为空，断言失败，打印所有报错信息，CI 门禁变红阻断提交
    assert not problems, "基线被改动或缺少指纹：\n" + "\n".join(problems)


def test_freeze_roundtrip_detects_change(repo, tmp_path) -> None:
    """工具自测：冻结→校验正常→修改文件→校验必须抓到改动。"""
    # 这个是工具本身的自测：用 pytest 自带的临时文件夹 tmp_path，不会污染真实仓库文件
    # 流程：新建文件 → 冻结生成指纹 → 校验正常 → 修改文件内容 → 校验应该抓到改动
    freeze = _load_freeze_script(repo)
    # 在临时目录创建 a.json 文件，写入初始内容
    (tmp_path / "a.json").write_text('{"x": 1}\n', encoding="utf-8")
    # 调用 write，给这个临时目录冻结，生成 SHA256SUMS
    freeze.write(tmp_path)
    # 校验：此时文件没有改动，check 返回空列表，断言通过
    assert freeze.check(tmp_path) == []
    # 修改 a.json 里面的内容，x 从 1 改成 2
    (tmp_path / "a.json").write_text('{"x": 2}\n', encoding="utf-8")
    # 校验：现在内容改动，check 应该返回【内容被改动：a.json】这条报错
    assert freeze.check(tmp_path) == ["内容被改动：a.json"]
