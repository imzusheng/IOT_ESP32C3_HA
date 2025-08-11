# app/lib/event_bus/core.py
"""
简化的事件总线核心模块
提供基础的发布订阅功能，支持高低优先级事件处理
高优先级使用硬件定时器，低优先级使用软件轮询避免占用硬件定时器

使用方式

# 创建事件总线
event_bus = EventBus()

# 主循环
while True:
    # 处理低优先级事件（软件轮询）
    event_bus.process_events()
    
    # 其他业务逻辑
    # ...
    
    # 适当的延时
    time.sleep_ms(10)
"""

import gc
import time

# 尝试导入MicroPython的machine模块，如果失败则使用模拟模块
try:
    from machine import Timer
except ImportError:
    # 在测试环境中使用模拟的machine模块
    try:
        from ..mock_machine import Timer
    except ImportError:
        print("警告：无法导入Timer模块，某些功能可能无法正常工作")
        Timer = None

from .events_const import EVENTS
from ..logger import get_global_logger

# 配置常量 - 提取硬编码值便于维护
CONFIG = {
    'QUEUE_SIZE': 64,             # 事件队列最大大小
    'HIGH_PRIORITY_TICK_MS': 20,  # 高优先级队列处理间隔(ms)
    'THROTTLE_MS': 500,           # 事件节流时间(ms)
    'STATS_INTERVAL': 30,         # 统计信息输出间隔(秒)
    'HIGH_PRIORITY_TIMER_ID': 0,  # 高优先级硬件定时器ID
    # 注意：低优先级事件的处理频率取决于主循环中process_events()的调用频率
}

# 高优先级事件列表 - 使用硬件定时器处理
HIGH_PRIORITY_EVENTS = {
    EVENTS.SYSTEM_STATE_CHANGE,
    EVENTS.SYSTEM_ERROR,  # 合并后的系统错误事件
    EVENTS.QUEUE_FULL_WARNING,
    EVENTS.WIFI_STATE_CHANGE,
    EVENTS.MQTT_STATE_CHANGE,
    EVENTS.NTP_STATE_CHANGE,
}

# 低优先级事件列表 - 使用软件轮询处理
LOW_PRIORITY_EVENTS = {
    EVENTS.MQTT_MESSAGE,
    EVENTS.SENSOR_DATA,
}

