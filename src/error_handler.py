# -*- coding: utf-8 -*-
"""
统一错误处理和日志模块

为ESP32C3设备提供集中式错误处理和日志管理：
- 统一错误分类和处理
- 智能日志系统
- 错误恢复机制
- 内存友好的日志缓冲
"""

import time
import gc
import sys
from enum import Enum

# =============================================================================
# 错误类型定义
# =============================================================================

class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK = "NETWORK_ERROR"
    HARDWARE = "HARDWARE_ERROR"
    MEMORY = "MEMORY_ERROR"
    CONFIG = "CONFIG_ERROR"
    SYSTEM = "SYSTEM_ERROR"
    MQTT = "MQTT_ERROR"
    WIFI = "WIFI_ERROR"
    DAEMON = "DAEMON_ERROR"

class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

# =============================================================================
# 错误信息类
# =============================================================================

class ErrorInfo:
    """错误信息类"""
    
    def __init__(self, error_type: ErrorType, message: str, context: str = ""):
        self.type = error_type
        self.message = message
        self.context = context
        self.timestamp = time.time()
        self.count = 1
    
    def to_dict(self):
        """转换为字典"""
        return {
            'type': self.type.value,
            'message': self.message,
            'context': self.context,
            'timestamp': self.timestamp,
            'count': self.count
        }
    
    def __str__(self):
        return f"[{self.type.value}] {self.message} (上下文: {self.context})"

# =============================================================================
# 错误统计类
# =============================================================================

class ErrorStats:
    """错误统计管理器"""
    
    def __init__(self):
        self._stats = {}
        self._max_history = 100
        self._error_history = []
        self._last_reset_time = time.time()
    
    def record_error(self, error_type: ErrorType, message: str, context: str = ""):
        """记录错误"""
        # 更新统计
        type_key = error_type.value
        if type_key not in self._stats:
            self._stats[type_key] = {
                'count': 0,
                'first_occurrence': time.time(),
                'last_occurrence': time.time()
            }
        
        self._stats[type_key]['count'] += 1
        self._stats[type_key]['last_occurrence'] = time.time()
        
        # 添加到历史记录
        error_info = ErrorInfo(error_type, message, context)
        self._error_history.append(error_info)
        
        # 保持历史记录在限制范围内
        if len(self._error_history) > self._max_history:
            self._error_history.pop(0)
        
        # 执行垃圾回收
        if len(self._error_history) % 10 == 0:
            gc.collect()
    
    def get_error_count(self, error_type: ErrorType = None):
        """获取错误计数"""
        if error_type is None:
            return sum(stat['count'] for stat in self._stats.values())
        
        return self._stats.get(error_type.value, {}).get('count', 0)
    
    def get_stats(self):
        """获取错误统计"""
        return self._stats.copy()
    
    def get_recent_errors(self, count: int = 10):
        """获取最近的错误"""
        return self._error_history[-count:]
    
    def reset_stats(self):
        """重置统计"""
        self._stats.clear()
        self._error_history.clear()
        self._last_reset_time = time.time()
        gc.collect()
    
    def should_trigger_recovery(self, error_type: ErrorType) -> bool:
        """检查是否应该触发恢复机制"""
        thresholds = {
            ErrorType.NETWORK: 10,
            ErrorType.HARDWARE: 3,
            ErrorType.MEMORY: 5,
            ErrorType.SYSTEM: 7,
            ErrorType.MQTT: 8,
            ErrorType.WIFI: 8,
            ErrorType.DAEMON: 5,
            ErrorType.CONFIG: 3
        }
        
        threshold = thresholds.get(error_type, 5)
        return self.get_error_count(error_type) >= threshold

# =============================================================================
# 日志缓冲区类
# =============================================================================

class LogBuffer:
    """内存友好的日志缓冲区"""
    
    def __init__(self, max_size: int = 50):
        self._max_size = max_size
        self._buffer = []
        self._buffer_lock = None  # 在MicroPython中简化处理
    
    def add_log(self, level: LogLevel, message: str, module: str = ""):
        """添加日志到缓冲区"""
        log_entry = {
            'timestamp': time.time(),
            'level': level.value,
            'message': message,
            'module': module
        }
        
        self._buffer.append(log_entry)
        
        # 保持缓冲区大小
        if len(self._buffer) > self._max_size:
            self._buffer.pop(0)
        
        # 定期垃圾回收
        if len(self._buffer) % 20 == 0:
            gc.collect()
    
    def get_logs(self, count: int = None):
        """获取日志"""
        if count is None:
            return self._buffer.copy()
        
        return self._buffer[-count:]
    
    def clear(self):
        """清空缓冲区"""
        self._buffer.clear()
        gc.collect()
    
    def get_size(self):
        """获取当前缓冲区大小"""
        return len(self._buffer)

# =============================================================================
# 统一日志记录器
# =============================================================================

