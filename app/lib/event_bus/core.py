# app/lib/event_bus/core.py
"""
优化的事件总线核心模块 - 参考JavaScript任务队列设计
- 移除节流机制，简化逻辑
- 高优先级任务绝对优先，不可丢失
- 队列满时进入警告/错误模式
- 优化内存使用和性能
"""

import gc
import time

# 尝试导入MicroPython的machine模块
try:
    from machine import Timer
except ImportError:
    try:
        from ..mock_machine import Timer
    except ImportError:
        print("警告：无法导入Timer模块")
        Timer = None

from .events_const import EVENTS, is_high_priority_event
from ..logger import get_global_logger

# 配置常量 - 针对嵌入式环境优化
CONFIG = {
    'MAX_QUEUE_SIZE': 64,          # 总队列大小，降低内存占用
    'TIMER_TICK_MS': 25,           # 定时器间隔，平衡响应性和性能
    'STATS_INTERVAL': 30,          # 统计间隔设置为30秒
    'TIMER_ID': 0,
    'HIGH_PRIORITY_RATIO': 0.6,    # 高优先级队列占60%
    'BATCH_PROCESS_COUNT': 5,      # 批处理数量
    'GC_THRESHOLD': 100,           # 垃圾回收阈值
}

# 系统状态常量
SYSTEM_STATUS = {
    'NORMAL': 'normal',
    'WARNING': 'warning', 
    'CRITICAL': 'critical'
}

class EventQueue:
    """优化的事件队列 - 减少内存分配"""
    
    def __init__(self, max_size):
        # 预分配列表以减少动态分配
        self.high_priority_queue = []
        self.low_priority_queue = []
        self.max_size = max_size
        self.high_priority_limit = int(max_size * CONFIG['HIGH_PRIORITY_RATIO'])
        self.low_priority_limit = max_size - self.high_priority_limit
        
        # 性能计数器
        self._high_drops = 0
        self._low_drops = 0
    
    def enqueue(self, event_item, is_high_priority=False):
        """
        入队事件 - 高优先级绝对优先
        """
        if is_high_priority:
            if len(self.high_priority_queue) >= self.high_priority_limit:
                self._high_drops += 1
                return False  # 高优先级满了返回False，触发严重错误
            self.high_priority_queue.append(event_item)
            return True
        else:
            # 低优先级：如果队列满了，为高优先级腾出空间
            total_size = len(self.high_priority_queue) + len(self.low_priority_queue)
            if total_size >= self.max_size:
                # 删除最旧的低优先级事件为高优先级腾出空间
                if self.low_priority_queue:
                    self.low_priority_queue.pop(0)
                    self._low_drops += 1
                else:
                    # 连低优先级队列都空了，说明高优先级占满了
                    self._low_drops += 1
                    return False
            
            self.low_priority_queue.append(event_item)
            return True
    
    def dequeue(self):
        """出队 - 高优先级绝对优先"""
        if self.high_priority_queue:
            return self.high_priority_queue.pop(0)
        elif self.low_priority_queue:
            return self.low_priority_queue.pop(0)
        return None
    
    def is_empty(self):
        return len(self.high_priority_queue) == 0 and len(self.low_priority_queue) == 0
    
    def get_stats(self):
        high_len = len(self.high_priority_queue)
        low_len = len(self.low_priority_queue)
        return {
            'high_priority_length': high_len,
            'low_priority_length': low_len,
            'total_length': high_len + low_len,
            'max_size': self.max_size,
            'usage_ratio': (high_len + low_len) / self.max_size if self.max_size > 0 else 0,
            'high_drops': self._high_drops,
            'low_drops': self._low_drops,
        }
    
    def clear(self):
        """清空队列"""
        self.high_priority_queue.clear()
        self.low_priority_queue.clear()


