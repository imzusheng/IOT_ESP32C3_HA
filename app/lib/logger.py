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


def _get_timestamp():
    """获取简化的时间戳"""
    try:
        total_seconds = (time.ticks_ms() // 1000) % (24 * 3600)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    except:
        return "00:00:00"


# 可选：INFO 级日志转发钩子（例如转发到 MQTT）
# 注意：应当由上层在网络就绪后注册，避免启动阶段阻塞或异常
_INFO_HOOK = None

def set_info_hook(hook):
    """
    注册/移除 INFO 级日志的转发钩子。
    hook: 可调用对象，签名为 hook(formatted_line: str)
    传入 None 表示移除钩子。
    """
    global _INFO_HOOK
    _INFO_HOOK = hook


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
        # 容错：避免 format 失败
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

    # 可选：INFO 级日志转发
    if level == INFO and _INFO_HOOK:
        try:
            _INFO_HOOK(line)
        except Exception:
            # 转发钩子不应影响主日志流程，静默失败
            pass


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
