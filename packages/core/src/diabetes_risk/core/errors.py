"""项目统一的异常基类。

所有“业务上可预期”的错误都继承 DriskError：命令行据此打印友好的中文信息并返回非零退出码，
服务层据此转成合适的 HTTP 状态码。程序缺陷（KeyError、TypeError 等）不包进来，照常抛出。
"""

from __future__ import annotations


# 一个空的子类，价值在“分类”：except DriskError 能一次接住所有可预期的业务错误
# （配置写错、目录自相矛盾……），而 TypeError、KeyError 这类程序缺陷不在其中，会照常带着堆栈抛出来。
# 以后的 ConfigError（A3）、CatalogError（A4）都继承它。
class DriskError(Exception):
    """本项目可预期错误的基类。"""
