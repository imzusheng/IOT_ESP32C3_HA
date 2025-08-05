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
SYSTEM_SAFE_MODE = "safe_mode"    # 安全模式：交替闪烁

# 闪烁模式常量
BLINK_FAST = 100                 # 快速闪烁：100ms周期
BLINK_NORMAL = 500               # 正常闪烁：500ms周期
BLINK_SLOW = 1000               # 慢速闪烁：1000ms周期

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
        
        # 闪烁状态管理
        self._blink_active = False
        self._blink_start_time = 0
        self._blink_period = BLINK_NORMAL
        self._blink_pattern = "alternating"  # alternating, sync, single
        
        # 初始化状态
        self.set_system_status(SYSTEM_OFF)
        
        print(f"[LED] LED预设管理器初始化完成，引脚: {pin1}, {pin2}")
    
    def set_system_status(self, status: str):
        """
        设置系统状态LED显示
        
        Args:
            status: 系统状态，支持：
                   - normal: 正常运行
                   - warning: 警告状态  
                   - error: 错误状态
                   - off: 关闭状态
                   - safe_mode: 安全模式（闪烁）
        """
        status = status.lower()
        
        # 停止当前闪烁
        self._blink_active = False
        
        if status == SYSTEM_NORMAL:
            self.led1.on()
            self.led2.off()
            print("[LED] 系统状态：正常运行")
            
        elif status == SYSTEM_WARNING:
            self.led1.on()
            self.led2.on()
            print("[LED] 系统状态：警告")
            
        elif status == SYSTEM_ERROR:
            self.led1.off()
            self.led2.on()
            print("[LED] 系统状态：错误")
            
        elif status == SYSTEM_OFF:
            self.led1.off()
            self.led2.off()
            print("[LED] 系统状态：关闭")
            
        elif status == SYSTEM_SAFE_MODE:
            self._start_safe_mode_blink()
            print("[LED] 系统状态：安全模式（闪烁）")
            
        else:
            print(f"[LED] 未知状态: {status}")
            self.set_system_status(SYSTEM_OFF)
    
    def _start_safe_mode_blink(self):
        """启动安全模式闪烁"""
        self._blink_active = True
        self._blink_start_time = time.ticks_ms()
        self._blink_period = BLINK_NORMAL
        self._blink_pattern = "alternating"
    
    def update_blink_state(self):
        """
        更新LED闪烁状态 - 需要在主循环中定期调用
        返回是否需要继续调用（True表示闪烁活跃）
        """
        if not self._blink_active:
            return False
        
        try:
            current_time = time.ticks_ms()
            elapsed = time.ticks_diff(current_time, self._blink_start_time)
            
            if self._blink_pattern == "alternating":
                # 交替闪烁模式
                blink_state = (elapsed // self._blink_period) % 2
                
                if blink_state == 0:
                    self.led1.on()
                    self.led2.off()
                else:
                    self.led1.off()
                    self.led2.on()
                    
            elif self._blink_pattern == "sync":
                # 同步闪烁模式
                blink_state = (elapsed // self._blink_period) % 2
                
                if blink_state == 0:
                    self.led1.on()
                    self.led2.on()
                else:
                    self.led1.off()
                    self.led2.off()
                    
            elif self._blink_pattern == "single":
                # 单LED闪烁模式
                blink_state = (elapsed // self._blink_period) % 2
                
                if blink_state == 0:
                    self.led1.on()
                    self.led2.off()
                else:
                    self.led1.off()
                    self.led2.off()
            
            return True
            
        except Exception as e:
            print(f"[LED] 闪烁状态更新失败: {e}")
            self._blink_active = False
            return False
    
    def stop_blink(self):
        """停止所有闪烁效果"""
        self._blink_active = False
        self.led1.off()
        self.led2.off()
        print("[LED] 闪烁效果已停止")
    
    def quick_notification(self, pattern: str = "flash", count: int = 3):
        """
        快速通知模式
        
        Args:
            pattern: 通知模式
                     - flash: 快速闪烁
                     - heartbeat: 心跳模式
                     - sos: SOS模式
            count: 重复次数
        """
        original_blink = self._blink_active
        
        # 停止当前闪烁
        self._blink_active = False
        
        try:
            if pattern == "flash":
                for _ in range(count):
                    self.led1.on()
                    self.led2.off()
                    time.sleep_ms(100)
                    self.led1.off()
                    self.led2.on()
                    time.sleep_ms(100)
                    
            elif pattern == "heartbeat":
                for _ in range(count):
                    self.led1.on()
                    time.sleep_ms(100)
                    self.led1.off()
                    time.sleep_ms(300)
                    self.led1.on()
                    time.sleep_ms(100)
                    self.led1.off()
                    time.sleep_ms(900)
                    
            elif pattern == "sos":
                # SOS模式：··· --- ···
                for _ in range(count):
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
                    time.sleep_ms(500)
                    
        except Exception as e:
            print(f"[LED] 快速通知失败: {e}")
        
        # 恢复原始闪烁状态
        if original_blink:
            self._blink_active = True
            self._blink_start_time = time.ticks_ms()
    
    def test_hardware(self):
        """测试LED硬件功能"""
        print("[LED] 开始LED硬件测试...")
        
        try:
            # 测试LED1
            print("[LED] 测试LED1...")
            self.led1.on()
            time.sleep_ms(500)
            self.led1.off()
            time.sleep_ms(200)
            
            # 测试LED2
            print("[LED] 测试LED2...")
            self.led2.on()
            time.sleep_ms(500)
            self.led2.off()
            time.sleep_ms(200)
            
            # 测试同时亮起
            print("[LED] 测试双LED同时亮起...")
            self.led1.on()
            self.led2.on()
            time.sleep_ms(500)
            self.led1.off()
            self.led2.off()
            
            # 测试交替闪烁
            print("[LED] 测试交替闪烁...")
            for _ in range(5):
                self.led1.on()
                self.led2.off()
                time.sleep_ms(250)
                self.led1.off()
                self.led2.on()
                time.sleep_ms(250)
            self.led1.off()
            self.led2.off()
            
            print("[LED] LED硬件测试完成")
            return True
            
        except Exception as e:
            print(f"[LED] LED硬件测试失败: {e}")
            return False
    
    def simple_blink_test(self, duration_ms: int = 5000):
        """
        简单闪烁测试 - 用于验证LED硬件
        
        Args:
            duration_ms: 测试持续时间（毫秒）
        """
        print(f"[LED] 开始简单闪烁测试，持续 {duration_ms}ms...")
        
        start_time = time.ticks_ms()
        end_time = start_time + duration_ms
        
        try:
            while time.ticks_ms() < end_time:
                # 交替闪烁
                self.led1.on()
                self.led2.off()
                time.sleep_ms(250)
                
                self.led1.off()
                self.led2.on()
                time.sleep_ms(250)
            
            # 测试完成，关闭LED
            self.led1.off()
            self.led2.off()
            print("[LED] 简单闪烁测试完成")
            return True
            
        except Exception as e:
            print(f"[LED] 简单闪烁测试失败: {e}")
            self.led1.off()
            self.led2.off()
            return False
    
    def get_status(self):
        """获取LED管理器状态"""
        return {
            'pin1': self.pin1,
            'pin2': self.pin2,
            'led1_state': self.led1.value(),
            'led2_state': self.led2.value(),
            'blink_active': self._blink_active,
            'blink_pattern': self._blink_pattern,
            'blink_period': self._blink_period
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

def update_led_blink():
    """更新LED闪烁状态的便捷函数"""
    manager = get_led_manager()
    return manager.update_blink_state()

def test_led_hardware():
    """测试LED硬件的便捷函数"""
    manager = get_led_manager()
    return manager.test_hardware()

def simple_blink_test(duration_ms: int = 5000):
    """简单闪烁测试的便捷函数"""
    manager = get_led_manager()
    return manager.simple_blink_test(duration_ms)

def quick_notification(pattern: str = "flash", count: int = 3):
    """快速通知的便捷函数"""
    manager = get_led_manager()
    manager.quick_notification(pattern, count)

# =============================================================================
# 兼容性函数（用于向后兼容）
# =============================================================================

class LEDTester:
    """兼容性类 - 保持与旧代码的兼容性"""
    
    def __init__(self, pins=[12, 13]):
        self.manager = LEDPresetManager(pins[0], pins[1] if len(pins) > 1 else 13)
    
    def test_all_leds(self):
        return self.manager.test_hardware()
    
    def simple_blink_test(self, duration_ms=5000):
        return self.manager.simple_blink_test(duration_ms)

def main():
    """主函数 - LED预设模块测试"""
    print("LED预设模块测试")
    
    # 初始化LED管理器
    manager = init_led_manager()
    
    # 测试硬件
    manager.test_hardware()
    time.sleep(1)
    
    # 测试系统状态
    print("\n=== 系统状态测试 ===")
    for status in [SYSTEM_NORMAL, SYSTEM_WARNING, SYSTEM_ERROR, SYSTEM_SAFE_MODE]:
        manager.set_system_status(status)
        time.sleep(2)
        
        # 如果是安全模式，需要更新闪烁状态
        if status == SYSTEM_SAFE_MODE:
            for _ in range(10):
                manager.update_blink_state()
                time.sleep_ms(200)
    
    # 恢复正常状态
    manager.set_system_status(SYSTEM_NORMAL)
    print("\nLED预设模块测试完成")

if __name__ == "__main__":
    main()