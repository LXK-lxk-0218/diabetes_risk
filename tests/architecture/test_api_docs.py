"""接口记录的说明部分：docs/api/ 写到的名字都存在、地基的公开函数和类都有一节、示例都能运行。

签名不在说明里抄，以 docs/interfaces.md 为准。这里守的是说明不能写错、不能漏、不能过期。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# 地基：卷一 A2–A4 做的 10 个模块。以后的新模块，等它被另一个包依赖时，
# 把名字加进这里，同一次提交在 docs/api/ 写说明（这是“检查”，由人改）。
FOUNDATION = (
    "diabetes_risk.core.catalog",
    "diabetes_risk.core.errors",
    "diabetes_risk.core.registry",
    "diabetes_risk.core.repro",
    "diabetes_risk.observability.log",
    "diabetes_risk.observability.timing",
    "drisk_training.config.catalog",
    "drisk_training.config.env",
    "drisk_training.config.loader",
    "drisk_training.config.sections",
)
# 配置段（名字以 Section 结尾的类）是配置文件的形状：字段以 configs/base.yaml 的注释和
# docs/interfaces.md 为准，不在说明里逐个写。说明管的是“怎么调用”。
EXEMPT = re.compile(r"\w+Section")
MODULE_HEADING = re.compile(r"## `([\w.]+)`")


def _documented(root: Path) -> dict[str, set[str]]:
    """docs/api/*.md 里写到的 {模块: {名字}}：每个 '## `模块`' 下面的 '### `名字`'。"""
    found: dict[str, set[str]] = {}
    for page in sorted((root / "docs" / "api").glob("*.md")):
        module = None
        for line in page.read_text(encoding="utf-8").splitlines():
            if heading := MODULE_HEADING.fullmatch(line):
                module = heading.group(1)
                found.setdefault(module, set())
            elif (name := re.fullmatch(r"### `(\w+)`", line)) and module:
                found[module].add(name.group(1))
    return found


def _public(repo) -> dict[str, set[str]]:
    """代码里每个模块的公开函数和类：从快照里读，和 docs/interfaces.md 是同一种读法。"""
    out: dict[str, set[str]] = {}
    module = None
    for line in repo.load_script("api_snapshot").render(repo.root).splitlines():
        if heading := MODULE_HEADING.fullmatch(line):
            module = heading.group(1)
            out[module] = set()
        elif module and (name := re.match(r"- `(?:@\S+ )*(?:async )?(?:def|class) (\w+)", line)):
            out[module].add(name.group(1))
    return out


def test_every_documented_name_exists_in_the_code(repo) -> None:
    """说明里写的每个名字，代码里都有：写错了，或者改了名没同步。"""
    public = _public(repo)
    wrong = sorted(
        f"{m}.{n}" for m, names in _documented(repo.root).items() for n in names if n not in public.get(m, set())
    )
    assert not wrong, f"docs/api/ 写到的这些名字，代码里没有（写错了，或者已经改名）：{wrong}"


def test_every_public_function_and_class_of_the_foundation_has_a_section(repo) -> None:
    """地基每个公开函数和类都有一节说明；配置段类除外（它们的形状由 YAML 和快照说明）。"""
    public, documented = _public(repo), _documented(repo.root)
    assert set(FOUNDATION) <= set(public), f"地基模块不见了：{sorted(set(FOUNDATION) - set(public))}"
    missing = [
        f"{m}.{n}"
        for m in FOUNDATION
        for n in sorted(public[m])
        if not EXEMPT.fullmatch(n) and n not in documented.get(m, set())
    ]
    assert not missing, f"地基的这些公开名字在 docs/api/ 里还没有说明：{missing}"


def _examples(root: Path) -> list[tuple[str, str]]:
    """docs/api/*.md 里的每一段 ```python 示例，连同它在哪一页第几段。"""
    out: list[tuple[str, str]] = []
    for page in sorted((root / "docs" / "api").glob("*.md")):
        blocks = re.findall(r"```python\n(.*?)```", page.read_text(encoding="utf-8"), re.S)
        out += [(f"{page.name} 第 {i} 段", code) for i, code in enumerate(blocks, 1)]
    return out


def test_every_example_in_the_docs_runs(repo) -> None:
    """每段示例都能在仓库根目录跑通：说明不能过期。"""
    examples = _examples(repo.root)
    assert examples, "docs/api/ 里一段示例都没有"
    env = {**os.environ, "PYTHONUTF8": "1"}
    failed = []
    for where, code in examples:
        # 每段示例单独起一个进程、在仓库根目录运行：示例里配置日志、绑定上下文，都不会影响别的测试
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            timeout=120,
        )
        if result.returncode != 0:
            last = (result.stderr.strip() or result.stdout.strip()).splitlines()[-1:]
            failed.append(f"{where}：{last}")
    assert not failed, "这些示例跑不通：\n" + "\n".join(failed)
