# app/lib/event_bus.py
# uPy-compatible reimplementation of https://github.com/rgilsenan/micropython-event-bus

class EventBus:
    """
    事件总线
    
    一个简单的同步事件总线，支持发布-订阅模式的模块间通信。
    是事件驱动架构的核心组件，提供松耦合的通信机制。
    
    特性:
    - 同步事件处理
    - 错误隔离和恢复
    - 支持任意参数传递
    - 订阅者管理
    - 详细的日志记录
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    def __init__(self, verbose=False):
        if self._initialized:
            return
            
        self.bus = {}
        self._verbose = verbose
        self._initialized = True

    def _log(self, msg, *args):
        if self._verbose:
            print(("[EventBus] " + msg).format(*args))

    def subscribe(self, event_name, callback):
        """
        订阅一个事件。
        :param event_name: 事件名称
        :param callback: 事件触发时调用的函数
        """
        if event_name not in self.bus:
            self.bus[event_name] = []
        
        if callback not in self.bus[event_name]:
            self.bus[event_name].append(callback)
            self._log("New subscription for event '{}': {}", event_name, callback)
        else:
            self._log("Callback {} already subscribed to event '{}'", callback, event_name)


    def unsubscribe(self, event_name, callback):
        """
        取消订阅一个事件。
        :param event_name: 事件名称
        :param callback: 要移除的回调函数
        """
        if event_name in self.bus and callback in self.bus[event_name]:
            self.bus[event_name].remove(callback)
            self._log("Unsubscribed {} from event '{}'", callback, event_name)
            if not self.bus[event_name]:
                del self.bus[event_name]
                self._log("Removed event '{}' as it has no subscribers", event_name)

    def publish(self, event_name, *args, **kwargs):
        """
        发布一个事件。
        :param event_name: 事件名称
        :param args: 传递给回调的位置参数
        :param kwargs: 传递给回调的关键字参数
        """
        if event_name in self.bus:
            self._log("Publishing event '{}' to {} subscribers", event_name, len(self.bus[event_name]))
            # 使用副本以允许在回调中修改原始订阅列表
            for callback in self.bus[event_name][:]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error in event bus callback for event '{event_name}': {e}")
                    # 在实际应用中，这里应该发布一个 SYSTEM_ERROR 事件
        else:
            self._log("Published event '{}' but no subscribers", event_name)

# 全局单例
# event_bus = EventBus()