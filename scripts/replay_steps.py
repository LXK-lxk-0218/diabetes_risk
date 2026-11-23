"""
逐个 step tag 回放质量门：证明“任意一步都能独立成立”。
用法（仓库根目录，需要能联网或已有 uv 缓存）：
    uv run python scripts/replay_steps.py              # 回放全部 step-* tag
    uv run python scripts/replay_steps.py step-A2      # 只回放指定的 tag
做法：为每个 tag 建一个临时 git worktree，在里面 uv run python scripts/ci.py，跑完删除。
"""

# 兼容旧版本 Python 的注解写法，现代 Python 可以不用
from __future__ import annotations

# subprocess：调用终端命令（git、uv）
import subprocess

# sys：读取命令行参数、控制程序退出码
import sys

# tempfile：自动创建临时文件夹，用完自动回收
import tempfile

# Path：面向对象处理文件路径，跨平台（Windows/Linux/Mac）
from pathlib import Path

# 拿到当前脚本文件所在路径，向上跳一层，定位到仓库根目录
ROOT = Path(__file__).resolve().parent.parent


def _git(*args: str) -> str:
    """在仓库根目录运行一条 git 命令，返回它的标准输出。

    check=True：git 失败（比如 tag 不存在）就直接抛异常，不把错误当成空结果继续往下走。
    """
    # cwd=ROOT 指定在仓库根目录执行 git；capture_output 捕获输出；text 按字符串处理
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def step_tags() -> list[str]:
    """全部 step-* tag，按创建时间排序：A1 在前，A2 在后。"""
    # --sort=creatordate：按标签创建时间排序，保证顺序是 A1→A2
    tags = _git("tag", "--list", "step-*", "--sort=creatordate").split()
    return tags


def replay(tag: str) -> bool:
    """在一个临时 worktree 里检出 tag，跑一遍质量门。

    worktree 是同一个仓库的第二个工作目录：检出旧 tag 不会碰你当前目录里的任何文件，
    所以哪怕你手上有没提交的修改，回放也是安全的。
    """
    # 创建临时目录，前缀 drisk-replay-，with 块结束自动删除临时目录
    with tempfile.TemporaryDirectory(prefix="drisk-replay-") as tmp:
        # 在临时目录里，再新建一个以 tag 命名的文件夹，作为 worktree 目录
        tree = Path(tmp) / tag
        # git worktree add --detach：游离头检出 tag，不创建分支，不会污染分支
        _git("worktree", "add", "--detach", str(tree), tag)
        try:
            # 打印分割线，方便看日志，flush=True 立刻输出，不缓存
            print(f"\n######## {tag} ########", flush=True)
            # 在这个 worktree 目录执行 ci 脚本（质量门禁：测试、基线校验等）
            # uv run 读取这个 tag 版本里的 uv.lock，安装对应版本依赖，环境隔离
            ret = subprocess.run(["uv", "run", "python", "scripts/ci.py"], cwd=tree)
            # 返回布尔值：返回码 0 代表成功，非 0 代表失败
            return ret.returncode == 0
        finally:
            # finally 无论上面 ci 成功还是崩溃，都会执行！
            # 强制删除 worktree，不然 git 会一直记录这个工作区，造成垃圾残留
            _git("worktree", "remove", "--force", str(tree))


def main(argv: list[str]) -> int:
    """主逻辑：读取参数、收集 tag、逐个回放、汇总结果。"""
    # 如果命令行传了 tag，就回放指定 tag；不传就拿到所有 step 标签
    tags = argv or step_tags()
    if not tags:
        print("没有 step-* tag 可以回放")
        return 1
    # 列表推导式：逐个执行 replay，保存（tag 名，是否成功）
    results = [(tag, replay(tag)) for tag in tags]
    # 打印汇总表头
    print("\n==== 回放结果 ====")
    # 循环打印每一个 tag 的结果
    for tag, ok in results:
        print(f"{'通过' if ok else '失败'}  {tag}")
    # 全部通过返回 0，只要有一个失败返回 1（CI 标准退出码）
    return 0 if all(ok for _, ok in results) else 1


# 程序入口：脚本直接运行时才执行 main，import 导入时不执行
if __name__ == "__main__":
    # 把命令行参数传给 main，退出码交给系统
    sys.exit(main(sys.argv[1:]))
