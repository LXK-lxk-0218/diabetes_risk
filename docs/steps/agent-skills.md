# 阶段 -3：智能体技能（Skills）

- 目标：把卷一的五份提示词拆成 6 套固定指令模板（技能），两种编程智能体读到同一份。
- 验收：`.agents/skills/` 下 6 个技能；`.claude/skills/` 与它逐字节相同；`tests/architecture/test_agent_files.py` 全绿；`uv run python scripts/ci.py` 全绿。
- 不做：课上不用的钩子（hooks）与 MCP；不让 `--write` 类的人工操作自动化；不写卷二之后的技能。

## 为什么要单一源头 + 镜像

- 现状：Codex、Cursor 等读 `.agents/skills/`；Claude Code 读 `.claude/skills/`。
- 只写一份：源头在 `.agents/skills/`，用 `scripts/sync_agent_files.py` 复制出镜像。
- 不用符号链接：Windows 上建链接要管理员权限，克隆下来也可能变成普通文本文件。
- 不用两份手写：改一处漏一处，两边 AI 拿到的规则会不一致。

## 新增文件

- `.agents/skills/spec-card/SKILL.md`：写规格卡（概要八项 + 精确决定七节），只写文档。
- `.agents/skills/acceptance-tests/SKILL.md`：只看规格卡出验收测试，用法 → 契约 → 规则三层。
- `.agents/skills/implement-step/SKILL.md`：先跑测试、说计划，人确认后实现，直到全绿。
- `.agents/skills/mutation-test/SKILL.md`：列 6–10 个“像对的”错误实现，检查测试强度。
- `.agents/skills/verify-step/SKILL.md`：交付前查质量门、受保护文件、签名快照。
- `.agents/skills/review-step/SKILL.md`：另开会话只读复核，最多 5 处，不下结论。
- `.claude/skills/`：由脚本生成的镜像，进 Git，不手改。
- `scripts/sync_agent_files.py`：`sync()` 整份复制；`--check` 只比对，不一致返回 1。
- `tests/architecture/test_agent_files.py`：守门测试，调用脚本的 `check()`。

## 技能格式

每个技能是一个文件夹，文件夹名就是技能名，里面必须有 `SKILL.md`。开头是 YAML 元数据：

- `name`：小写字母、数字、连字符，最多 64 字符，必须和文件夹名一致。
- `description`：最多 1024 字符，写清“干什么、什么时候用”，智能体靠它判断要不要读全文。

渐进加载：智能体先看名字和一句话简介，匹配上才读全文；脚本、参考资料只在需要时再读。
