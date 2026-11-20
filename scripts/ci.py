"""
ci.py — 项目唯一质量门：一条命令，五道检查，全绿才算合格。

五道质量门（串联安检，任意一道不合格直接停下）：
  1. ruff check        — 代码规范检查
  2. ruff format --check — 代码格式化检查
  3. mypy               — 类型检查
  4. lint-imports       — 分层依赖契约检查
  5. pytest + coverage  — 单元测试 + 覆盖率
"""

import os
import subprocess
import sys

# Windows 下强制 UTF-8 输出，避免 GBK 编码错误
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
CHECK = "[OK]"
CROSS = "[FAIL]"


def run_step(step_name: str, command: list[str]) -> bool:
    """运行一个检查步骤，返回是否通过。"""
    print(f"\n{YELLOW}[{step_name}]{RESET} running...")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.returncode == 0:
            print(f"{GREEN}[{step_name}] PASS {CHECK}{RESET}")
            lines = result.stdout.strip().split("\n")
            for line in lines[-3:]:
                if line.strip():
                    print(f"  {line.strip()}")
            return True
        else:
            print(f"{RED}[{step_name}] FAIL {CROSS}{RESET}")
            if result.stdout.strip():
                print(result.stdout[:2000])
            if result.stderr.strip():
                print(result.stderr[:2000])
            return False
    except FileNotFoundError:
        print(f"{RED}[{step_name}] command not found: {command[0]}{RESET}")
        return False
    except subprocess.TimeoutExpired:
        print(f"{RED}[{step_name}] timeout{RESET}")
        return False


def main() -> int:
    print(f"{'=' * 60}")
    print("  Diabetes Risk Screening - Quality Gate")
    print("  Only pass standard: uv run python scripts/ci.py")
    print(f"{'=' * 60}")

    steps: list[tuple[str, list[str]]] = [
        ("1/5 ruff check", ["uv", "run", "ruff", "check"]),
        ("2/5 ruff format", ["uv", "run", "ruff", "format", "--check"]),
        ("3/5 mypy type check", ["uv", "run", "mypy"]),
        ("4/5 import-linter contracts", ["uv", "run", "lint-imports"]),
        (
            "5/5 pytest + coverage",
            [
                "uv",
                "run",
                "pytest",
                "--cov=diabetes_risk",
                "--cov=drisk_training",
                "--cov=drisk_api",
                "--cov-report=term",
            ],
        ),
    ]

    passed = 0
    failed = 0

    for step_name, command in steps:
        if run_step(step_name, command):
            passed += 1
        else:
            failed += 1
            print(f"\n{RED}Quality gate stopped at step {passed + failed}.{RESET}")
            break

    total = passed + failed
    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"{GREEN}  ALL GREEN [{passed}/{total} PASSED]{RESET}")
        print(f"{'=' * 60}")
        return 0
    else:
        print(f"{RED}  FAILED [{passed}/{total}] ({failed} failed){RESET}")
        print(f"{'=' * 60}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
