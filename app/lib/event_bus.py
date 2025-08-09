# app/lib/event_bus.py (优化后版本)
try:
    import micropython as _micropython
    _schedule = _micropython.schedule
except Exception:
    # 提供在桌面 Python 环境下的降级实现，使测试可运行
    def _schedule(cb, arg):
        # 直接同步调用以保证语义正确（测试中有 sleep，不影响）
        cb(arg)

class EventBus:
    """
    事件总线 (优化版本)
    
    一个异步非阻塞的事件总线，支持发布-订阅模式的模块间通信。
    是事件驱动架构的核心组件，提供松耦合通信机制。
    
    特性:
    - 异步非阻塞事件处理 (使用 micropython.schedule)
    - 增强的错误处理和报告
    - 内省与调试工具
    - 单例模式，内存友好
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
        self._error_recursion_depth = 0  # 初始化错误递归深度
        self._MAX_ERROR_RECURSION = 3    # 最大错误递归深度
        self._initialized = True
        if self._verbose:
            print("[EventBus] Initialized.")

    def _log(self, msg, *args):
        if self._verbose:
            print(("[EventBus] " + msg).format(*args))

    def subscribe(self, event_name, callback):
        """
        订阅一个事件。
        :param event_name: 事件名称
        :param callback: 事件触发时调用的函数
        """
        if not callable(callback):
            self._log("Subscription failed: callback for '{}' is not callable.", event_name)
            return

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
                self._log("Event '{}' removed as it has no subscribers.", event_name)

    def publish(self, event_name, *args, **kwargs):
        """
        异步发布一个事件。回调将被调度执行，而不是立即执行。
        :param event_name: 事件名称
        :param args: 传递给回调的位置参数
        :param kwargs: 传递给回调的关键字参数
        """
        if event_name in self.bus:
            self._log("Publishing event '{}' to {} subscribers", event_name, len(self.bus[event_name]))
            # 使用副本以允许在回调中安全地修改原始订阅列表
            for callback in self.bus[event_name][:]:
                try:
                    # 将实际的调用封装在一个函数中，以便 schedule 能正确处理
                    def scheduled_call(cb, a, kw, evt_name):
                        try:
                            # 优先使用新签名：callback(event_name, *args, **kwargs)
                            cb(evt_name, *a, **kw)
                        except TypeError as e1:
                            # 回退到旧签名：callback(*args, **kwargs)
                            try:
                                cb(*a, **kw)
                            except TypeError as e2:
                                # 最后尝试无参调用：callback()
                                try:
                                    cb()
                                except Exception as e:
                                    # 仍失败则进入统一错误处理
                                    raise e
                        except Exception as e:
                            # 非签名问题的异常，直接进入统一错误处理
                            raise e
                    
                    def handle_error(evt_name, cb, err):
                        print(f"Error in scheduled callback for '{evt_name}': {err}")
                        # 发生异常时，发布一个系统错误事件
                        if evt_name != "system.error":  # 避免无限循环
                            # 检查错误递归深度
                            if self._error_recursion_depth < self._MAX_ERROR_RECURSION:
                                # 获取回调函数的描述性名称
                                callback_name = self._get_callback_name(cb)
                                # 提供更完整的错误上下文信息
                                error_context = {
                                    "source": "event_bus",
                                    "event": evt_name,
                                    "callback_name": callback_name,
                                    "error_type": "event_callback",
                                    "error_message": str(err),
                                    "recursion_depth": self._error_recursion_depth + 1
                                }
                                # 增加递归深度计数器
                                self._error_recursion_depth += 1
                                try:
                                    self.publish("system.error", error_context=error_context)
                                except Exception as publish_error:
                                    # 如果 publish 方法本身失败，记录错误但继续执行
                                    print(f"[EventBus] Failed to publish system.error event: {publish_error}")
                                finally:
                                    # 减少递归深度计数器
                                    self._error_recursion_depth -= 1
                            else:
                                print(f"[EventBus] Maximum error recursion depth reached. Stopping error propagation for event '{evt_name}'")
                        else:
                            # 处理 system.error 事件本身的错误
                            if self._error_recursion_depth == 0:
                                print(f"[EventBus] Critical: Error in system.error handler: {err}")
                                # 重置递归深度，防止系统完全卡死
                                self._error_recursion_depth = 0

                    # 修复 lambda 函数变量捕获问题，通过默认参数捕获当前值
                    _schedule(lambda _, cb=callback, a=args, kw=kwargs, evt_name=event_name:
                              (scheduled_call(cb, a, kw, evt_name)), None)
                except Exception as e:
                    # 调度本身失败（例如队列满）或 scheduled_call 抛出的异常
                    handle_error(event_name, callback, e)
        else:
            self._log("Published event '{}' but no subscribers.", event_name)
            
    # --- 内省与调试工具 ---
    def list_events(self):
        """返回所有已注册的事件名称列表。"""
        return list(self.bus.keys())

    def list_subscribers(self, event_name):
        """返回指定事件的所有订阅者回调函数列表。"""
        subscribers = self.bus.get(event_name, [])
        return [str(cb) for cb in subscribers]  # 返回字符串表示，更安全

    def has_subscribers(self, event_name):
        """检查是否有订阅者订阅了指定事件。"""
        return event_name in self.bus and len(self.bus[event_name]) > 0
        
    def _get_callback_name(self, callback):
        """
        获取回调函数的描述性名称。
        对于 lambda 函数或匿名函数，提供更有意义的标识。
        
        :param callback: 回调函数
        :return: 描述性的回调函数名称
        """
        try:
            # 尝试获取函数名称
            if hasattr(callback, '__name__'):
                name = callback.__name__
                # 如果是 lambda 函数，提供更有意义的标识
                if name == '<lambda>':
                    return f"lambda_function_at_{id(callback)}"
                # 如果是匿名函数或特殊名称
                elif name.startswith('<') and name.endswith('>'):
                    return f"anonymous_function_{id(callback)}"
                else:
                    return name
            # 如果是可调用对象但没有 __name__ 属性
            elif hasattr(callback, '__class__'):
                return f"{callback.__class__.__name__}_instance_{id(callback)}"
            else:
                return f"callable_object_{id(callback)}"
        except Exception:
            # 如果获取名称时出错，返回通用标识
            return f"unknown_callback_{id(callback)}"