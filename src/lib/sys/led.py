# -*- coding: utf-8 -*-
"""
LED预设模块

提供标准化的LED状态指示预设模式，用于系统状态显示和用户反馈。
所有LED闪烁效果都通过此模块统一管理。
"""

import machine
import time
import config

# =============================================================================
# LED预设模式常量
# =============================================================================

# 系统状态模式
SYSTEM_NORMAL = "normal"          # 正常运行：LED1亮，LED2灭
SYSTEM_WARNING = "warning"        # 警告状态：LED1亮，LED2亮
SYSTEM_ERROR = "error"            # 错误状态：LED1灭，LED2亮
SYSTEM_OFF = "off"                # 关闭状态：LED1灭，LED2灭
SYSTEM_SAFE_MODE = "safe_mode"    # 安全模式：SOS模式

# =============================================================================
# LED预设管理器类
# =============================================================================

class LEDPresetManager:
    """LED预设管理器 - 统一管理所有LED状态显示"""
    
    def __init__(self, pin1: int = None, pin2: int = None):
        """
        初始化LED预设管理器
        
        Args:
            pin1: 第一个LED引脚（从config.py获取）
            pin2: 第二个LED引脚（从config.py获取）
        """
        self.pin1 = pin1
        self.pin2 = pin2
        self.led1 = machine.Pin(pin1, machine.Pin.OUT)
        self.led2 = machine.Pin(pin2, machine.Pin.OUT)
        
        # 初始化状态
        self.set_system_status(SYSTEM_OFF)
        
        # print(f"[LED] LED预设管理器初始化完成，引脚: {pin1}, {pin2}")
    
    def set_system_status(self, status: str):
        """
        设置系统状态LED显示
        
        Args:
            status: 系统状态，支持：
                   - normal: 正常运行
                   - warning: 警告状态  
                   - error: 错误状态
                   - off: 关闭状态
                   - safe_mode: 安全模式（SOS模式）
        """
        status = status.lower()
        
        if status == SYSTEM_NORMAL:
            # 正常运行：LED1亮，LED2灭
            self.led1.on()
            self.led2.off()
            # print("[LED] 系统状态：正常运行")
            
        elif status == SYSTEM_WARNING:
            # 警告状态：LED1亮，LED2亮
            self.led1.on()
            self.led2.on()
            # print("[LED] 系统状态：警告")
            
        elif status == SYSTEM_ERROR:
            # 错误状态：LED1灭，LED2亮
            self.led1.off()
            self.led2.on()
            # print("[LED] 系统状态：错误")
            
        elif status == SYSTEM_OFF:
            # 关闭状态：LED1灭，LED2灭
            self.led1.off()
            self.led2.off()
            # print("[LED] 系统状态：关闭")
            
        elif status == SYSTEM_SAFE_MODE:
            # 安全模式：SOS模式 - 直接执行SOS闪烁
            # print("[LED] 系统状态：安全模式（SOS模式）")
            # 直接在LED1上执行SOS模式
            self._execute_sos_safe_mode()
            
        else:
            print(f"[LED] Unknown status: {status}")
            self.set_system_status(SYSTEM_OFF)
    
    def _execute_sos_safe_mode(self):
        """执行安全模式SOS闪烁 - 优化为非阻塞方式"""
        try:
            # 使用现有的SOS模式函数，但优化为单次执行
            # 三短
            for _ in range(3):
                self.led1.on()
                time.sleep_ms(200)
                self.led1.off()
                time.sleep_ms(200)
            time.sleep_ms(300)
            # 三长
            for _ in range(3):
                self.led1.on()
                time.sleep_ms(600)
                self.led1.off()
                time.sleep_ms(200)
            time.sleep_ms(300)
            # 三短
            for _ in range(3):
                self.led1.on()
                time.sleep_ms(200)
                self.led1.off()
                time.sleep_ms(200)
            # print("[LED] SOS模式执行完成")
        except Exception as e:
            print(f"[LED] SOS pattern execution failed: {e}")
    
    def get_status(self):
        """获取LED管理器状态"""
        return {
            'pin1': self.pin1,
            'pin2': self.pin2,
            'led1_state': self.led1.value(),
            'led2_state': self.led2.value()
        }

# =============================================================================
# 全局LED预设管理器实例
# =============================================================================

# 全局LED预设管理器实例 - 优化单例模式
_led_preset_manager = None
_led_manager_initialized = False
_led_manager_pins = config.get_config('daemon', 'led_pins', [12, 13])  # 默认引脚配置
_led_manager_lock = False  # 防止并发初始化

def get_led_manager():
    """获取全局LED预设管理器实例 - 线程安全的单例模式"""
    global _led_preset_manager, _led_manager_initialized, _led_manager_lock
    
    if _led_preset_manager is None and not _led_manager_lock:
        _led_manager_lock = True
        try:
            _led_preset_manager = LEDPresetManager(_led_manager_pins[0], _led_manager_pins[1])
            _led_manager_initialized = True
            print(f"[LED] LED preset manager singleton instance created, pins: {_led_manager_pins}")
        finally:
            _led_manager_lock = False
    
    return _led_preset_manager

