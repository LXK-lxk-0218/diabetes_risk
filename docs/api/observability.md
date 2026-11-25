# observability：日志与阶段计时

`diabetes_risk.observability` 放运行时的两件事：结构化日志，以及阶段耗时。签名见 [`docs/interfaces.md`](../interfaces.md) 里的同名模块。

## `diabetes_risk.observability.log`

结构化运行日志：每条日志是一组键值，带事件名、级别、UTC 时间和上下文；居民标识和特征值在输出前被遮住（嵌套在字典、列表里的也一样）。

模块还导出两个常量：`DEFAULT_REDACT`（`resident_id`、`visit_id`、`features`、`name`、`phone`、`id_card`）和 `REDACTED`（遮住后的值 `"***"`）。`name` 也在清单里，所以表示非个人信息的名字要写 `model_name`、`file_name`，否则会被遮住。常量不是函数或类，所以不单独成节。

### `configure_logging`

入口启动时配置一次全局日志：级别、格式、脱敏清单和输出流。

**用法**：`configure_logging("INFO", "json")` 输出 JSON 行；第二个参数传 `"console"` 输出给人看的格式。默认输出到 stderr；测试用 `stream=...` 接到内存。后面的调用会重新配置全局日志；`redact=` 可以换一份脱敏清单。

**出错抛什么**：级别名不认识，或格式不是 `"json"` / `"console"`，抛 `ValueError`，消息里带合法的选项。

**谁在用**：命令行入口、服务入口和测试；入口之外不要反复配置。

### `get_logger`

按模块取日志器，名字会写进每条日志的 `logger` 字段。

**用法**：在模块顶部 `get_logger(__name__)`，之后用 `.info`、`.warning`、`.error`、`.debug` 写事件；事件名用英文“动词_名词”。它是惰性的：先取日志器、后 `configure_logging` 也会用上新配置，脱敏不会被绕开。

**出错抛什么**：没有自定义异常；日志输出和格式问题由底层日志库处理。

**谁在用**：每一步的业务模块（AGENTS.md 的 A2 规则）。

### `bind_context`

把 `run_id`、`request_id` 这类字段绑定到当前线程或任务的日志上下文，之后写的日志自动带上。

**用法**：一次运行或一次请求开始时绑定；同一个线程/任务里的日志都带这些字段。上下文里的敏感键也会被脱敏。

**出错抛什么**：没有自定义异常。

**谁在用**：命令行入口、服务入口。

### `clear_context`

清掉当前上下文绑定的字段，避免带进下一次运行或请求。

**用法**：在运行或请求结束时调用，通常放在 `finally` 里；清掉后新日志不再带 `run_id` 等字段。

**出错抛什么**：没有自定义异常。

**谁在用**：命令行入口、服务入口。

```python
import io
import json

from diabetes_risk.observability.log import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)

stream = io.StringIO()
log = get_logger("demo")  # 先取日志器，再配置：惰性日志器仍会用新配置
configure_logging("INFO", "json", stream=stream)

bind_context(run_id="r-001")
log.info("rows_cleaned", rule="weight_jin_to_kg", rows=520)
log.info("predicted", resident_id="R0000014", score=0.42, nested={"resident_id": "R1"})
clear_context()
log.info("rows_cleaned", rule="weight_jin_to_kg", rows=521)

records = [json.loads(line) for line in stream.getvalue().splitlines()]
assert len(records) == 3
first, second, third = records
assert first["event"] == "rows_cleaned"
assert first["level"] == "info"
assert first["logger"] == "demo"
assert first["ts"].endswith("Z")
assert first["run_id"] == "r-001"
assert first["rows"] == 520
assert "resident_id" not in first
assert second["event"] == "predicted"
assert second["resident_id"] == "***"
assert second["nested"] == {"resident_id": "***"}
assert second["run_id"] == "r-001"
assert third["event"] == "rows_cleaned"
assert "run_id" not in third
assert third["rows"] == 521
```

## `diabetes_risk.observability.timing`

