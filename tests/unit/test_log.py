"""结构化日志：JSON 输出、上下文绑定、脱敏、级别过滤。"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator

import pytest

from diabetes_risk.observability.log import bind_context, clear_context, configure_logging, get_logger


# 夹具：把日志配置成 JSON、写进一个内存缓冲区（StringIO），测试从里面读日志。
# yield 之前是准备，之后是收尾：清掉上下文、恢复默认配置，测试之间互不影响
@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    configure_logging("INFO", "json", stream=buffer)
    yield buffer
    clear_context()
    configure_logging("INFO", "console")


# 把缓冲区里的内容按行切开，每行解析成一个字典；空行跳过
def _records(buffer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


# 每条日志都要带上事件名、级别、logger 名和时间戳；调用时传的字段（rows）原样保留
def test_json_record_has_standard_fields(stream: io.StringIO) -> None:
    get_logger("prepare").info("dataset_built", rows=32632)
    # (record,) = …：解包成“正好一个元素”；多一条或少一条日志都会直接报错
    (record,) = _records(stream)
    assert record["event"] == "dataset_built"
    assert record["level"] == "info"
    assert record["logger"] == "prepare"
    assert record["rows"] == 32632
    assert "ts" in record


# 绑定的上下文出现在之后的每条日志里，clear_context() 以后就不再出现
def test_bound_context_appears_until_cleared(stream: io.StringIO) -> None:
    bind_context(run_id="r-001")
    get_logger("train").info("fit_started")
    clear_context()
    get_logger("train").info("fit_finished")
    first, second = _records(stream)
    assert first["run_id"] == "r-001"
    assert "run_id" not in second


# 居民编号和整条特征被替换成 *** ；不在清单里的字段（score）照常记录
def test_sensitive_fields_are_redacted(stream: io.StringIO) -> None:
    get_logger("api").info("predicted", resident_id="R0000014", features={"age": 58}, score=0.4)
    (record,) = _records(stream)
    assert record["resident_id"] == "***"
    assert record["features"] == "***"
    assert record["score"] == 0.4


# 级别是 INFO：debug 被过滤掉，warning 留下
def test_level_filtering(stream: io.StringIO) -> None:
    get_logger("x").debug("too_detailed")
    get_logger("x").warning("worth_seeing")
    assert [r["event"] for r in _records(stream)] == ["worth_seeing"]


# 拼错的级别名在配置时就报错，而不是悄悄退回默认级别
def test_unknown_level_rejected() -> None:
    with pytest.raises(ValueError, match="未知日志级别"):
        configure_logging("LOUD")
