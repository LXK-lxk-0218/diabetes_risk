"""让不同的编程智能体读到同一套规矩和技能。

唯一的源头：
    AGENTS.md              项目规矩（Codex、Cursor 等直接读；Claude Code 经 CLAUDE.md 第一行引入）
    .agents/skills/        技能（Codex、Cursor 等直接读）
给 Claude Code 生成的镜像（不要手改）：
    .claude/skills/        和 .agents/skills/ 逐字节相同
为什么用脚本复制，而不用符号链接：Windows 上建符号链接要管理员权限，克隆下来也可能变成普通文本文件。

用法（仓库根目录）：
    uv run python scripts/sync_agent_files.py           同步：把 .agents/skills/ 镜像到 .claude/skills/
    uv run python scripts/sync_agent_files.py --check   只检查，不一致就列出来并返回 1（架构测试用它）
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# 仓库根：本文件在 scripts/ 下，往上一级就是仓库根。不依赖“当前目录在哪”
ROOT = Path(__file__).resolve().parent.parent
# 唯一源头与生成的镜像（都相对仓库根）
SOURCE = Path(".agents/skills")
MIRROR = Path(".claude/skills")


def _files(base: Path) -> dict[str, bytes]:
    """一个技能目录下的全部文件：{相对路径: 字节}。目录不存在时返回空字典。"""
    if not base.is_dir():
        return {}
    # 逐字节读：比对和复制都以字节为准，换行符、编码都算差异
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def check(root: Path = ROOT) -> list[str]:
    """返回问题清单；空清单表示两套工具读到的是同一份东西。"""
    problems: list[str] = []
    # CLAUDE.md 第一行是否引入 AGENTS.md，由 tests/architecture/test_layout.py 守着（卷一 A1），这里不重复
    source, mirror = _files(root / SOURCE), _files(root / MIRROR)
    # 只在源头有的：镜像缺文件（加了技能忘了同步）
    for name in sorted(source.keys() - mirror.keys()):
        problems.append(f".claude/skills 缺少 {name}")
    # 只在镜像有的：有人直接往镜像里加东西
    for name in sorted(mirror.keys() - source.keys()):
        problems.append(f".claude/skills 多出 {name}（技能只能加在 .agents/skills）")
    # 两边都有但内容不同：有人手改了镜像
    for name in sorted(source.keys() & mirror.keys()):
        if source[name] != mirror[name]:
            problems.append(f".claude/skills/{name} 和 .agents/skills 里的不一样（不要手改镜像）")
    return problems


def sync(root: Path = ROOT) -> None:
    """把源头整份复制到镜像：先删旧镜像，避免删掉的技能残留在镜像里。"""
    mirror = root / MIRROR
    if mirror.exists():
        shutil.rmtree(mirror)
    if (root / SOURCE).is_dir():
        shutil.copytree(root / SOURCE, mirror)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同步技能库给不同的编程智能体")
    parser.add_argument("--check", action="store_true", help="只检查，不修改")
    args = parser.parse_args(argv)
    if not args.check:
        sync()
    problems = check()
    for p in problems:
        print(f"✗ {p}")
    print("智能体文件：一致" if not problems else f"智能体文件：{len(problems)} 处不一致")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
