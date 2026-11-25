"""A2 阶段计时：验收测试（人维护，智能体只读）。出题依据：docs/steps/A2.md、docs/api/observability.md。"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterator, Mapping

import pytest

from diabetes_risk.observability.log import configure_logging, get_logger
from diabetes_risk.observability.timing import current_emitter, timed, use_emitter


class ListEmitter:
    """测试用的接收方：只要有一个 emit 方法，就能当 MetricsEmitter 用。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, float, dict[str, str]]] = []

    def emit(self, name: str, value: float, tags: Mapping[str, str] | None = None) -> None:
        self.records.append((name, value, dict(tags or {})))


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    configure_logging("INFO", "json", stream=buffer)
    yield buffer
    configure_logging()


def _timed_records(buffer: io.StringIO) -> list[dict[str, object]]:
    records = [json.loads(line) for line in buffer.getvalue().splitlines() if line.strip()]
    return [r for r in records if r["event"] == "stage_timed"]


# ------------------------------------------------------------------ 用法


def test_usage_nested_with_blocks_join_the_path(stream: io.StringIO) -> None:
    """with 写法；嵌套时日志里的阶段名是 prepare.load。里层先结束、先记。"""
    with timed("prepare"):
        with timed("load"):
            pass
    inner, outer = _timed_records(stream)
    assert inner["stage"] == "prepare.load" and outer["stage"] == "prepare"
    assert inner["failed"] is False and outer["failed"] is False
    assert isinstance(inner["duration_ms"], int | float) and inner["duration_ms"] >= 0


def test_usage_decorator_keeps_the_function(stream: io.StringIO) -> None:
    """装饰器写法；返回值、函数名都不变，每调用一次记一次。"""

    @timed("fit")
    def fit(x: int) -> int:
        """训练。"""
        return x * 2

    assert fit(21) == 42 and fit(1) == 2
    assert fit.__name__ == "fit" and fit.__doc__ == "训练。"
    assert [r["stage"] for r in _timed_records(stream)] == ["fit", "fit"]


def test_usage_emitter_receives_the_duration(stream: io.StringIO) -> None:
    """use_emitter 里，耗时还会发给接收方；离开以后不再发。"""
    emitter = ListEmitter()
    with use_emitter(emitter):
        with timed("train"):
            with timed("fit"):
                pass
    with timed("after"):
        pass
    names = [name for name, _, _ in emitter.records]
    assert names == ["timing.train.fit_seconds", "timing.train_seconds"]
    assert all(value >= 0 and tags == {"failed": "false"} for _, value, tags in emitter.records)


# ------------------------------------------------------------------ 契约


@pytest.mark.parametrize("bad", ["", "a.b", None])
def test_stage_name_must_be_non_empty_without_dots(bad: object) -> None:
    """阶段名不能为空、不能含点号（点号留给嵌套路径），也不能不是字符串。"""
    with pytest.raises(ValueError):
        timed(bad)


def test_as_target_exposes_path_and_seconds() -> None:
    """with timed("x") as t，离开以后能读 t.path 和 t.seconds。"""
    with timed("outer"):
        with timed("x") as t:
            pass
    assert t.path == "outer.x"
    assert t.seconds is not None and t.seconds >= 0


def test_generator_functions_are_rejected() -> None:
    """生成器函数（含 async 生成器）一律拒绝：计时会在第一次 yield 时就结束。"""

    def gen() -> Iterator[int]:
        yield 1

    async def agen():
        yield 1

    for func in (gen, agen):
        with pytest.raises(TypeError):
            timed("x")(func)


def test_exception_is_reraised_and_marked_failed(stream: io.StringIO) -> None:
    """块里抛的异常原样往外抛，不被吞掉；耗时照样记，标记 failed。"""
    emitter = ListEmitter()
    with use_emitter(emitter), pytest.raises(ZeroDivisionError):
        with timed("boom"):
            raise ZeroDivisionError("坏数据")
    (record,) = _timed_records(stream)
    assert record["stage"] == "boom" and record["failed"] is True
    assert emitter.records[0][2] == {"failed": "true"}


def test_use_emitter_restores_the_previous_one() -> None:
    """use_emitter 嵌套使用，退出时精确恢复外层的设置。"""
    outer, inner = ListEmitter(), ListEmitter()
    assert current_emitter() is None
    with use_emitter(outer):
        with use_emitter(inner):
            assert current_emitter() is inner
        assert current_emitter() is outer
    assert current_emitter() is None


# ------------------------------------------------------------------ 性质


def test_sibling_stages_are_not_prefixed_at_any_depth(stream: io.StringIO) -> None:
    """每一层退出后都恢复嵌套状态。深度 1–4 的链之后，紧跟的同级阶段都不带前缀。"""
    for depth in range(1, 5):
        stages = [f"s{i}" for i in range(depth)]
        timers = [timed(s) for s in stages]
        for t in timers:
            t.__enter__()
        for t in reversed(timers):
            t.__exit__(None, None, None)
        with timed("next") as sibling:
            pass
        assert timers[-1].path == ".".join(stages)
        assert sibling.path == "next", depth


def test_async_tasks_do_not_mix_paths(stream: io.StringIO) -> None:
    """两个 async 任务交替运行，各自的嵌套路径不会串（服务同时处理多个请求时也一样）。"""

    async def job(name: str) -> str:
        with timed(name):
            await asyncio.sleep(0)
            with timed("inner") as t:
                await asyncio.sleep(0)
            return t.path

    async def main() -> list[str]:
        return list(await asyncio.gather(job("a"), job("b")))

    assert asyncio.run(main()) == ["a.inner", "b.inner"]


def test_async_function_is_timed_until_it_finishes(stream: io.StringIO) -> None:
    """async 函数要等 await 完成才算结束：函数里的日志一定在 stage_timed 之前。"""

    @timed("fetch")
    async def fetch() -> int:
        await asyncio.sleep(0)
        get_logger("demo").info("fetch_body_ran")
        return 7

    assert asyncio.run(fetch()) == 7
    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert events == ["fetch_body_ran", "stage_timed"]


def test_emitter_is_chosen_at_call_time_not_at_decoration_time() -> None:
    """函数在导入时就被装饰了，那时还没有接收方；调用时在 use_emitter 里，就发给它。"""

    @timed("load")
    def load() -> None:
        pass

    emitter = ListEmitter()
    with use_emitter(emitter):
        load()
    assert [name for name, _, _ in emitter.records] == ["timing.load_seconds"]


def test_broken_emitter_never_breaks_the_business(stream: io.StringIO) -> None:
    """接收方出错，被计时的代码照常返回；只多一条 timing_emit_failed 警告。"""

    class Broken:
        def emit(self, name: str, value: float, tags: Mapping[str, str] | None = None) -> None:
            raise ConnectionError("tracker down")

    @timed("train")
    def train() -> str:
        return "model"

    with use_emitter(Broken()):
        assert train() == "model"
    events = [json.loads(line)["event"] for line in stream.getvalue().splitlines()]
    assert events == ["stage_timed", "timing_emit_failed"]


def test_broken_log_stream_never_breaks_the_business() -> None:
    """日志写不出去（输出流坏了），被计时的代码照常返回。"""

    class BrokenStream(io.StringIO):
        def write(self, text: str) -> int:
            raise OSError("stream closed")

    configure_logging("INFO", "json", stream=BrokenStream())
    try:
        with timed("clean") as t:
            pass
        assert t.seconds is not None
    finally:
        configure_logging()
