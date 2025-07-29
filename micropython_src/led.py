# led.py
"""
LED控制模块

从core.py中分离出来的独立LED控制系统，提供：
- PWM硬件控制
- 多种灯效模式
- 事件驱动控制
- 动态配置更新
"""

import time
import machine
from machine import Pin, PWM
from config import (
    get_event_id, DEBUG, 
    EV_LED_SET_EFFECT, EV_LED_SET_BRIGHTNESS, EV_LED_EMERGENCY_OFF,
    get_led_pin_1, get_led_pin_2, get_pwm_freq, get_max_brightness
)

class SimpleLED:
    """简化的LED控制器"""
    
    def __init__(self):
        self.pin1 = get_led_pin_1()
        self.pin2 = get_led_pin_2()
        self.pwm1 = None
        self.pwm2 = None
        self.initialized = False
        self.current_effect = 'off'
        self.effect_params = {}
        
    def init(self):
        """初始化LED"""
        try:
            # 如果已经初始化，先清理
            if self.pwm1:
                self.pwm1.deinit()
            if self.pwm2:
                self.pwm2.deinit()
            
            # 获取最新配置
            self.pin1 = get_led_pin_1()
            self.pin2 = get_led_pin_2()
            freq = get_pwm_freq()
            
            self.pwm1 = PWM(Pin(self.pin1), freq=freq)
            self.pwm2 = PWM(Pin(self.pin2), freq=freq)
            self.pwm1.duty_u16(0)
            self.pwm2.duty_u16(0)
            self.initialized = True
            
            if DEBUG:
                print(f"[LED] 初始化成功 - 引脚: {self.pin1}, {self.pin2}, 频率: {freq}Hz")
            
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 初始化失败: {e}")
            return False
    
    def deinit(self):
        """关闭LED"""
        try:
            if self.pwm1:
                self.pwm1.deinit()
            if self.pwm2:
                self.pwm2.deinit()
            self.pwm1 = None
            self.pwm2 = None
            self.initialized = False
            
            if DEBUG:
                print("[LED] 已关闭")
            
        except Exception as e:
            if DEBUG:
                print(f"[LED] 关闭失败: {e}")
    
    def set_brightness(self, led_num=1, brightness=0):
        """设置LED亮度"""
        if not self.initialized:
            return False
        
        try:
            # 确保亮度在有效范围内
            max_brightness = get_max_brightness()
            brightness = max(0, min(brightness, max_brightness))
            
            # 转换为16位PWM值
            duty = int(brightness * 65535 / max_brightness) if max_brightness > 0 else 0
            
            if led_num == 1 and self.pwm1:
                self.pwm1.duty_u16(duty)
            elif led_num == 2 and self.pwm2:
                self.pwm2.duty_u16(duty)
            elif led_num == 0:  # 两个LED都设置
                if self.pwm1:
                    self.pwm1.duty_u16(duty)
                if self.pwm2:
                    self.pwm2.duty_u16(duty)
            
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 设置亮度失败: {e}")
            return False
    
    def set_effect(self, effect='off', **params):
        """设置LED效果"""
        if not self.initialized:
            return False
        
        try:
            self.current_effect = effect
            self.effect_params = params
            
            max_brightness = get_max_brightness()
            brightness = params.get('brightness', max_brightness)
            led_num = params.get('led_num', 1)
            
            if effect == 'off':
                self.set_brightness(1, 0)
                self.set_brightness(2, 0)
            elif effect == 'on':
                self.set_brightness(1, brightness)
                self.set_brightness(2, brightness)
            elif effect == 'single_on':
                if led_num == 1:
                    self.set_brightness(1, brightness)
                    self.set_brightness(2, 0)
                else:
                    self.set_brightness(1, 0)
                    self.set_brightness(2, brightness)
            elif effect == 'blink':
                # 简单的交替闪烁
                current_time = time.ticks_ms()
                if (current_time // 500) % 2:
                    self.set_brightness(1, brightness)
                    self.set_brightness(2, 0)
                else:
                    self.set_brightness(1, 0)
                    self.set_brightness(2, brightness)
            
            if DEBUG:
                print(f"[LED] 设置效果: {effect}")
            
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 设置效果失败: {e}")
            return False
    
    def update_config(self, new_config):
        """更新配置"""
        try:
            # 检查是否需要更新PWM频率
            if 'pwm_freq' in new_config and self.pwm1 and self.pwm2:
                new_freq = new_config['pwm_freq']
                self.pwm1.freq(new_freq)
                self.pwm2.freq(new_freq)
                if DEBUG:
                    print(f"[LED] 更新PWM频率为: {new_freq}Hz")
            
            # 检查是否需要重新应用亮度
            if 'max_brightness' in new_config:
                if DEBUG:
                    print(f"[LED] 最大亮度更新为: {new_config['max_brightness']}")
                # 如果当前有效果在运行，重新应用以适应新的亮度设置
                if self.current_effect != 'off':
                    self.set_effect(self.current_effect, **self.effect_params)
            
        except Exception as e:
            if DEBUG:
                print(f"[LED] 配置更新失败: {e}")
    
    def emergency_off(self):
        """紧急关闭"""
        try:
            self.set_effect('off')
            if DEBUG:
                print("[LED] 紧急关闭完成")
        except Exception as e:
            if DEBUG:
                print(f"[LED] 紧急关闭失败: {e}")
    
    def get_status(self):
        """获取LED状态"""
        return {
            'initialized': self.initialized,
            'current_effect': self.current_effect,
            'effect_params': self.effect_params.copy(),
            'pin1': self.pin1,
            'pin2': self.pin2
        }

# 全局LED实例
_global_led = SimpleLED()

def init_led():
    """初始化LED"""
    return _global_led.init()

def deinit_led():
    """关闭LED"""
    _global_led.deinit()

def set_led_effect(effect, **params):
    """设置LED效果"""
    return _global_led.set_effect(effect, **params)

def set_led_brightness(led_num, brightness):
    """设置LED亮度"""
    return _global_led.set_brightness(led_num, brightness)

def update_led_config(new_config):
    """更新LED配置"""
    _global_led.update_config(new_config)

def emergency_led_off():
    """紧急关闭LED"""
    _global_led.emergency_off()

def get_led_status():
    """获取LED状态"""
    return _global_led.get_status()