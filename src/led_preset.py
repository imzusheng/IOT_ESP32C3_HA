# -*- coding: utf-8 -*-
"""
LED预设模块

提供标准化的LED状态指示预设模式，用于系统状态显示和用户反馈。
所有LED闪烁效果都通过此模块统一管理。
"""

import machine
import time

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
    
    def __init__(self, pin1: int = 12, pin2: int = 13):
        """
        初始化LED预设管理器
        
        Args:
            pin1: 第一个LED引脚，默认12
            pin2: 第二个LED引脚，默认13
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
            # 安全模式：SOS模式
            sos_pattern(0)
            # print("[LED] 系统状态：安全模式（SOS模式）")
            
        else:
            print(f"[LED] 未知状态: {status}")
            self.set_system_status(SYSTEM_OFF)
    
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

# 全局LED预设管理器实例
_led_preset_manager = None

def get_led_manager():
    """获取全局LED预设管理器实例"""
    global _led_preset_manager
    if _led_preset_manager is None:
        _led_preset_manager = LEDPresetManager()
    return _led_preset_manager

def init_led_manager(pin1: int = 12, pin2: int = 13):
    """初始化全局LED预设管理器"""
    global _led_preset_manager
    _led_preset_manager = LEDPresetManager(pin1, pin2)
    return _led_preset_manager

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
    """SOS求救信号模式的便捷函数 (··· --- ···)"""
    manager = get_led_manager()
    # print(f"[LED] LED {led_index} SOS模式")
    led = manager.led1 if led_index == 0 else manager.led2
    # 三短
    for _ in range(3):
        led.on()
        time.sleep(0.2)
        led.off()
        time.sleep(0.2)
    time.sleep(0.3)
    # 三长
    for _ in range(3):
        led.on()
        time.sleep(0.6)
        led.off()
        time.sleep(0.2)
    time.sleep(0.3)
    # 三短
    for _ in range(3):
        led.on()
        time.sleep(0.2)
        led.off()
        time.sleep(0.2)
    time.sleep(0.5)

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
    print(f"[LED] LED {led_index} 呼吸灯模式 ({cycles}次)")
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
    print(f"[LED] LED {led_index} 自定义模式")
    led = manager.led1 if led_index == 0 else manager.led2
    for on_time, off_time in pattern:
        led.on()
        time.sleep(on_time)
        led.off()
        time.sleep(off_time)