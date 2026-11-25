"""A2 结构化日志：验收测试（人维护，智能体只读）。出题依据：docs/steps/A2.md、docs/api/observability.md。"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator

import pytest

from diabetes_risk.observability.log import bind_context, clear_context, configure_logging, get_logger


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    """把日志收进一个 StringIO，每行解析成一个字典；用完恢复默认配置、清掉上下文。"""
    buffer = io.StringIO()
    configure_logging("INFO", "json", stream=buffer)
    yield buffer
    clear_context()
    configure_logging()


def _records(buffer: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]


# ------------------------------------------------------------------ 用法


def test_usage_one_line_one_json_record(stream: io.StringIO) -> None:
    """每条日志一行 JSON，带事件名、级别、日志器名、UTC 时间和自己的字段。"""
    get_logger("prepare").info("rows_cleaned", rule="weight_jin_to_kg", rows=520)
    (record,) = _records(stream)
    assert record["event"] == "rows_cleaned"
    assert record["level"] == "info"
    assert record["logger"] == "prepare"
    assert record["rule"] == "weight_jin_to_kg" and record["rows"] == 520
    assert str(record["ts"]).endswith("Z")


def test_usage_context_is_attached_until_cleared(stream: io.StringIO) -> None:
    """bind_context 绑定一次，之后每条都带上；clear_context 之后不再带。"""
    bind_context(run_id="r-001")
    get_logger("train").info("fit_started")
    clear_context()
    get_logger("train").info("fit_finished")
    first, second = _records(stream)
    assert first["run_id"] == "r-001"
    assert "run_id" not in second


def test_usage_logger_created_before_configure_follows_later_config() -> None:
    """模块顶层先 get_logger（甚至先 bind），之后才 configure_logging，新配置照样生效，脱敏也不会被绕开。"""
    log = get_logger("early").bind(run_id="r-001")
    buffer = io.StringIO()
    configure_logging("INFO", "json", stream=buffer)
    try:
        log.info("still_works", resident_id="R0000014")
        record = json.loads(buffer.getvalue())
        assert record["event"] == "still_works" and record["run_id"] == "r-001"
        assert record["resident_id"] == "***"
    finally:
        configure_logging()


# ------------------------------------------------------------------ 契约


def test_chinese_is_written_as_is(stream: io.StringIO) -> None:
    """JSON 里的中文原样输出，不转成 \\uXXXX。"""
    get_logger("x").info("note_written", note="空腹血糖")
    assert "空腹血糖" in stream.getvalue()


def test_level_filtering(stream: io.StringIO) -> None:
    """低于设定级别的日志不输出。"""
    get_logger("x").debug("too_detailed")
    get_logger("x").warning("worth_seeing")
    assert [r["event"] for r in _records(stream)] == ["worth_seeing"]


def test_exception_is_formatted_into_the_record(stream: io.StringIO) -> None:
    """在 except 里用 .exception() 记录，堆栈进 exception 字段。"""
    try:
        raise ValueError("坏数据")
    except ValueError:
        get_logger("x").exception("step_failed")
    (record,) = _records(stream)
    assert "ValueError: 坏数据" in str(record["exception"])


@pytest.mark.parametrize(("level", "fmt"), [("LOUD", "json"), ("INFO", "xml")])
def test_unknown_level_or_format_is_rejected(level: str, fmt: str) -> None:
    """级别或格式拼错，配置时就报 ValueError。"""
    with pytest.raises(ValueError):
        configure_logging(level, fmt)


# ------------------------------------------------------------------ 性质


@pytest.mark.parametrize("key", ["resident_id", "visit_id", "features", "name", "phone", "id_card"])
def test_every_default_sensitive_key_is_redacted_at_any_depth(stream: io.StringIO, key: str) -> None:
    """默认清单里的每个键，在顶层、字典里、列表里的字典里，值都换成 ***；别的字段不动。"""
    get_logger("api").info("predicted", score=0.4, **{key: "R0000014"}, nested={key: "R1"}, items=[{key: "R2"}])
    (record,) = _records(stream)
    assert record[key] == "***"
    assert record["nested"] == {key: "***"}
    assert record["items"] == [{key: "***"}]
    assert record["score"] == 0.4


def test_bound_context_is_redacted_too(stream: io.StringIO) -> None:
    """上下文里绑定的敏感字段也会被遮住。"""
    bind_context(resident_id="R0000014")
    get_logger("api").info("request_received")
    assert _records(stream)[0]["resident_id"] == "***"


def test_custom_redact_list_replaces_the_default() -> None:
    """redact 参数给出自己的清单。"""
    buffer = io.StringIO()
    configure_logging("INFO", "json", redact={"token"}, stream=buffer)
    try:
        get_logger("x").info("called", token="abc", resident_id="R1")
        record = json.loads(buffer.getvalue())
        assert record["token"] == "***" and record["resident_id"] == "R1"
    finally:
        configure_logging()
