# app/lib/logger.py
import utime as time
from app.event_const import EVENT

class Logger:
    """
    日志系统 (重构版本)
    
    一个简单的、基于事件总线的日志记录器。
    它订阅日志事件并将其打印到控制台。
    是事件驱动架构的日志管理组件。
    
    特性:
    - 事件驱动日志记录
    - 多级别日志支持 (DEBUG, INFO, WARN, ERROR)
    - 内存优化设计
    - 时间戳格式化
    - 统一的接口
    - MQTT集成支持
    - 错误隔离处理
    """
    def __init__(self, level=EVENT.LOG_INFO):
        self._level_map = {
            EVENT.LOG_DEBUG: 0,
            EVENT.LOG_INFO: 1,
            EVENT.LOG_WARN: 2,
            EVENT.LOG_ERROR: 3,
        }
        self._level = self._level_map.get(level, 1)
        self._log_format = "[{time_str}] [{level_str}] {msg}"
        if hasattr(EVENT, 'LOG_DEBUG'):
            self._log_format = "[{time_str}] [{level_str}] {msg}"
        else:
            self._log_format = "[{level_str}] {msg}"


    def setup(self, event_bus):
        """
        在事件总线上注册日志处理器。
        :param event_bus: EventBus 的实例
        """
        # 订阅所有日志事件
        if hasattr(EVENT, 'LOG_DEBUG'):
            event_bus.subscribe(EVENT.LOG_DEBUG, self._handle_log)
        event_bus.subscribe(EVENT.LOG_INFO, self._handle_log)
        event_bus.subscribe(EVENT.LOG_WARN, self._handle_log)
        event_bus.subscribe(EVENT.LOG_ERROR, self._handle_log)
        print("Logger setup complete. Subscribed to log events.")

    def set_level(self, new_level):
        """
        设置新的日志记录级别。
        :param new_level: 来自 EVENT 的日志级别常量
        """
        self._level = self._level_map.get(new_level, 1)

    def _handle_log(self, event_name, msg, *args):
        """
        处理接收到的日志事件。
        """
        log_level = self._level_map.get(event_name)
        if log_level is None or log_level < self._level:
            return

        level_str = event_name.split('.')[-1].upper()
        
        try:
            full_msg = msg.format(*args)
        except:
            full_msg = msg

        if hasattr(EVENT, 'LOG_DEBUG'):
            time_str = str(time.ticks_ms())
            print(self._log_format.format(time_str=time_str, level_str=level_str, msg=full_msg))
        else:
            print(self._log_format.format(level_str=level_str, msg=full_msg))

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