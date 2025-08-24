"""
事件总线模块
提供发布-订阅模式的异步非阻塞事件处理

注意:
- 本文件已合并原 lock/evnets_const.py 的常量定义, 统一在此处集中管理
- 文件由 lock/event_bus.py 移动并重命名为 lib/event_bus_lock.py
"""

import gc
try:
    import utime as time
except Exception:
    import time

from lib.logger import debug, info, warning, error


# 简单的安全日志装饰器
def safe_log(level="error"):
    """装饰器: 包装目标函数, 自动捕获并安全记录异常"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if level == "error":
                    error("函数{}异常: {}", func.__name__, str(e), module="EventBus")
                elif level == "warning":
                    warning("函数{}异常: {}", func.__name__, str(e), module="EventBus")
                elif level == "info":
                    info("函数{}异常: {}", func.__name__, str(e), module="EventBus")
                else:
                    debug("函数{}异常: {}", func.__name__, str(e), module="EventBus")
                return None

        return wrapper

    return decorator


# ================= 合并: 事件常量集中管理 =================
# 系统状态常量
SYSTEM_STATUS = {
    "NORMAL": "normal",
    "WARNING": "warning",
    "CRITICAL": "critical",
}

# 事件常量
EVENTS = {
    # WiFi 网络状态变化事件
    "WIFI_STATE_CHANGE": "wifi.state_change",  # data: (state, info) e.g., scanning, connecting, connected, disconnected
    # MQTT 状态变化事件
    "MQTT_STATE_CHANGE": "mqtt.state_change",  # data: (state, info) e.g., connected, disconnected
    # MQTT 消息事件
    "MQTT_MESSAGE": "mqtt.message",  # data: (topic, message)
    # 系统状态变化事件
    "SYSTEM_STATE_CHANGE": "system.state_change",  # data: (state, info) e.g., 1.init, 2.running, 3.error, 4.shutdown
    # 系统错误事件
    "SYSTEM_ERROR": "system.error",  # data: (error_type, error_info)
    # NTP 时间同步状态变化事件
    "NTP_STATE_CHANGE": "ntp.state_change",  # data: (state, info) e.g., success, failed, syncing
    # 传感器数据事件
    "SENSOR_DATA": "sensor.data",  # data: (sensor_id, value)
}
# ======================================================


class EventQueue:
    """简化的事件队列 - 单队列模式"""

    def __init__(self, max_size):
        self.queue = []
        self.max_size = max_size
        self._drops = 0

    def enqueue(self, event_item):
        """入队事件"""
        if len(self.queue) >= self.max_size:
            # 队列满时删除最旧的事件
            self.queue.pop(0)
            self._drops += 1

        self.queue.append(event_item)
        return True

    def dequeue(self):
        """出队事件"""
        if self.queue:
            return self.queue.pop(0)
        return None

    def is_empty(self):
        return len(self.queue) == 0

    def get_stats(self):
        return {
            "total_length": len(self.queue),
            "max_size": self.max_size,
            "usage_ratio": len(self.queue) / self.max_size if self.max_size > 0 else 0,
            "drops": self._drops,
        }

    def clear(self):
        """清空队列"""
        self.queue.clear()


class EventBusConfig:
    """事件总线配置"""
    TIMER_TICK_MS = 25  # 定时器间隔, 平衡响应性和性能
    MAX_QUEUE_SIZE = 64  # 总队列大小, 降低内存占用
    BATCH_PROCESS_COUNT = 5  # 批处理数量
    GC_THRESHOLD = 100  # 垃圾回收阈值

    @classmethod
    def get_dict(cls):
        """获取配置字典格式(向后兼容)"""
        return {
            "MAX_QUEUE_SIZE": cls.MAX_QUEUE_SIZE,
            "TIMER_TICK_MS": cls.TIMER_TICK_MS,
            "BATCH_PROCESS_COUNT": cls.BATCH_PROCESS_COUNT,
            "GC_THRESHOLD": cls.GC_THRESHOLD,
        }


class EventBus:
    """简化的事件总线 - 单队列模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """改进的单例初始化"""
        if not EventBus._initialized:
            self._init_once()
            EventBus._initialized = True

    def _init_once(self):
        """单次初始化"""
        self.subscribers = {}  # {event_name: [callback1, callback2, ...]}
        self.event_queue = EventQueue(EventBusConfig.MAX_QUEUE_SIZE)

        # 系统状态管理
        self._system_status = SYSTEM_STATUS["NORMAL"]

        # 性能计数器
        self._processed_count = 0
        self._error_count = 0

        # 保存EVENTS引用到实例, 避免NameError
        self.EVENTS = EVENTS

        # 手动处理时间记录
        self._last_process_time = 0

    def process_events(self):
        """手动处理事件 - 由主循环调用"""
        # 检查是否到了处理时间
        current_time = time.ticks_ms()
        if self._last_process_time == 0:
            self._last_process_time = current_time

        if (
            time.ticks_diff(current_time, self._last_process_time)
            < EventBusConfig.TIMER_TICK_MS
        ):
            return  # 未到处理时间

        self._last_process_time = current_time

        try:
            # 批量处理事件
            processed = 0
            while (
                processed < EventBusConfig.BATCH_PROCESS_COUNT
                and not self.event_queue.is_empty()
            ):
                event_item = self.event_queue.dequeue()
                if event_item:
                    self._execute_event(event_item)
                    processed += 1
                    self._processed_count += 1

            # 定期垃圾回收
            if self._processed_count % EventBusConfig.GC_THRESHOLD == 0:
                gc.collect()

        except Exception as e:
            self._handle_processing_error(e)
        finally:
            # 轻量维护: 仅更新系统状态
            self._check_system_status()

    def _handle_processing_error(self, exc):
        """处理事件处理错误"""
        self._error_count += 1
        error_msg = str(exc)
        error("事件处理异常: {}", error_msg, module="EventBus")
        # 最小化副作用: 仅入队一个系统状态提示, 避免递归引用未定义变量
        try:
            evt = (self.EVENTS["SYSTEM_STATE_CHANGE"], ("processing_error",), {"error": error_msg})
            self.event_queue.enqueue(evt)
        except Exception:
            # 忽略二次错误, 避免形成异常风暴
            pass

        # 系统错误事件发布由 _handle_callback_error 负责, 此处不再重复

    @safe_log("error")
    def _execute_event(self, event_item):
        """执行事件"""
        event_name, args, kwargs = event_item

        # 减少热路径日志, 降低串口IO与CPU占用
        if event_name not in self.subscribers:
            warning("事件 {} 没有订阅者", event_name, module="EventBus")
            return

        callbacks = self.subscribers[event_name][:]
        for callback in callbacks:
            try:
                callback(event_name, *args, **kwargs)
            except Exception as e:
                self._handle_callback_error(event_name, callback, e)

    def _handle_callback_error(self, event_name, callback, exc):
        """处理回调错误"""
        self._error_count += 1
        error("回调失败: {} - {}", event_name, str(exc), module="EventBus")

        # 发布系统错误事件
        if event_name != EVENTS["SYSTEM_STATE_CHANGE"]:
            error_event = (
                EVENTS["SYSTEM_STATE_CHANGE"],
                ("callback_error",),
                {
                    "error": str(exc),
                    "event": event_name,
                    "callback_name": getattr(callback, "__name__", "unknown"),
                },
            )
            # 直接入队避免递归调用publish
            self.event_queue.enqueue(error_event)

    def _check_system_status(self):
        """检查并更新系统状态"""
        queue_stats = self.event_queue.get_stats()
        old_status = self._system_status

        # 检查队列使用率
        if queue_stats["usage_ratio"] > 0.8:
            self._system_status = SYSTEM_STATUS["WARNING"]
            if old_status == SYSTEM_STATUS["NORMAL"]:
                self._publish_direct_system_event(
                    "warning",
                    {
                        # 简化信息载荷, 避免过多日志
                        "queue_usage": queue_stats["usage_ratio"],
                        "drops": queue_stats["drops"],
                    },
                )
        elif queue_stats["usage_ratio"] < 0.3 and old_status != SYSTEM_STATUS["NORMAL"]:
            self._system_status = SYSTEM_STATUS["NORMAL"]
            self._publish_direct_system_event(
                "normal",
                {
                    "queue_usage": queue_stats["usage_ratio"],
                },
            )

    def _publish_direct_system_event(self, state, info):
        """直接入队系统事件, 避免递归发布"""
        try:
            evt = (EVENTS["SYSTEM_STATE_CHANGE"], (state,), info or {})
            self.event_queue.enqueue(evt)
        except Exception as e:
            warning("系统事件入队失败: {}", str(e), module="EventBus")

    @safe_log("error")
    def subscribe(self, event_name, callback):
        if event_name not in self.subscribers:
            self.subscribers[event_name] = []
        self.subscribers[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        if event_name in self.subscribers and callback in self.subscribers[event_name]:
            self.subscribers[event_name].remove(callback)

    @safe_log("error")
    def publish(self, event_name, *args, **kwargs):
        # 松耦合: 仅入队, 由 process_events 批处理
        self.event_queue.enqueue((event_name, args, kwargs))

    def has_subscribers(self, event_name):
        return event_name in self.subscribers and len(self.subscribers[event_name]) > 0

    def get_stats(self):
        return {
            "processed": self._processed_count,
            "errors": self._error_count,
            "queue": self.event_queue.get_stats(),
        }

    def _print_stats(self):
        stats = self.get_stats()
        debug("EventBus统计: {}", stats, module="EventBus")

    @safe_log("error")
    def cleanup(self):
        # 清理资源
        self.subscribers.clear()
        self.event_queue.clear()

    def get_system_status(self):
        return self._system_status
