# app/lib/event_bus.py (MicroPython 专用版本 - 计时器队列版本)
import utime as time
from machine import Timer

class EventBus:
    """
    事件总线 (MicroPython 实机版本 - 计时器队列驱动)
    支持发布-订阅模式的异步非阻塞事件处理，替代 micropython.schedule，
    避免 queue full 问题，提升稳定性。
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(EventBus, cls).__new__(cls)
        return cls._instance

    def __init__(self, verbose=False, queue_size=64, tick_ms=10):
        if self._initialized:
            return

        self.bus = {}
        self._verbose = verbose

        # 错误处理相关
        self._error_recursion_depth = 0
        self._MAX_ERROR_RECURSION = 3

        # 事件队列（循环队列实现）
        self._queue_size = queue_size
        self._queue = [None] * queue_size
        self._q_head = 0
        self._q_tail = 0
        self._q_len = 0

        # 频率限制
        self._event_rate_limiter = {}

        # 事件优先级映射（0=最高，4=最低）
        self._event_priority = {
            'system.error': 0,
            'system.critical': 0,
            'memory.critical': 0,
            'recovery.failed': 0,
            'mqtt.disconnected': 1,
            'wifi.disconnected': 1,
            'log.error': 1,
            'system.warning': 2,
            'log.warn': 2,
            'ntp.sync.failed': 2,
            'wifi.connected': 3,
            'mqtt.connected': 3,
            'mqtt.message': 3,
            'sensor.data': 3,
            'log.info': 3,
            'time.updated': 3,
            'ntp.sync.success': 3,
            'log.debug': 4,
            'system.heartbeat': 4,
            'wifi.connecting': 4,
            'ntp.sync.started': 4,
            'sensor.data.summary': 4,
            'network.status.summary': 4
        }

        # 启动计时器轮询队列
        self._timer = Timer(-1)
        self._timer.init(period=tick_ms, mode=Timer.PERIODIC, callback=self._process_queue)

        # 队列监控
        self._queue_warning_threshold = 0.6  # 60%警告阈值
        self._queue_warning_sent = False

        self._initialized = True
        self._log("事件总线已初始化 (计时器队列模式)")

    # ------------------ 日志 ------------------
    def _log(self, msg, *args):
        if self._verbose:
            try:
                from lib.logger import get_global_logger
                logger = get_global_logger()
                logger.info(msg, *args, module="EventBus")
            except:
                pass

    # ------------------ 订阅 / 取消订阅 ------------------
    def subscribe(self, event_name, callback):
        if not callable(callback):
            self._log("订阅失败: '{}' 的回调函数不可调用。", event_name)
            return
        if event_name not in self.bus:
            self.bus[event_name] = []
        if callback not in self.bus[event_name]:
            self.bus[event_name].append(callback)
            self._log("新增事件 '{}' 的订阅者: {}", event_name, callback)

    def unsubscribe(self, event_name, callback):
        if event_name in self.bus and callback in self.bus[event_name]:
            self.bus[event_name].remove(callback)
            self._log("已取消事件 '{}' 的订阅者: {}", callback, event_name)
            if not self.bus[event_name]:
                del self.bus[event_name]

    # ------------------ 发布事件 ------------------
    def publish(self, event_name, *args, **kwargs):
        if self._is_event_rate_limited(event_name):
            return

        priority = self._event_priority.get(event_name, 3)
        if priority == 0:
            # 关键事件立即同步执行
            self._dispatch_event(event_name, args, kwargs)
        else:
            if self._q_len < self._queue_size:
                self._queue[self._q_tail] = (event_name, args, kwargs)
                self._q_tail = (self._q_tail + 1) % self._queue_size
                self._q_len += 1
                
                # 检查队列占用率
                self._check_queue_usage()
            else:
                # 队列满，尝试丢弃低优先级事件
                self._drop_low_priority_event(priority)

    def _drop_low_priority_event(self, new_priority):
        lowest_idx = -1
        lowest_priority = -1
        i = self._q_head
        for _ in range(self._q_len):
            ev_name, _, _ = self._queue[i]
            p = self._event_priority.get(ev_name, 3)
            if p > lowest_priority:
                lowest_priority = p
                lowest_idx = i
            i = (i + 1) % self._queue_size

        if lowest_priority > new_priority and lowest_idx >= 0:
            self._queue[lowest_idx] = None
            self._q_len -= 1
        else:
            # 新事件优先级不够高，直接丢弃
            pass

    # ------------------ 计时器处理队列 ------------------
    def _process_queue(self, _):
        if self._q_len == 0:
            return
        event = self._queue[self._q_head]
        self._queue[self._q_head] = None
        self._q_head = (self._q_head + 1) % self._queue_size
        self._q_len -= 1
        if event:
            event_name, args, kwargs = event
            self._dispatch_event(event_name, args, kwargs)

    # ------------------ 队列监控 ------------------
    def _check_queue_usage(self):
        """检查队列使用率，在达到阈值时发出警告"""
        usage_ratio = self._q_len / self._queue_size
        
        if usage_ratio >= self._queue_warning_threshold and not self._queue_warning_sent:
            # 直接输出警告到控制台
            print(f"[EventBus] 警告: 事件队列使用率达到{usage_ratio:.1%} ({self._q_len}/{self._queue_size})")
            
            # 同时记录到日志
            self._log("事件队列使用率达到{:.1%} ({}/{})", usage_ratio, self._q_len, self._queue_size)
            
            self._queue_warning_sent = True
        elif usage_ratio < self._queue_warning_threshold * 0.8:  # 降到48%以下才重置
            self._queue_warning_sent = False

    # ------------------ 执行回调 ------------------
    def _dispatch_event(self, event_name, args, kwargs):
        if event_name in self.bus:
            for callback in self.bus[event_name][:]:
                try:
                    self._invoke_callback_compat(callback, event_name, args, kwargs)
                except Exception as e:
                    self._handle_callback_error(event_name, callback, e)
        else:
            self._log("发布事件 '{}'，但无订阅者。", event_name)

    def _invoke_callback_compat(self, callback, event_name, args, kwargs):
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
        callback()

    def _handle_callback_error(self, event_name, callback, error):
        if event_name != "system.error":
            if self._error_recursion_depth < self._MAX_ERROR_RECURSION:
                self._error_recursion_depth += 1
                try:
                    callback_name = self._get_callback_name(callback)
                    error_context = {
                        "source": "event_bus",
                        "event": event_name,
                        "callback_name": callback_name,
                        "error_type": "event_callback",
                        "error_message": str(error),
                        "recursion_depth": self._error_recursion_depth
                    }
                    self.publish("system.error", error_context=error_context)
                except:
                    pass
                finally:
                    self._error_recursion_depth -= 1
        else:
            self._error_recursion_depth = 0

    # ------------------ 频率限制 ------------------
    def _is_event_rate_limited(self, event_name):
        now = time.ticks_ms()
        rate_limited_events = {
            'log.info': 500,
            'log.warn': 300,
            'log.error': 100,
            'system.error': 1000,
            'wifi.connecting': 2000,
            'wifi.disconnected': 1000,
            'ntp.sync.started': 5000,
            'mqtt.disconnected': 1000,
            'mqtt.connected': 2000,
            'sensor.data': 1000,
            'system.heartbeat': 5000,
            'time.updated': 2000,
        }
        if event_name in rate_limited_events:
            min_interval = rate_limited_events[event_name]
            last_time = self._event_rate_limiter.get(event_name, 0)
            if time.ticks_diff(now, last_time) < min_interval:
                return True
            self._event_rate_limiter[event_name] = now
        return False

    # ------------------ 内省 / 调试 ------------------
    def list_events(self):
        return list(self.bus.keys())

    def list_subscribers(self, event_name):
        subscribers = self.bus.get(event_name, [])
        return [str(cb) for cb in subscribers]

    def has_subscribers(self, event_name):
        return event_name in self.bus and len(self.bus[event_name]) > 0

    def get_stats(self):
        usage_ratio = self._q_len / self._queue_size if self._queue_size > 0 else 0
        return {
            'total_events': len(self.bus),
            'total_subscribers': sum(len(cbs) for cbs in self.bus.values()),
            'queue_length': self._q_len,
            'queue_size': self._queue_size,
            'queue_usage_ratio': usage_ratio,
            'queue_warning_threshold': self._queue_warning_threshold,
            'queue_warning_sent': self._queue_warning_sent,
            'error_recursion_depth': self._error_recursion_depth
        }

    def _get_callback_name(self, callback):
        try:
            if hasattr(callback, '__name__'):
                name = callback.__name__
                if name == '<lambda>':
                    return f"lambda_function_at_{id(callback)}"
                elif name.startswith('<') and name.endswith('>'):
                    return f"anonymous_function_{id(callback)}"
                else:
                    return name
            elif hasattr(callback, '__class__'):
                return f"{callback.__class__.__name__}_instance_{id(callback)}"
            else:
                return f"callable_object_{id(callback)}"
        except:
            return f"unknown_callback_{id(callback)}"