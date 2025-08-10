# app/lib/event_bus.py (MicroPython 专用版本)
import micropython as _micropython
import utime as time

# 使用 MicroPython 的调度接口
_schedule = _micropython.schedule
_queue_full_check = False  # 目前不提供查询队列状态的能力

class EventBus:
    """
    事件总线 (MicroPython 实机版本)
    
    一个异步非阻塞的事件总线，支持发布-订阅模式的模块间通信。
    是事件驱动架构的核心组件，提供松耦合通信机制。
    
    特性:
    - 异步非阻塞事件处理 (使用 micropython.schedule)
    - 增强的错误处理和报告
    - 内省与调试工具
    - 单例模式，内存友好
    - 调度队列溢出防护（队列满时降级为同步执行）
    - 事件优先级支持
    - 增大的调度队列容量
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
        self._schedule_errors = 0        # 调度错误计数
        self._max_schedule_errors = 10   # 最大调度错误次数
        self._event_rate_limiter = {}    # 事件频率限制器
        self._event_priority = {         # 事件优先级映射
            'system.error': 0,           # 最高优先级
            'system.critical': 0,
            'memory.critical': 0,
            'log.error': 1,              # 高优先级
            'log.warn': 2,
            'system.warning': 2,
            'log.info': 3,               # 中优先级
            'system.ready': 3,
            'wifi.connected': 3,
            'mqtt.connected': 3,
            'log.debug': 4,              # 低优先级
            'system.heartbeat': 4
        }
        self._initialized = True
        if self._verbose:
            # 使用全局logger如果可用
            try:
                from lib.logger import get_global_logger
                logger = get_global_logger()
                logger.info("EventBus initialized", module="EventBus")
            except:
                pass

    def _log(self, msg, *args):
        if self._verbose:
            # 使用全局logger如果可用
            try:
                from lib.logger import get_global_logger
                logger = get_global_logger()
                logger.info(msg, *args, module="EventBus")
            except:
                # EventBus 初始化失败时不做任何输出
                pass

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

    def _is_event_rate_limited(self, event_name):
        """检查事件是否被频率限制"""
        now = time.ticks_ms()
        
        # 某些事件需要频率限制防止调度队列溢出（可按需扩展）
        rate_limited_events = {
            'log.info': 500,       # 日志事件最小间隔500ms
            'log.warn': 300,       # 警告日志最小间隔300ms
            'log.error': 100,      # 错误日志最小间隔100ms
            'system.error': 1000,  # 系统错误事件最小间隔1秒
            'wifi.connecting': 2000,   # WiFi连接状态最小间隔2秒
            'ntp.sync.started': 5000,  # NTP同步开始最小间隔5秒
        }
        
        if event_name in rate_limited_events:
            min_interval = rate_limited_events[event_name]
            last_time = self._event_rate_limiter.get(event_name, 0)
            
            if time.ticks_diff(now, last_time) < min_interval:
                return True  # 被限制
            
            self._event_rate_limiter[event_name] = now
        
        return False

    def publish(self, event_name, *args, **kwargs):
        """
        异步发布一个事件。回调将被调度执行，而不是立即执行。
        :param event_name: 事件名称
        :param args: 传递给回调的位置参数
        :param kwargs: 传递给回调的关键字参数
        """
        # 事件频率限制
        if self._is_event_rate_limited(event_name):
            return  # 静默丢弃被限制的事件
        
        if event_name in self.bus:
            self._log("Publishing event '{}' to {} subscribers", event_name, len(self.bus[event_name]))
            # 根据优先级排序订阅者（如果有优先级设置）
            subscribers = self.bus[event_name][:]
            
            # 如果调度错误过多，切换为同步调用模式
            if self._schedule_errors > self._max_schedule_errors:
                for callback in subscribers:
                    try:
                        self._execute_callback_sync(callback, event_name, args, kwargs)
                    except Exception as e:
                        self._handle_callback_error(event_name, callback, e)
            else:
                # 对于高优先级事件，使用更积极的调度策略
                priority = self._event_priority.get(event_name, 3)  # 默认中等优先级
                for callback in subscribers:
                    try:
                        if priority <= 1:  # 高优先级事件立即执行
                            self._execute_callback_sync(callback, event_name, args, kwargs)
                        else:
                            self._execute_callback_async(callback, event_name, args, kwargs)
                    except Exception as e:
                        self._handle_callback_error(event_name, callback, e)
        else:
            self._log("Published event '{}' but no subscribers.", event_name)

    def _execute_callback_sync(self, callback, event_name, args, kwargs):
        """同步执行回调（当调度队列有问题时的降级方案）"""
        try:
            self._invoke_callback_compat(callback, event_name, args, kwargs)
        except Exception as e:
            self._handle_callback_error(event_name, callback, e)

    def _execute_callback_async(self, callback, event_name, args, kwargs):
        """异步执行回调（正常情况）"""
        def scheduled_wrapper(_):
            try:
                self._invoke_callback_compat(callback, event_name, args, kwargs)
            except Exception as e:
                self._handle_callback_error(event_name, callback, e)
        
        # 尝试调度执行
        try:
            _schedule(scheduled_wrapper, None)
        except Exception as schedule_error:
            # 调度失败（如队列满），记录错误并降级为同步执行
            self._schedule_errors += 1
            error_msg = f"Schedule queue full for event '{event_name}', falling back to sync execution"
            if "queue full" in str(schedule_error).lower():
                try:
                    from lib.logger import get_global_logger
                    logger = get_global_logger()
                    logger.warning(error_msg, module="EventBus")
                except:
                    # 静默处理调度错误
                    pass
            else:
                error_msg = f"Schedule error for event '{event_name}': {schedule_error}"
                try:
                    from lib.logger import get_global_logger
                    logger = get_global_logger()
                    logger.error(error_msg, module="EventBus")
                except:
                    # 静默处理调度错误
                    pass
            
            # 降级为同步执行（为实机可靠性保留）
            self._execute_callback_sync(callback, event_name, args, kwargs)

    def _invoke_callback_compat(self, callback, event_name, args, kwargs):
        """兼容性调用回调函数（针对订阅者签名差异的适配，非桌面兼容）"""
        # 兼容性调用链：逐步放宽参数，优先保留 evt_name，其次去掉不被支持的关键字参数
        try:
            callback(event_name, *args, **kwargs)
            return
        except TypeError:
            pass
        try:
            callback(event_name, *args)
            return
        except TypeError:
            pass
        try:
            callback(*args, **kwargs)
            return
        except TypeError:
            pass
        try:
            callback(*args)
            return
        except TypeError:
            pass
        # 最后降级为无参调用，避免彻底失败
        callback()

    def _handle_callback_error(self, event_name, callback, error):
        """处理回调函数执行错误"""
        error_msg = f"Error in callback for '{event_name}': {error}"
        # 静默处理回调错误，避免无限循环
        # 发生异常时，发布一个系统错误事件（但要避免无限循环）
        if event_name != "system.error":  # 避免无限循环
            # 检查错误递归深度
            if self._error_recursion_depth < self._MAX_ERROR_RECURSION:
                # 获取回调函数的描述性名称
                callback_name = self._get_callback_name(callback)
                # 提供更完整的错误上下文信息
                error_context = {
                    "source": "event_bus",
                    "event": event_name,
                    "callback_name": callback_name,
                    "error_type": "event_callback",
                    "error_message": str(error),
                    "recursion_depth": self._error_recursion_depth + 1
                }
                # 增加递归深度计数器
                self._error_recursion_depth += 1
                try:
                    self.publish("system.error", error_context=error_context)
                except Exception as publish_error:
                    # 如果 publish 方法本身失败，记录错误但继续执行
                    # 静默处理发布错误
                    pass
                finally:
                    # 减少递归深度计数器
                    self._error_recursion_depth -= 1
            else:
                # 静默处理递归深度错误
                  pass
        else:
            # 处理 system.error 事件本身的错误
            if self._error_recursion_depth == 0:
                # 静默处理系统错误处理器错误
                # 重置递归深度，防止系统完全卡死
                self._error_recursion_depth = 0

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
        
    def get_stats(self):
        """获取事件总线统计信息"""
        return {
            'total_events': len(self.bus),
            'total_subscribers': sum(len(callbacks) for callbacks in self.bus.values()),
            'schedule_errors': self._schedule_errors,
            'error_recursion_depth': self._error_recursion_depth
        }
        
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