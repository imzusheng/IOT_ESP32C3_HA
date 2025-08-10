# -*- coding: utf-8 -*-
"""
通用LED预设闪烁模块 (v4.2 - 单例模式)

主要特性:
- 单例模式: 防止重复实例化，保证硬件控制的唯一性。
- 高度统一: 所有模式均由同一逻辑驱动。
- 易于扩展: 添加新模式只需定义一个新的时间序列。
"""

import machine
import utime as time
import micropython
from lib.logger import get_global_logger

# 尝试导入uasyncio，如果失败则禁用该功能
try:
    import uasyncio
    UASYNCIO_AVAILABLE = True
except ImportError:
    UASYNCIO_AVAILABLE = False

class LEDPatternController:
    """
    管理一组LED并根据预设ID播放闪烁模式。
    采用单例模式实现，并使用一个通用的序列处理器来驱动所有模式。
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(LEDPatternController, cls).__new__(cls)
        return cls._instance

    # --- 模式参数常量 ---
    TIMER_PERIOD_MS = 50

    # 所有模式均定义为“亮-灭”时间序列 (单位: ms)
    BLINK_SEQUENCE = [500, 500]
    PULSE_SEQUENCE = [150, 150, 150, 850]
    CRUISE_SEQUENCE = [50, 950]
    SOS_SEQUENCE = [
        200, 200, 200, 200, 200, 700, # S
        600, 200, 600, 200, 600, 700, # O
        200, 200, 200, 200, 200, 2000, # S
    ]

    def __init__(self, led_pins: list = None):
        """
        初始化LED模式控制器。
        由于是单例，只有在第一次实例化时led_pins参数才会生效。

        Args:
            led_pins (list, optional): 一个包含LED引脚编号的列表。仅在首次创建时需要。
        """
        if self._initialized:
            return

        # 初始化logger
        self.logger = get_global_logger()
        
        if not led_pins:
            self.logger.error("首次实例化时必须提供至少一个LED引脚", module="LED")
            return

        self.led_pins = led_pins
        self.leds = self._init_leds()

        if not self.leds:
            self.logger.error("没有有效的LED被初始化", module="LED")
            return

        # 模式和状态变量
        self.current_pattern_id = 'off'
        self.pattern_state = {}
        # 调度标记：避免重复调度导致队列溢出
        self._is_update_scheduled = False

        # 模式字典
        self.patterns = {
            'off': self._update_off,
            'blink': lambda: self._update_sequence(self.BLINK_SEQUENCE),
            'pulse': lambda: self._update_sequence(self.PULSE_SEQUENCE),
            'cruise': lambda: self._update_sequence(self.CRUISE_SEQUENCE),
            'sos': lambda: self._update_sequence(self.SOS_SEQUENCE),
        }

        # 运行控制器 (定时器或uasyncio任务)
        self.timer = None
        self.uasyncio_task = None
        self._start_controller()

        self._initialized = True
        self.logger.info(f"控制器已初始化，引脚: {self.led_pins}", module="LED")


    def _init_leds(self) -> list:
        """根据引脚列表初始化LED对象。"""
        leds = []
        for pin in self.led_pins:
            try:
                leds.append(machine.Pin(pin, machine.Pin.OUT, value=0))
            except Exception as e:
                self.logger.error(f"初始化引脚{pin}的LED失败: {e}", module="LED")
                leds.append(None)
        return [led for led in leds if led is not None]

    def _start_controller(self):
        """尝试启动硬件定时器，如果失败则尝试启动uasyncio任务。"""
        if self._start_hardware_timer():
            return
        if UASYNCIO_AVAILABLE and self._start_uasyncio_task():
            return
        self.logger.warning("无法启动控制器，模式将不会运行", module="LED")

    def _start_hardware_timer(self) -> bool:
        """尝试启动一个硬件定时器。"""
        for i in range(4):
            try:
                self.timer = machine.Timer(i)
                self.timer.init(period=self.TIMER_PERIOD_MS, mode=machine.Timer.PERIODIC, callback=self._update_callback)
                return True
            except (ValueError, OSError):
                self.timer = None
                continue
        return False

    def _start_uasyncio_task(self) -> bool:
        """启动一个uasyncio任务作为备用方案。"""
        try:
            self.uasyncio_task = uasyncio.create_task(self._uasyncio_loop())
            return True
        except Exception as e:
            self.logger.error(f"启动uasyncio任务失败: {e}", module="LED")
            return False

    async def _uasyncio_loop(self):
        """uasyncio的异步更新循环。"""
        while True:
            self._update_patterns()
            await uasyncio.sleep_ms(self.TIMER_PERIOD_MS)

    def _update_callback(self, timer):
        """硬件定时器的回调函数。"""
        # 使用 schedule 在非中断上下文执行更新逻辑，并通过标志防止队列被塞满
        if not self._is_update_scheduled:
            self._is_update_scheduled = True
            try:
                micropython.schedule(self._scheduled_update, 0)
            except Exception as e:
                # 如果调度失败（例如队列满），立即清除标志，等待下次尝试
                self._is_update_scheduled = False
                self.logger.error(f"调度失败: {e}", module="LED")

    def _scheduled_update(self, _):
        """被调度执行的更新函数，保证不在中断上下文中运行。"""
        try:
            self._update_patterns()
        except Exception as e:
            self.logger.error(f"调度更新出错: {e}", module="LED")
        finally:
            # 清除调度中的标记，允许下一次调度
            self._is_update_scheduled = False

    def play(self, pattern_id: str):
        """
        播放一个预设的闪烁模式。
        通过停止和重启定时器来确保状态切换的原子性。
        """
        if pattern_id not in self.patterns:
            self.logger.error(f"未知的模式ID '{pattern_id}'", module="LED")
            return

        # 修复: 停止控制器以避免并发问题
        self._stop_controller()

        self.current_pattern_id = pattern_id
        self.pattern_state = {'step': 0, 'last_update': time.ticks_ms()}

        # 立即设置初始状态
        if pattern_id == 'off':
            self._set_all_leds(0)
        else:
            # 大多数模式以“亮”开始
            self._set_all_leds(1)
        
        # 重启控制器
        self._start_controller()

    def _stop_controller(self):
        """停止定时器或uasyncio任务。"""
        if self.timer:
            self.timer.deinit()
            self.timer = None
        if self.uasyncio_task:
            self.uasyncio_task.cancel()
            self.uasyncio_task = None

    def _update_patterns(self, _=None):
        """根据当前模式ID调用相应的更新函数。"""
        try:
            handler = self.patterns.get(self.current_pattern_id)
            if handler:
                handler()
        except Exception as e:
            self.logger.error(f"更新模式出错: {e}", module="LED")

    def _set_all_leds(self, value: int):
        """辅助函数，设置所有LED的状态。"""
        for led in self.leds:
            led.value(value)

    def _update_off(self):
        """关闭所有LED。"""
        self._set_all_leds(0)

    def _update_sequence(self, sequence: list):
        """通用序列处理器。"""
        state = self.pattern_state
        current_time = time.ticks_ms()
        step = state.get('step', 0)

        if time.ticks_diff(current_time, state['last_update']) >= sequence[step]:
            state['step'] = (step + 1) % len(sequence)
            state['last_update'] = current_time
            is_on = state['step'] % 2 == 0
            self._set_all_leds(is_on)

    def cleanup(self):
        """清理资源，停止控制器。"""
        if self.timer:
            self.timer.deinit()
            self.timer = None
        if self.uasyncio_task:
            self.uasyncio_task.cancel()
            self.uasyncio_task = None
        self._set_all_leds(0)
        self.logger.info("控制器已清理", module="LED")

# 模块初始化
# LED pattern module loaded
