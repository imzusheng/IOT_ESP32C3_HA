# logger.py
"""
日志系统模块

从core.py中分离出来的独立日志系统，提供：
- 基于事件总线的日志记录
- 内存队列管理
- 日志级别过滤
- 动态日志级别调整
"""

import time
import gc
from collections import deque
from .config import get_event_id, DEBUG, LOG_LEVEL_CRITICAL, LOG_LEVEL_WARNING, LOG_LEVEL_INFO, LOG_LEVEL_ERROR

class SimpleLogger:
    """简化的日志系统"""
    
    def __init__(self, max_queue_size=50):
        self.log_queue = deque((), max_queue_size)
        self.enabled = True
        self.min_log_level = LOG_LEVEL_INFO  # 默认记录INFO及以上级别
        self._level_names = {
            LOG_LEVEL_CRITICAL: "CRITICAL",
            LOG_LEVEL_ERROR: "ERROR", 
            LOG_LEVEL_WARNING: "WARNING",
            LOG_LEVEL_INFO: "INFO"
        }
        
    def set_log_level(self, level):
        """动态设置日志级别"""
        self.min_log_level = level
        if DEBUG:
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
            timestamp = time.time()
            level_name = self._level_names.get(level, "UNKNOWN")
            log_entry = f"[{level_name}] {timestamp}: {message}"
            self.log_queue.append(log_entry)
            
            if DEBUG:
                print(log_entry)
                
            # 如果是严重错误，考虑立即写入闪存（如果需要的话）
            if level == LOG_LEVEL_CRITICAL:
                self._handle_critical_log(log_entry)
                
        except Exception as e:
            if DEBUG:
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
            if DEBUG:
                print(f"[Logger] 关键日志写入失败: {e}")
    
    def log_critical(self, message):
        """记录关键日志"""
        self.log(LOG_LEVEL_CRITICAL, message)
    
    def log_error(self, message):
        """记录错误日志"""
        self.log(LOG_LEVEL_ERROR, message)
    
    def log_warning(self, message):
        """记录警告日志"""
        self.log(LOG_LEVEL_WARNING, message)
    
    def log_info(self, message):
        """记录信息日志"""
        self.log(LOG_LEVEL_INFO, message)
    
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

# 全局日志实例
_global_logger = SimpleLogger()

def init_logger():
    """初始化日志系统"""
    if DEBUG:
        print("[Logger] 日志系统已初始化")
    return True

def set_log_level(level):
    """设置全局日志级别"""
    _global_logger.set_log_level(level)

def log_critical(message):
    """记录关键日志"""
    _global_logger.log_critical(message)

def log_error(message):
    """记录错误日志"""
    _global_logger.log_error(message)

def log_warning(message):
    """记录警告日志"""
    _global_logger.log_warning(message)

def log_info(message):
    """记录信息日志"""
    _global_logger.log_info(message)

def get_recent_logs(count=10):
    """获取最近的日志"""
    return _global_logger.get_recent_logs(count)

def clear_logs():
    """清空日志"""
    _global_logger.clear_logs()

def get_log_stats():
    """获取日志统计信息"""
    return _global_logger.get_log_stats()