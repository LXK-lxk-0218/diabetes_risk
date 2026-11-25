---
name: verify-step
description: 一步交付前的检查：质量门、受保护文件有没有被动、签名快照只多不少。实现说“做完了”、准备打 step tag 之前使用；只报告结果，不替人下“通过”的结论。
---
# verify-step：交付前查三样

每一项都贴命令和输出原文，不要只说“通过了”。

1. 质量门：`uv run python scripts/ci.py`，最后一行要是“质量门：全绿”。
2. 受保护的文件，spec tag 之后谁动过：
   `git log --stat --format="%s" spec-<第一个小步>..HEAD -- tests/acceptance tests/architecture docs/specs scripts/ci.py baselines .importlinter`
   列出来的每个提交都要说清来历；`feat` 提交出现在这里，就停下来报告。
3. 签名快照改了哪几行：`git diff spec-<第一个小步>..HEAD -- docs/interfaces.md`
   以 `+` 开头的要对得上规格卡的“接口”一节；以 `-` 开头的是改了已有接口，停下来报告。
4. 只报告看到了什么，由人决定能不能打 `step-<步骤>` tag。
