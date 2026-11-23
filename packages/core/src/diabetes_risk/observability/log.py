"""结构化运行日志（structlog）。

- 本地开发用 console 格式，容器与 CI 用 json 格式；
- run_id、request_id 等上下文用 bind_context 绑定一次，之后每条日志自动带上；
- 运行日志不写特征值和居民标识：命中脱敏清单的字段一律替换成 *** 。

模块名叫 log.py 而不是 logging.py，避免和标准库同名。
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterable
from typing import Any, Literal, TextIO, cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, WrappedLogger

# 默认脱敏清单：这些字段一旦出现在日志里，值一律换成 ***。
# 居民编号、随访编号、整条特征、姓名、电话、身份证号，任何一个都能把一行日志对到一个具体的人。
# frozenset 是不可变的集合，模块级常量不会被谁顺手改掉
DEFAULT_REDACT: frozenset[str] = frozenset({"resident_id", "visit_id", "features", "name", "phone", "id_card"})
REDACTED = "***"

# 类型别名。structlog 的“处理器”就是一个函数：收到 (logger, 方法名, 事件字典)，返回加工后的事件字典。
# 每条日志依次流过 configure_logging 里列出的处理器，最后一个负责把字典变成一行文字。
Processor = Callable[[WrappedLogger, str, EventDict], EventDict]


# 工厂函数：返回一个处理器。内层的 redact 记住了外层的 keys（这叫“闭包”），每条日志都拿它比对
def _redactor(keys: frozenset[str]) -> Processor:
    def redact(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        # 集合交集：只处理“既在清单里、又真的出现在这条日志里”的字段
        for key in keys & event_dict.keys():
            event_dict[key] = REDACTED
        return event_dict

    return redact


class _CurrentStderr:
    """写到“此刻的” sys.stderr：pytest 会替换并关闭它，不能提前把对象存下来。"""

    # 为什么要多这一层：logger_factory 会把拿到的文件对象存下来一直用，而 pytest 在每个测试里
    # 都会换一个新的 stderr、关掉旧的；直接存 stderr 对象，下一个测试一写日志就报“写入已关闭的文件”。
    # 这个类每次写的时候才去取当前的那个 stderr，所以总能写对地方。
    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()


def _current_stderr() -> TextIO:
    # cast 只是告诉 mypy“把它当 TextIO 看”，运行时什么也不做；它只实现了 write 和 flush，对 structlog 已经够用
    return cast(TextIO, _CurrentStderr())


def configure_logging(
    level: str = "INFO",
    fmt: Literal["json", "console"] = "console",
    *,
    redact: Iterable[str] = DEFAULT_REDACT,
    stream: TextIO | None = None,
) -> None:
    """全局配置一次。stream 默认 stderr；测试时可以传一个 StringIO 收集输出。"""
    # 把 "info"、"INFO" 统一成大写，再换成数字级别（DEBUG=10、INFO=20、WARNING=30……）；查不到说明拼错了
    numeric = logging.getLevelNamesMapping().get(level.upper())
    if numeric is None:
        raise ValueError(f"未知日志级别：{level}")
    # 渲染器决定一条日志最后长什么样：json 每行一个 JSON，适合机器收集；console 适合人在终端里看。
    # ensure_ascii=False：中文原样输出，不变成 \uXXXX
    renderer: Any = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    # 处理器按列表顺序执行，顺序有讲究，见每一行上面的注释
    structlog.configure(
        processors=[
            # 1. 并入 bind_context 绑定的上下文字段（run_id 等）
            structlog.contextvars.merge_contextvars,
            # 2. 加上 level 字段（info、warning……）
            structlog.processors.add_log_level,
            # 3. 加上 ISO 格式的时间戳，字段名叫 ts
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            # 4. 脱敏：排在“并入上下文”之后，上下文里绑定的敏感字段也会被替换；排在渲染之前，渲染出来的已经是 ***
            _redactor(frozenset(redact)),
            # 5. 最后一步：渲染成一行文字
            renderer,
        ],
        # 低于设定级别的调用（例如级别是 INFO 时的 debug）直接变成空操作，几乎没有开销
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        # 写到哪里：没传 stream 就写“当前的” stderr；测试传入 StringIO，就能把日志收起来逐行解析
        logger_factory=structlog.PrintLoggerFactory(file=_current_stderr() if stream is None else stream),
        # 不缓存：之后再调用 configure_logging 改配置也能生效（测试里每个用例都会重新配置一次）
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    """按模块取日志器；name 会作为 logger 字段出现在每条日志里。

    返回的是“惰性”日志器：每次写日志时才按当时的配置组装。所以可以在模块顶层创建，
    之后再调用 configure_logging 也会生效（.bind() 只是把字段挂到惰性代理上，不会固定配置）。
    """
    # 坑：写成 structlog.get_logger(logger=name) 会抛 TypeError。
    # 正确做法是先拿惰性代理 get_logger()，再用 .bind() 挂上 logger 字段；cast 只是告诉 mypy 返回类型
    return cast(FilteringBoundLogger, structlog.get_logger().bind(logger=name))


def bind_context(**values: Any) -> None:
    """绑定上下文（基于 contextvars）：之后同一上下文里的日志都带上这些字段。"""
    # contextvars：每个线程、每个 async 任务各有一份上下文，同时处理多个请求时字段不会串
    structlog.contextvars.bind_contextvars(**values)


def clear_context() -> None:
    # 一次运行或一次请求结束时调用，免得这次绑定的字段带进下一次
    structlog.contextvars.clear_contextvars()
