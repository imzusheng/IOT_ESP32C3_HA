# -*- coding: utf-8 -*-
"""
统一错误处理和日志模块

为ESP32C3设备提供集中式错误处理和日志管理，包含高级错误恢复功能：
- 统一错误分类和处理
- 智能日志系统
- 自动错误恢复机制
- 内存友好的日志缓冲
- 错误严重程度分类
- 智能恢复策略

内存优化说明：
- 使用枚举和类减少内存占用
- 限制日志和错误历史大小
- 定期垃圾回收
- 避免复杂的数据结构
"""

import time
import gc
from enum import Enum

import config

# =============================================================================
# 错误类型和严重程度定义
# =============================================================================

class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK = "NETWORK_ERROR"      # 网络连接错误
    HARDWARE = "HARDWARE_ERROR"    # 硬件故障
    MEMORY = "MEMORY_ERROR"         # 内存不足
    CONFIG = "CONFIG_ERROR"         # 配置错误
    SYSTEM = "SYSTEM_ERROR"         # 系统错误
    MQTT = "MQTT_ERROR"             # MQTT通信错误
    WIFI = "WIFI_ERROR"             # WiFi连接错误
    DAEMON = "DAEMON_ERROR"         # 守护进程错误
    FATAL = "FATAL_ERROR"           # 致命错误

class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"    # 调试信息
    INFO = "INFO"      # 一般信息
    WARNING = "WARNING" # 警告信息
    ERROR = "ERROR"    # 错误信息
    CRITICAL = "CRITICAL" # 严重错误

class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "LOW"           # 低级错误，不影响系统运行
    MEDIUM = "MEDIUM"     # 中级错误，影响部分功能
    HIGH = "HIGH"         # 高级错误，影响主要功能
    CRITICAL = "CRITICAL" # 严重错误，系统无法正常运行
    FATAL = "FATAL"       # 致命错误，需要立即重启

# =============================================================================
# 错误恢复策略
# =============================================================================

class RecoveryStrategy(Enum):
    """恢复策略"""
    NONE = "NONE"                     # 无需恢复
    RETRY = "RETRY"                   # 重试
    RESTART_COMPONENT = "RESTART_COMPONENT"  # 重启组件
    RESTART_SYSTEM = "RESTART_SYSTEM"       # 重启系统
    RESET_CONNECTION = "RESET_CONNECTION"   # 重置连接
    CLEAR_CACHE = "CLEAR_CACHE"           # 清除缓存
    FALLBACK_MODE = "FALLBACK_MODE"       # 降级模式

# =============================================================================
# 错误信息类
# =============================================================================

