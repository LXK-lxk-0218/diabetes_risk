"""唯一质量门：一条命令依次跑完五道门，任何一道失败即整体失败。

用法（仓库根目录）：
    uv run python scripts/ci.py

五道门，便宜的在前，贵的在后：
    1. ruff 检查       语法错误、没用到的导入、容易出错的写法
    2. ruff 格式       只检查、不改写（--check）；格式不对就失败
    3. mypy 类型       函数必须写类型标注，类型对不上就失败
    4. import-linter   三个包之间的依赖方向（契约写在 .importlinter）
    5. pytest + 覆盖率 测试全过，并且覆盖率不低于门槛

覆盖率门槛只写在 pyproject.toml 的 [tool.coverage.report] fail_under，这里读它，不写死。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import NamedTuple

# 仓库根目录 = 本文件所在目录（scripts/）的上一级。
# 用 __file__ 定位，不依赖“当前在哪个目录”：从任何目录启动，找到的都是同一个根（防 E1）
ROOT = Path(__file__).resolve().parent.parent


class Gate(NamedTuple):
    """一道门：name 是给人看的显示名，command 是真正执行的命令。守门测试断言的是 command。"""

    name: str
    command: list[str]


def _tool(name: str) -> str:
    """找到当前虚拟环境里的命令行工具（Windows 下带 .exe）。

    lint-imports 没有 `python -m` 入口，只能按可执行文件调用。
    先在当前解释器所在目录（.venv/bin 或 .venv/Scripts）里找，找不到再交给系统 PATH。
    """
    bindir = Path(sys.executable).parent
    for candidate in (bindir / name, bindir / f"{name}.exe"):
        if candidate.exists():
            return str(candidate)
    return name


def _coverage_floor() -> int:
    """从 pyproject.toml 读覆盖率门槛：门槛只有这一个出处，改门槛只改一处（防 E8）。"""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return int(data["tool"]["coverage"]["report"]["fail_under"])


def gates() -> list[Gate]:
    """五道门，按顺序。

    一律用当前虚拟环境的解释器（sys.executable）去跑，用的就是 uv.lock 锁定的版本，
    而不是系统里碰巧装着的某个版本（防 E2）。
    """
    py = sys.executable
    return [
        Gate("ruff 检查", [py, "-m", "ruff", "check", "."]),
        Gate("ruff 格式", [py, "-m", "ruff", "format", "--check", "."]),
        Gate("mypy 类型", [py, "-m", "mypy"]),
        Gate("import-linter 分层契约", [_tool("lint-imports"), "--no-logo"]),
        Gate(
            "pytest + 覆盖率",
            [py, "-m", "pytest", "--cov", "--cov-report=term-missing", f"--cov-fail-under={_coverage_floor()}"],
        ),
    ]


def main() -> int:
    # 子进程一律打开 Python 的 UTF-8 模式。中文 Windows 默认按 GBK 读写文本，而仓库里的配置文件是 UTF-8、
    # 带中文（例如 .importlinter 的契约名）：不打开的话，某道门读配置时可能报 UnicodeDecodeError
    env = {**os.environ, "PYTHONUTF8": "1"}
    planned = gates()
    results: list[tuple[str, bool, float]] = []
    for gate in planned:
        # flush=True：先把标题打印出来，再让子进程输出，两者不会错位
        print(f"\n==== {gate.name} ====", flush=True)
        start = time.perf_counter()
        # cwd=ROOT：每道门都在仓库根目录运行，工具才能读到根目录的配置
        ok = subprocess.run(gate.command, cwd=ROOT, env=env).returncode == 0
        results.append((gate.name, ok, time.perf_counter() - start))
        if not ok:
            # 失败即停：后一道门建立在前一道之上，继续跑只会让真正的错误淹没在输出里
            break
    print("\n==== 结果 ====")
    for name, ok, seconds in results:
        print(f"{'通过' if ok else '失败'}  {name}  ({seconds:.1f}s)")
    # 全绿要同时满足：五道门都跑到了，而且都通过。只写 all(...) 不够：all([]) 是 True
    all_ok = len(results) == len(planned) and all(ok for _, ok, _ in results)
    print("质量门：全绿" if all_ok else "质量门：未通过")
    # 返回码给机器看：0 通过，1 失败。回放脚本就靠它判断每个 tag 的结果
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
