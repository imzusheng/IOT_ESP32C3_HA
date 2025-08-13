"""
事件总线模块
提供发布-订阅模式的异步非阻塞事件处理
"""

import gc
import time

from lib.logger import safe_log, _log
from machine import Timer

# 配置类 - 集中化配置管理
class EventBusConfig:
    TIMER_ID = 0
    MAX_QUEUE_SIZE = 64          # 总队列大小, 降低内存占用
    TIMER_TICK_MS = 25           # 定时器间隔, 平衡响应性和性能
    STATS_INTERVAL = 30          # 统计间隔设置为30秒
    BATCH_PROCESS_COUNT = 5      # 批处理数量
    GC_THRESHOLD = 100           # 垃圾回收阈值
    
    # 错误累积与断路器配置
    ERROR_THRESHOLD = 10         # 错误阈值
    RECOVERY_TIME = 60           # 恢复时间(秒)
    
    @classmethod
    def get_dict(cls):
        """获取配置字典格式（向后兼容）"""
        return {
            'TIMER_ID': cls.TIMER_ID,
            'MAX_QUEUE_SIZE': cls.MAX_QUEUE_SIZE,
            'TIMER_TICK_MS': cls.TIMER_TICK_MS,
            'STATS_INTERVAL': cls.STATS_INTERVAL,
            'BATCH_PROCESS_COUNT': cls.BATCH_PROCESS_COUNT,
            'GC_THRESHOLD': cls.GC_THRESHOLD,
        }

# 系统状态常量
SYSTEM_STATUS = {
    'NORMAL': 'normal',
    'WARNING': 'warning', 
    'CRITICAL': 'critical'
}

# 事件常量模块
EVENTS = {
    # WiFi 网络状态变化事件
    'WIFI_STATE_CHANGE': "wifi.state_change",  # data: (state, info) state可以是: scanning, connecting, connected, disconnected
    
    # MQTT 状态变化事件
    'MQTT_STATE_CHANGE': "mqtt.state_change",  # data: (state, info) state可以是: connected, disconnected
    
    # 系统状态变化事件
    'SYSTEM_STATE_CHANGE': "system.state_change",  # data: (state, info) state可以是: 1.init, 2.running, 3.error, 4.shutdown
    
    # 系统错误事件
    'SYSTEM_ERROR': "system.error",  # data: (error_type, error_info) 系统错误事件
    
    # NTP 时间同步状态变化事件
    'NTP_STATE_CHANGE': "ntp.state_change",  # data: (state, info) state可以是: success, failed, syncing
}

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
            'total_length': len(self.queue),
            'max_size': self.max_size,
            'usage_ratio': len(self.queue) / self.max_size if self.max_size > 0 else 0,
            'drops': self._drops,
        }
    
    def clear(self):
        """清空队列"""
        self.queue.clear()


