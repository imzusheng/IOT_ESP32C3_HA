# core.py
"""
核心模块 - 事件总线

提供轻量级事件总线功能：
- 支持异步和同步事件处理
- 事件订阅和发布机制
- 错误隔离和调试支持
"""

import gc
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
from .config import DEBUG, get_event_id, LOG_LEVEL_CRITICAL, LOG_LEVEL_WARNING, LOG_LEVEL_INFO
from .utils import get_memory_info, get_system_status, format_time

try:
    from collections import defaultdict
except ImportError:
    # MicroPython fallback
    class defaultdict:
        def __init__(self, default_factory):
            self.default_factory = default_factory
            self.data = {}
        
        def __getitem__(self, key):
            if key not in self.data:
                self.data[key] = self.default_factory()
            return self.data[key]
        
        def __setitem__(self, key, value):
            self.data[key] = value
        
        def get(self, key, default=None):
            return self.data.get(key, default)
        
        def clear(self):
            self.data.clear()

# =============================================================================
# 轻量级事件总线
# =============================================================================

class EventBus:
    """轻量级事件总线 - 优化版本"""
    
    def __init__(self):
        self._subscribers = defaultdict(list)
    
    def subscribe(self, event_type, callback):
        """订阅事件"""
        if not callable(callback):
            raise ValueError("Callback must be callable")
        
        event_id = get_event_id(event_type)
        self._subscribers[event_id].append(callback)
        
        if DEBUG:
            print(f"[EventBus] 订阅事件: {event_type} (ID:{event_id})")
        
        def unsubscribe():
            if callback in self._subscribers[event_id]:
                self._subscribers[event_id].remove(callback)
                if DEBUG:
                    print(f"[EventBus] 取消订阅: {event_type} (ID:{event_id})")
        
        return unsubscribe
    
    def publish(self, event_type, **kwargs):
        """发布事件"""
        event_id = get_event_id(event_type)
        
        if event_id not in self._subscribers:
            return
        
        if DEBUG:
            print(f"[EventBus] 发布事件: {event_type} (ID:{event_id})")
        
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._notify_async(event_id, **kwargs))
        except RuntimeError:
            self._notify_sync(event_id, **kwargs)
    
    async def _notify_async(self, event_id, **kwargs):
        """异步通知订阅者"""
        for callback in self._subscribers[event_id][:]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(**kwargs)
                else:
                    callback(**kwargs)
            except Exception as e:
                if DEBUG:
                    print(f"[EventBus] 回调错误: {e}")
                if callback in self._subscribers[event_id]:
                    self._subscribers[event_id].remove(callback)
        gc.collect()
    
    def _notify_sync(self, event_id, **kwargs):
        """同步通知订阅者"""
        for callback in self._subscribers[event_id][:]:
            try:
                if not asyncio.iscoroutinefunction(callback):
                    callback(**kwargs)
            except Exception as e:
                if DEBUG:
                    print(f"[EventBus] 回调错误: {e}")
                if callback in self._subscribers[event_id]:
                    self._subscribers[event_id].remove(callback)
        gc.collect()
    
    def get_subscribers_count(self, event_type):
        """获取订阅者数量"""
        event_id = get_event_id(event_type)
        return len(self._subscribers.get(event_id, []))

# 全局事件总线实例
_global_event_bus = EventBus()

def subscribe(event_type, callback):
    """全局订阅函数"""
    return _global_event_bus.subscribe(event_type, callback)

def publish(event_type, **kwargs):
    """全局发布函数"""
    _global_event_bus.publish(event_type, **kwargs)

def get_subscribers_count(event_type):
    """获取订阅者数量"""
    return _global_event_bus.get_subscribers_count(event_type)

# =============================================================================
# 日志接口函数（委托给logger模块）
# =============================================================================

def log_critical(message):
    """记录关键日志"""
    publish(LOG_LEVEL_CRITICAL, message=message)

def log_warning(message):
    """记录警告日志"""
    publish(LOG_LEVEL_WARNING, message=message)

def log_info(message):
    """记录信息日志"""
    publish(LOG_LEVEL_INFO, message=message)



# =============================================================================
# 事件总线清理功能
# =============================================================================

def clear_all_events():
    """清理所有事件订阅"""
    global _global_event_bus
    _global_event_bus._subscribers.clear()
    if DEBUG:
        print("[CORE] 所有事件订阅已清理")



# =============================================================================
# 初始化函数
# =============================================================================

def init_system():
    """初始化系统核心组件（仅事件总线）"""
    try:
        # 清理事件总线
        clear_all_events()
        
        if DEBUG:
            print("[CORE] 事件总线初始化完成")
        
        return True
    except Exception as e:
        error_msg = f"事件总线初始化失败: {e}"
        if DEBUG:
            print(f"[CORE] [ERROR] {error_msg}")
        return False

def cleanup_system():
    """清理系统资源"""
    try:
        clear_all_events()
        if DEBUG:
            print("[CORE] 事件总线资源清理完成")
    except Exception as e:
        if DEBUG:
            print(f"[CORE] [ERROR] 事件总线清理失败: {e}")