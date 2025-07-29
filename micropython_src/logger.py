# logger.py
"""
日志管理模块 - 基于事件总线的日志系统

这个模块实现了一个基于事件总线的日志系统，通过订阅日志事件来处理日志记录。
相比原来直接访问daemon模块的日志队列，这种方式实现了更好的模块解耦。

主要功能：
1. 订阅日志事件（log_critical, log_info, log_warning等）
2. 异步处理日志消息
3. 日志文件滚动备份
4. 内存中的日志队列管理

支持的日志级别：
- CRITICAL: 关键错误，需要立即关注
- WARNING: 警告信息
- INFO: 一般信息
"""

import os
import time
import config
import event_bus

try:
    import uasyncio as asyncio
except ImportError:
    # 在标准Python环境中使用asyncio
    import asyncio

# 从配置模块获取日志配置
_log_config = config.get_log_config()
LOG_FILE = _log_config['log_file']
MAX_LOG_SIZE = _log_config['max_log_size']
MAX_LOG_QUEUE_SIZE = _log_config['max_log_queue_size']

# 内存中的日志队列
_log_queue = []

def _rotate_log():
    """
    如果日志文件过大，则进行滚动备份
    
    当日志文件大小超过配置的最大值时，将当前日志文件重命名为备份文件，
    并创建新的日志文件。这样可以避免日志文件无限增长。
    """
    try:
        # os.stat() 用于获取文件状态，第6个元素是文件大小
        size = os.stat(LOG_FILE)[6]
        if size > MAX_LOG_SIZE:
            # 删除旧的备份文件（如果存在）
            if 'error.log.bak' in os.listdir():
                os.remove('error.log.bak')
            # 将当前日志文件重命名为备份文件
            os.rename(LOG_FILE, 'error.log.bak')
            print(f"[Logger] 日志文件已滚动，大小: {size} 字节")
    except OSError:
        # 如果 error.log 文件不存在，则什么都不做
        pass

def _format_log_message(level, message):
    """
    格式化日志消息
    
    Args:
        level (str): 日志级别
        message (str): 日志消息
    
    Returns:
        str: 格式化后的日志消息
    """
    try:
        timestamp = time.localtime()
        time_str = f"{timestamp[0]}-{timestamp[1]:02d}-{timestamp[2]:02d} {timestamp[3]:02d}:{timestamp[4]:02d}:{timestamp[5]:02d}"
        return f"{time_str} - {level}: {message}\n"
    except Exception as e:
        return f"TIME_ERROR - {level}: {message}\n"

def _add_to_queue(level, message):
    """
    将日志消息添加到内存队列
    
    Args:
        level (str): 日志级别
        message (str): 日志消息
    """
    global _log_queue
    
    try:
        formatted_message = _format_log_message(level, message)
        
        # 如果队列已满，移除最旧的消息
        if len(_log_queue) >= MAX_LOG_QUEUE_SIZE:
            _log_queue.pop(0)
        
        _log_queue.append(formatted_message)
        
    except Exception as e:
        print(f"[Logger] [ERROR] 添加日志到队列失败: {e}")

# 事件处理函数
def on_log_critical(message, **kwargs):
    """
    处理关键错误日志事件
    
    Args:
        message (str): 日志消息
        **kwargs: 其他参数
    """
    _add_to_queue("CRITICAL", message)
    # 关键错误也打印到控制台
    print(f"[CRITICAL] {message}")

def on_log_warning(message, **kwargs):
    """
    处理警告日志事件
    
    Args:
        message (str): 日志消息
        **kwargs: 其他参数
    """
    _add_to_queue("WARNING", message)

def on_log_info(message, **kwargs):
    """
    处理信息日志事件
    
    Args:
        message (str): 日志消息
        **kwargs: 其他参数
    """
    _add_to_queue("INFO", message)

def process_log_queue():
    """
    处理日志队列，将消息写入文件
    
    这个函数应该在主循环中被定期调用，将内存中的日志消息
    批量写入到日志文件中。
    """
    global _log_queue
    
    if not _log_queue:
        return  # 队列为空，直接返回

    # 先检查是否需要滚动日志
    _rotate_log()
    
    try:
        # a+ 模式：如果文件不存在则创建，如果存在则在末尾追加
        with open(LOG_FILE, 'a+') as f:
            while _log_queue:
                # 从队列头部取出一个条目并写入文件
                f.write(_log_queue.pop(0))
    except Exception as e:
        print(f"[Logger] [ERROR] 写入日志失败: {e}")

def get_log_queue_size():
    """
    获取当前日志队列大小
    
    Returns:
        int: 队列中的日志消息数量
    """
    return len(_log_queue)

def clear_log_queue():
    """
    清空日志队列（主要用于测试）
    """
    global _log_queue
    _log_queue.clear()
    print("[Logger] 日志队列已清空")

def init_logger():
    """
    初始化日志系统
    
    订阅相关的日志事件，使日志系统开始工作。
    这个函数应该在系统启动时调用。
    """
    try:
        # 订阅日志事件
        event_bus.subscribe('log_critical', on_log_critical)
        event_bus.subscribe('log_warning', on_log_warning)
        event_bus.subscribe('log_info', on_log_info)
        
        print("[Logger] 日志系统初始化完成")
        return True
        
    except Exception as e:
        print(f"[Logger] [ERROR] 日志系统初始化失败: {e}")
        return False

# 便捷的日志记录函数
def log_critical(message):
    """
    记录关键错误日志的便捷函数
    
    Args:
        message (str): 日志消息
    """
    event_bus.publish('log_critical', message=message)

def log_warning(message):
    """
    记录警告日志的便捷函数
    
    Args:
        message (str): 日志消息
    """
    event_bus.publish('log_warning', message=message)

def log_info(message):
    """
    记录信息日志的便捷函数
    
    Args:
        message (str): 日志消息
    """
    event_bus.publish('log_info', message=message)