class EventBus:
    """
    简化的事件总线实现
    支持高低优先级事件处理，高优先级使用硬件定时器，低优先级使用软件轮询
    """
    
    _instance = None  # 单例实例

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 只要_instance不为None即判断为已经初始化
        if hasattr(self, 'bus'):
            return
        
        self.bus = {}  # 事件订阅字典 {event_name: [callback1, callback2, ...]}
        
        # 高优先级队列（硬件定时器处理）
        self._high_priority_queue = []
        self._high_q_len = 0
        
        # 低优先级队列（软件轮询处理）
        self._low_priority_queue = []
        self._low_q_len = 0
        
        self._queue_size = CONFIG['QUEUE_SIZE']  # 队列最大大小
        
        # 初始化节流器
        self._throttlers = self._init_throttlers()
        
        # 启动高优先级硬件定时器处理队列
        if Timer:
            self._high_timer = Timer(CONFIG['HIGH_PRIORITY_TIMER_ID'])
            self._high_timer.init(period=CONFIG['HIGH_PRIORITY_TICK_MS'], mode=Timer.PERIODIC, 
                                 callback=self._process_high_priority_queue)
        else:
            self._high_timer = None
            print("警告：无法创建硬件定时器，高优先级事件将使用软件轮询")
        
        # 低优先级使用软件轮询，不占用硬件定时器
        # 处理频率取决于主循环中process_events()的调用频率
        
        # 统计信息相关
        self._last_stats_time = time.time()
        self._queue_full_warned = False  # 队列满警告标志

    def _init_throttlers(self):
        """初始化所有事件的节流器"""
        from ..utils.helpers import Throttle
        from .events_const import get_all_events
        throttlers = {}
        for event in get_all_events():
            throttlers[event] = Throttle(CONFIG['THROTTLE_MS'])  # 使用配置的节流时间
        return throttlers

    def _print_stats(self, _):
        """输出统计信息（不再占用定时器资源）"""
        try:
            stats = self.get_stats()
            logger = get_global_logger()
            logger.info("事件总线统计: 事件数={}, 订阅者数={}, 高优先级队列={}, 低优先级队列={}, 总队列={}/{} ({}%)", 
                       stats['total_events'], 
                       stats['total_subscribers'], 
                       stats['high_priority_queue_length'],
                       stats['low_priority_queue_length'],
                       stats['total_queue_length'], 
                       stats['queue_size'],
                       int(stats['queue_usage_ratio'] * 100),
                       module="EventBus")
        except Exception as e:
            print(f"[EventBus] 统计: 事件数={stats['total_events']}, "
                  f"订阅者数={stats['total_subscribers']}, "
                  f"高优先级队列={stats['high_priority_queue_length']}, "
                  f"低优先级队列={stats['low_priority_queue_length']}, "
                  f"总队列={stats['total_queue_length']}/{stats['queue_size']} "
                  f"({int(stats['queue_usage_ratio'] * 100)}%)")

    def subscribe(self, event_name, callback):
        """订阅事件"""
        if event_name not in self.bus:
            self.bus[event_name] = []
        if callback not in self.bus[event_name]:
            self.bus[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        """取消订阅事件"""
        if event_name in self.bus and callback in self.bus[event_name]:
            self.bus[event_name].remove(callback)
            if not self.bus[event_name]:
                del self.bus[event_name]

    def publish(self, event_name, *args, **kwargs):
        """发布事件到对应优先级队列"""
        if not self._should_publish_event(event_name):
            return False
        
        # 检查队列满警告
        self._check_queue_full_warning()
        
        # 根据事件优先级分发到不同队列
        if event_name in HIGH_PRIORITY_EVENTS:
            if self._high_q_len >= self._queue_size // 2:  # 高优先级队列占一半
                return False
            self._high_priority_queue.append((event_name, args, kwargs))
            self._high_q_len += 1
        else:
            if self._low_q_len >= self._queue_size // 2:  # 低优先级队列占一半
                return False
            self._low_priority_queue.append((event_name, args, kwargs))
            self._low_q_len += 1
        
        return True

    def _process_high_priority_queue(self, _):
        """处理高优先级事件队列（硬件定时器回调）"""
        if self._high_q_len == 0:
            return
        
        # 处理一个高优先级事件
        event_name, args, kwargs = self._high_priority_queue.pop(0)
        self._high_q_len -= 1
        
        self._execute_callbacks(event_name, args, kwargs)
        
        # 队列为空时进行垃圾回收
        if self._high_q_len == 0:
            gc.collect()
    
    def _process_low_priority_queue_software(self):
        """软件轮询处理低优先级事件队列（不占用硬件定时器）"""
        if self._low_q_len == 0:
            return
        
        # 每次调用处理一个低优先级事件
        event_name, args, kwargs = self._low_priority_queue.pop(0)
        self._low_q_len -= 1
        
        self._execute_callbacks(event_name, args, kwargs)
        
        # 队列为空时进行垃圾回收
        if self._low_q_len == 0:
            gc.collect()
    
    def _execute_callbacks(self, event_name, args, kwargs):
        """执行事件回调"""
        if event_name in self.bus:
            for callback in self.bus[event_name]:
                try:
                    callback(event_name, *args, **kwargs)
                except Exception as e:
                    try:
                        logger = get_global_logger()
                        logger.error("事件回调执行失败: {} - {}", event_name, str(e), module="EventBus")
                    except:
                        print(f"[EventBus] 错误: 事件回调执行失败: {event_name} - {e}")
                    
                    # 发布系统错误事件到高优先级队列
                    if self._high_q_len < self._queue_size // 2:
                        self._high_priority_queue.append((
                            EVENTS.SYSTEM_ERROR, 
                            (), 
                            {
                                'error_type': 'callback_error',
                                'error_context': {
                                    'error': str(e),
                                    'event': event_name,
                                    'callback': callback.__name__ if hasattr(callback, '__name__') else str(callback)
                                }
                            }
                        ))
                        self._high_q_len += 1
        
        # 检查是否需要输出统计信息（基于时间差）
        self._check_and_print_stats()
    
    def _check_and_print_stats(self):
        """检查并输出统计信息"""
        current_time = time.time()
        if current_time - self._last_stats_time >= CONFIG['STATS_INTERVAL']:
            self._last_stats_time = current_time
            self._print_stats(None)

    def _should_publish_event(self, event_name):
        """检查事件是否应该发布（未被节流）"""
        throttler = self._throttlers.get(event_name)
        if throttler:
            return throttler.should_trigger()
        return True

    def _check_queue_full_warning(self):
        """检查队列是否满并发出警告"""
        total_queue_len = self._high_q_len + self._low_q_len
        if total_queue_len >= self._queue_size and not self._queue_full_warned:
            self._queue_full_warned = True
            # 发布队列满警告事件
            self._high_priority_queue.append((EVENTS.QUEUE_FULL_WARNING, ('WARN',), {}))
            self._high_q_len += 1
            # 设置系统状态为WARN
            self._high_priority_queue.append((EVENTS.SYSTEM_STATE_CHANGE, ('WARN',), {}))
            self._high_q_len += 1
        elif total_queue_len < self._queue_size * 0.8:  # 队列使用率低于80%时重置警告
            self._queue_full_warned = False

    def process_events(self):
        """
        主循环中调用此方法来处理低优先级事件
        处理频率完全取决于主循环的调用频率
        建议在主循环中每10-50ms调用一次以获得合适的响应性
        """
        # 处理低优先级事件队列
        self._process_low_priority_queue_software()
        
        # 如果没有硬件定时器，也在这里处理高优先级事件
        if not self._high_timer:
            self._process_high_priority_queue(None)

    def list_events(self):
        """列出所有已订阅的事件"""
        return list(self.bus.keys())

    def list_subscribers(self, event_name):
        """列出指定事件的所有订阅者"""
        return self.bus.get(event_name, [])

    def has_subscribers(self, event_name):
        """检查事件是否有订阅者"""
        return event_name in self.bus and len(self.bus[event_name]) > 0

    def get_stats(self):
        """获取简化的统计信息"""
        total_queue_len = self._high_q_len + self._low_q_len
        usage_ratio = total_queue_len / self._queue_size if self._queue_size > 0 else 0
        return {
            'total_events': len(self.bus),  # 已订阅的事件数量
            'total_subscribers': sum(len(cbs) for cbs in self.bus.values()),  # 总订阅者数量
            'high_priority_queue_length': self._high_q_len,  # 高优先级队列长度
            'low_priority_queue_length': self._low_q_len,  # 低优先级队列长度
            'total_queue_length': total_queue_len,  # 总队列长度
            'queue_size': self._queue_size,  # 队列最大大小
            'queue_usage_ratio': usage_ratio,  # 队列使用率
            'using_hardware_timer': self._high_timer is not None,  # 是否使用硬件定时器
        }

    def cleanup(self):
        """清理资源"""
        if self._high_timer:
            self._high_timer.deinit()
            self._high_timer = None