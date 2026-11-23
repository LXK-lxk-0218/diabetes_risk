"""阶段计时：嵌套路径、无接收方、异常、接收方故障、装饰器（同步 / 异步 / 生成器）。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping

import pytest

from diabetes_risk.observability.timing import current_emitter, timed, use_emitter


# 测试用的接收方：把收到的每条耗时记进列表，测试再检查列表内容。
# 它没有继承 MetricsEmitter，只是有一个签名相同的 emit 方法 —— 这就是 Protocol 的意思
class ListEmitter:
    def __init__(self) -> None:
        self.records: list[tuple[str, float, Mapping[str, str] | None]] = []

    def emit(self, name: str, value: float, tags: Mapping[str, str] | None = None) -> None:
        self.records.append((name, value, tags))


# 一个总是出错的接收方：模拟“追踪服务挂了”
class BrokenEmitter:
    def emit(self, name: str, value: float, tags: Mapping[str, str] | None = None) -> None:
        raise RuntimeError("追踪服务挂了")


# 内层先结束，所以先记 train.fit、再记 train；内层的 path 是拼好的 train.fit
def test_nested_stages_build_a_path() -> None:
    sink = ListEmitter()
    with use_emitter(sink):
        with timed("train"):
            with timed("fit") as inner:
                pass
    assert [name for name, _, _ in sink.records] == ["timing.train.fit_seconds", "timing.train_seconds"]
    assert inner.path == "train.fit"
    assert inner.seconds is not None and inner.seconds >= 0


# 没有设置接收方时也能用：只写日志，不发送
def test_works_without_emitter() -> None:
    assert current_emitter() is None
    with timed("clean") as t:
        pass
    assert t.seconds is not None


# 被计时的代码抛了异常：耗时照样记录（failed 为 true），异常也照样抛出来，不会被计时吞掉
def test_exception_is_recorded_and_propagates() -> None:
    sink = ListEmitter()
    with use_emitter(sink), pytest.raises(ZeroDivisionError):
        with timed("bad"):
            # 1 / 0 故意制造 ZeroDivisionError。ruff 的 B018 会提示“表达式的结果没被使用”，noqa 说明这里是故意的
            1 / 0  # noqa: B018
    # 嵌套解包：断言正好有一条记录，并取出它的名字和标签
    ((name, _, tags),) = sink.records
    assert name == "timing.bad_seconds"
    assert tags == {"failed": "true"}


# 接收方抛异常，被计时的业务照常完成，只多一条警告日志
def test_broken_emitter_does_not_break_business() -> None:
    with use_emitter(BrokenEmitter()):
        with timed("clean") as t:
            result = 1 + 1
    assert result == 2 and t.seconds is not None


# 离开 use_emitter 以后，接收方恢复成原来的 None
def test_emitter_is_restored_after_block() -> None:
    sink = ListEmitter()
    with use_emitter(sink):
        assert current_emitter() is sink
    assert current_emitter() is None


# 装饰器写法：同步函数和 async 函数都要计时正确，装饰后的函数名不变
def test_decorator_sync_and_async() -> None:
    sink = ListEmitter()

    @timed("load")
    def load(x: int) -> int:
        return x * 2

    @timed("serve")
    async def serve(x: int) -> int:
        await asyncio.sleep(0)
        return x + 1

    with use_emitter(sink):
        assert load(3) == 6
        # asyncio.run 运行一个 async 函数并等它结束；新任务会复制当前上下文，所以接收方在里面也取得到
        assert asyncio.run(serve(1)) == 2
    assert [name for name, _, _ in sink.records] == ["timing.load_seconds", "timing.serve_seconds"]
    assert load.__name__ == "load"


# 生成器函数不能被装饰：在装饰的那一刻就报错，而不是悄悄量出一个错误的耗时
def test_generator_functions_are_rejected() -> None:
    def rows() -> Iterator[int]:
        yield 1

    with pytest.raises(TypeError, match="生成器"):
        timed("rows")(rows)


# 空名字和带点号的名字都不合法
@pytest.mark.parametrize("bad", ["", "train.fit"])
def test_invalid_stage_names(bad: str) -> None:
    with pytest.raises(ValueError, match="阶段名"):
        timed(bad)