class UnifiedLogger:
    """统一日志记录器"""
    
    def __init__(self, mqtt_client=None):
        self._mqtt_client = mqtt_client
        self._log_level = LogLevel.INFO
        self._log_buffer = LogBuffer()
        self._console_enabled = True
        self._mqtt_enabled = True
        self._log_format = "[{level}] [{time}] [{module}] {message}"
    
    def set_log_level(self, level: LogLevel):
        """设置日志级别"""
        self._log_level = level
    
    def set_mqtt_client(self, mqtt_client):
        """设置MQTT客户端"""
        self._mqtt_client = mqtt_client
    
    def enable_console(self, enabled: bool):
        """启用/禁用控制台输出"""
        self._console_enabled = enabled
    
    def enable_mqtt(self, enabled: bool):
        """启用/禁用MQTT输出"""
        self._mqtt_enabled = enabled
    
    def log(self, level: LogLevel, message: str, module: str = ""):
        """记录日志"""
        # 检查日志级别
        if not self._should_log(level):
            return
        
        # 格式化时间
        t = time.localtime(time.time())
        time_str = f"{t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        
        # 格式化日志消息
        formatted_msg = self._log_format.format(
            level=level.value,
            time=time_str,
            module=module,
            message=message
        )
        
        # 添加到缓冲区
        self._log_buffer.add_log(level, message, module)
        
        # 控制台输出
        if self._console_enabled:
            # 添加颜色
            color_map = {
                LogLevel.DEBUG: "\033[0;37m",    # 灰色
                LogLevel.INFO: "\033[0;32m",     # 绿色
                LogLevel.WARNING: "\033[0;33m",   # 黄色
                LogLevel.ERROR: "\033[0;31m",     # 红色
                LogLevel.CRITICAL: "\033[1;31m"   # 亮红色
            }
            reset_color = "\033[0m"
            
            color = color_map.get(level, "")
            print(f"{color}{formatted_msg}{reset_color}")
        
        # MQTT输出
        if self._mqtt_enabled and self._mqtt_client and hasattr(self._mqtt_client, 'is_connected') and self._mqtt_client.is_connected:
            try:
                if hasattr(self._mqtt_client, 'log'):
                    self._mqtt_client.log(level.value, f"[{module}] {message}")
                elif hasattr(self._mqtt_client, 'publish'):
                    # 直接使用publish方法
                    topic = getattr(self._mqtt_client, 'topic', 'esp32c3/logs')
                    self._mqtt_client.publish(topic, formatted_msg)
            except Exception as e:
                # MQTT发送失败时不影响主流程
                if self._console_enabled:
                    print(f"[Logger] MQTT发送失败: {e}")
    
    def debug(self, message: str, module: str = ""):
        """调试日志"""
        self.log(LogLevel.DEBUG, message, module)
    
    def info(self, message: str, module: str = ""):
        """信息日志"""
        self.log(LogLevel.INFO, message, module)
    
    def warning(self, message: str, module: str = ""):
        """警告日志"""
        self.log(LogLevel.WARNING, message, module)
    
    def error(self, message: str, module: str = ""):
        """错误日志"""
        self.log(LogLevel.ERROR, message, module)
    
    def critical(self, message: str, module: str = ""):
        """严重错误日志"""
        self.log(LogLevel.CRITICAL, message, module)
    
    def _should_log(self, level: LogLevel) -> bool:
        """检查是否应该记录该级别的日志"""
        levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return levels.index(level) >= levels.index(self._log_level)
    
    def get_recent_logs(self, count: int = 10):
        """获取最近的日志"""
        return self._log_buffer.get_logs(count)
    
    def clear_logs(self):
        """清空日志"""
        self._log_buffer.clear()

# =============================================================================
# 错误处理器类
# =============================================================================