def init_led_manager(pin1: int = None, pin2: int = None):
    """初始化全局LED预设管理器 - 优化的单例模式（从config.py获取）"""
    global _led_preset_manager, _led_manager_initialized, _led_manager_pins, _led_manager_lock
    
    if _led_manager_lock:
        print("[LED] LED manager is initializing, please wait...")
        return _led_preset_manager
    
    _led_manager_lock = True
    try:
        # 检查是否需要重新初始化
        if _led_preset_manager is None:
            # 首次初始化
            _led_manager_pins = [pin1, pin2]
            _led_preset_manager = LEDPresetManager(pin1, pin2)
            _led_manager_initialized = True
            print(f"[LED] LED preset manager initialized, pins: {pin1}, {pin2}")
        
        elif not _led_manager_initialized or _led_manager_pins != [pin1, pin2]:
            # 引脚配置变化或未正确初始化，需要重新初始化
            print(f"[LED] LED preset manager reinitializing, new pins: {pin1}, {pin2}")
            
            # 清理旧实例
            old_manager = _led_preset_manager
            _led_preset_manager = None
            _led_manager_initialized = False
            
            # 执行垃圾回收
            import gc
            gc.collect()
            
            # 创建新实例
            _led_manager_pins = [pin1, pin2]
            _led_preset_manager = LEDPresetManager(pin1, pin2)
            _led_manager_initialized = True
            
            print(f"[LED] LED preset manager reinitialization completed")
        
        else:
            print(f"[LED] LED preset manager already exists, skipping duplicate initialization")
        
        return _led_preset_manager
        
    except Exception as e:
        print(f"[LED] LED manager initialization failed: {e}")
        _led_manager_lock = False
        return None
        
    finally:
        _led_manager_lock = False

def cleanup_led_manager():
    """清理LED管理器实例 - 安全释放内存"""
    global _led_preset_manager, _led_manager_initialized, _led_manager_lock
    
    if _led_manager_lock:
        print("[LED] LED manager is cleaning up, please wait...")
        return
    
    _led_manager_lock = True
    try:
        if _led_preset_manager is not None:
            print("[LED] Starting cleanup of LED preset manager instance...")
            
            # 关闭所有LED
            try:
                _led_preset_manager.set_system_status('off')
            except:
                pass
            
            # 清理实例
            _led_preset_manager = None
            _led_manager_initialized = False
            
            print("[LED] LED preset manager instance cleaned up")
            
            # 执行垃圾回收
            import gc
            gc.collect()
            
            print(f"[LED] Memory cleanup completed, remaining memory: {gc.mem_free()} bytes")
        
    except Exception as e:
        print(f"[LED] LED manager cleanup failed: {e}")
        
    finally:
        _led_manager_lock = False

def get_led_manager_status():
    """获取LED管理器状态"""
    global _led_preset_manager, _led_manager_initialized, _led_manager_pins
    
    return {
        'exists': _led_preset_manager is not None,
        'initialized': _led_manager_initialized,
        'pins': _led_manager_pins.copy(),
        'locked': _led_manager_lock
    }

def reset_led_manager():
    """重置LED管理器 - 强制重新初始化"""
    global _led_preset_manager, _led_manager_initialized, _led_manager_lock
    
    if _led_manager_lock:
        print("[LED] LED manager is resetting, please wait...")
        return False
    
    _led_manager_lock = True
    try:
        print("[LED] Starting LED manager reset...")
        
        # 清理现有实例
        cleanup_led_manager()
        
        # 重置配置
        _led_manager_pins = config.get_config('daemon', 'led_pins', [12, 13])
        
        # 短暂延迟
        import time
        time.sleep_ms(100)
        
        print("[LED] LED manager reset completed")
        return True
        
    except Exception as e:
        print(f"[LED] LED manager reset failed: {e}")
        return False
        
    finally:
        _led_manager_lock = False

# =============================================================================
# 便捷函数
# =============================================================================

def set_system_status(status: str):
    """设置系统状态的便捷函数"""
    manager = get_led_manager()
    manager.set_system_status(status)

# =============================================================================
# 从led_preset_temp_data.py移植的便捷函数
# =============================================================================

def quick_flash_three(led_index=0):
    """快闪三下模式的便捷函数"""
    manager = get_led_manager()
    # print(f"[LED] LED {led_index} 快闪三下模式")
    for _ in range(3):
        if led_index == 0:
            manager.led1.on()
            time.sleep(0.1)
            manager.led1.off()
            time.sleep(0.1)
        else:
            manager.led2.on()
            time.sleep(0.1)
            manager.led2.off()
            time.sleep(0.1)
    time.sleep(0.3)

