# event_bus.py
"""
事件总线模块 - 实现发布/订阅模式的核心基础设施

这个模块提供了一个轻量级的事件总线系统，用于实现模块间的解耦通信。
通过事件发布和订阅机制，各个模块可以独立工作，只通过事件进行交互。

主要功能：
1. 事件订阅：允许模块订阅感兴趣的事件类型
2. 事件发布：允许模块发布事件，通知所有订阅者
3. 异步处理：支持异步回调函数的执行
4. 错误隔离：单个回调函数的错误不会影响其他订阅者

支持的事件类型：
- 'wifi_connected': WiFi连接成功事件
- 'wifi_disconnected': WiFi断开连接事件
- 'ntp_synced': NTP时间同步成功事件
- 'temperature_overheat': 温度过热事件
- 'enter_safe_mode': 进入安全模式事件
- 'exit_safe_mode': 退出安全模式事件
- 'log_critical': 关键错误日志事件
- 'log_info': 信息日志事件
- 'log_warning': 警告日志事件
"""

try:
    import uasyncio as asyncio
except ImportError:
    # 在标准Python环境中使用asyncio
    import asyncio

class EventBus:
    """
    事件总线类 - 实现发布/订阅模式
    
    这个类管理事件的订阅和发布，支持异步回调函数的执行。
    每个事件类型可以有多个订阅者，发布事件时会通知所有订阅者。
    """
    
    def __init__(self):
        """
        初始化事件总线
        
        _subscribers: 存储事件订阅者的字典
        格式: {event_type: [callback1, callback2, ...]}
        """
        self._subscribers = {}
    
    def subscribe(self, event_type, callback):
        """
        订阅指定类型的事件
        
        Args:
            event_type (str): 事件类型名称
            callback (callable): 事件发生时要调用的回调函数
                               可以是同步函数或异步函数
        
        Example:
            event_bus.subscribe('wifi_connected', on_wifi_connected)
            event_bus.subscribe('temperature_overheat', on_overheat)
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            print(f"[EventBus] 已订阅事件: {event_type}")
        else:
            print(f"[EventBus] [WARNING] 重复订阅事件: {event_type}")
    
    def unsubscribe(self, event_type, callback):
        """
        取消订阅指定类型的事件
        
        Args:
            event_type (str): 事件类型名称
            callback (callable): 要取消的回调函数
        """
        if event_type in self._subscribers:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                print(f"[EventBus] 已取消订阅事件: {event_type}")
                
                # 如果没有订阅者了，删除该事件类型
                if not self._subscribers[event_type]:
                    del self._subscribers[event_type]
    
    def publish(self, event_type, **kwargs):
        """
        发布事件，通知所有订阅者
        
        Args:
            event_type (str): 事件类型名称
            **kwargs: 事件参数，会传递给所有回调函数
        
        Example:
            event_bus.publish('wifi_connected', ip_address='192.168.1.100')
            event_bus.publish('temperature_overheat', temperature=65.5)
        """
        if event_type not in self._subscribers:
            # 没有订阅者，静默忽略
            return
        
        print(f"[EventBus] 发布事件: {event_type}")
        
        # 尝试创建异步任务，如果没有事件循环则同步执行
        try:
            # 检查是否有运行中的事件循环
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._notify_subscribers(event_type, **kwargs))
        except RuntimeError:
            # 没有运行中的事件循环，同步执行回调
            self._notify_subscribers_sync(event_type, **kwargs)
    
    async def _notify_subscribers(self, event_type, **kwargs):
        """
        异步通知所有订阅者
        
        这个方法确保即使某个回调函数出错，也不会影响其他订阅者。
        支持同步和异步回调函数。
        
        Args:
            event_type (str): 事件类型名称
            **kwargs: 事件参数
        """
        subscribers = self._subscribers.get(event_type, [])
        
        for callback in subscribers:
            try:
                # 检查是否是异步函数
                if asyncio.iscoroutinefunction(callback):
                    await callback(**kwargs)
                else:
                    callback(**kwargs)
            except Exception as e:
                print(f"[EventBus] [ERROR] 事件回调执行失败: {event_type}, 错误: {e}")
                # 继续执行其他回调，不让单个错误影响整个系统
    
    def _notify_subscribers_sync(self, event_type, **kwargs):
        """
        同步通知所有订阅者
        
        这个方法用于没有事件循环的环境中，只支持同步回调函数。
        
        Args:
            event_type (str): 事件类型名称
            **kwargs: 事件参数
        """
        subscribers = self._subscribers.get(event_type, [])
        
        for callback in subscribers:
            try:
                # 只执行同步回调函数
                if not asyncio.iscoroutinefunction(callback):
                    callback(**kwargs)
                else:
                    print(f"[EventBus] [WARNING] 跳过异步回调函数: {callback.__name__}")
            except Exception as e:
                print(f"[EventBus] [ERROR] 事件回调执行失败: {event_type}, 错误: {e}")
                # 继续执行其他回调，不让单个错误影响整个系统
    
    def get_subscribers_count(self, event_type):
        """
        获取指定事件类型的订阅者数量
        
        Args:
            event_type (str): 事件类型名称
        
        Returns:
            int: 订阅者数量
        """
        return len(self._subscribers.get(event_type, []))
    
    def list_event_types(self):
        """
        列出所有已订阅的事件类型
        
        Returns:
            list: 事件类型列表
        """
        return list(self._subscribers.keys())
    
    def clear_all_subscribers(self):
        """
        清除所有订阅者（主要用于测试或重置）
        """
        self._subscribers.clear()
        print("[EventBus] 已清除所有订阅者")

# 全局事件总线实例
# 这是整个系统的事件通信中心
_global_event_bus = EventBus()

# 导出的公共接口函数
def subscribe(event_type, callback):
    """
    订阅事件的便捷函数
    
    Args:
        event_type (str): 事件类型
        callback (callable): 回调函数
    """
    _global_event_bus.subscribe(event_type, callback)

def unsubscribe(event_type, callback):
    """
    取消订阅事件的便捷函数
    
    Args:
        event_type (str): 事件类型
        callback (callable): 回调函数
    """
    _global_event_bus.unsubscribe(event_type, callback)

def publish(event_type, **kwargs):
    """
    发布事件的便捷函数
    
    Args:
        event_type (str): 事件类型
        **kwargs: 事件参数
    """
    _global_event_bus.publish(event_type, **kwargs)

def get_subscribers_count(event_type):
    """
    获取订阅者数量的便捷函数
    
    Args:
        event_type (str): 事件类型
    
    Returns:
        int: 订阅者数量
    """
    return _global_event_bus.get_subscribers_count(event_type)

def list_event_types():
    """
    列出所有事件类型的便捷函数
    
    Returns:
        list: 事件类型列表
    """
    return _global_event_bus.list_event_types()

def get_event_bus():
    """
    获取全局事件总线实例（用于高级操作）
    
    Returns:
        EventBus: 全局事件总线实例
    """
    return _global_event_bus