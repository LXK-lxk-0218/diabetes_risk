---
name: implement-step
description: 照规格卡和验收测试实现一步：先跑测试、说计划，人确认以后再写代码，直到验收测试和质量门全绿。规格卡和验收测试已经提交、打了 spec tag 以后使用。
---
# implement-step：先说计划，再照规格卡和测试写

1. 先别写代码。读 `AGENTS.md`、这一步的规格卡（`docs/specs/<步骤>.md`）和验收测试。
2. 跑一次验收测试，说清哪些红、为什么红。
3. 用几句话说计划，在会话里说，不写成文件：
   - 新建、修改哪些文件，都要在规格卡“位置与依赖方向”里；
   - 每个公开名字的签名；
   - 每条不变量打算怎么保证；
   - 有什么副作用（比如配置指纹会变）；
   - 要加的依赖和 `uv add` 命令。
4. 等人回“开始”。
5. 每改一轮：`uv run ruff format .` → `uv run ruff check --fix .` → `uv run python scripts/ci.py`。
6. 不改 `tests/acceptance/`、`tests/architecture/`、`docs/specs/`、门槛和契约；觉得它们有问题，停下来说明。
7. 新增了公开名字：做完以后告诉人，由人运行 `uv run python scripts/api_snapshot.py --write`。
8. 同一项检查三轮还红，停下来，贴出失败输出和试过的办法。
9. 交付时贴原文：改了哪些文件；`git status --short` 和 `git diff --stat`；质量门最后几行。
