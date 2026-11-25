"""结构化运行日志（structlog）。接口与理由见 docs/api/observability.md。

- 每条日志是一组键值，而不是拼出来的一句话：机器能按字段检索、统计，脱敏也能按键名做；
- 本地开发用 console 格式，容器与 CI 用 json 格式；
- run_id、request_id 等上下文用 bind_context 绑定一次，之后每条日志自动带上；
- 这是医疗数据：命中脱敏清单的字段，不管在第几层，值一律替换成 *** 。

模块名叫 log.py 而不是 logging.py，避免和标准库同名。
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterable
from typing import Any, Literal, TextIO, cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, WrappedLogger

# 默认脱敏清单：居民编号、随访编号、整条特征、姓名、电话、身份证号，任何一个都能把一行日志对到一个具体的人。
# frozenset 是不可变的集合，模块级常量不会被谁顺手改掉
DEFAULT_REDACT: frozenset[str] = frozenset({"resident_id", "visit_id", "features", "name", "phone", "id_card"})
REDACTED = "***"

# structlog 的“处理器”就是一个函数：收到 (logger, 方法名, 事件字典)，返回加工后的事件字典
_Processor = Callable[[WrappedLogger, str, EventDict], EventDict]


def _redact_value(value: Any, keys: frozenset[str]) -> Any:
    """递归往下找：字典里的字典、列表里的字典，命中清单的键一律遮住。"""
    # 日志的字段常是嵌套结构（一天的特征、一批记录）；只遮顶层会漏掉嵌套里的标识
    if isinstance(value, dict):
        return {k: REDACTED if k in keys else _redact_value(v, keys) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact_value(item, keys) for item in value]
    return value


def _redactor(keys: frozenset[str]) -> _Processor:
    # 工厂函数：返回一个处理器，内层函数记住了外层的 keys（闭包），每条日志都拿它比对
    def redact(_logger: WrappedLogger, _method: str, event_dict: EventDict) -> EventDict:
        for key, value in list(event_dict.items()):
            event_dict[key] = REDACTED if key in keys else _redact_value(value, keys)
        return event_dict

    return redact


class _CurrentStderr:
    """写到“此刻的” sys.stderr：pytest 会替换并关闭它，不能提前把对象存下来。"""

    # logger_factory 会把拿到的文件对象存下来一直用，而 pytest 在每个测试里都会换一个新的 stderr、
    # 关掉旧的；直接存 stderr 对象，下一个测试一写日志就报“写入已关闭的文件”。
    # 这个类每次写的时候才去取当前的那个 stderr，所以总能写对地方。
    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()


def configure_logging(
    level: str = "INFO",
    fmt: Literal["json", "console"] = "console",
    *,
    redact: Iterable[str] = DEFAULT_REDACT,
    stream: TextIO | None = None,
) -> None:
    """全局配置一次：级别、格式、脱敏清单、写到哪（默认 stderr；测试时传一个 StringIO 收集输出）。"""
    # 把 "info"、"INFO" 统一成大写，再换成数字级别（DEBUG=10、INFO=20、WARNING=30……）；查不到说明拼错了
    numeric = logging.getLevelNamesMapping().get(level.upper())
    if numeric is None:
        raise ValueError(f"未知日志级别：{level}")
    # 格式拼错也当场报错，而不是悄悄退回 console：否则容器里以为在出 JSON，实际出了给人看的格式
    if fmt not in ("json", "console"):
        raise ValueError(f"未知日志格式：{fmt}（可选：json、console）")
    # 渲染器决定一条日志最后长什么样：json 每行一个 JSON，适合机器收集；console 适合人在终端里看。
    # ensure_ascii=False：中文原样输出，不变成 \uXXXX
    renderer: Any = (
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    # 处理器按顺序执行：并入上下文 → 加级别 → 加时间 → 格式化异常 → 脱敏 → 渲染。
    # 脱敏排在“并入上下文”之后、渲染之前：上下文里的敏感字段也会被遮住，渲染出来的已经是 ***
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            # UTC 时间戳：不同时区的机器写出来的日志可以直接比较先后
            structlog.processors.TimeStamper(fmt="iso", key="ts", utc=True),
            # 把 .exception() 的堆栈格式化成 exception 字段，JSON 里也能看到错误原因
            structlog.processors.format_exc_info,
            _redactor(frozenset(redact)),
            renderer,
        ],
        # 低于设定级别的调用（例如级别是 INFO 时的 debug）直接变成空操作，几乎没有开销
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        # 写到哪里：没传 stream 就写“当前的” stderr；测试传入 StringIO，就能把日志收起来逐行解析
        logger_factory=structlog.PrintLoggerFactory(file=cast(TextIO, _CurrentStderr()) if stream is None else stream),
        # 不缓存：之后再调用 configure_logging 改配置也能生效（测试里每个用例都会重新配置一次）
        cache_logger_on_first_use=False,
    )


class _LazyLogger:
    """惰性日志器：每写一条日志，才按“此刻的”配置组装一次。

    structlog 的 get_logger().bind(...) 会在 bind 的那一刻按当时的配置组装好，之后再改配置不生效：
    模块顶层创建的日志器如果早于 configure_logging，就会绕开脱敏。这个类把组装推迟到真正写日志的时候。
    """

    def __init__(self, values: dict[str, Any]) -> None:
        self._values = values

    def bind(self, **values: Any) -> _LazyLogger:
        # 绑定新字段也保持惰性：返回一个带着更多字段的新惰性日志器
        return _LazyLogger({**self._values, **values})

    def __getattr__(self, method: str) -> Any:
        # .info / .warning / .exception ……：此刻才组装，用的是此刻的配置
        return getattr(structlog.get_logger().bind(**self._values), method)


def get_logger(name: str) -> FilteringBoundLogger:
    """按模块取日志器；name 会作为 logger 字段出现在每条日志里。

    可以放在模块顶层：返回的是惰性日志器，之后再调用 configure_logging 也会生效。
    """
    # 坑：structlog.get_logger(logger=name) 会抛 TypeError（logger 这个参数名被占用了），
    # 所以把 logger 字段放进惰性日志器里；cast 只是告诉 mypy 返回类型
    return cast(FilteringBoundLogger, _LazyLogger({"logger": name}))


def bind_context(**values: Any) -> None:
    """绑定上下文：之后同一上下文里的日志都带上这些字段。每个线程、每个 async 任务各有一份，不会串。"""
    # contextvars：每个线程、每个 async 任务各有一份上下文，同时处理多个请求时字段不会串
    structlog.contextvars.bind_contextvars(**values)


def clear_context() -> None:
    """一次运行或一次请求结束时调用，免得这次绑定的字段带进下一次。"""
    structlog.contextvars.clear_contextvars()
