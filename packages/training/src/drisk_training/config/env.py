"""环境参数：走环境变量（前缀 DRISK_），也可以写在仓库根目录的 .env 里。不进 Git。
业务与实验参数写 configs/*.yaml；环境参数（日志级别、以后的 MLflow 地址等）写这里；密钥绝不进 Git。
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvSettings(BaseSettings):
    """环境参数：DRISK_ 前缀的环境变量，对应 config/env.py 的 EnvSettings。"""

    model_config = SettingsConfigDict(env_prefix="DRISK_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