class EventBus:
    """优化的事件总线 - 解决内存和性能问题"""
    
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 在这里进行初始化，避免_initialized冗余
            cls._instance._init_once()
        return cls._instance

    def _init_once(self):
        """单次初始化"""
        self.subscribers = {}  # {event_name: [callback1, callback2, ...]}
        self.event_queue = EventQueue(CONFIG['MAX_QUEUE_SIZE'])
        
        # 系统状态管理
        self._system_status = SYSTEM_STATUS['NORMAL']
        
        # 性能计数器
        self._processed_count = 0
        self._error_count = 0
        self._last_stats_time = time.time()
        self._last_gc_time = time.time()
        
        # 启动定时器
        self._timer = None
        self._start_timer()

    def _start_timer(self):
        """启动定时器"""
        if Timer:
            try:
                self._timer = Timer(CONFIG['TIMER_ID'])
                self._timer.init(
                    period=CONFIG['TIMER_TICK_MS'], 
                    mode=Timer.PERIODIC, 
                    callback=self._timer_callback
                )
            except Exception as e:
                print(f"[EventBus] 定时器启动失败: {e}")
                self._timer = None

    def _timer_callback(self, timer):
        """定时器回调 - 核心处理逻辑"""
        try:
            # 批量处理事件
            processed = 0
            while processed < CONFIG['BATCH_PROCESS_COUNT'] and not self.event_queue.is_empty():
                event_item = self.event_queue.dequeue()
                if event_item:
                    self._execute_event(event_item)
                    processed += 1
                    self._processed_count += 1
            
            # 定期垃圾回收
            if self._processed_count % CONFIG['GC_THRESHOLD'] == 0:
                gc.collect()
            
        except Exception as e:
            self._error_count += 1
            print(f"[EventBus] 定时器异常: {e}")
        finally:
            # 定期输出统计和状态检查 - 无论是否处理事件都执行
            # 这确保了即使没有事件时也会按时间间隔输出统计信息
            try:
                self._periodic_maintenance()
            except Exception as maintenance_error:
                print(f"[EventBus] 维护任务异常: {maintenance_error}")

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
        """处理回调错误 - 避免递归"""
        self._error_count += 1
        try:
            logger = get_global_logger()
            logger.error("回调失败: {} - {}", event_name, str(error), module="EventBus")
        except:
            print(f"[EventBus] 回调失败: {event_name} - {error}")
        
        # 只在非系统错误事件时才发布系统错误
        if event_name != EVENTS.SYSTEM_ERROR:
            error_event = (
                EVENTS.SYSTEM_ERROR,
                ('callback_error',),
                {
                    'error': str(error),
                    'event': event_name,
                    'callback_name': getattr(callback, '__name__', 'unknown')
                }
            )
            # 直接入队避免递归调用publish
            self.event_queue.enqueue(error_event, is_high_priority=True)

    def _periodic_maintenance(self):
        """定期维护任务"""
        current_time = time.time()
        
        # 检查系统状态
        self._check_system_status()
        
        # 定期输出统计
        if current_time - self._last_stats_time >= CONFIG['STATS_INTERVAL']:
            self._last_stats_time = current_time
            self._print_stats()

    def _check_system_status(self):
        """检查并更新系统状态"""
        queue_stats = self.event_queue.get_stats()
        old_status = self._system_status
        
        # 检查是否进入严重错误模式
        if queue_stats['high_drops'] > 0:
            self._system_status = SYSTEM_STATUS['CRITICAL']
            if old_status != SYSTEM_STATUS['CRITICAL']:
                self._publish_direct_system_event('critical_error', {
                    'reason': 'high_priority_queue_full',
                    'high_drops': queue_stats['high_drops']
                })
        # 检查是否进入警告模式  
        elif queue_stats['usage_ratio'] > 0.8:
            self._system_status = SYSTEM_STATUS['WARNING']
            if old_status == SYSTEM_STATUS['NORMAL']:
                self._publish_direct_system_event('warning', {
                    'reason': 'queue_usage_high',
                    'usage_ratio': queue_stats['usage_ratio']
                })
        # 恢复正常模式
        elif queue_stats['usage_ratio'] < 0.6:
            if self._system_status != SYSTEM_STATUS['NORMAL']:
                self._system_status = SYSTEM_STATUS['NORMAL']
                self._publish_direct_system_event('recovered', {'from_status': old_status})

    def _publish_direct_system_event(self, state, info):
        """直接发布系统事件，避免队列满时的递归问题"""
        event_item = (EVENTS.SYSTEM_STATE_CHANGE, (state,), info)
        # 系统状态事件强制入队
        if len(self.event_queue.high_priority_queue) < self.event_queue.high_priority_limit:
            self.event_queue.high_priority_queue.append(event_item)

    # 公共接口
    
    def subscribe(self, event_name, callback):
        """订阅事件"""
        if event_name not in self.subscribers:
            self.subscribers[event_name] = []
        if callback not in self.subscribers[event_name]:
            self.subscribers[event_name].append(callback)

    def unsubscribe(self, event_name, callback):
        """取消订阅"""
        if event_name in self.subscribers:
            try:
                self.subscribers[event_name].remove(callback)
                if not self.subscribers[event_name]:
                    del self.subscribers[event_name]
            except ValueError:
                pass  # callback不在列表中

    def publish(self, event_name, *args, **kwargs):
        """发布事件"""
        # 检查是否有订阅者
        if not self.has_subscribers(event_name):
            return True
        
        # 严重错误模式下只处理系统事件
        if (self._system_status == SYSTEM_STATUS['CRITICAL'] and 
            not is_high_priority_event(event_name)):
            return False
        
        # 入队事件
        event_item = (event_name, args, kwargs)
        is_high_priority = is_high_priority_event(event_name)
        
        success = self.event_queue.enqueue(event_item, is_high_priority)
        
        # 高优先级事件入队失败时立即进入严重错误模式
        if not success and is_high_priority:
            self._system_status = SYSTEM_STATUS['CRITICAL']
        
        return success

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
        try:
            stats = self.get_stats()
            logger = get_global_logger()
            logger.info("EventBus: 事件={}, 订阅者={}, 队列={}/{} ({}%), 已处理={}, 错误={}, 状态={}", 
                       stats['event_types'],
                       stats['total_subscribers'], 
                       stats['total_length'],
                       stats['max_size'],
                       int(stats['usage_ratio'] * 100),
                       stats['processed_count'],
                       stats['error_count'],
                       stats['system_status'],
                       module="EventBus")
        except:
            # 降级输出
            stats = self.get_stats()
            print(f"[EventBus] 队列:{stats['total_length']}/{stats['max_size']}, "
                  f"处理:{stats['processed_count']}, 状态:{stats['system_status']}")

    def cleanup(self):
        """清理资源"""
        if self._timer:
            try:
                self._timer.deinit()
            except:
                pass
            finally:
                self._timer = None
        
        self.event_queue.clear()
        self.subscribers.clear()
        
        # 重置计数器
        self._processed_count = 0
        self._error_count = 0
        self._system_status = SYSTEM_STATUS['NORMAL']

    def get_system_status(self):
        """获取当前系统状态"""
        return self._system_status

    def stop_timer(self):
        """停止事件总线定时器"""
        if self._timer:
            try:
                self._timer.deinit()
            except:
                pass
            finally:
                self._timer = None

    def start_timer(self):
        """启动事件总线定时器"""
        if not self._timer:
            self._start_timer()

# 便捷函数
def get_event_bus():
    """获取事件总线实例"""
    return EventBus()