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

# 内存优化：预分配常用的小对象
_EMPTY_DICT = {}
_EMPTY_LIST = []
# =============================================================================
# 轻量级事件总线
# =============================================================================

class EventBus:
    """轻量级事件总线 - 精简版本"""
    
    def __init__(self, config_getter=None, debug=False):
        # 使用简单字典替代defaultdict，减少内存占用
        self._subscribers = {}
        self.config_getter = config_getter
        self.debug = debug
        
        # 如果没有提供config_getter，尝试导入默认配置
        if self.config_getter is None:
            try:
                from .config import get_event_id, DEBUG
                self.get_event_id = get_event_id
                self.debug = DEBUG
            except ImportError:
                # 提供默认的get_event_id实现
                self.get_event_id = lambda x: x
                self.debug = debug
        else:
            self.get_event_id = getattr(config_getter, 'get_event_id', lambda x: x)
            self.debug = getattr(config_getter, 'DEBUG', debug)
    
    def subscribe(self, event_type, callback):
        """订阅事件"""
        if not callable(callback):
            raise ValueError("Callback must be callable")
        
        event_id = self.get_event_id(event_type)
        
        # 如果事件ID不存在，创建订阅者列表
        if event_id not in self._subscribers:
            self._subscribers[event_id] = []
        
        self._subscribers[event_id].append(callback)
        
        if self.debug:
            print(f"[EventBus] 订阅事件: {event_type} (ID:{event_id})")
        
        def unsubscribe():
            if event_id in self._subscribers and callback in self._subscribers[event_id]:
                self._subscribers[event_id].remove(callback)
                if self.debug:
                    print(f"[EventBus] 取消订阅: {event_type} (ID:{event_id})")
        
        return unsubscribe
    
    def publish(self, event_type, **kwargs):
        """发布事件 - 精简版本，减少异步任务创建"""
        event_id = self.get_event_id(event_type)
        
        if event_id not in self._subscribers:
            return
        
        if self.debug:
            print(f"[EventBus] 发布事件: {event_type} (ID:{event_id})")
        
        # 简化为同步调用，减少异步任务开销
        self._notify_sync(event_id, **kwargs)
    
    def _notify_sync(self, event_id, **kwargs):
        """同步通知订阅者 - 精简版本"""
        if event_id not in self._subscribers:
            return
            
        subscribers = self._subscribers[event_id]
        if not subscribers:
            return
            
        # 直接遍历，减少副本创建
        failed_callbacks = []
        
        for callback in subscribers:
            try:
                # 只处理同步回调，避免异步检查开销
                if not asyncio.iscoroutinefunction(callback):
                    callback(**kwargs)
            except Exception as e:
                if self.debug:
                    print(f"[EventBus] 回调错误: {e}")
                failed_callbacks.append(callback)
        
        # 批量移除失败的回调
        if failed_callbacks:
            for callback in failed_callbacks:
                if callback in subscribers:
                    subscribers.remove(callback)
        
        # 定期垃圾回收
        gc.collect()
    
    def get_subscribers_count(self, event_type):
        """获取订阅者数量"""
        event_id = self.get_event_id(event_type)
        return len(self._subscribers.get(event_id, []))
    
    def clear_event_subscribers(self, event_type):
        """清除特定事件的订阅者"""
        event_id = self.get_event_id(event_type)
        if event_id in self._subscribers:
            del self._subscribers[event_id]
            if self.debug:
                print(f"[EventBus] 清除事件订阅者: {event_type} (ID:{event_id})")
    
    def get_memory_usage(self):
        """获取事件总线内存使用情况"""
        return {
            'total_events': len(self._subscribers),
            'total_subscribers': sum(len(subs) for subs in self._subscribers.values())
        }

# 全局事件总线实例（延迟初始化）
_global_event_bus = None

def _ensure_global_event_bus():
    """确保全局事件总线已初始化"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus

def subscribe(event_type, callback):
    """全局订阅函数"""
    return _ensure_global_event_bus().subscribe(event_type, callback)

def publish(event_type, **kwargs):
    """全局发布函数"""
    _ensure_global_event_bus().publish(event_type, **kwargs)

def get_subscribers_count(event_type):
    """获取订阅者数量"""
    return _ensure_global_event_bus().get_subscribers_count(event_type)

def create_event_bus(config_getter=None, debug=False):
    """创建事件总线实例（依赖注入工厂函数）"""
    return EventBus(config_getter=config_getter, debug=debug)

# =============================================================================
# 日志接口函数（委托给logger模块） - [FIX] 移除以下所有函数
# =============================================================================

# def log_critical(message): ...
# def log_warning(message): ...
# def log_info(message): ...



# =============================================================================
# 事件总线清理功能
# =============================================================================

def clear_all_events():
    """清理所有事件订阅"""
    global _global_event_bus
    if _global_event_bus is not None:
        _global_event_bus._subscribers.clear()
        try:
            from .config import DEBUG
            debug = DEBUG
        except ImportError:
            debug = False
        if debug:
            print("[CORE] 所有事件订阅已清理")



# =============================================================================
# 初始化函数
# =============================================================================

def init_system():
    """初始化系统核心组件（仅事件总线）"""
    try:
        # 清理事件总线
        clear_all_events()
        
        try:
            from .config import DEBUG
            debug = DEBUG
        except ImportError:
            debug = False
            
        if debug:
            print("[CORE] 事件总线初始化完成")
        
        return True
    except Exception as e:
        error_msg = f"事件总线初始化失败: {e}"
        try:
            from .config import DEBUG
            debug = DEBUG
        except ImportError:
            debug = False
        if debug:
            print(f"[CORE] [ERROR] {error_msg}")
        return False

def cleanup_system():
    """清理系统资源"""
    try:
        clear_all_events()
        try:
            from .config import DEBUG
            debug = DEBUG
        except ImportError:
            debug = False
        if debug:
            print("[CORE] 事件总线资源清理完成")
    except Exception as e:
        try:
            from .config import DEBUG
            debug = DEBUG
        except ImportError:
            debug = False
        if debug:
            print(f"[CORE] [ERROR] 事件总线清理失败: {e}")