class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, logger: UnifiedLogger):
        self._logger = logger
        self._error_stats = ErrorStats()
        self._recovery_actions = {}
        self._register_recovery_actions()
    
    def _register_recovery_actions(self):
        """注册恢复动作"""
        self._recovery_actions = {
            ErrorType.NETWORK: self._handle_network_error,
            ErrorType.MEMORY: self._handle_memory_error,
            ErrorType.HARDWARE: self._handle_hardware_error,
            ErrorType.SYSTEM: self._handle_system_error,
            ErrorType.MQTT: self._handle_mqtt_error,
            ErrorType.WIFI: self._handle_wifi_error,
            ErrorType.DAEMON: self._handle_daemon_error,
            ErrorType.CONFIG: self._handle_config_error
        }
    
    def handle_error(self, error_type: ErrorType, error: Exception, context: str = ""):
        """处理错误"""
        # 记录错误
        error_message = str(error)
        self._error_stats.record_error(error_type, error_message, context)
        
        # 记录日志
        self._logger.error(f"{error_type.value}: {error_message}", "ErrorHandler")
        
        # 执行恢复动作
        if error_type in self._recovery_actions:
            try:
                self._recovery_actions[error_type](error_type, error_message, context)
            except Exception as e:
                self._logger.error(f"恢复动作失败: {e}", "ErrorHandler")
        
        # 检查是否需要触发系统恢复
        if self._error_stats.should_trigger_recovery(error_type):
            self._trigger_system_recovery(error_type)
    
    def _handle_network_error(self, error_type: ErrorType, message: str, context: str):
        """处理网络错误"""
        self._logger.warning(f"网络错误: {message}", "ErrorHandler")
        # 强制垃圾回收
        gc.collect()
    
    def _handle_memory_error(self, error_type: ErrorType, message: str, context: str):
        """处理内存错误"""
        self._logger.warning(f"内存错误: {message}", "ErrorHandler")
        # 强制垃圾回收
        gc.collect()
        # 清理日志缓冲区
        if hasattr(self._logger, '_log_buffer'):
            self._logger._log_buffer.clear()
    
    def _handle_hardware_error(self, error_type: ErrorType, message: str, context: str):
        """处理硬件错误"""
        self._logger.warning(f"硬件错误: {message}", "ErrorHandler")
        # 硬件错误可能需要重启
        self._logger.critical("检测到硬件错误，建议重启系统", "ErrorHandler")
    
    def _handle_system_error(self, error_type: ErrorType, message: str, context: str):
        """处理系统错误"""
        self._logger.warning(f"系统错误: {message}", "ErrorHandler")
        # 强制垃圾回收
        gc.collect()
    
    def _handle_mqtt_error(self, error_type: ErrorType, message: str, context: str):
        """处理MQTT错误"""
        self._logger.warning(f"MQTT错误: {message}", "ErrorHandler")
        # MQTT错误通常由连接管理器处理
    
    def _handle_wifi_error(self, error_type: ErrorType, message: str, context: str):
        """处理WiFi错误"""
        self._logger.warning(f"WiFi错误: {message}", "ErrorHandler")
        # WiFi错误通常由WiFi管理器处理
    
    def _handle_daemon_error(self, error_type: ErrorType, message: str, context: str):
        """处理守护进程错误"""
        self._logger.warning(f"守护进程错误: {message}", "ErrorHandler")
        # 守护进程错误可能需要重启守护进程
    
    def _handle_config_error(self, error_type: ErrorType, message: str, context: str):
        """处理配置错误"""
        self._logger.warning(f"配置错误: {message}", "ErrorHandler")
        # 配置错误需要管理员干预
    
    def _trigger_system_recovery(self, error_type: ErrorType):
        """触发系统恢复"""
        self._logger.critical(f"触发系统恢复: {error_type.value}", "ErrorHandler")
        
        # 执行系统恢复动作
        gc.collect()
        
        # 根据错误类型执行特定恢复
        if error_type == ErrorType.MEMORY:
            # 内存错误：深度清理
            self._deep_memory_cleanup()
        elif error_type == ErrorType.HARDWARE:
            # 硬件错误：建议重启
            self._logger.critical("硬件错误无法恢复，建议手动重启", "ErrorHandler")
    
    def _deep_memory_cleanup(self):
        """深度内存清理"""
        self._logger.info("执行深度内存清理", "ErrorHandler")
        
        # 多次垃圾回收
        for _ in range(3):
            gc.collect()
            time.sleep_ms(100)
        
        # 清理错误统计历史
        self._error_stats.get_recent_errors(0)  # 清空历史
        
        self._logger.info("深度内存清理完成", "ErrorHandler")
    
    def get_error_stats(self):
        """获取错误统计"""
        return self._error_stats.get_stats()
    
    def get_recent_errors(self, count: int = 10):
        """获取最近的错误"""
        return self._error_stats.get_recent_errors(count)
    
    def reset_error_stats(self):
        """重置错误统计"""
        self._error_stats.reset_stats()
        self._logger.info("错误统计已重置", "ErrorHandler")

# =============================================================================
# 全局实例
# =============================================================================

# 创建全局日志记录器
_logger = UnifiedLogger()

# 创建全局错误处理器
_error_handler = ErrorHandler(_logger)

def get_logger():
    """获取全局日志记录器"""
    return _logger

def get_error_handler():
    """获取全局错误处理器"""
    return _error_handler

def set_mqtt_client(mqtt_client):
    """设置MQTT客户端"""
    _logger.set_mqtt_client(mqtt_client)

def set_log_level(level: LogLevel):
    """设置日志级别"""
    _logger.set_log_level(level)

def log_error(error_type: ErrorType, error: Exception, context: str = ""):
    """记录错误"""
    _error_handler.handle_error(error_type, error, context)

def get_error_stats():
    """获取错误统计"""
    return _error_handler.get_error_stats()

def get_recent_errors(count: int = 10):
    """获取最近的错误"""
    return _error_handler.get_recent_errors(count)

def reset_error_stats():
    """重置错误统计"""
    _error_handler.reset_error_stats()

# =============================================================================
# 便捷函数
# =============================================================================

def debug(message: str, module: str = ""):
    """调试日志"""
    _logger.debug(message, module)

def info(message: str, module: str = ""):
    """信息日志"""
    _logger.info(message, module)

def warning(message: str, module: str = ""):
    """警告日志"""
    _logger.warning(message, module)

def error(message: str, module: str = ""):
    """错误日志"""
    _logger.error(message, module)

def critical(message: str, module: str = ""):
    """严重错误日志"""
    _logger.critical(message, module)

# =============================================================================
# 初始化
# =============================================================================

# 设置默认日志级别
set_log_level(LogLevel.INFO)

# 执行垃圾回收
gc.collect()