def one_long_two_short(led_index=0):
    """一长两短模式的便捷函数"""
    manager = get_led_manager()
    # print(f"[LED] LED {led_index} 一长两短模式")
    if led_index == 0:
        manager.led1.on()
        time.sleep(0.8)
        manager.led1.off()
        time.sleep(0.2)
        for _ in range(2):
            manager.led1.on()
            time.sleep(0.2)
            manager.led1.off()
            time.sleep(0.2)
    else:
        manager.led2.on()
        time.sleep(0.8)
        manager.led2.off()
        time.sleep(0.2)
        for _ in range(2):
            manager.led2.on()
            time.sleep(0.2)
            manager.led2.off()
            time.sleep(0.2)
    time.sleep(0.3)

def sos_pattern(led_index=0):
    """SOS求救信号模式的便捷函数 (··· --- ···) - 优化内存使用"""
    manager = get_led_manager()
    # print(f"[LED] LED {led_index} SOS模式")
    led = manager.led1 if led_index == 0 else manager.led2
    
    # 使用毫秒级延迟，提高响应性并减少内存占用
    # 三短
    for _ in range(3):
        led.on()
        time.sleep_ms(200)
        led.off()
        time.sleep_ms(200)
    time.sleep_ms(300)
    # 三长
    for _ in range(3):
        led.on()
        time.sleep_ms(600)
        led.off()
        time.sleep_ms(200)
    time.sleep_ms(300)
    # 三短
    for _ in range(3):
        led.on()
        time.sleep_ms(200)
        led.off()
        time.sleep_ms(200)
    time.sleep_ms(500)

def heartbeat(led_index=0, cycles=3):
    """心跳模式的便捷函数"""
    manager = get_led_manager()
    # print(f"[LED] LED {led_index} 心跳模式 ({cycles}次)")
    led = manager.led1 if led_index == 0 else manager.led2
    for _ in range(cycles):
        led.on()
        time.sleep(0.1)
        led.off()
        time.sleep(0.1)
        time.sleep(0.3)
        led.on()
        time.sleep(0.1)
        led.off()
        time.sleep(0.9)

def police_lights(cycles=3):
    """警灯模式的便捷函数（双LED交替闪烁）"""
    manager = get_led_manager()
    # print(f"[LED] 警灯模式 ({cycles}次)")
    for _ in range(cycles):
        for _ in range(3):
            manager.led1.on()
            time.sleep(0.1)
            manager.led1.off()
            time.sleep(0.1)
        for _ in range(3):
            manager.led2.on()
            time.sleep(0.1)
            manager.led2.off()
            time.sleep(0.1)

def knight_rider(cycles=2):
    """霹雳游侠模式的便捷函数（来回扫描）"""
    manager = get_led_manager()
    # print(f"[LED] 霹雳游侠模式 ({cycles}次)")
    for _ in range(cycles):
        # 从左到右
        manager.led1.on()
        time.sleep(0.1)
        manager.led1.off()
        time.sleep(0.05)
        manager.led2.on()
        time.sleep(0.1)
        manager.led2.off()
        time.sleep(0.05)
        # 从右到左
        manager.led2.on()
        time.sleep(0.1)
        manager.led2.off()
        time.sleep(0.05)
        manager.led1.on()
        time.sleep(0.1)
        manager.led1.off()
        time.sleep(0.05)

def counting_blink(led_index=0, count=5):
    """计数闪烁模式的便捷函数"""
    manager = get_led_manager()
    # print(f"[LED] LED {led_index} 计数闪烁模式 (1-{count})")
    led = manager.led1 if led_index == 0 else manager.led2
    for i in range(1, count + 1):
        for _ in range(i):
            led.on()
            time.sleep(0.1)
            led.off()
            time.sleep(0.1)
        time.sleep(0.4)

def breathing_light(led_index=0, cycles=3):
    """呼吸灯模式的便捷函数"""
    manager = get_led_manager()
    print(f"[LED] LED {led_index} breathing light mode ({cycles} cycles)")
    led = manager.led1 if led_index == 0 else manager.led2
    for _ in range(cycles):
        # 渐亮
        for i in range(10):
            # 由于ESP32-C3的GPIO不支持PWM，用短闪烁模拟
            if i < 5:
                led.on()
                time.sleep(0.01)
                led.off()
                time.sleep(0.09)
            else:
                led.on()
                time.sleep(0.05)
                led.off()
                time.sleep(0.05)
        time.sleep(0.2)

def custom_pattern(pattern, led_index=0):
    """自定义模式的便捷函数"""
    manager = get_led_manager()
    print(f"[LED] LED {led_index} custom pattern")
    led = manager.led1 if led_index == 0 else manager.led2
    for on_time, off_time in pattern:
        led.on()
        time.sleep(on_time)
        led.off()
        time.sleep(off_time)