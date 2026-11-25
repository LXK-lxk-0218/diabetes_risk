"""阶段计时：同一个 timed 既能当 with 用，也能当装饰器用。接口与理由见 docs/api/observability.md。

它是底层工具，不是性能监控系统：只回答“这一段花了多久”，把结果写进运行日志；
需要的话，再交给调用方指定的接收方（卷二 C-L1c 的训练记录、以后服务的指标）。

两条关键设计：
1. 耗时“发到哪里”在调用时从上下文取（use_emitter），不在装饰时写死：装饰器在导入时就执行了，
   那时训练记录还不存在；
2. 计时本身出错（写日志出错、接收方出错）都不能拖垮被计时的业务。
"""

from __future__ import annotations

import functools
import inspect
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from types import TracebackType
from typing import Any, ParamSpec, Protocol, TypeVar, cast

from diabetes_risk.observability.log import get_logger

# _P 代表“被装饰函数的全部参数”，_R 代表它的返回值：装饰之后，参数和返回值的类型都和原来一样
_P = ParamSpec("_P")
_R = TypeVar("_R")

# 可以在模块顶层创建：get_logger 返回的是惰性日志器，配置在真正写日志时才生效（见 log.py）
_log = get_logger("timing")


# Protocol（协议）只规定“长什么样”，不要求继承：任何对象只要有一个签名相同的 emit 方法，
# mypy 就把它当作 MetricsEmitter。所以核心包不用依赖 MLflow，卷二的追踪器、测试里的列表都能直接当接收方
class MetricsEmitter(Protocol):
    """耗时的接收方。卷二由训练记录实现（C-L1c）；测试里用一个列表收集。"""

    # 方法体写成 ...：协议只声明签名，不提供实现
    def emit(self, name: str, value: float, tags: Mapping[str, str] | None = None) -> None: ...


# 两个 ContextVar（上下文变量）。用起来像全局变量，但每个线程、每个 async 任务看到的是各自那一份：
#   _emitter：耗时发到哪里；默认 None，表示只写日志、不发送
#   _stack：当前嵌套在哪些阶段里，例如 ("train", "fit")
_emitter: ContextVar[MetricsEmitter | None] = ContextVar("drisk_timing_emitter", default=None)
_stack: ContextVar[tuple[str, ...]] = ContextVar("drisk_timing_stack", default=())


# @contextmanager 把一个生成器函数变成 with 能用的东西：yield 之前的代码在进入 with 时执行，
# finally 里的代码在离开 with 时执行（哪怕块里抛了异常）
@contextmanager
def use_emitter(emitter: MetricsEmitter | None) -> Iterator[None]:
    """在一段代码里设置“耗时发到哪里”，退出时恢复原来的设置。"""
    # set() 返回一个 token，记着“设置之前的值”；reset(token) 精确恢复到那个值，嵌套使用也不会乱
    token = _emitter.set(emitter)
    try:
        yield
    finally:
        _emitter.reset(token)


def current_emitter() -> MetricsEmitter | None:
    return _emitter.get()


def _report(path: str, seconds: float, failed: bool) -> None:
    # 先写一条结构化日志：不管有没有接收方，耗时都留在运行日志里
    try:
        _log.info("stage_timed", stage=path, duration_ms=round(seconds * 1000, 1), failed=failed)
    except Exception:
        # 日志写不出去（例如输出流被关了）也不能让业务失败：计时是附带的
        pass
    emitter = _emitter.get()
    if emitter is None:
        return
    # 指标名形如 timing.train.fit_seconds；标签记下这个阶段是不是以异常结束
    try:
        emitter.emit(f"timing.{path}_seconds", seconds, {"failed": str(failed).lower()})
    except Exception as exc:
        # 接收方坏了（例如追踪服务挂了）只记一条警告，不能把正在跑的训练拖垮
        try:
            _log.warning("timing_emit_failed", stage=path, error=repr(exc))
        except Exception:
            pass


class timed:
    """两种写法：``with timed("clean"): ...`` 或 ``@timed("clean")``。

    嵌套时阶段名自动拼成路径，例如在 ``timed("train")`` 里面的 ``timed("fit")`` 记为 ``train.fit``。
    """

    # 写成类而不是函数：同一个对象既要实现 __enter__/__exit__（给 with 用），又要实现 __call__（给 @ 用）。
    # 类名小写，用起来读着像一个函数（和标准库的 contextlib.suppress、functools.partial 一样）
    def __init__(self, stage: str) -> None:
        # 点号留给“嵌套路径”当分隔符：阶段名自己带点，train.fit 就分不清是一层还是两层。
        # 非字符串（例如把 None 当阶段名）在这里就报错，而不是等到拼路径时才失败
        if not isinstance(stage, str) or not stage or "." in stage:
            raise ValueError(f"阶段名不能为空，也不能含点号：{stage!r}")
        self.stage = stage
        # path：嵌套拼接后的完整阶段名，进入 with 时才算得出来，这里先用 stage 占位
        self.path = stage
        # seconds：离开 with 时填入耗时；with timed("x") as t 之后可以读 t.seconds
        self.seconds: float | None = None
        self._start = 0.0
        # _token：进入时压栈留下的凭据，离开时用它出栈
        self._token: Token[tuple[str, ...]] | None = None

    def __enter__(self) -> timed:
        # 进入：读出外层正在计时的阶段，把自己接在后面，例如 ("train",) → ("train", "fit")
        parent = _stack.get()
        self.path = ".".join((*parent, self.stage))
        self._token = _stack.set((*parent, self.stage))
        # perf_counter：专门量时间间隔的高精度时钟，不受系统改时间影响
        self._start = time.perf_counter()
        # 返回自己：with timed("x") as t 里的 t 就是这个对象
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # 离开：with 块无论正常结束还是抛了异常，都会走到这里
        self.seconds = time.perf_counter() - self._start
        # 出栈：恢复到进入之前的嵌套状态
        if self._token is not None:
            _stack.reset(self._token)
            self._token = None
        # exc_type 不是 None，说明 with 块里抛了异常：照样记录耗时，并标记 failed。
        # 本方法返回 None（不是 True），异常会继续往外抛，计时不会把错误吞掉
        _report(self.path, self.seconds, failed=exc_type is not None)

    def __call__(self, func: Callable[_P, _R]) -> Callable[_P, _R]:
        # 当装饰器用时，@timed("load") 先创建一个实例，再把函数交给这里的 __call__。
        # 生成器函数一调用就立刻返回生成器，函数体还没开始执行，计时会马上结束，量到的不是真实耗时，所以拒绝
        if inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func):
            raise TypeError(f"timed 不能装饰生成器函数：{func.__qualname__}（计时会在第一次 yield 时就结束）")
        # 只记下阶段名：每次调用都在包装函数里新建一个 timed 实例，不复用 self，递归、并发都安全
        stage = self.stage
        # async def 定义的函数要用 async 包装：await 完成才算结束，否则量到的只是“创建协程”那一瞬间
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # @functools.wraps(func) 把原函数的名字、文档字符串复制给包装函数（测试检查了 load.__name__ == "load"）。
                # 包装函数的参数写成 Any，所以下面 return 处要用 cast 告诉 mypy：对外它仍是原来的签名
                with timed(stage):
                    return await func(*args, **kwargs)

            return cast(Callable[_P, _R], async_wrapper)

        @functools.wraps(func)
        def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            # 普通函数：_P.args、_P.kwargs 原样转发全部参数，mypy 能检查调用方传的参数对不对
            with timed(stage):  # 每次调用新建一个实例：递归、并发都安全
                return func(*args, **kwargs)

        return wrapper
