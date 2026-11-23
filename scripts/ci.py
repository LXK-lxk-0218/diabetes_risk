"""
唯一质量门：一条命令依次跑完五道门，任何一道失败即整体失败。

用法（仓库根目录）：
    uv run python scripts/ci.py

五道门，便宜的在前，贵的在后：
    1. ruff 检查       语法错误、没用到的导入、容易出错的写法
    2. ruff 格式       只检查、不改写（--check）；格式不对就失败
    3. mypy 类型       函数必须写类型标注，类型对不上就失败
    4. import-linter   三个包之间的依赖方向（契约写在 .importlinter）
    5. pytest + 覆盖率 测试全过，并且覆盖率不低于门槛

覆盖率门槛从 pyproject.toml 的 [tool.coverage.report] fail_under 读取，这里不写死。
"""

# 开启延迟类型注解，类型提示可以直接写，不用提前导入类型
from __future__ import annotations

# 读取系统环境变量，用来注入PYTHONUTF8
import os

# 用来启动子进程，调用ruff/mypy/pytest等工具
import subprocess

# 获取当前解释器、控制程序退出码
import sys

# 计时，统计每道门耗时
import time

# tomllib 用来读取toml配置文件（python3.11+内置）
import tomllib

# 路径处理，跨平台兼容Windows、Mac、Linux
from pathlib import Path

# 仓库根目录 = 本文件所在目录（scripts/）的上一级。
# 用 __file__ 定位，不依赖“当前在哪个目录”：从任何目录启动，找到的都是同一个根（防 E1）。
# __file__：当前ci.py文件路径；resolve()拿到绝对路径；parent是scripts文件夹；parent.parent就是项目根目录
ROOT = Path(__file__).resolve().parent.parent


def _tool(name: str) -> str:
    """找到当前虚拟环境里的命令行工具（Windows 下带 .exe）。

    lint-imports 没有 `python -m` 入口，只能按可执行文件调用。
    先在当前解释器所在目录（.venv/bin 或 .venv/Scripts）里找，找不到再交给系统 PATH。
    """
    # sys.executable 是当前虚拟环境python解释器的完整路径，parent就是虚拟环境的bin/Scripts目录
    bindir = Path(sys.executable).parent
    # 优先尝试：不带exe、带exe两个候选（适配Windows）
    for candidate in (bindir / name, bindir / f"{name}.exe"):
        # 如果这个可执行文件存在，直接返回它的完整路径
        if candidate.exists():
            return str(candidate)
    # 虚拟环境里找不到，就直接返回名字，交给系统PATH去查找
    return name


def _coverage_floor() -> str:
    """从 pyproject.toml 读覆盖率门槛。

    门槛只写在 pyproject.toml 一个地方：这里读它，架构测试检查它不能被调低。
    要是在本文件里再写一个 85，就有了两处，改一处漏一处（E8）。
    """
    # 读取根目录下pyproject.toml文本，utf-8编码
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    # 从配置里取出 coverage 的fail_under阈值，转字符串返回，给pytest命令用
    return str(data["tool"]["coverage"]["report"]["fail_under"])


def steps() -> list[tuple[str, list[str]]]:
    """五道门，每一道是（显示名, 命令）。

    一律用当前虚拟环境的解释器（sys.executable）去跑，
    这样用的就是 uv.lock 锁定的那个版本，而不是系统里碰巧装着的某个版本（防 E2）。
    """
    # 获取当前虚拟环境python解释器路径
    py = sys.executable
    # 返回五道门清单：(显示名称, 命令参数列表)
    return [
        ("ruff 检查", [py, "-m", "ruff", "check", "."]),
        ("ruff 格式", [py, "-m", "ruff", "format", "--check", "."]),
        ("mypy 类型", [py, "-m", "mypy"]),
        ("import-linter 分层契约", [_tool("lint-imports")]),
        (
            "pytest + 覆盖率",
            [py, "-m", "pytest", "--cov", "--cov-report=term-missing", f"--cov-fail-under={_coverage_floor()}"],
        ),
    ]


def main() -> int:
    # 子进程一律打开 Python 的 UTF-8 模式（PYTHONUTF8=1）。中文 Windows 默认按 GBK 读写文本，
    # 而仓库里的配置文件都是 UTF-8、带中文（例如 .importlinter 的契约名）：不打开的话，
    # 某道门读配置时可能直接报 UnicodeDecodeError。1.2 里每个人都设过一次，这里再兜一次底。
    # 在原有环境变量基础上，追加/覆盖 PYTHONUTF8=1
    env = {**os.environ, "PYTHONUTF8": "1"}
    # 保存每道门结果：(名称, 是否通过, 耗时秒数)
    results: list[tuple[str, bool, float]] = []
    # 循环遍历每一道质量门
    for name, cmd in steps():
        # flush=True：先把标题打印出来，再让子进程输出，两者不会错位
        print(f"\n==== {name} ====", flush=True)
        # 记录开始时间
        t0 = time.perf_counter()
        # cwd=ROOT：每道门都在仓库根目录运行，工具才能读到根目录的配置；env 见上
        # 执行命令，返回值等于0代表成功
        ok = subprocess.run(cmd, cwd=ROOT, env=env).returncode == 0
        # 记录这道门的结果、耗时
        results.append((name, ok, time.perf_counter() - t0))
        if not ok:
            # 失败即停：后一道门建立在前一道之上，继续跑只会让真正的错误淹没在输出里
            break
    # 打印汇总结果标题
    print("\n==== 结果 ====")
    # 遍历打印每一道门的状态、耗时
    for name, ok, seconds in results:
        print(f"{'通过' if ok else '失败'}  {name}  ({seconds:.1f}s)")
    # 全绿要同时满足两件事：五道门都跑到了，而且都通过。
    # 只写 all(...) 不够：all([]) 是 True，一道门都没跑也会被当成“全绿”。
    all_ok = len(results) == len(steps()) and all(ok for _, ok, _ in results)
    print("质量门：全绿" if all_ok else "质量门：未通过")
    # 返回码给机器看：0 通过，1 失败。replay_steps.py 就靠它判断每个 tag 的结果。
    return 0 if all_ok else 1


if __name__ == "__main__":
    # 启动入口，把main的返回码交给系统
    sys.exit(main())