class EventBus:
    """简化的事件总线 - 单队列模式与错误断路器"""
    
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
        self._system_status = SYSTEM_STATUS['NORMAL']
        
        # 性能计数器
        self._processed_count = 0
        self._error_count = 0
        self._last_stats_time = time.time()
        
        # 错误累积与断路器
        self._consecutive_errors = 0
        self._circuit_breaker_open = False
        self._last_error_time = 0
        
        # 启动定时器
        self._timer = None
        self._start_timer()

    @safe_log('error')
    def _start_timer(self):
        """启动定时器"""
        if Timer:
            try:
                self._timer = Timer(EventBusConfig.TIMER_ID)
                self._timer.init(
                    period=EventBusConfig.TIMER_TICK_MS, 
                    mode=Timer.PERIODIC, 
                    callback=self._timer_callback
                )
                _log('info', "EventBus定时器已启动 - 周期={}ms", EventBusConfig.TIMER_TICK_MS, module="EventBus")
            except Exception as e:
                _log('error', "定时器启动失败: {}", str(e), module="EventBus")
                self._timer = None
        else:
            _log('warning', "Timer模块不可用, EventBus将无法自动处理事件", module="EventBus")

    @safe_log('error')
    def _timer_callback(self, timer):
        """定时器回调 - 核心处理逻辑"""
        # 检查断路器状态
        if self._circuit_breaker_open:
            current_time = time.time()
            if current_time - self._last_error_time > EventBusConfig.RECOVERY_TIME:
                self._circuit_breaker_open = False
                self._consecutive_errors = 0
                _log('info', "断路器已恢复, 重新开始处理事件", module="EventBus")
            else:
                return  # 断路器开启, 跳过处理
        
        try:
            # 批量处理事件
            processed = 0
            while processed < EventBusConfig.BATCH_PROCESS_COUNT and not self.event_queue.is_empty():
                event_item = self.event_queue.dequeue()
                if event_item:
                    self._execute_event(event_item)
                    processed += 1
                    self._processed_count += 1
            
            # 定期垃圾回收
            if self._processed_count % EventBusConfig.GC_THRESHOLD == 0:
                gc.collect()
            
            # 处理成功, 重置连续错误计数
            self._consecutive_errors = 0
            
        except Exception as e:
            self._handle_timer_error(e)
        finally:
            # 定期维护任务
             self._periodic_maintenance()

    def _handle_timer_error(self, error):
        """处理定时器错误和断路器逻辑"""
        self._error_count += 1
        self._consecutive_errors += 1
        self._last_error_time = time.time()
        
        _log('error', "定时器处理异常: {}", str(error), module="EventBus")
        
        # 检查是否需要开启断路器
        if self._consecutive_errors >= EventBusConfig.ERROR_THRESHOLD:
            self._circuit_breaker_open = True
            _log('warning', "连续错误达到阈值({}), 断路器已开启", EventBusConfig.ERROR_THRESHOLD, module="EventBus")

    @safe_log('error')
    def _execute_event(self, event_item):
        """执行事件"""
        event_name, args, kwargs = event_item
        
        if event_name not in self.subscribers:
            return
        
        # 复制订阅者列表避免迭代时修改
        callbacks = self.subscribers[event_name][:]
        
        for callback in callbacks:
            try:
                callback(event_name, *args, **kwargs)
            except Exception as e:
                self._handle_callback_error(event_name, callback, e)

    def _handle_callback_error(self, event_name, callback, error):
        """处理回调错误"""
        self._error_count += 1
        _log('error', "回调失败: {} - {}", event_name, str(error), module="EventBus")
        
        # 发布系统错误事件
        if event_name != EVENTS.SYSTEM_STATE_CHANGE:
            error_event = (
                EVENTS.SYSTEM_STATE_CHANGE,
                ('callback_error',),
                {
                    'error': str(error),
                    'event': event_name,
                    'callback_name': getattr(callback, '__name__', 'unknown')
                }
            )
            # 直接入队避免递归调用publish
            self.event_queue.enqueue(error_event)

    @safe_log('error')
    def _periodic_maintenance(self):
        """定期维护任务"""
        current_time = time.time()
        
        # 检查系统状态
        self._check_system_status()
        
        # 定期输出统计
        if current_time - self._last_stats_time >= EventBusConfig.STATS_INTERVAL:
            self._last_stats_time = current_time
            self._print_stats()

    def _check_system_status(self):
        """检查并更新系统状态"""
        queue_stats = self.event_queue.get_stats()
        old_status = self._system_status
        
        # 检查断路器状态
        if self._circuit_breaker_open:
            self._system_status = SYSTEM_STATUS['CRITICAL']
        # 检查队列使用率
        elif queue_stats['usage_ratio'] > 0.8:
            self._system_status = SYSTEM_STATUS['WARNING']
            if old_status == SYSTEM_STATUS['NORMAL']:
                self._publish_direct_system_event('warning', {
                    'reason': 'queue_usage_high',
                    'usage_ratio': queue_stats['usage_ratio']
                })
        # 恢复正常模式
        elif queue_stats['usage_ratio'] < 0.6 and not self._circuit_breaker_open:
            if self._system_status != SYSTEM_STATUS['NORMAL']:
                self._system_status = SYSTEM_STATUS['NORMAL']
                self._publish_direct_system_event('recovered', {'from_status': old_status})

    def _publish_direct_system_event(self, state, info):
        """直接发布系统事件"""
        event_item = (EVENTS['SYSTEM_STATE_CHANGE'], (state,), info)
        # 系统状态事件直接入队
        self.event_queue.enqueue(event_item)

    # 公共接口
    
    @safe_log('error')
    def subscribe(self, event_name, callback):
        """订阅事件"""
        if event_name not in self.subscribers:
            self.subscribers[event_name] = []
        if callback not in self.subscribers[event_name]:
            self.subscribers[event_name].append(callback)
            _log('info', "订阅事件: {} -> {}个回调", event_name, len(self.subscribers[event_name]), module="EventBus")

    def unsubscribe(self, event_name, callback):
        """取消订阅"""
        if event_name in self.subscribers:
            try:
                self.subscribers[event_name].remove(callback)
                if not self.subscribers[event_name]:
                    del self.subscribers[event_name]
            except ValueError:
                pass  # callback不在列表中

    @safe_log('error')
    def publish(self, event_name, *args, **kwargs):
        """发布事件"""
        # 检查是否有订阅者
        if not self.has_subscribers(event_name):
            return True
        
        # 断路器开启时拒绝新事件
        if self._circuit_breaker_open:
            _log('warning', "断路器开启, 丢弃事件: {}", event_name, module="EventBus")
            return False
        
        # 入队事件
        event_item = (event_name, args, kwargs)
        return self.event_queue.enqueue(event_item)

    def has_subscribers(self, event_name):
        """检查是否有订阅者"""
        return event_name in self.subscribers and len(self.subscribers[event_name]) > 0

    def get_stats(self):
        """获取统计信息"""
        queue_stats = self.event_queue.get_stats()
        stats = {
            'event_types': len(self.subscribers),
            'total_subscribers': sum(len(cbs) for cbs in self.subscribers.values()),
            'processed_count': self._processed_count,
            'error_count': self._error_count,
            'system_status': self._system_status,
            'timer_active': self._timer is not None,
        }
        # 合并队列统计信息
        stats.update(queue_stats)
        return stats

    def _print_stats(self):
        """输出统计信息"""
        stats = self.get_stats()
        _log('info', "EventBus: 事件={}, 订阅者={}, 队列={}/{} ({}%), 已处理={}, 错误={}, 状态={}, 断路器={}", 
             stats['event_types'],
             stats['total_subscribers'], 
             stats['total_length'],
             stats['max_size'],
             int(stats['usage_ratio'] * 100),
             stats['processed_count'],
             stats['error_count'],
             stats['system_status'],
             '开启' if self._circuit_breaker_open else '关闭',
             module="EventBus")

    @safe_log('error')
    def cleanup(self):
        """清理资源"""
        if self._timer:
            try:
                self._timer.deinit()
            except:
                pass
            finally:
                self._timer = None
                _log('info', "EventBus定时器已停止", module="EventBus")
        
        self.event_queue.clear()
        self.subscribers.clear()
        
        # 重置计数器和状态
        self._processed_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        self._circuit_breaker_open = False
        self._system_status = SYSTEM_STATUS['NORMAL']

    def get_system_status(self):
        """获取当前系统状态"""
        return self._system_status

    @safe_log('error')
    def stop_timer(self):
        """停止事件总线定时器"""
        if self._timer:
            try:
                self._timer.deinit()
            except:
                pass
            finally:
                self._timer = None
                _log('info', "EventBus定时器已停止", module="EventBus")

    @safe_log('error')
    def start_timer(self):
        """启动事件总线定时器"""
        if not self._timer:
            self._start_timer()