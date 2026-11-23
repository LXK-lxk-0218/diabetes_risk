"""可复现与谱系：随机种子、文件与对象指纹、git 版本。

这里的指纹是后面所有“说得清从哪来”的基础：配置指纹、目录指纹、数据文件指纹、manifest 都用它。
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Any


def set_global_seed(seed: int) -> None:
    """固定 Python 与 NumPy（如果已安装）的全局随机数。模型自己的 random_state 另外传。"""
    # 先固定 Python 自带的 random 模块
    random.seed(seed)
    # numpy 不是核心包的依赖：装了就一起固定，没装就跳过。导入写在函数里面，
    # 核心包被导入时不会因为缺 numpy 而失败
    try:
        import numpy as np  # 延迟导入：核心包不强制依赖 numpy
    except ImportError:
        return
    # 这只管 numpy 的“全局”随机数。scikit-learn 等模型用自己的 random_state，要另外传
    np.random.seed(seed)


def sha256_bytes(data: bytes) -> str:
    # hexdigest()：把 32 字节的摘要写成 64 个十六进制字符；讲义里说的“前 8 位”“前 12 位”就是它的开头
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """分块计算文件指纹，大文件也不会一次读进内存。"""
    # 分块喂给同一个 digest，结果和一次读完整个文件完全相同（测试里用 chunk_size=7 验证过）
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        # iter(函数, 哨兵)：反复调用函数，直到返回值等于哨兵 b""（读到文件末尾）才停
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_default(obj: Any) -> str:
    # json.dumps 遇到不认识的类型（日期、路径……）时调用本函数，由它决定怎么转成字符串。
    # 日期统一写成 ISO 格式（2024-03-02），不受地区设置影响；datetime 是 date 的子类，两种都在这里处理
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    # 路径一律用正斜杠：Windows 上的 data\raw 和 Linux 上的 data/raw 得到同一个指纹
    if isinstance(obj, Path):
        return obj.as_posix()
    # 其他类型一律拒绝，而不是用 str(obj) 糊弄过去：str() 的结果可能带内存地址，每次运行都不一样
    raise TypeError(f"无法规范化为 JSON：{type(obj).__name__}")


def canonical_json(obj: Any) -> str:
    """规范化 JSON：键排序、紧凑分隔符、中文原样。同样的内容永远得到同样的字符串。"""
    # 四个参数各管一件事：
    #   sort_keys=True         键排序：{"b": 1, "a": 2} 和 {"a": 2, "b": 1} 写出来一样
    #   ensure_ascii=False     中文原样输出，不转成 \uXXXX
    #   separators=(",", ":")  去掉默认的空格，输出最紧凑，也就没有“空格多一个少一个”的差别
    #   default=_json_default  遇到日期、路径时交给上面的函数
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def sha256_json(obj: Any) -> str:
    """对象的内容指纹：先规范化成 JSON，再取 SHA256。键的顺序、缩进都不影响结果。"""
    # 字符串要先编码成字节才能算指纹；固定用 UTF-8，不跟随系统默认编码（中文 Windows 默认是 GBK）
    return sha256_bytes(canonical_json(obj).encode("utf-8"))


def _git(root: Path, *args: str) -> str | None:
    try:
        # 在 root 目录里运行一条 git 命令。check=True：git 返回非零就抛异常；capture_output + text：
        # 把输出收成字符串；timeout=10：git 卡住时不让整个程序跟着卡住
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        # OSError：找不到 git 程序；SubprocessError：包括非零退出（CalledProcessError）和超时（TimeoutExpired）。
        # 任何一种都返回 None，表示“不知道”，而不是让程序崩溃
        return None
    return result.stdout.strip()


def git_sha(root: Path) -> str | None:
    """当前提交号；不在 git 仓库里或没装 git 时返回 None。"""
    # or None：空字符串也当作“不知道”
    return _git(root, "rev-parse", "HEAD") or None


def git_dirty(root: Path) -> bool | None:
    """工作区是否有未提交的改动；无法判断时返回 None。"""
    # --porcelain：机器可读的简短格式，工作区干净时输出为空
    status = _git(root, "status", "--porcelain")
    # 三种结果要分开：None 不知道；False 干净；True 有未提交的改动
    return None if status is None else bool(status)