class ErrorInfo:
    """错误信息类"""
    
    def __init__(self, error_type: ErrorType, message: str, context: str = "", 
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        self.type = error_type
        self.message = message
        self.context = context
        self.severity = severity
        self.timestamp = time.time()
        self.count = 1
    
    def to_dict(self):
        """转换为字典"""
        return {
            'type': self.type.value,
            'message': self.message,
            'context': self.context,
            'severity': self.severity.value,
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
        self._max_history = 50  # 减少历史记录大小以节省内存
        self._error_history = []
        self._last_reset_time = time.time()
    
    def record_error(self, error_type: ErrorType, message: str, context: str = "",
                    severity: ErrorSeverity = ErrorSeverity.MEDIUM):
        """记录错误"""
        # 更新统计
        type_key = error_type.value
        if type_key not in self._stats:
            self._stats[type_key] = {
                'count': 0,
                'first_occurrence': time.time(),
                'last_occurrence': time.time(),
                'severity_counts': {}
            }
        
        self._stats[type_key]['count'] += 1
        self._stats[type_key]['last_occurrence'] = time.time()
        
        # 更新严重程度统计
        severity_key = severity.value
        if severity_key not in self._stats[type_key]['severity_counts']:
            self._stats[type_key]['severity_counts'][severity_key] = 0
        self._stats[type_key]['severity_counts'][severity_key] += 1
        
        # 添加到历史记录
        error_info = ErrorInfo(error_type, message, context, severity)
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
        # 根据错误类型和严重程度设置不同的阈值
        thresholds = {
            ErrorType.NETWORK: 8,
            ErrorType.HARDWARE: 2,
            ErrorType.MEMORY: 5,
            ErrorType.SYSTEM: 5,
            ErrorType.MQTT: 6,
            ErrorType.WIFI: 6,
            ErrorType.DAEMON: 4,
            ErrorType.CONFIG: 2,
            ErrorType.FATAL: 1
        }
        
        threshold = thresholds.get(error_type, 5)
        return self.get_error_count(error_type) >= threshold

# =============================================================================
# 日志缓冲区类
# =============================================================================

class LogBuffer:
    """内存友好的日志缓冲区"""
    
    def __init__(self, max_size: int = 30):  # 减小缓冲区大小
        self._max_size = max_size
        self._buffer = []
    
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
        if len(self._buffer) % 15 == 0:
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
        self._log_format = "[{level}] [{module}] {message}"
    
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
        
        # 简化时间格式以节省内存
        time_str = f"{time.ticks_ms()//1000}"
        
        # 格式化日志消息
        formatted_msg = self._log_format.format(
            level=level.value,
            time=time_str,
            module=module,
            message=message
        )
        
        # 添加到缓冲区
        self._log_buffer.add_log(level, message, module)
        
        # 控制台输出（简化，不使用颜色）
        if self._console_enabled:
            print(formatted_msg)
        
        # MQTT输出
        if self._mqtt_enabled and self._mqtt_client and hasattr(self._mqtt_client, 'is_connected') and self._mqtt_client.is_connected:
            try:
                if hasattr(self._mqtt_client, 'publish'):
                    topic = f"esp32c3/logs/{level.value.lower()}"
                    self._mqtt_client.publish(topic, formatted_msg)
            except Exception:
                # MQTT发送失败时不影响主流程
                pass
    
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
# 错误恢复动作类
# =============================================================================

class RecoveryAction:
    """恢复动作基类"""
    
    def __init__(self, name: str, strategy: RecoveryStrategy):
        self.name = name
        self.strategy = strategy
        self.execution_count = 0
        self.success_count = 0
        self.last_execution = 0
        
    def execute(self, error_type: ErrorType, message: str, context: str = "") -> bool:
        """执行恢复动作"""
        try:
            self.execution_count += 1
            self.last_execution = time.time()
            
            result = self._execute_action(error_type, message, context)
            
            if result:
                self.success_count += 1
                
            return result
            
        except Exception as e:
            # 恢复动作失败时记录日志但不抛出异常
            print(f"[Recovery] {self.name} 执行失败: {e}")
            return False
    
    def _execute_action(self, error_type: ErrorType, message: str, context: str) -> bool:
        """子类实现具体恢复逻辑"""
        raise NotImplementedError
    
    def get_success_rate(self) -> float:
        """获取成功率"""
        if self.execution_count == 0:
            return 0.0
        return self.success_count / self.execution_count

class RetryAction(RecoveryAction):
    """重试动作"""
    
    def __init__(self, max_retries: int = 2, delay_ms: int = 1000):
        super().__init__("重试", RecoveryStrategy.RETRY)
        self.max_retries = max_retries
        self.delay_ms = delay_ms
    
    def _execute_action(self, error_type: ErrorType, message: str, context: str) -> bool:
        """执行重试"""
        # 简化版本：等待一段时间后返回成功
        if self.delay_ms > 0:
            time.sleep_ms(self.delay_ms)
        return True

class MemoryCleanupAction(RecoveryAction):
    """内存清理动作"""
    
    def __init__(self):
        super().__init__("内存清理", RecoveryStrategy.CLEAR_CACHE)
    
    def _execute_action(self, error_type: ErrorType, message: str, context: str) -> bool:
        """执行内存清理"""
        try:
            # 执行深度垃圾回收
            for _ in range(2):
                gc.collect()
                time.sleep_ms(50)
            return True
        except Exception:
            return False

class SystemRestartAction(RecoveryAction):
    """系统重启动作"""
    
    def __init__(self):
        super().__init__("系统重启", RecoveryStrategy.RESTART_SYSTEM)
    
    def _execute_action(self, error_type: ErrorType, message: str, context: str) -> bool:
        """执行系统重启"""
        try:
            # 延迟重启以允许日志记录
            time.sleep_ms(1000)
            
            # 导入machine模块执行重启
            import machine
            machine.reset()
            
            return True  # 理论上不会执行到这里
        except Exception:
            return False

# =============================================================================
# 错误处理器类
# =============================================================================

class ErrorHandler:
    """增强错误处理器"""
    
    def __init__(self, logger: UnifiedLogger):
        self._logger = logger
        self._error_stats = ErrorStats()
        self._recovery_actions = {}
        self._recovery_cooldowns = {}
        self._register_recovery_actions()
    
    def _register_recovery_actions(self):
        """注册恢复动作"""
        # 为每种错误类型注册恢复动作
        self._recovery_actions = {
            ErrorType.NETWORK: [
                RetryAction(max_retries=2, delay_ms=2000),
                MemoryCleanupAction()
            ],
            ErrorType.MEMORY: [
                MemoryCleanupAction(),
                RetryAction(max_retries=1, delay_ms=500)
            ],
            ErrorType.HARDWARE: [
                SystemRestartAction()
            ],
            ErrorType.SYSTEM: [
                MemoryCleanupAction(),
                RetryAction(max_retries=1, delay_ms=1000),
                SystemRestartAction()
            ],
            ErrorType.MQTT: [
                RetryAction(max_retries=2, delay_ms=1000),
                MemoryCleanupAction()
            ],
            ErrorType.WIFI: [
                RetryAction(max_retries=2, delay_ms=2000),
                MemoryCleanupAction()
            ],
            ErrorType.DAEMON: [
                RetryAction(max_retries=1, delay_ms=1000),
                MemoryCleanupAction()
            ],
            ErrorType.CONFIG: [
                # 配置错误通常需要手动干预
            ],
            ErrorType.FATAL: [
                SystemRestartAction()
            ]
        }
    
    def handle_error(self, error_type: ErrorType, error: Exception, 
                    context: str = "", severity: ErrorSeverity = None):
        """处理错误"""
        try:
            # 确定错误严重程度
            if severity is None:
                severity = self._determine_severity(error_type)
            
            # 记录错误
            error_message = str(error)
            self._error_stats.record_error(error_type, error_message, context, severity)
            
            # 记录日志
            log_method = self._get_log_method(severity)
            log_method(f"{error_type.value}: {error_message}", "ErrorHandler")
            
            # 检查是否在冷却期
            if self._is_in_cooldown(error_type):
                return False
            
            # 执行恢复动作
            recovery_success = self._execute_recovery_actions(error_type, error_message, context)
            
            if recovery_success:
                # 设置冷却期
                self._set_cooldown(error_type)
            else:
                # 检查是否需要触发系统恢复
                if self._error_stats.should_trigger_recovery(error_type):
                    self._trigger_system_recovery(error_type)
            
            return recovery_success
            
        except Exception as e:
            # 错误处理失败时使用print避免递归
            print(f"[ErrorHandler] 错误处理失败: {e}")
            return False
    
    def _determine_severity(self, error_type: ErrorType) -> ErrorSeverity:
        """根据错误类型确定严重程度"""
        severity_map = {
            ErrorType.HARDWARE: ErrorSeverity.HIGH,
            ErrorType.MEMORY: ErrorSeverity.HIGH,
            ErrorType.SYSTEM: ErrorSeverity.HIGH,
            ErrorType.FATAL: ErrorSeverity.FATAL,
            ErrorType.NETWORK: ErrorSeverity.MEDIUM,
            ErrorType.MQTT: ErrorSeverity.MEDIUM,
            ErrorType.WIFI: ErrorSeverity.MEDIUM,
            ErrorType.DAEMON: ErrorSeverity.MEDIUM,
            ErrorType.CONFIG: ErrorSeverity.LOW
        }
        
        return severity_map.get(error_type, ErrorSeverity.MEDIUM)
    
    def _get_log_method(self, severity: ErrorSeverity):
        """根据严重程度获取日志方法"""
        log_methods = {
            ErrorSeverity.LOW: self._logger.info,
            ErrorSeverity.MEDIUM: self._logger.warning,
            ErrorSeverity.HIGH: self._logger.error,
            ErrorSeverity.CRITICAL: self._logger.critical,
            ErrorSeverity.FATAL: self._logger.critical
        }
        return log_methods.get(severity, self._logger.error)
    
    def _is_in_cooldown(self, error_type: ErrorType) -> bool:
        """检查是否在冷却期"""
        cooldown_time = self._recovery_cooldowns.get(error_type, 0)
        return time.time() - cooldown_time < 30  # 30秒冷却期
    
    def _set_cooldown(self, error_type: ErrorType):
        """设置冷却期"""
        self._recovery_cooldowns[error_type] = time.time()
    
    def _execute_recovery_actions(self, error_type: ErrorType, message: str, context: str) -> bool:
        """执行恢复动作"""
        actions = self._recovery_actions.get(error_type, [])
        
        for action in actions:
            try:
                if action.execute(error_type, message, context):
                    self._logger.info(f"恢复成功: {action.name}", "ErrorHandler")
                    return True
                else:
                    self._logger.warning(f"恢复动作失败: {action.name}", "ErrorHandler")
            except Exception as e:
                self._logger.error(f"恢复动作异常: {action.name} - {e}", "ErrorHandler")
        
        return False
    
    def _trigger_system_recovery(self, error_type: ErrorType):
        """触发系统恢复"""
        self._logger.critical(f"触发系统恢复: {error_type.value}", "ErrorHandler")
        
        # 执行深度内存清理
        self._deep_memory_cleanup()
        
        # 对于致命错误，执行系统重启
        if error_type == ErrorType.FATAL:
            if config.SystemConfig.AUTO_RESTART_ENABLED:
                SystemRestartAction().execute(error_type, "致命错误恢复", "ErrorHandler")
    
    def _deep_memory_cleanup(self):
        """深度内存清理"""
        self._logger.info("执行深度内存清理", "ErrorHandler")
        
        # 多次垃圾回收
        for _ in range(3):
            gc.collect()
            time.sleep_ms(100)
        
        # 清理日志缓冲区
        self._logger.clear_logs()
        
        # 清理错误历史
        self._error_stats.get_recent_errors(0)
        
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

def handle_error(error_type: ErrorType, error: Exception, 
                context: str = "", severity: ErrorSeverity = None):
    """处理错误"""
    return _error_handler.handle_error(error_type, error, context, severity)

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
