# logger.py
"""
日志系统模块

从core.py中分离出来的独立日志系统，提供：
- 基于事件总线的日志记录
- 内存队列管理
- 日志级别过滤
- 动态日志级别调整
"""

import gc
import time
from collections import deque

# 兼容性处理：为标准Python环境提供time函数
try:
    from time import time
except ImportError:
    # 如果没有time函数，使用ticks_ms转换
    def time():
        return time.ticks_ms() / 1000.0

class SimpleLogger:
    """简化的日志系统"""

    def __init__(self, max_queue_size=50, config_getter=None, debug=False):
        self.log_queue = deque((), max_queue_size)
        self.enabled = True
        self.config_getter = config_getter
        self.debug = debug

        # 获取日志级别常量
        if self.config_getter is not None:
            self.LOG_LEVEL_CRITICAL = getattr(config_getter, 'LOG_LEVEL_CRITICAL', 101)
            self.LOG_LEVEL_ERROR = getattr(config_getter, 'LOG_LEVEL_ERROR', 104)
            self.LOG_LEVEL_WARNING = getattr(config_getter, 'LOG_LEVEL_WARNING', 102)
            self.LOG_LEVEL_INFO = getattr(config_getter, 'LOG_LEVEL_INFO', 103)
            self.debug = getattr(config_getter, 'DEBUG', debug)
        else:
            # 尝试导入默认配置
            try:
                from .config import LOG_LEVEL_CRITICAL, LOG_LEVEL_ERROR, LOG_LEVEL_WARNING, LOG_LEVEL_INFO, DEBUG
                self.LOG_LEVEL_CRITICAL = LOG_LEVEL_CRITICAL
                self.LOG_LEVEL_ERROR = LOG_LEVEL_ERROR
                self.LOG_LEVEL_WARNING = LOG_LEVEL_WARNING
                self.LOG_LEVEL_INFO = LOG_LEVEL_INFO
                self.debug = DEBUG
            except ImportError:
                # 使用默认值
                self.LOG_LEVEL_CRITICAL = 101
                self.LOG_LEVEL_ERROR = 104
                self.LOG_LEVEL_WARNING = 102
                self.LOG_LEVEL_INFO = 103
                self.debug = debug

        self.min_log_level = self.LOG_LEVEL_INFO  # 默认记录INFO及以上级别
        self._level_names = {
            self.LOG_LEVEL_CRITICAL: "CRITICAL",
            self.LOG_LEVEL_ERROR: "ERROR",
            self.LOG_LEVEL_WARNING: "WARNING",
            self.LOG_LEVEL_INFO: "INFO"
        }

    def set_log_level(self, level):
        """动态设置日志级别"""
        self.min_log_level = level
        if self.debug:
            level_name = self._level_names.get(level, str(level))
            print(f"[Logger] 日志级别设置为: {level_name}")

    def should_log(self, level):
        """检查是否应该记录该级别的日志"""
        return self.enabled and level >= self.min_log_level

    def log(self, level, message):
        """记录日志"""
        if not self.should_log(level):
            return

        try:
            timestamp = time()
            level_name = self._level_names.get(level, "UNKNOWN")
            log_entry = f"[{level_name}] {timestamp}: {message}"
            self.log_queue.append(log_entry)

            if self.debug:
                print(log_entry)

            # 如果是严重错误，考虑立即写入闪存（如果需要的话）
            if level == self.LOG_LEVEL_CRITICAL:
                self._handle_critical_log(log_entry)

        except Exception as e:
            if self.debug:
                print(f"[Logger] 日志记录失败: {e}")

    def _handle_critical_log(self, log_entry):
        """处理关键日志，原子性地写入到文件"""
        try:
            # 使用临时文件确保原子性写入
            temp_file = '/critical_log.tmp'
            log_file = '/critical_log.txt'

            # 先写入临时文件
            with open(temp_file, 'w') as f:
                f.write(log_entry + '\n')
                f.flush()  # 确保数据写入存储

            # 原子性地重命名文件
            try:
                import os
                os.rename(temp_file, log_file)
            except (ImportError, OSError):
                # 如果重命名失败，直接写入目标文件
                with open(log_file, 'a') as f:
                    f.write(log_entry + '\n')
                    f.flush()
                # 清理临时文件
                try:
                    import os
                    os.remove(temp_file)
                except:
                    pass

        except Exception as e:
            if self.debug:
                print(f"[Logger] 关键日志写入失败: {e}")

    def log_critical(self, message):
        """记录关键日志"""
        self.log(self.LOG_LEVEL_CRITICAL, message)

    def log_error(self, message):
        """记录错误日志"""
        self.log(self.LOG_LEVEL_ERROR, message)

    def log_warning(self, message):
        """记录警告日志"""
        self.log(self.LOG_LEVEL_WARNING, message)

    def log_info(self, message):
        """记录信息日志"""
        self.log(self.LOG_LEVEL_INFO, message)

    def get_recent_logs(self, count=10):
        """获取最近的日志"""
        return list(self.log_queue)[-count:]

    def clear_logs(self):
        """清空日志队列"""
        self.log_queue.clear()
        gc.collect()

    def get_log_stats(self):
        """获取日志统计信息"""
        return {
            'queue_size': len(self.log_queue),
            'max_size': self.log_queue.maxlen,
            'enabled': self.enabled,
            'min_level': self.min_log_level
        }

# 全局日志实例（延迟初始化）
_global_logger = None

def _ensure_global_logger():
    """确保全局日志实例已初始化"""
    global _global_logger
    if _global_logger is None:
        _global_logger = SimpleLogger()
    return _global_logger

def init_logger():
    """初始化日志系统"""
    logger = _ensure_global_logger()
    if logger.debug:
        print("[Logger] 日志系统已初始化")
    return True

def create_logger(max_queue_size=50, config_getter=None, debug=False):
    """创建日志实例（依赖注入工厂函数）"""
    return SimpleLogger(max_queue_size=max_queue_size, config_getter=config_getter, debug=debug)

def set_log_level(level):
    """设置全局日志级别"""
    _ensure_global_logger().set_log_level(level)

def log_critical(message):
    """记录关键日志"""
    _ensure_global_logger().log_critical(message)

def log_error(message):
    """记录错误日志"""
    _ensure_global_logger().log_error(message)

def log_warning(message):
    """记录警告日志"""
    _ensure_global_logger().log_warning(message)

def log_info(message):
    """记录信息日志"""
    _ensure_global_logger().log_info(message)

def get_recent_logs(count=10):
    """获取最近的日志"""
    return _ensure_global_logger().get_recent_logs(count)

def clear_logs():
    """清空日志"""
    _ensure_global_logger().clear_logs()

def get_log_stats():
    """获取日志统计信息"""
    return _ensure_global_logger().get_log_stats()
