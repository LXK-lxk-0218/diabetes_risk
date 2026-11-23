"""指纹、规范化 JSON、种子、git 信息。"""

from __future__ import annotations

import hashlib
import random
from datetime import date
from pathlib import Path

import pytest

from diabetes_risk.core.repro import (
    canonical_json,
    git_dirty,
    git_sha,
    set_global_seed,
    sha256_file,
    sha256_json,
)


# tmp_path 是 pytest 自带的夹具：每个测试拿到一个独立的临时目录，测完自动清理，不碰仓库里的文件
def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc" * 1000)
    # chunk_size=7 故意取一个不能整除 3000 的数：最后一块不满，结果也必须和一次性算的相同
    assert sha256_file(path, chunk_size=7) == hashlib.sha256(b"abc" * 1000).hexdigest()


# a 和 b 内容相同，键的顺序不同（外层、内层都打乱了）：规范化之后必须逐字相同，中文不被转义
def test_canonical_json_ignores_key_order_and_keeps_chinese() -> None:
    a = {"b": 1, "a": {"y": [1, 2], "x": "年龄"}}
    b = {"a": {"x": "年龄", "y": [1, 2]}, "b": 1}
    assert canonical_json(a) == canonical_json(b) == '{"a":{"x":"年龄","y":[1,2]},"b":1}'
    assert sha256_json(a) == sha256_json(b)


# 日期转成 ISO 字符串，路径转成正斜杠；不认识的类型（object()）必须报错
def test_canonical_json_serializes_dates_and_paths() -> None:
    assert canonical_json({"d": date(2024, 3, 2), "p": Path("data") / "raw"}) == '{"d":"2024-03-02","p":"data/raw"}'
    with pytest.raises(TypeError, match="无法规范化"):
        canonical_json({"x": object()})


# 同一个种子设两次，得到的随机数序列必须一模一样
def test_set_global_seed_is_reproducible() -> None:
    set_global_seed(42)
    first = [random.random() for _ in range(3)]
    set_global_seed(42)
    assert [random.random() for _ in range(3)] == first


# 临时目录不是 git 仓库：两个函数都返回 None，而不是抛异常
def test_git_info_outside_repository(tmp_path: Path) -> None:
    assert git_sha(tmp_path) is None
    assert git_dirty(tmp_path) is None
