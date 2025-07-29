# core.py
"""
核心功能模块 - 代码体积优化版本

这个模块合并了多个小模块的功能，减少文件数量和导入开销：
- 事件总线核心功能
- 基础工具函数
- 常用硬件操作
- 系统状态管理

优化策略：
1. 减少模块文件数量
2. 合并相关功能
3. 减少导入开销
4. 使用整数常量替代字符串
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
# 轻量级日志系统
# =============================================================================

class SimpleLogger:
    """简化的日志系统"""
    
    def __init__(self, max_queue_size=50):
        self.log_queue = deque((), max_queue_size)
        self.enabled = True
        
        # 订阅日志事件
        subscribe(LOG_LEVEL_CRITICAL, self._on_critical)
        subscribe(LOG_LEVEL_WARNING, self._on_warning)
        subscribe(LOG_LEVEL_INFO, self._on_info)
    
    def _on_critical(self, message="", **kwargs):
        """处理关键日志"""
        self._add_log("CRITICAL", message)
    
    def _on_warning(self, message="", **kwargs):
        """处理警告日志"""
        self._add_log("WARNING", message)
    
    def _on_info(self, message="", **kwargs):
        """处理信息日志"""
        self._add_log("INFO", message)
    
    def _add_log(self, level, message):
        """添加日志到队列"""
        if not self.enabled:
            return
        
        try:
            timestamp = time.time()
            log_entry = f"[{level}] {timestamp}: {message}"
            self.log_queue.append(log_entry)
            
            if DEBUG:
                print(log_entry)
        except Exception as e:
            if DEBUG:
                print(f"[Logger] 日志记录失败: {e}")
    
    def get_recent_logs(self, count=10):
        """获取最近的日志"""
        return list(self.log_queue)[-count:]
    
    def clear_logs(self):
        """清空日志队列"""
        self.log_queue.clear()
        gc.collect()

# 全局日志实例
_global_logger = SimpleLogger()

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
# 简化的LED控制
# =============================================================================

class SimpleLED:
    """简化的LED控制器"""
    
    def __init__(self, pin1=2, pin2=8):
        self.pin1 = pin1
        self.pin2 = pin2
        self.pwm1 = None
        self.pwm2 = None
        self.initialized = False
        
        # 订阅LED事件
        subscribe(EV_LED_SET_EFFECT, self._on_set_effect)
        subscribe(EV_LED_SET_BRIGHTNESS, self._on_set_brightness)
        subscribe(EV_LED_EMERGENCY_OFF, self._on_emergency_off)
    
    def init(self):
        """初始化LED"""
        try:
            self.pwm1 = PWM(Pin(self.pin1), freq=1000)
            self.pwm2 = PWM(Pin(self.pin2), freq=1000)
            self.pwm1.duty_u16(0)
            self.pwm2.duty_u16(0)
            self.initialized = True
            
            if DEBUG:
                print("[LED] 初始化成功")
            
            publish(get_event_id('led_initialized'), success=True)
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 初始化失败: {e}")
            publish(get_event_id('led_initialized'), success=False, error=str(e))
            return False
    
    def deinit(self):
        """关闭LED"""
        try:
            if self.pwm1:
                self.pwm1.deinit()
            if self.pwm2:
                self.pwm2.deinit()
            self.initialized = False
            
            if DEBUG:
                print("[LED] 已关闭")
            
            publish(get_event_id('led_deinitialized'))
        except Exception as e:
            if DEBUG:
                print(f"[LED] 关闭失败: {e}")
    
    def set_brightness(self, led_num=1, brightness=0):
        """设置LED亮度"""
        if not self.initialized:
            return False
        
        try:
            duty = int(brightness * 65535 / 100)  # 转换为16位PWM值
            
            if led_num == 1 and self.pwm1:
                self.pwm1.duty_u16(duty)
            elif led_num == 2 and self.pwm2:
                self.pwm2.duty_u16(duty)
            
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 设置亮度失败: {e}")
            return False
    
    def set_effect(self, effect='off'):
        """设置LED效果"""
        if not self.initialized:
            return False
        
        try:
            if effect == 'off':
                self.set_brightness(1, 0)
                self.set_brightness(2, 0)
            elif effect == 'on':
                self.set_brightness(1, 50)
                self.set_brightness(2, 50)
            elif effect == 'blink':
                # 简单的交替闪烁
                current_time = time.ticks_ms()
                if (current_time // 500) % 2:
                    self.set_brightness(1, 100)
                    self.set_brightness(2, 0)
                else:
                    self.set_brightness(1, 0)
                    self.set_brightness(2, 100)
            
            publish(get_event_id('led_effect_changed'), effect=effect)
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 设置效果失败: {e}")
            return False
    
    def _on_set_effect(self, effect='off', **kwargs):
        """处理设置效果事件"""
        self.set_effect(effect)
    
    def _on_set_brightness(self, led_num=1, brightness=0, **kwargs):
        """处理设置亮度事件"""
        self.set_brightness(led_num, brightness)
    
    def _on_emergency_off(self, **kwargs):
        """处理紧急关闭事件"""
        self.set_effect('off')
        publish(get_event_id('led_emergency_off_completed'))

# 全局LED实例
_global_led = SimpleLED()

def init_led():
    """初始化LED"""
    return _global_led.init()

def deinit_led():
    """关闭LED"""
    _global_led.deinit()

def set_led_effect(effect):
    """设置LED效果"""
    return _global_led.set_effect(effect)

def set_led_brightness(led_num, brightness):
    """设置LED亮度"""
    return _global_led.set_brightness(led_num, brightness)

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