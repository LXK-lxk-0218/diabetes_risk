"""A2 指纹与可复现：验收测试（人维护，智能体只读）。出题依据：docs/steps/A2.md、docs/api/core.md。"""

from __future__ import annotations

import hashlib
import random
import subprocess
from datetime import date, datetime
from itertools import permutations
from pathlib import Path

import pytest

from diabetes_risk.core.repro import (
    canonical_json,
    git_dirty,
    git_sha,
    set_global_seed,
    sha256_bytes,
    sha256_file,
    sha256_json,
)

# ------------------------------------------------------------------ 用法


def test_usage_same_content_same_fingerprint() -> None:
    """同一份口径换个键的顺序写，指纹不变；改一个数，指纹就变。"""
    spec = {"window_days": 90, "fpg_pos": 7.0, "train_end": date(2024, 6, 30)}
    reordered = {"train_end": date(2024, 6, 30), "fpg_pos": 7.0, "window_days": 90}
    assert sha256_json(spec) == sha256_json(reordered)
    assert sha256_json(spec) != sha256_json({**spec, "window_days": 60})


def test_usage_file_fingerprint_matches_hashlib(tmp_path: Path) -> None:
    """文件指纹就是文件字节的 SHA256（第 0 阶段的 file_sha256）。"""
    path = tmp_path / "incident.db"
    path.write_bytes(b"SQLite format 3\x00" * 1000)
    assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ 契约


def test_sha256_bytes_is_hex_sha256() -> None:
    """64 位小写十六进制。空字节串的 SHA256 是公开的已知值。"""
    assert sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_canonical_json_is_compact_sorted_and_keeps_chinese() -> None:
    """键排序、紧凑分隔符、中文原样（不转成 \\uXXXX）。"""
    assert canonical_json({"b": 1, "a": "年龄"}) == '{"a":"年龄","b":1}'


def test_canonical_json_writes_dates_and_paths_the_same_everywhere() -> None:
    """日期写成 ISO 字符串；路径一律正斜杠（Windows 上也一样）。"""
    assert canonical_json({"d": date(2024, 3, 2)}) == '{"d":"2024-03-02"}'
    assert canonical_json({"t": datetime(2024, 3, 2, 8, 30)}) == '{"t":"2024-03-02T08:30:00"}'
    assert canonical_json({"p": Path("data") / "raw" / "incident.db"}) == '{"p":"data/raw/incident.db"}'


@pytest.mark.parametrize("value", [object(), {1, 2}, b"bytes"])
def test_canonical_json_rejects_unknown_types(value: object) -> None:
    """不认识的类型直接报 TypeError，不用 str() 糊弄过去。"""
    with pytest.raises(TypeError):
        canonical_json({"x": value})


def test_git_functions_return_none_outside_a_repo(tmp_path: Path) -> None:
    """不在 git 仓库里时返回 None（表示“不知道”），不抛错。"""
    assert git_sha(tmp_path) is None
    assert git_dirty(tmp_path) is None


def test_git_functions_inside_a_repo(tmp_path: Path) -> None:
    """在仓库里，git_sha 是 40 位提交号；git_dirty 区分干净和有改动。"""

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True)

    git("init", "-q")
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-q", "-m", "first")
    sha = git_sha(tmp_path)
    assert sha is not None and len(sha) == 40
    assert git_dirty(tmp_path) is False
    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    assert git_dirty(tmp_path) is True


def test_set_global_seed_makes_random_repeatable() -> None:
    """同一个种子，Python 的全局随机数序列相同。"""
    set_global_seed(42)
    first = [random.random() for _ in range(3)]
    set_global_seed(42)
    assert [random.random() for _ in range(3)] == first


# ------------------------------------------------------------------ 性质


def test_key_order_never_changes_the_fingerprint() -> None:
    """四个键的 24 种写入顺序，指纹全都一样。"""
    items = [("window_days", 90), ("max_report_lag_days", 30), ("fpg_pos", 7.0), ("hba1c_pos", 6.5)]
    fingerprints = {sha256_json(dict(order)) for order in permutations(items)}
    assert len(fingerprints) == 1


@pytest.mark.parametrize("chunk_size", [1, 7, 1 << 20])
def test_chunk_size_never_changes_the_file_fingerprint(tmp_path: Path, chunk_size: int) -> None:
    """分块读，块多大都得到同一个指纹。"""
    path = tmp_path / "data.bin"
    path.write_bytes(bytes(range(256)) * 50)
    assert sha256_file(path, chunk_size=chunk_size) == hashlib.sha256(path.read_bytes()).hexdigest()