阶段计时：`with timed("stage")` 或 `@timed("stage")` 两种写法，嵌套自动拼路径，耗时写日志，并可按调用时指定的接收方发指标。它是底层工具，不是性能监控系统；计时本身出错不拖垮业务。

### `MetricsEmitter`

计时指标的接收方协议：实现一个 `emit` 方法即可，不需要继承。

**用法**：实现一个 `emit` 方法即可，不需要继承；标签可以省略。指标名形如 `timing.<路径>_seconds`，标签里有 `failed` 的 `"true"` / `"false"`。

**出错抛什么**：接收方自己抛的异常会被计时层吞掉，并额外记一条 `timing_emit_failed` 警告；不会改变业务结果。

**谁在用**：C-L1c 的训练记录；以后服务要接指标时也用它。

### `use_emitter`

在 `with` 块里设置当前计时指标的接收方，退出时恢复原来的接收方。

**用法**：可以嵌套；传 `None` 表示这一段不接指标。接收方在调用时设置，不写进装饰器参数。

**出错抛什么**：没有自定义异常；块内异常照常外抛。

**谁在用**：C-L1c 的训练入口、需要临时接指标的测试。

### `current_emitter`

取当前生效的计时指标接收方。

**用法**：在 `with use_emitter(...)` 块里返回那个接收方；没有设置时返回 `None`。

**出错抛什么**：没有自定义异常。

**谁在用**：需要在计时之外补发指标、或做测试断言的代码。

### `timed`

给一段代码或一个函数计时；既是 `with` 上下文管理器，也是装饰器。

**用法**：`with timed("load") as t:` 包住一段，离开 `with` 后读 `t.path` 和 `t.seconds`；嵌套时路径用点连接，例如外层 `prepare`、内层 `load` 得到 `prepare.load`。装饰函数时写 `@timed("fit")`，同步函数和异步函数都支持。成功和失败都会写日志并发出指标，失败时标签里的 `failed` 是 `"true"`。

**出错抛什么**：阶段名为空、含点号或不是字符串时抛 `ValueError`；装饰生成器函数时抛 `TypeError`（消息里带“生成器”）；块内异常原样外抛，不会被计时层换掉。计时日志或接收方自己出错时只记警告，不影响业务。

**谁在用**：`prepare`、`train` 等阶段。

```python
from diabetes_risk.observability.timing import (
    MetricsEmitter,
    current_emitter,
    timed,
    use_emitter,
)


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, dict[str, str] | None]] = []

    def emit(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        self.calls.append((name, value, tags))


recorder: MetricsEmitter = Recorder()
assert current_emitter() is None

with use_emitter(recorder):
    assert current_emitter() is recorder
    with timed("prepare") as outer:
        with timed("load") as inner:
            pass
    assert outer.path == "prepare"
    assert inner.path == "prepare.load"
    assert outer.seconds is not None and outer.seconds >= 0
    assert inner.seconds is not None and inner.seconds >= 0

assert current_emitter() is None
assert [name for name, _, _ in recorder.calls] == [
    "timing.prepare.load_seconds",
    "timing.prepare_seconds",
]
assert recorder.calls[0][2] == {"failed": "false"}
assert recorder.calls[1][2] == {"failed": "false"}


@timed("fit")
def fit(value: int) -> int:
    return value + 1


with use_emitter(recorder):
    assert fit(1) == 2
assert recorder.calls[-1][0] == "timing.fit_seconds"

try:
    with use_emitter(recorder):
        with timed("boom"):
            raise RuntimeError("boom")
except RuntimeError:
    pass
assert recorder.calls[-1][0] == "timing.boom_seconds"
assert recorder.calls[-1][2] == {"failed": "true"}

try:
    timed("a.b")
except ValueError as exc:
    assert "阶段名不能为空" in str(exc)
else:
    raise AssertionError("带点号的阶段名应抛 ValueError")


def generate():
    yield 1


try:
    timed("generate")(generate)
except TypeError as exc:
    assert "生成器" in str(exc)
else:
    raise AssertionError("生成器函数应抛 TypeError")
```
