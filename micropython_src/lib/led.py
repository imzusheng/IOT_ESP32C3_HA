# led.py
"""
LED控制模块 - 增强版本

合并了utils.py中的LED功能，提供完整的LED管理：
- PWM硬件控制
- 多种灯效模式和异步任务
- 事件驱动控制
- 动态配置更新
- 温度优化支持
"""

import time
import machine
import uasyncio as asyncio
from machine import Pin, PWM
from lib import core
from config import (
    get_event_id, DEBUG, 
    EV_LED_SET_EFFECT, EV_LED_SET_BRIGHTNESS, EV_LED_EMERGENCY_OFF,
    LED_PIN_1, LED_PIN_2, PWM_FREQ, MAX_BRIGHTNESS, FADE_STEP
)

class LEDManager:
    """增强的LED管理器 - 支持异步灯效和事件驱动"""
    
    def __init__(self):
        self.pin1 = LED_PIN_1
        self.pin2 = LED_PIN_2
        self.pwm1 = None
        self.pwm2 = None
        self.initialized = False
        
        # 灯效状态
        self.current_effect = 'off'
        self.effect_params = {}
        self.led1_brightness = 0
        self.led2_brightness = 0
        
        # 动画状态
        self.blink_state = False
        self.blink_counter = 0
        self.safe_mode_active = False
        
        # 动态配置变量（用于温度优化）
        self.led_update_interval_ms = 50
        self.current_pwm_freq = PWM_FREQ
        self.current_max_brightness = MAX_BRIGHTNESS
        
        # 任务控制
        self.task_running = False
        self.led_task = None
        
    def init(self):
        """初始化LED硬件"""
        try:
            # 如果已经初始化，先清理
            if self.pwm1:
                self.pwm1.deinit()
            if self.pwm2:
                self.pwm2.deinit()
            
            # 创建PWM对象
            pin1 = machine.Pin(self.pin1, machine.Pin.OUT)
            pin2 = machine.Pin(self.pin2, machine.Pin.OUT)
            self.pwm1 = machine.PWM(pin1, freq=self.current_pwm_freq, duty_u16=0)
            self.pwm2 = machine.PWM(pin2, freq=self.current_pwm_freq, duty_u16=0)
            
            self.initialized = True
            
            if DEBUG:
                print(f"[LED] 初始化成功 - 引脚: {self.pin1}, {self.pin2}, 频率: {self.current_pwm_freq}Hz")
            
            # 发布初始化成功事件
            core.publish(get_event_id('led_initialized'), success=True)
            
            # 订阅LED控制事件
            self._subscribe_to_events()
            
            return True
            
        except Exception as e:
            error_msg = f"LED初始化失败: {e}"
            if DEBUG:
                print(f"[LED] [ERROR] {error_msg}")
            
            core.publish(get_event_id('led_initialized'), success=False, error=error_msg)
            core.publish(get_event_id('log_critical'), message=error_msg)
            
            self.pwm1 = None
            self.pwm2 = None
            return False
    
    def deinit(self):
        """关闭并释放PWM硬件资源"""
        try:
            # 停止LED任务
            self.stop_led_task()
            
            if self.pwm1:
                self.pwm1.deinit()
            if self.pwm2:
                self.pwm2.deinit()
            self.pwm1 = None
            self.pwm2 = None
            self.initialized = False
            
            if DEBUG:
                print("[LED] PWM 已关闭")
            
            core.publish(get_event_id('led_deinitialized'))
            
        except Exception as e:
            error_msg = f"PWM 关闭失败: {e}"
            if DEBUG:
                print(f"[LED] [ERROR] {error_msg}")
            core.publish(get_event_id('log_error'), message=error_msg)
    
    def _subscribe_to_events(self):
        """订阅LED相关的事件"""
        core.subscribe(EV_LED_SET_EFFECT, self._on_led_set_effect)
        core.subscribe(EV_LED_SET_BRIGHTNESS, self._on_led_set_brightness)
        core.subscribe(EV_LED_EMERGENCY_OFF, self._on_led_emergency_off)
        core.subscribe(get_event_id('config_update'), self._on_config_update)
        core.subscribe(get_event_id('wifi_connecting_blink'), self._on_wifi_connecting_blink)
        
        if DEBUG:
            print("[LED] 已订阅LED控制事件")
    
    def _on_config_update(self, **kwargs):
        """处理配置更新事件（温度优化）"""
        new_config = kwargs.get('config', {})
        temp_level = kwargs.get('temp_level', 'normal')
        source = kwargs.get('source', 'unknown')
        
        if source == 'temp_optimizer':
            if DEBUG:
                print(f"[LED] 收到温度优化配置更新，温度级别: {temp_level}")
            
            # 更新LED更新间隔
            if 'led_interval_ms' in new_config:
                self.led_update_interval_ms = max(50, new_config['led_interval_ms'])
                if DEBUG:
                    print(f"[LED] 更新呼吸灯间隔为: {self.led_update_interval_ms}ms")
            
            # 更新PWM频率
            if 'pwm_freq' in new_config and self.pwm1 and self.pwm2:
                try:
                    new_freq = new_config['pwm_freq']
                    self.pwm1.freq(new_freq)
                    self.pwm2.freq(new_freq)
                    self.current_pwm_freq = new_freq
                    if DEBUG:
                        print(f"[LED] 更新PWM频率为: {new_freq}Hz")
                except Exception as e:
                    if DEBUG:
                        print(f"[LED] [ERROR] PWM频率更新失败: {e}")
            
            # 更新最大亮度
            if 'max_brightness' in new_config:
                self.current_max_brightness = new_config['max_brightness']
                if DEBUG:
                    print(f"[LED] 更新最大亮度为: {self.current_max_brightness}")
    
    def _on_led_set_effect(self, **event_data):
        """处理设置LED效果的事件"""
        mode = event_data.get('mode', 'off')
        led_num = event_data.get('led_num', 1)
        brightness = event_data.get('brightness', self.current_max_brightness)
        self.set_effect(mode, led_num, brightness)
    
    def _on_led_set_brightness(self, **event_data):
        """处理设置LED亮度的事件"""
        led_num = event_data.get('led_num', 1)
        brightness = event_data.get('brightness', self.current_max_brightness)
        self.set_brightness(led_num, brightness)
    
    def _on_led_emergency_off(self, **event_data):
        """处理紧急关闭LED的事件"""
        if DEBUG:
            print("[LED] 收到紧急关闭信号")
        self.set_effect('off')
        core.publish(get_event_id('led_emergency_off_completed'))
    
    async def _on_wifi_connecting_blink(self, **event_data):
        """WiFi连接时的LED闪烁指示"""
        if not self.pwm1 or not self.pwm2:
            return
        
        # 异步闪烁：使用asyncio.sleep实现非阻塞延时
        self.pwm1.duty_u16(self.current_max_brightness)
        self.pwm2.duty_u16(self.current_max_brightness)
        await asyncio.sleep_ms(100)
        self.pwm1.duty_u16(0)
        self.pwm2.duty_u16(0)
        await asyncio.sleep_ms(100)
    
    def set_brightness(self, led_num=1, brightness=0):
        """设置LED亮度"""
        if not self.initialized:
            return False
        
        try:
            # 确保亮度在有效范围内
            brightness = max(0, min(brightness, self.current_max_brightness))
            
            # 转换为16位PWM值
            duty = int(brightness * 65535 / self.current_max_brightness) if self.current_max_brightness > 0 else 0
            
            if led_num == 1 and self.pwm1:
                self.pwm1.duty_u16(duty)
                self.led1_brightness = brightness
            elif led_num == 2 and self.pwm2:
                self.pwm2.duty_u16(duty)
                self.led2_brightness = brightness
            elif led_num == 0:  # 两个LED都设置
                if self.pwm1:
                    self.pwm1.duty_u16(duty)
                    self.led1_brightness = brightness
                if self.pwm2:
                    self.pwm2.duty_u16(duty)
                    self.led2_brightness = brightness
            
            return True
        except Exception as e:
            if DEBUG:
                print(f"[LED] 设置亮度失败: {e}")
            return False
    
    def set_effect(self, mode='off', led_num=1, brightness_u16=None):
        """设置LED效果"""
        if not self.initialized:
            if DEBUG:
                print("[LED] [WARNING] PWM未初始化，无法设置灯效")
            return False
        
        if brightness_u16 is None:
            brightness_u16 = self.current_max_brightness
        
        if DEBUG:
            print(f"[LED] 设置灯效为: {mode}")
        
        self.current_effect = mode
        self.effect_params = {'led_num': led_num, 'brightness_u16': brightness_u16}
        
        if mode == 'off':
            self.set_brightness(1, 0)
            self.set_brightness(2, 0)
        elif mode == 'single_on':
            if led_num == 1:
                self.set_brightness(1, brightness_u16)
                self.set_brightness(2, 0)
            else:
                self.set_brightness(1, 0)
                self.set_brightness(2, brightness_u16)
        elif mode == 'both_on':
            self.set_brightness(1, brightness_u16)
            self.set_brightness(2, brightness_u16)
        elif mode in ['fast_blink', 'slow_blink', 'alternate_blink', 'double_blink', 'heartbeat_blink']:
            # 重置闪烁效果的起始状态
            self.blink_state = False
            self.blink_counter = 0
        else:
            error_msg = f"未知的灯效模式: {mode}"
            if DEBUG:
                print(f"[LED] [WARNING] {error_msg}")
            core.publish(get_event_id('log_warning'), message=error_msg)
            self.current_effect = 'off'
        
        # 发布灯效变化事件
        core.publish(get_event_id('led_effect_changed'), 
                    effect=self.current_effect, 
                    params=self.effect_params)
        
        return True
    
    def start_led_task(self):
        """启动LED异步任务"""
        if not self.task_running:
            self.task_running = True
            self.led_task = asyncio.create_task(self._led_effect_task())
            if DEBUG:
                print("[LED] LED异步任务已启动")
    
    def stop_led_task(self):
        """停止LED异步任务"""
        self.task_running = False
        if self.led_task and not self.led_task.done():
            self.led_task.cancel()
            if DEBUG:
                print("[LED] LED异步任务已停止")
    
    async def _led_effect_task(self):
        """LED效果异步任务：处理各种闪烁效果"""
        print("[LED] LED效果异步任务已启动")
        
        while self.task_running:
            try:
                # 处理各种闪烁效果
                if self.current_effect == 'fast_blink':
                    # 快闪：200ms间隔
                    if self.pwm1 and self.pwm2:
                        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
                        if self.blink_state:
                            self.set_brightness(1, brightness)
                            self.set_brightness(2, brightness)
                        else:
                            self.set_brightness(1, 0)
                            self.set_brightness(2, 0)
                        self.blink_state = not self.blink_state
                    await asyncio.sleep_ms(200)
                    
                elif self.current_effect == 'slow_blink':
                    # 慢闪：1000ms间隔
                    if self.pwm1 and self.pwm2:
                        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
                        if self.blink_state:
                            self.set_brightness(1, brightness)
                            self.set_brightness(2, brightness)
                        else:
                            self.set_brightness(1, 0)
                            self.set_brightness(2, 0)
                        self.blink_state = not self.blink_state
                    await asyncio.sleep_ms(1000)
                    
                elif self.current_effect == 'alternate_blink':
                    # 交替闪烁：500ms间隔
                    if self.pwm1 and self.pwm2:
                        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
                        if self.blink_state:
                            self.set_brightness(1, brightness)
                            self.set_brightness(2, 0)
                        else:
                            self.set_brightness(1, 0)
                            self.set_brightness(2, brightness)
                        self.blink_state = not self.blink_state
                    await asyncio.sleep_ms(500)
                    
                elif self.current_effect == 'double_blink':
                    # 双闪：快速闪烁两次，然后暂停
                    if self.pwm1 and self.pwm2:
                        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
                        self.blink_counter += 1
                        if self.blink_counter <= 4:  # 两次闪烁（开-关-开-关）
                            if self.blink_state:
                                self.set_brightness(1, brightness)
                                self.set_brightness(2, brightness)
                            else:
                                self.set_brightness(1, 0)
                                self.set_brightness(2, 0)
                            self.blink_state = not self.blink_state
                            await asyncio.sleep_ms(150)
                        else:
                            # 暂停阶段
                            self.set_brightness(1, 0)
                            self.set_brightness(2, 0)
                            await asyncio.sleep_ms(800)
                            self.blink_counter = 0
                            self.blink_state = False
                            
                elif self.current_effect == 'heartbeat_blink':
                    # 心跳闪烁：模拟心跳节奏
                    if self.pwm1 and self.pwm2:
                        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
                        self.blink_counter += 1
                        if self.blink_counter == 1:
                            # 第一次跳动
                            self.set_brightness(1, brightness)
                            self.set_brightness(2, brightness)
                            await asyncio.sleep_ms(100)
                            self.set_brightness(1, 0)
                            self.set_brightness(2, 0)
                            await asyncio.sleep_ms(100)
                        elif self.blink_counter == 2:
                            # 第二次跳动
                            self.set_brightness(1, brightness)
                            self.set_brightness(2, brightness)
                            await asyncio.sleep_ms(100)
                            self.set_brightness(1, 0)
                            self.set_brightness(2, 0)
                            await asyncio.sleep_ms(600)  # 长暂停
                            self.blink_counter = 0
                        else:
                            self.blink_counter = 0
                else:
                    # 非动画模式下，使用动态更新间隔
                    await asyncio.sleep_ms(self.led_update_interval_ms)
                    
            except Exception as e:
                error_msg = f"LED效果任务错误: {e}"
                if DEBUG:
                    print(f"[LED] [ERROR] {error_msg}")
                core.publish(get_event_id('log_warning'), message=error_msg)
                # 发生错误时等待更长时间，避免错误循环
                await asyncio.sleep_ms(2000)
        
        print("[LED] LED效果异步任务已停止")
    
    def get_status(self):
        """获取LED状态"""
        return {
            'initialized': self.initialized,
            'current_effect': self.current_effect,
            'effect_params': self.effect_params.copy(),
            'led1_brightness': self.led1_brightness,
            'led2_brightness': self.led2_brightness,
            'task_running': self.task_running,
            'pin1': self.pin1,
            'pin2': self.pin2,
            'pwm_freq': self.current_pwm_freq,
            'max_brightness': self.current_max_brightness
        }

