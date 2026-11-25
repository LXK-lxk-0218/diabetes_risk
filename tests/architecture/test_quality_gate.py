"""守门测试：质量门本身也要有测试守着。断言真正执行的命令，不断言给人看的显示名。"""

from __future__ import annotations

from pathlib import Path


def test_five_gates_run_the_real_tools_in_order(repo) -> None:
    """五道门按顺序跑真正要跑的工具；显示名怎么改都不影响这条测试。"""
    commands = [gate.command for gate in repo.load_script("ci").gates()]
    assert len(commands) == 5
    # 去掉第一项（解释器路径，每台机器不同），比后面的参数
    assert commands[0][1:] == ["-m", "ruff", "check", "."]
    assert commands[1][1:] == ["-m", "ruff", "format", "--check", "."]
    assert commands[2][1:] == ["-m", "mypy"]
    # lint-imports 是可执行文件：Linux 上叫 lint-imports，Windows 上叫 lint-imports.exe，stem 都是 lint-imports
    assert Path(commands[3][0]).stem == "lint-imports"
    assert commands[4][1:4] == ["-m", "pytest", "--cov"]


def test_coverage_gate_uses_the_floor_in_pyproject(repo) -> None:
    """覆盖率门槛只有一个出处：pyproject。ci.py 里写死一个数（哪怕写成 0），这里就红。"""
    floor = repo.toml("pyproject.toml")["tool"]["coverage"]["report"]["fail_under"]
    assert repo.load_script("ci").gates()[-1].command[-1] == f"--cov-fail-under={floor}"
