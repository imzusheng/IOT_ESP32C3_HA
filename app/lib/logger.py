# app/lib/logger.py - 极简日志系统
"""
极简日志系统 - 专为ESP32-C3嵌入式环境设计

特点:
- 零配置, 拿来即用
- 固定格式: [时间] [级别] [模块] 消息
"""

import utime as time

# 日志级别
DEBUG = 0
INFO = 1
WARNING = 2
ERROR = 3

# 当前日志级别 (可根据需要修改)
LOG_LEVEL = INFO

# ANSI颜色代码
COLOR_RED = '\033[1;31m'
COLOR_ORANGE = '\033[1;33m'
COLOR_JADE = '\033[1;32m'  # 翠绿色
COLOR_INDIGO = '\033[1;34m'  # 靛蓝色
COLOR_RESET = '\033[0m'

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

def _log(level, level_name, msg, *args, module=None):
    """核心日志函数"""
    if level < LOG_LEVEL:
        return
    
    # 格式化消息
    try:
        formatted_msg = msg.format(*args) if args else msg
    except:
        formatted_msg = msg
    
    # 构建日志前缀
    timestamp = _get_timestamp()
    
    # 根据级别添加颜色
    if level == ERROR:
        colored_level_name = f"{COLOR_RED}{level_name}{COLOR_RESET}"
    elif level == WARNING:
        colored_level_name = f"{COLOR_ORANGE}{level_name}{COLOR_RESET}"
    else:
        colored_level_name = level_name
    
    if module:
        # 为特定模块设置颜色
        module_name = module.upper()
        if module_name == "FSM":
            colored_module = f"{COLOR_JADE}{module_name}{COLOR_RESET}"
        elif module_name == "NET":
            colored_module = f"{COLOR_INDIGO}{module_name}{COLOR_RESET}"
        else:
            colored_module = module_name
        
        prefix = f"[{timestamp}] [{colored_level_name}] [{colored_module}]"
    else:
        prefix = f"[{timestamp}] [{colored_level_name}]"
    
    # 直接输出
    print(f"{prefix} {formatted_msg}")

# 全局日志函数
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