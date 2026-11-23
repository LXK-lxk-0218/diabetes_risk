"""
冻结基线：给 baselines/<名称>/ 下的每个文件算 SHA256，写进同目录的 SHA256SUMS。
用法（仓库根目录）：
    uv run python scripts/freeze_baseline.py baselines/<名称> --write    # 冻结（只在建立基线时做一次）
    uv run python scripts/freeze_baseline.py baselines/<名称> --check    # 校验（任何时候都可以跑）
基线一经冻结即只读：后面所有新实现都和它对账，不能反过来改它。
架构测试 tests/architecture/test_baselines.py 会对每个基线目录跑 --check 的同一套逻辑。
"""

# 向前兼容注解，支持类型提示
from __future__ import annotations

# 导入命令行参数解析模块
import argparse

# 哈希算法库，用来计算 SHA256 指纹
import hashlib

# 系统模块，用来控制程序退出码
import sys

# 路径库，跨平台安全处理文件路径
from pathlib import Path

# 哈希清单文件名，固定叫 SHA256SUMS
# 清单文件自己不参与哈希计算
SUMS = "SHA256SUMS"


def sha256_file(path: Path) -> str:
    """按字节算文件的 SHA256。

    每次读 1 MiB（1 << 20 字节），大文件也不会一次读进内存。
    iter(函数, b"") 的意思是：反复调用函数，直到它返回空字节串（读到文件末尾）为止。
    """
    # 新建一个 sha256 哈希对象
    digest = hashlib.sha256()
    # rb 二进制只读打开，保证读取原始字节，不能用文本模式
    with path.open("rb") as fh:
        # 循环读取，每次读取 1MB，直到读到文件末尾返回空字节 b"" 停止
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            # 把读到的字节块更新进哈希计算
            digest.update(chunk)
    # 返回十六进制的哈希字符串
    return digest.hexdigest()


def compute(directory: Path) -> dict[str, str]:
    """目录下除 SHA256SUMS 以外的全部文件 → {相对路径（正斜杠）: sha256}。

    两个细节决定了“同一个目录在任何机器上算出同一份清单”：
    - sorted：文件按路径排序，清单的行序固定；
    - as_posix()：路径一律用正斜杠，Windows 上写出来的清单和 Linux 上逐字节相同。
    """
    # 递归遍历目录所有内容，只保留文件，过滤掉 SHA256SUMS 清单本身，并且排序
    files = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != SUMS)
    # 构建字典：key=相对路径（统一正斜杠），value=文件哈希
    return {p.relative_to(directory).as_posix(): sha256_file(p) for p in files}


def read_sums(directory: Path) -> dict[str, str]:
    """读回 SHA256SUMS。每行格式与 sha256sum 命令相同：“指纹  相对路径”。"""
    # 准备空字典，存放清单里记录的【路径-哈希】
    result: dict[str, str] = {}
    # 读取清单文本，按行分割
    for line in (directory / SUMS).read_text(encoding="utf-8").splitlines():
        # 跳过空行
        if line.strip():
            # maxsplit=1：只在第一处空白切开，文件名里就算带有空格，也不会被切错
            digest, name = line.split(maxsplit=1)
            result[name.strip()] = digest
    return result


def check(directory: Path) -> list[str]:
    """返回问题清单；空清单表示基线完好。

    三类问题分开报：缺文件、多文件、内容被改。只说“不一致”，查起来就要从头比。
    """
    # 如果目录里根本没有 SHA256SUMS 清单，直接返回报错
    if not (directory / SUMS).is_file():
        return [f"{directory} 缺少 {SUMS}"]
    # 读取清单里预期哈希，同时计算当前目录真实文件哈希
    expected, actual = read_sums(directory), compute(directory)
    # 集合差集：预期有、实际没有 → 缺少文件
    problems = [f"缺少文件：{n}" for n in sorted(expected.keys() - actual.keys())]
    # 集合差集：实际有、清单里没有 → 多出未知文件
    problems += [f"多出文件：{n}" for n in sorted(actual.keys() - expected.keys())]
    # 交集：两边都存在，但是哈希不一样 → 文件内容改动
    problems += [f"内容被改动：{n}" for n in sorted(expected.keys() & actual.keys()) if expected[n] != actual[n]]
    return problems


def write(directory: Path) -> None:
    """计算并写入 SHA256SUMS。

    newline="\\n"：在 Windows 上也写 LF 换行。否则清单本身的字节在两种系统上不同。
    """
    # 拼接每一行：哈希 + 两个空格 + 文件路径，和系统 sha256sum 格式对齐
    lines = [f"{digest}  {name}" for name, digest in compute(directory).items()]
    # 写入清单，强制换行符为 LF，utf-8 编码，保证跨平台字节一致
    (directory / SUMS).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    """程序入口，解析命令行参数，分发 write/check 逻辑。"""
    parser = argparse.ArgumentParser(description="冻结或校验一个基线目录")
    # 第一个位置参数：基线目录路径
    parser.add_argument("directory", type=Path)
    # 互斥参数组：--write 和 --check 只能选一个，必须选一个
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="计算并写入 SHA256SUMS")
    mode.add_argument("--check", action="store_true", help="按 SHA256SUMS 校验")
    args = parser.parse_args(argv)
    # 如果是写入冻结模式
    if args.write:
        write(args.directory)
        print(f"已冻结：{args.directory / SUMS}")
        return 0
    # 校验模式：拿到所有问题
    problems = check(args.directory)
    # 逐条打印问题
    for p in problems:
        print(p)
    # 输出最终结论
    print("基线完好" if not problems else f"基线校验失败：{len(problems)} 处")
    # 返回退出码：0 代表成功，非 0 代表失败，CI 可以识别这个状态
    return 0 if not problems else 1


if __name__ == "__main__":
    # 执行入口，把 main 返回值作为程序退出码
    sys.exit(main())
