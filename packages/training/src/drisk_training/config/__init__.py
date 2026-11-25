"""配置系统：YAML 继承（extends）、按段校验、配置指纹、环境参数。"""

# 包的“门面”：外面统一写 from drisk_training.config import load_settings，不用记它在哪个模块
from drisk_training.config.loader import ConfigError, config_hash, deep_merge, load_raw, load_settings
from drisk_training.config.sections import Settings

# __all__ 列出对外公开的名字；ruff 也据此知道上面两行导入是“故意导出”，不是没用到的导入
__all__ = ["ConfigError", "Settings", "config_hash", "deep_merge", "load_raw", "load_settings"]
