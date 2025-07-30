# led.py
"""
LED控制模块 - 增强版本

合并了utils.py中的LED功能，提供完整的LED管理�?- PWM硬件控制
- 多种灯效模式和异步任�?- 事件驱动控制
- 动态配置更�?- 温度优化支持
"""

try:
    import machine
except ImportError:
    machine = None
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
# PWM导入已移除，因为在当前代码中未使用
from .config import (
    get_event_id, DEBUG,
    EV_LED_SET_EFFECT, EV_LED_SET_BRIGHTNESS, EV_LED_EMERGENCY_OFF
)

class LEDManager:
    """增强的LED管理�?- 支持异步灯效和事件驱�?""

    def __init__(self, event_bus=None, config_getter=None):
        # 依赖注入
        self.event_bus = event_bus
        self.config_getter = config_getter

        # 获取LED配置
        self.pin1 = config_getter.get_led_pin_1() if config_getter else 2
        self.pin2 = config_getter.get_led_pin_2() if config_getter else 3
        self.pwm1 = None
        self.pwm2 = None
        self.initialized = False

        # 灯效状�?        self.current_effect = 'off'
        self.effect_params = {}
        self.led1_brightness = 0
        self.led2_brightness = 0

        # 动画状�?        self.blink_state = False
        self.blink_counter = 0
        self.safe_mode_active = False

        # 动态配置变量（用于温度优化�?        self.led_update_interval_ms = 50
        self.current_pwm_freq = config_getter.get_pwm_freq() if config_getter else 1000
        self.current_max_brightness = config_getter.get_max_brightness() if config_getter else 1023

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
                print("[LED] 初始化成功 - 引脚:", str(self.pin1) + ",", str(self.pin2) + ", 频率:", str(self.current_pwm_freq) + "Hz")

            # 发布初始化成功事件
            if self.event_bus:
                self.event_bus.publish(get_event_id('led_initialized'), success=True)

            # 订阅LED控制事件
            self._subscribe_to_events()

            return True

        except (OSError, ValueError, AttributeError) as e:
            error_msg = "LED初始化失败: " + str(e)
            if DEBUG:
                print("[LED] [ERROR]", error_msg)

            if self.event_bus:
                self.event_bus.publish(get_event_id('led_initialized'), success=False, error=error_msg)
                self.event_bus.publish(get_event_id('log_critical'), message=error_msg)

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

            if self.event_bus:
                self.event_bus.publish(get_event_id('led_deinitialized'))

        except (OSError, AttributeError) as e:
            error_msg = "PWM 关闭失败: " + str(e)
            if DEBUG:
                print("[LED] [ERROR]", error_msg)
            if self.event_bus:
                self.event_bus.publish(get_event_id('log_error'), message=error_msg)

    def _subscribe_to_events(self):
        """订阅LED相关的事件"""
        if self.event_bus:
            self.event_bus.subscribe(EV_LED_SET_EFFECT, self._on_led_set_effect)
            self.event_bus.subscribe(EV_LED_SET_BRIGHTNESS, self._on_led_set_brightness)
            self.event_bus.subscribe(EV_LED_EMERGENCY_OFF, self._on_led_emergency_off)
            self.event_bus.subscribe(get_event_id('config_update'), self._on_config_update)
            self.event_bus.subscribe(get_event_id('wifi_connecting_blink'), self._on_wifi_connecting_blink)

            if DEBUG:
                print("[LED] 已订阅LED控制事件")

    def _on_config_update(self, **kwargs):
        """处理配置更新事件"""
        changed_sections = kwargs.get('changed', [])
        new_config = kwargs.get('new_config', {})
        source = kwargs.get('source', 'config_reload')

        # 检查是否有LED相关的配置变更
        if not ('led' in changed_sections or source == 'temp_optimizer'):
            return

        if DEBUG:
            print("[LED] 收到配置更新，来源:", source)

        # 处理温度优化配置
        if source == 'temp_optimizer':
            self._handle_temp_optimizer_config(kwargs, new_config)
        # 处理LED配置变更
        elif 'led' in changed_sections:
            if DEBUG:
                print("[LED] LED配置已更新，将在下次初始化时生效")

    def _handle_temp_optimizer_config(self, kwargs, new_config):
        """处理温度优化配置"""
        temp_level = kwargs.get('temp_level', 'normal')
        if DEBUG:
            print("[LED] 温度优化级别:", temp_level)

        self._update_led_interval(new_config)
        self._update_pwm_frequency(new_config)
        self._update_max_brightness(new_config)

    def _update_led_interval(self, new_config):
        """更新LED更新间隔"""
        if 'led_interval_ms' in new_config:
            self.led_update_interval_ms = max(50, new_config['led_interval_ms'])
            if DEBUG:
                print("[LED] 更新呼吸灯间隔为:", str(self.led_update_interval_ms) + "ms")

    def _update_pwm_frequency(self, new_config):
        """更新PWM频率"""
        if 'pwm_freq' not in new_config or not (self.pwm1 and self.pwm2):
            return

        try:
            new_freq = new_config['pwm_freq']
            self.pwm1.freq(new_freq)
            self.pwm2.freq(new_freq)
            self.current_pwm_freq = new_freq
            if DEBUG:
                print("[LED] 更新PWM频率为:", str(new_freq) + "Hz")
        except (OSError, ValueError) as e:
            if DEBUG:
                print("[LED] [ERROR] PWM频率更新失败:", str(e))

    def _update_max_brightness(self, new_config):
        """更新最大亮度""
        if 'max_brightness' in new_config:
            self.current_max_brightness = new_config['max_brightness']
            if DEBUG:
                print("[LED] 更新最大亮度为:", str(self.current_max_brightness))

    def _on_led_set_effect(self, **event_data):
        """处理设置LED效果的事�?""
        mode = event_data.get('mode', 'off')
        led_num = event_data.get('led_num', 1)
        brightness = event_data.get('brightness', self.current_max_brightness)
        self.set_effect(mode, led_num, brightness)

    def _on_led_set_brightness(self, **event_data):
        """处理设置LED亮度的事�?""
        led_num = event_data.get('led_num', 1)
        brightness = event_data.get('brightness', self.current_max_brightness)
        self.set_brightness(led_num, brightness)

    def _on_led_emergency_off(self, **_event_data):
        """处理紧急关闭LED的事�?""
        if DEBUG:
            print("[LED] 收到紧急关闭信�?)
        self.set_effect('off')
        if self.event_bus:
            self.event_bus.publish(get_event_id('led_emergency_off_completed'))

    async def _on_wifi_connecting_blink(self, **_event_data):
        """WiFi连接时的LED闪烁指示"""
        if not self.pwm1 or not self.pwm2:
            return

        # 异步闪烁：使用asyncio.sleep实现非阻塞延�?        self.pwm1.duty_u16(self.current_max_brightness)
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

            # 转换�?6位PWM�?            duty = int(brightness * 65535 / self.current_max_brightness) if self.current_max_brightness > 0 else 0

            if led_num == 1 and self.pwm1:
                self.pwm1.duty_u16(duty)
                self.led1_brightness = brightness
            elif led_num == 2 and self.pwm2:
                self.pwm2.duty_u16(duty)
                self.led2_brightness = brightness
            elif led_num == 0:  # 两个LED都设�?                if self.pwm1:
                    self.pwm1.duty_u16(duty)
                    self.led1_brightness = brightness
                if self.pwm2:
                    self.pwm2.duty_u16(duty)
                    self.led2_brightness = brightness

            return True
        except (OSError, ValueError, AttributeError) as e:
            if DEBUG:
                print("[LED] 设置亮度失败:", str(e))
            return False

    def set_effect(self, mode='off', led_num=1, brightness_u16=None):
        """设置LED效果"""
        if not self.initialized:
            if DEBUG:
                print("[LED] [WARNING] PWM未初始化，无法设置灯�?)
            return False

        if brightness_u16 is None:
            brightness_u16 = self.current_max_brightness

        if DEBUG:
            print("[LED] 设置灯效�?", mode)

        self.current_effect = mode
        self.effect_params = {'led_num': led_num, 'brightness_u16': brightness_u16}

        # 使用字典映射来减少分�?        effect_handlers = {
            'off': self._handle_off_effect,
            'single_on': self._handle_single_on_effect,
            'both_on': self._handle_both_on_effect
        }

        blink_effects = ['fast_blink', 'slow_blink', 'alternate_blink', 'double_blink', 'heartbeat_blink']

        if mode in effect_handlers:
            effect_handlers[mode](led_num, brightness_u16)
        elif mode in blink_effects:
            self._handle_blink_effect()
        else:
            self._handle_unknown_effect(mode)

        # 发布灯效变化事件
        if self.event_bus:
            self.event_bus.publish(get_event_id('led_effect_changed'),
                        effect=self.current_effect,
                        params=self.effect_params)

        return True

    def _handle_off_effect(self, _led_num, _brightness_u16):
        """处理关闭效果"""
        self.set_brightness(1, 0)
        self.set_brightness(2, 0)

    def _handle_single_on_effect(self, led_num, brightness_u16):
        """处理单个LED开启效�?""
        if led_num == 1:
            self.set_brightness(1, brightness_u16)
            self.set_brightness(2, 0)
        else:
            self.set_brightness(1, 0)
            self.set_brightness(2, brightness_u16)

    def _handle_both_on_effect(self, _led_num, brightness_u16):
        """处理两个LED都开启效�?""
        self.set_brightness(1, brightness_u16)
        self.set_brightness(2, brightness_u16)

    def _handle_blink_effect(self):
        """处理闪烁效果"""
        self.blink_state = False
        self.blink_counter = 0

    def _handle_unknown_effect(self, mode):
        """处理未知效果"""
        error_msg = "未知的灯效模�? " + mode
        if DEBUG:
            print("[LED] [WARNING]", error_msg)
        if self.event_bus:
            self.event_bus.publish(get_event_id('log_warning'), message=error_msg)
        self.current_effect = 'off'

    def start_led_task(self):
        """启动LED异步任务"""
        if not self.task_running:
            self.task_running = True
            self.led_task = asyncio.create_task(self._led_effect_task())
            if DEBUG:
                print("[LED] LED异步任务已启�?)

    def stop_led_task(self):
        """停止LED异步任务"""
        self.task_running = False
        if self.led_task and not self.led_task.done():
            self.led_task.cancel()
            if DEBUG:
                print("[LED] LED异步任务已停�?)

    async def _led_effect_task(self):
        """LED效果异步任务：处理各种闪烁效�?""
        print("[LED] LED效果异步任务已启�?)

        # 效果处理器映�?        effect_handlers = {
            'fast_blink': self._handle_fast_blink,
            'slow_blink': self._handle_slow_blink,
            'alternate_blink': self._handle_alternate_blink,
            'double_blink': self._handle_double_blink,
            'heartbeat_blink': self._handle_heartbeat_blink
        }

        while self.task_running:
            try:
                handler = effect_handlers.get(self.current_effect)
                if handler:
                    await handler()
                else:
                    # 非动画模式下，使用动态更新间�?                    await asyncio.sleep_ms(self.led_update_interval_ms)

            except (OSError, ValueError, AttributeError,
                    asyncio.CancelledError) as e:
                error_msg = "LED效果任务错误: " + str(e)
                if DEBUG:
                    print("[LED] [ERROR]", error_msg)
                if self.event_bus:
                    self.event_bus.publish(get_event_id('log_warning'), message=error_msg)
                # 发生错误时等待更长时间，避免错误循环
                await asyncio.sleep_ms(2000)

        print("[LED] LED效果异步任务已停�?)

    async def _handle_fast_blink(self):
        """处理快闪效果"""
        if self.pwm1 and self.pwm2:
            brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
            self._toggle_both_leds(brightness)
        await asyncio.sleep_ms(200)

    async def _handle_slow_blink(self):
        """处理慢闪效果"""
        if self.pwm1 and self.pwm2:
            brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
            self._toggle_both_leds(brightness)
        await asyncio.sleep_ms(1000)

    async def _handle_alternate_blink(self):
        """处理交替闪烁效果"""
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

    async def _handle_double_blink(self):
        """处理双闪效果"""
        if not (self.pwm1 and self.pwm2):
            return

        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
        self.blink_counter += 1

        if self.blink_counter <= 4:  # 两次闪烁（开-�?开-关）
            self._toggle_both_leds(brightness)
            await asyncio.sleep_ms(150)
        else:
            # 暂停阶段
            self.set_brightness(1, 0)
            self.set_brightness(2, 0)
            await asyncio.sleep_ms(800)
            self.blink_counter = 0
            self.blink_state = False

    async def _handle_heartbeat_blink(self):
        """处理心跳闪烁效果"""
        if not (self.pwm1 and self.pwm2):
            return

        brightness = self.effect_params.get('brightness_u16', self.current_max_brightness)
        self.blink_counter += 1

        if self.blink_counter == 1:
            # 第一次跳�?            await self._heartbeat_pulse(brightness)
        elif self.blink_counter == 2:
            # 第二次跳�?            await self._heartbeat_pulse(brightness)
            await asyncio.sleep_ms(600)  # 长暂�?            self.blink_counter = 0
        else:
            self.blink_counter = 0

    def _toggle_both_leds(self, brightness):
        """切换两个LED的状�?""
        if self.blink_state:
            self.set_brightness(1, brightness)
            self.set_brightness(2, brightness)
        else:
            self.set_brightness(1, 0)
            self.set_brightness(2, 0)
        self.blink_state = not self.blink_state

    async def _heartbeat_pulse(self, brightness):
        """心跳脉冲"""
        self.set_brightness(1, brightness)
        self.set_brightness(2, brightness)
        await asyncio.sleep_ms(100)
        self.set_brightness(1, 0)
        self.set_brightness(2, 0)
        await asyncio.sleep_ms(100)

    def get_status(self):
        """获取LED状�?""
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

# 全局LED管理器实例（向后兼容�?_global_led_manager = None

def _ensure_global_led_manager():
    """确保全局LED管理器已初始化（向后兼容�?""
    # pylint: disable=global-statement,import-outside-toplevel
    global _global_led_manager
    if _global_led_manager is None:
        # 导入core和config以保持向后兼容�?        try:
            from . import core
            from . import config
            _global_led_manager = LEDManager(event_bus=core, config_getter=config)
        except ImportError:
            _global_led_manager = LEDManager()
    return _global_led_manager

# 外部接口函数
def init_led():
    """初始化LED"""
    manager = _ensure_global_led_manager()
    return manager.init()

def deinit_led():
    """关闭LED"""
    manager = _ensure_global_led_manager()
    manager.deinit()

def set_led_effect(effect, **params):
    """设置LED效果"""
    manager = _ensure_global_led_manager()
    led_num = params.get('led_num', 1)
    brightness = params.get('brightness', manager.current_max_brightness)
    return manager.set_effect(effect, led_num, brightness)

def set_led_brightness(led_num, brightness):
    """设置LED亮度"""
    manager = _ensure_global_led_manager()
    return manager.set_brightness(led_num, brightness)

def start_led_task():
    """启动LED异步任务"""
    manager = _ensure_global_led_manager()
    manager.start_led_task()

def stop_led_task():
    """停止LED异步任务"""
    manager = _ensure_global_led_manager()
    manager.stop_led_task()

def emergency_led_off():
    """紧急关闭LED"""
    manager = _ensure_global_led_manager()
    manager.set_effect('off')

def get_led_status():
    """获取LED状�?""
    manager = _ensure_global_led_manager()
    return manager.get_status()

def update_led_config(new_config):
    """更新LED配置"""
    manager = _ensure_global_led_manager()
    # pylint: disable=protected-access
    manager._on_config_update(config=new_config, source='manual')

# 依赖注入接口
def create_led_manager(event_bus, config_getter):
    """创建LED管理器实例（依赖注入�?""
    return LEDManager(event_bus=event_bus, config_getter=config_getter)