# 全局LED管理器实例
_global_led_manager = LEDManager()

# 外部接口函数
def init_led():
    """初始化LED"""
    return _global_led_manager.init()

def deinit_led():
    """关闭LED"""
    _global_led_manager.deinit()

def set_led_effect(effect, **params):
    """设置LED效果"""
    led_num = params.get('led_num', 1)
    brightness = params.get('brightness', _global_led_manager.current_max_brightness)
    return _global_led_manager.set_effect(effect, led_num, brightness)

def set_led_brightness(led_num, brightness):
    """设置LED亮度"""
    return _global_led_manager.set_brightness(led_num, brightness)

def start_led_task():
    """启动LED异步任务"""
    _global_led_manager.start_led_task()

def stop_led_task():
    """停止LED异步任务"""
    _global_led_manager.stop_led_task()

def emergency_led_off():
    """紧急关闭LED"""
    _global_led_manager.set_effect('off')

def get_led_status():
    """获取LED状态"""
    return _global_led_manager.get_status()

def update_led_config(new_config):
    """更新LED配置"""
    _global_led_manager._on_config_update(config=new_config, source='manual')

# 兼容性函数（保持向后兼容）
def init_leds():
    """初始化LED（兼容性函数）"""
    return init_led()

def deinit_leds():
    """关闭LED（兼容性函数）"""
    deinit_led()

def set_effect(mode, led_num=1, brightness_u16=None):
    """设置LED效果（兼容性函数）"""
    if brightness_u16 is None:
        brightness_u16 = _global_led_manager.current_max_brightness
    return _global_led_manager.set_effect(mode, led_num, brightness_u16)