# app/lib/logger.py - 极简日志系统
"""
极简日志系统 - 专为ESP32-C3嵌入式环境设计

特点:
- 零配置, 拿来即用
- 固定格式: [时间] [级别] [模块] 消息
"""

try:
    import utime as time
except ImportError:
    import time

# 日志级别
DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3

# 当前日志级别 (可根据需要修改)
LOG_LEVEL = INFO

# ANSI颜色代码
COLOR_RED = "\033[1;31m"
COLOR_ORANGE = "\033[1;33m"
COLOR_JADE = "\033[1;32m"  # 翠绿色
COLOR_INDIGO = "\033[1;34m"  # 靛蓝色
COLOR_RESET = "\033[0m"





def _log(level, level_name, msg, *args, module=None):
    """核心日志函数"""
    if level < LOG_LEVEL:
        return

    try:
        ts = time.ticks_ms() if hasattr(time, "ticks_ms") else int(time.time() * 1000)
    except Exception:
        ts = 0

    # 统一格式化消息
    try:
        message = msg.format(*args) if args else str(msg)
    except Exception:
        # 容错: 避免 format 失败
        try:
            message = f"{msg} | args={args}"
        except Exception:
            message = str(msg)

    line = "[{:02d}:{:02d}:{:02d}] [{}] [{}] {}".format(
        (ts // 1000) // 3600 % 24,
        (ts // 1000) // 60 % 60,
        (ts // 1000) % 60,
        level_name,
        module or "-",
        message,
    )

    # 控制台输出
    print(line)


def debug(msg, *args, module=None):
    """调试日志"""
    _log(DEBUG, "DEBUG", msg, *args, module=module)


def info(msg, *args, module=None):
    """信息日志"""
    _log(INFO, "INFO ", msg, *args, module=module)


def warning(msg, *args, module=None):
    """警告日志"""
    _log(WARNING, "WARN ", msg, *args, module=module)


def error(msg, *args, module=None):
    """错误日志"""
    _log(ERROR, "ERROR", msg, *args, module=module)


# 便捷别名
warn = warning
critical = error
