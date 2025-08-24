# -*- coding: utf-8 -*-
"""
通用LED预设闪烁模块 (v6.1 - 优化版)

主要特性:
- 硬件定时器驱动: 完全独立于主循环和asyncio, 不会被任何代码阻塞
- 开箱即用: 无需初始化, 直接调用函数即可使用
- 延迟初始化: 首次调用时自动初始化
- 单例模式: 防止重复实例化, 保证硬件控制的唯一性
- 高度统一: 所有模式均由同一逻辑驱动
- 易于扩展: 添加新模式只需定义一个新的时间序列
"""

import machine
import utime as time
from lib.logger import error
# 注意: utils 模块的导入在 _init_hardware_timer() 中进行, 避免循环导入问题, utils 可能依赖于其他硬件模块

# =============================================================================
# 配置常量
# =============================================================================

# 默认LED引脚配置
DEFAULT_LED_PINS = [12, 13]

# 定时器参数
TIMER_PERIOD_MS = 50  # 硬件定时器周期, 50ms保证精确性

# 日志模块名
MODULE_NAME = "LED"

# 默认启动模式
DEFAULT_STARTUP_MODE = "cruise"

# 所有模式均定义为"亮-灭"时间序列 (单位: ms)
BLINK_SEQUENCE = [500, 500]
PULSE_SEQUENCE = [150, 150, 150, 850]
CRUISE_SEQUENCE = [50, 1500]
SOS_SEQUENCE = [
    200, 200, 200, 200, 200, 700,  # S
    600, 200, 600, 200, 600, 700,  # O
    200, 200, 200, 200, 200, 2000,  # S
]

# =============================================================================
# 内部实现类
# =============================================================================


class _LEDPatternController:
    """
    LED模式控制器的内部实现类。
    采用硬件定时器实现完全非阻塞的LED控制。
    """

    def __init__(self, led_pins: list):
        """初始化LED模式控制器"""
        self.led_pins = led_pins
        self.leds = self._init_leds()

        if not self.leds:
            error("没有有效的LED被初始化", module=MODULE_NAME)
            return

        # 模式和状态变量
        self.current_pattern_id = "off"
        self.pattern_state = {}

        # 硬件定时器相关
        self._timer = None
        self._timer_manager = None

        # 模式字典
        self.patterns = {
            "off": self._update_off,
            "blink": lambda: self._update_sequence(BLINK_SEQUENCE),
            "pulse": lambda: self._update_sequence(PULSE_SEQUENCE),
            "cruise": lambda: self._update_sequence(CRUISE_SEQUENCE),
            "sos": lambda: self._update_sequence(SOS_SEQUENCE),
        }

        # 初始化硬件定时器
        self._init_hardware_timer()
        # 初始化即进入默认模式, 避免外部依赖
        try:
            self.play(DEFAULT_STARTUP_MODE)
        except Exception:
            pass

    def _init_leds(self) -> list:
        """根据引脚列表初始化LED对象。"""
        leds = []
        for pin in self.led_pins:
            try:
                leds.append(machine.Pin(pin, machine.Pin.OUT, value=0))
            except Exception as e:
                error(f"初始化引脚{pin}的LED失败: {e}", module=MODULE_NAME)
                leds.append(None)
        return [led for led in leds if led is not None]

    def _init_hardware_timer(self):
        """初始化硬件定时器"""
        try:
            from utils import get_hardware_timer_manager
            self._timer_manager = get_hardware_timer_manager()
            self._timer = self._timer_manager.create_timer(
                TIMER_PERIOD_MS, self._timer_callback
            )
            if not self._timer:
                error("LED硬件定时器创建失败", module=MODULE_NAME)
        except Exception as e:
            error(f"LED硬件定时器初始化失败: {e}", module=MODULE_NAME)

    def _timer_callback(self, timer):
        """硬件定时器回调函数"""
        try:
            handler = self.patterns.get(self.current_pattern_id)
            if handler:
                handler()
        except Exception:
            # 静默异常, 避免影响硬件定时器稳定性
            pass

    def play(self, pattern_id: str):
        """
        播放一个预设的闪烁模式。
        由硬件定时器独立驱动, 不依赖任何外部循环。
        """
        if pattern_id not in self.patterns:
            error(f"未知的模式ID '{pattern_id}'", module=MODULE_NAME)
            return

        self.current_pattern_id = pattern_id
        self.pattern_state = {"step": 0, "last_update": time.ticks_ms()}

        # 立即设置初始状态
        if pattern_id == "off":
            self._set_all_leds(0)
        else:
            # 大多数模式以"亮"开始
            self._set_all_leds(1)

    def _set_all_leds(self, value: int):
        """辅助函数, 设置所有LED的状态。"""
        for led in self.leds:
            led.value(value)

    def _update_off(self):
        """关闭所有LED。"""
        self._set_all_leds(0)

    def _update_sequence(self, sequence: list):
        """通用序列处理器。"""
        state = self.pattern_state
        current_time = time.ticks_ms()
        step = state.get("step", 0)

        if time.ticks_diff(current_time, state["last_update"]) >= sequence[step]:
            state["step"] = (step + 1) % len(sequence)
            state["last_update"] = current_time
            is_on = state["step"] % 2 == 0
            self._set_all_leds(is_on)

    def cleanup(self):
        """清理资源。"""
        self._set_all_leds(0)
        if self._timer and self._timer_manager:
            try:
                self._timer_manager.release_timer(self._timer)
            except Exception:
                pass


# =============================================================================
# 模块级别的单例实例和全局函数
# =============================================================================

# 全局单例实例
_instance = None


def _get_instance():
    """获取或创建LED控制器实例(延迟初始化)"""
    global _instance
    if _instance is None:
        _instance = _LEDPatternController(DEFAULT_LED_PINS)
    return _instance


# =============================================================================
# 公共接口函数
# =============================================================================


def play(pattern_id: str):
    """
    播放LED模式。
    首次调用时会自动初始化LED控制器。

    Args:
        pattern_id (str): 模式ID, 支持 'off', 'blink', 'pulse', 'cruise', 'sos' ...

    Example:
        from hw.led import play
        play('blink')  # 闪烁模式
    """
    controller = _get_instance()
    controller.play(pattern_id)


def cleanup():
    """
    清理LED资源。

    Example:
        from hw.led import cleanup
        cleanup()  # 清理LED控制器
    """
    global _instance
    if _instance:
        _instance.cleanup()
        _instance = None


# LED module loaded silently