"""
事件总线模块
提供发布-订阅模式的异步非阻塞事件处理
"""

import gc
import time

from lib.logger import debug, info, warning, error


# 简单的安全日志装饰器
def safe_log(level="error"):
    """装饰器：包装目标函数, 自动捕获并安全记录异常"""

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


# 配置类 - 集中化配置管理
class EventBusConfig:
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



# 优先从集中管理的模块导入常量, 以实现统一管理
from .evnets_const import SYSTEM_STATUS, EVENTS



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

    def _handle_processing_error(self, error):
        """处理事件处理错误"""
        self._error_count += 1
        error_msg = str(error)
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

    def _handle_callback_error(self, event_name, callback, error):
        """处理回调错误"""
        self._error_count += 1
        error("回调失败: {} - {}", event_name, str(error), module="EventBus")

        # 发布系统错误事件
        if event_name != EVENTS["SYSTEM_STATE_CHANGE"]:
            error_event = (
                EVENTS["SYSTEM_STATE_CHANGE"],
                ("callback_error",),
                {
                    "error": str(error),
                    "event": event_name,
                    "callback_name": getattr(callback, "__name__", "unknown"),
                },
            )
            # 直接入队避免递归调用publish
            self.event_queue.enqueue(error_event)

    @safe_log("error")
    def _periodic_maintenance(self):
        """定期维护任务"""
        current_time = time.time()

        # 检查系统状态
        self._check_system_status()

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
                        "reason": "queue_usage_high",
                        "usage_ratio": queue_stats["usage_ratio"],
                    },
                )
        # 恢复正常模式
        elif self._system_status != SYSTEM_STATUS["NORMAL"]:
            self._system_status = SYSTEM_STATUS["NORMAL"]
            self._publish_direct_system_event(
                "recovered", {"from_status": old_status}
            )

    def _publish_direct_system_event(self, state, info):
        """直接发布系统事件"""
        event_item = (self.EVENTS["SYSTEM_STATE_CHANGE"], (state,), info)
        # 系统状态事件直接入队
        self.event_queue.enqueue(event_item)

    # 公共接口

    @safe_log("error")
    def subscribe(self, event_name, callback):
        """订阅事件"""
        if event_name not in self.subscribers:
            self.subscribers[event_name] = []
        if callback not in self.subscribers[event_name]:
            self.subscribers[event_name].append(callback)
            debug(
                "订阅事件: {} -> {}个回调",
                event_name,
                len(self.subscribers[event_name]),
                module="EventBus",
            )

    def unsubscribe(self, event_name, callback):
        """取消订阅"""
        if event_name in self.subscribers:
            try:
                self.subscribers[event_name].remove(callback)
                if not self.subscribers[event_name]:
                    del self.subscribers[event_name]
            except ValueError:
                pass  # callback不在列表中

    @safe_log("error")
    def publish(self, event_name, *args, **kwargs):
        """发布事件"""
        if not self.has_subscribers(event_name):
            # 移除无订阅者时的调试日志, 降低日志IO
            return True

        event_item = (event_name, args, kwargs)
        success = self.event_queue.enqueue(event_item)
        if not success:
            error("事件入队失败: {}", event_name, module="EventBus")
        return success

    def has_subscribers(self, event_name):
        """检查是否有订阅者"""
        return event_name in self.subscribers and len(self.subscribers[event_name]) > 0

    def get_stats(self):
        """获取统计信息"""
        queue_stats = self.event_queue.get_stats()
        stats = {
            "event_types": len(self.subscribers),
            "total_subscribers": sum(len(cbs) for cbs in self.subscribers.values()),
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "system_status": self._system_status,
        }
        # 合并队列统计信息
        stats.update(queue_stats)
        return stats

    def _print_stats(self):
        """输出统计信息"""
        stats = self.get_stats()
        info(
            "EventBus: 事件={}, 订阅者={}, 队列={}/{} ({}%), 已处理={}, 错误={}, 状态={}",
            stats["event_types"],
            stats["total_subscribers"],
            stats["total_length"],
            stats["max_size"],
            int(stats["usage_ratio"] * 100),
            stats["processed_count"],
            stats["error_count"],
            stats["system_status"],
            module="EventBus",
        )

    @safe_log("error")
    def cleanup(self):
        """清理资源"""
        self.event_queue.clear()
        self.subscribers.clear()

        # 重置计数器和状态
        self._processed_count = 0
        self._error_count = 0
        self._system_status = SYSTEM_STATUS["NORMAL"]

    def get_system_status(self):
        """获取当前系统状态"""
        return self._system_status
