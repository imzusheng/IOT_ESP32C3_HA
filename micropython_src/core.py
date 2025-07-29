# core.py
"""
核心事件总线模块

重构后的核心模块专注于事件总线功能：
- 轻量级事件总线实现
- 异步和同步事件处理
- 事件订阅和发布管理
- 基础工具函数

其他功能已分离到独立模块：
- 日志系统: logger.py
- LED控制: led.py
"""

import asyncio
import gc
import time
import machine
import network
from machine import Pin, PWM
from collections import defaultdict, deque
from config import (
    get_event_id, get_log_level_id, DEBUG,
    EV_WIFI_CONNECTING, EV_WIFI_CONNECTED, EV_WIFI_ERROR, EV_WIFI_TIMEOUT,
    EV_LED_SET_EFFECT, EV_LED_SET_BRIGHTNESS, EV_LED_EMERGENCY_OFF,
    LOG_LEVEL_CRITICAL, LOG_LEVEL_WARNING, LOG_LEVEL_INFO
)

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
# 基础工具函数
# =============================================================================

def get_memory_info():
    """获取内存信息"""
    try:
        import gc
        gc.collect()
        free = gc.mem_free()
        allocated = gc.mem_alloc()
        total = free + allocated
        return {
            'free': free,
            'allocated': allocated,
            'total': total,
            'percent_used': (allocated / total) * 100 if total > 0 else 0
        }
    except:
        return {'free': 0, 'allocated': 0, 'total': 0, 'percent_used': 0}

def get_system_status():
    """获取系统状态"""
    try:
        # 检查WiFi状态
        wlan = network.WLAN(network.STA_IF)
        wifi_connected = wlan.isconnected()
        
        # 获取内存信息
        mem_info = get_memory_info()
        
        # 获取温度（如果支持）
        temp = None
        try:
            import esp32
            temp = esp32.mcu_temperature()
        except:
            pass
        
        return {
            'wifi_connected': wifi_connected,
            'memory': mem_info,
            'temperature': temp,
            'timestamp': time.time()
        }
    except Exception as e:
        if DEBUG:
            print(f"[Utils] 获取系统状态失败: {e}")
        return {}

def format_time(timestamp=None):
    """格式化时间"""
    try:
        if timestamp is None:
            timestamp = time.time()
        
        local_time = time.localtime(timestamp)
        return f"{local_time[0]}-{local_time[1]:02d}-{local_time[2]:02d} {local_time[3]:02d}:{local_time[4]:02d}:{local_time[5]:02d}"
    except:
        return "时间格式化失败"

# =============================================================================
# LED接口函数（委托给led模块）
# =============================================================================

def init_led():
    """初始化LED（委托给led模块）"""
    try:
        import led
        return led.init_led()
    except ImportError:
        if DEBUG:
            print("[Core] LED模块未找到")
        return False

def deinit_led():
    """关闭LED（委托给led模块）"""
    try:
        import led
        led.deinit_led()
    except ImportError:
        pass

def set_led_effect(effect, **params):
    """设置LED效果（委托给led模块）"""
    try:
        import led
        return led.set_led_effect(effect, **params)
    except ImportError:
        return False

def set_led_brightness(led_num, brightness):
    """设置LED亮度（委托给led模块）"""
    try:
        import led
        return led.set_led_brightness(led_num, brightness)
    except ImportError:
        return False

# =============================================================================
# 兼容性函数
# =============================================================================

def init():
    """初始化事件总线（兼容性函数）"""
    if DEBUG:
        print("[Core] 事件总线已初始化")

def init_event_bus():
    """初始化事件总线"""
    init()

def init_logger():
    """初始化日志系统"""
    if DEBUG:
        print("[Core] 日志系统已初始化")

def process_log_queue():
    """处理日志队列（兼容性函数）"""
    # 简化版本，日志由事件系统自动处理
    pass

# =============================================================================
# 初始化函数
# =============================================================================

def init_core_systems():
    """初始化核心系统"""
    try:
        # 初始化LED
        init_led()
        
        if DEBUG:
            print("[Core] 核心系统初始化完成")
        
        log_info("核心系统初始化完成")
        return True
    except Exception as e:
        if DEBUG:
            print(f"[Core] 核心系统初始化失败: {e}")
        log_critical(f"核心系统初始化失败: {e}")
        return False

def cleanup_core_systems():
    """清理核心系统"""
    try:
        deinit_led()
        _global_logger.clear_logs()
        gc.collect()
        
        if DEBUG:
            print("[Core] 核心系统清理完成")
    except Exception as e:
        if DEBUG:
            print(f"[Core] 核心系统清理失败: {e}")