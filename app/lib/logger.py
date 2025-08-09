# app/lib/logger.py
try:
    import ulogging
except ImportError:
    from lib.lock import ulogging

from event_const import EVENT

class Logger:
    """
    基于 ulogging 的日志系统 (重构版本)
    
    使用 MicroPython 的 ulogging 模块作为底层日志记录器，
    同时保持与事件总线的集成。提供更高效的日志处理
    和更好的内存管理。
    
    特性:
    - 基于 ulogging 的高效日志记录
    - 事件驱动日志记录
    - 多级别日志支持 (DEBUG, INFO, WARN, ERROR)
    - 内存优化设计
    - 时间戳格式化
    - 统一的接口
    - MQTT集成支持
    - 错误隔离处理
    """
    def __init__(self, level=EVENT.LOG_INFO):
        # ulogging 级别映射
        self._ulogging_level_map = {
            EVENT.LOG_DEBUG: ulogging.DEBUG,
            EVENT.LOG_INFO: ulogging.INFO,
            EVENT.LOG_WARN: ulogging.WARNING,
            EVENT.LOG_ERROR: ulogging.ERROR,
        }
        
        # 兼容原有的级别映射
        self._level_map = {
            EVENT.LOG_DEBUG: 0,
            EVENT.LOG_INFO: 1,
            EVENT.LOG_WARN: 2,
            EVENT.LOG_ERROR: 3,
        }
        
        # 创建 ulogging 实例
        self._logger = ulogging.getLogger("ESP32C3")
        
        # 设置日志级别
        ulogging_level = self._ulogging_level_map.get(level, ulogging.INFO)
        self._logger.setLevel(ulogging_level)
        
        # 设置兼容的级别
        self._level = self._level_map.get(level, 1)
        
        # 配置日志格式
        self._setup_logger_format()
        
        # 事件总线引用
        self._event_bus = None
        
    def _setup_logger_format(self):
        """配置 ulogging 的输出格式"""
        # 检查是否支持 Formatter（简化版 ulogging 可能不支持）
        if hasattr(ulogging, 'Formatter'):
            # 创建格式化器
            formatter = ulogging.Formatter(
                fmt='[%(asctime)s] [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'
            )
            
            # 获取根处理器并设置格式
            for handler in self._logger.handlers:
                if hasattr(handler, 'setFormatter'):
                    handler.setFormatter(formatter)
                    
            # 如果没有处理器，添加一个流处理器
            if not self._logger.handlers:
                if hasattr(ulogging, 'StreamHandler'):
                    handler = ulogging.StreamHandler()
                    handler.setFormatter(formatter)
                    self._logger.addHandler(handler)
        else:
            # 简化版 ulogging，直接使用基本配置
            ulogging.basicConfig(level=ulogging.INFO)


    def setup(self, event_bus):
        """
        在事件总线上注册日志处理器。
        :param event_bus: EventBus 的实例
        """
        self._event_bus = event_bus
        
        # 订阅所有日志事件
        if hasattr(EVENT, 'LOG_DEBUG'):
            event_bus.subscribe(EVENT.LOG_DEBUG, self._handle_log)
        event_bus.subscribe(EVENT.LOG_INFO, self._handle_log)
        event_bus.subscribe(EVENT.LOG_WARN, self._handle_log)
        event_bus.subscribe(EVENT.LOG_ERROR, self._handle_log)
        
        # 使用 ulogging 记录设置完成（如果可用）
        try:
            self._logger.info("Logger setup complete. Subscribed to log events.")
        except:
            pass  # 如果 ulogging 还未完全初始化，忽略错误

    def set_level(self, new_level):
        """
        设置新的日志记录级别。
        :param new_level: 来自 EVENT 的日志级别常量
        """
        # 设置兼容的级别
        self._level = self._level_map.get(new_level, 1)
        
        # 设置 ulogging 级别
        ulogging_level = self._ulogging_level_map.get(new_level, ulogging.INFO)
        self._logger.setLevel(ulogging_level)
        
        # 记录级别变更（如果可用）
        try:
            self._logger.info(f"Log level changed to: {new_level}")
        except:
            pass  # 如果 ulogging 不可用，忽略

    def _handle_log(self, event_name, msg, *args):
        """
        处理接收到的日志事件。
        使用 ulogging 进行实际的日志记录。
        """
        log_level = self._level_map.get(event_name)
        if log_level is None or log_level < self._level:
            return

        # 格式化消息
        try:
            full_msg = msg.format(*args)
        except:
            full_msg = msg

        # 根据事件类型使用对应的 ulogging 方法
        if event_name == EVENT.LOG_DEBUG:
            self._logger.debug(full_msg)
        elif event_name == EVENT.LOG_INFO:
            self._logger.info(full_msg)
        elif event_name == EVENT.LOG_WARN:
            self._logger.warning(full_msg)
        elif event_name == EVENT.LOG_ERROR:
            self._logger.error(full_msg)
        else:
            self._logger.info(full_msg)
            
    # 直接日志方法 - 提供更直接的日志记录接口
    def debug(self, msg, *args):
        """直接记录调试日志"""
        self._handle_log(EVENT.LOG_DEBUG, msg, *args)
        
    def info(self, msg, *args):
        """直接记录信息日志"""
        self._handle_log(EVENT.LOG_INFO, msg, *args)
        
    def warning(self, msg, *args):
        """直接记录警告日志"""
        self._handle_log(EVENT.LOG_WARN, msg, *args)
        
    def error(self, msg, *args):
        """直接记录错误日志"""
        self._handle_log(EVENT.LOG_ERROR, msg, *args)
        
    def critical(self, msg, *args):
        """直接记录严重错误日志"""
        try:
            full_msg = msg.format(*args)
        except:
            full_msg = msg
        self._logger.error(f"CRITICAL: {full_msg}")
        
    # 事件发布辅助方法
    def publish_log(self, event_name, msg, *args):
        """通过事件总线发布日志事件"""
        if self._event_bus:
            self._event_bus.publish(event_name, msg, *args)
        else:
            # 如果没有事件总线，直接记录
            self._handle_log(event_name, msg, *args)

# 辅助函数，方便在代码中发布日志事件
# 使用方法: log(event_bus, EVENT.LOG_INFO, "System started with config: {}", config)
def log(event_bus, event_name, msg, *args):
    """
    一个发布日志事件的辅助函数。
    :param event_bus: EventBus 实例
    :param event_name: 日志事件名称 (e.g., EVENT.LOG_INFO)
    :param msg: 日志消息，可以是格式化字符串
    :param args: 格式化字符串的参数
    """
    event_bus.publish(event_name, msg, *args)
    
# 全局日志实例 - 用于在没有事件总线的情况下直接记录
_global_logger = None

def get_global_logger():
    """获取全局日志实例"""
    global _global_logger
    if _global_logger is None:
        _global_logger = Logger()
    return _global_logger

def set_global_logger(logger):
    """设置全局日志实例"""
    global _global_logger
    _global_logger = logger
    
# 便捷的全局日志函数
def debug(msg, *args):
    """全局调试日志函数"""
    logger = get_global_logger()
    logger.debug(msg, *args)
    
def info(msg, *args):
    """全局信息日志函数"""
    logger = get_global_logger()
    logger.info(msg, *args)
    
def warning(msg, *args):
    """全局警告日志函数"""
    logger = get_global_logger()
    logger.warning(msg, *args)
    
def error(msg, *args):
    """全局错误日志函数"""
    logger = get_global_logger()
    logger.error(msg, *args)
    
def critical(msg, *args):
    """全局严重错误日志函数"""
    logger = get_global_logger()
    logger.critical(msg, *args)