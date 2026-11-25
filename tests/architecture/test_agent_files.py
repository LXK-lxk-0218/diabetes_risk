"""守卫：两种编程智能体读到同一套技能。

技能只写在 .agents/skills/（Codex、Cursor 等读）；.claude/skills/（Claude Code 读）由脚本复制，
两边必须逐字节相同。有人手改了镜像、或者加了技能忘了同步，这条测试就红。
"""

from __future__ import annotations


def test_skills_mirror_is_in_sync(repo) -> None:
    problems = repo.load_script("sync_agent_files").check(repo.root)
    assert not problems, "；".join(problems) + "。运行 uv run python scripts/sync_agent_files.py 修复"
