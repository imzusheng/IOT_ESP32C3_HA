# -*- coding: utf-8 -*-
# app/utils/timers.py
"""
ESP32-C3 硬件定时器管理器。

用法:
- from utils import get_hardware_timer_manager
- tm = get_hardware_timer_manager()
- timer = tm.create_timer(period_ms, callback, mode=machine.Timer.PERIODIC)
- tm.release_timer(timer) 使用完毕后释放

注意:
- 从有限的硬件定时器 [0..MAX_HARDWARE_TIMERS-1] 中分配。
"""

import machine
from lib.logger import warning, error

# 可配置常量
MAX_HARDWARE_TIMERS = 2
MODULE_NAME = "Timer"


class HardwareTimerManager:
    """
    管理 ESP32 硬件定时器。
    """

    def __init__(self):
        self.timers = {}
        self.used_ids = set()

    def get_available_timer(self):
        """获取可用的硬件定时器 ID。"""
        for timer_id in range(MAX_HARDWARE_TIMERS):  # ESP32 有 MAX_HARDWARE_TIMERS 个硬件定时器
            if timer_id not in self.used_ids:
                return timer_id
        return None

    def create_timer(self, period_ms, callback, mode=machine.Timer.PERIODIC):
        """创建硬件定时器。返回定时器实例，失败时返回 None。"""
        timer_id = self.get_available_timer()
        if timer_id is None:
            warning("没有可用的硬件定时器", module=MODULE_NAME)
            return None

        try:
            timer = machine.Timer(timer_id)
            timer.init(period=period_ms, mode=mode, callback=callback)

            self.timers[timer_id] = timer
            self.used_ids.add(timer_id)

            return timer
        except Exception as e:
            error(f"创建硬件定时器{timer_id}失败: {e}", module=MODULE_NAME)
            return None

    def release_timer(self, timer):
        """释放硬件定时器。"""
        if timer in self.timers.values():
            timer_id = None
            for tid, t in self.timers.items():
                if t == timer:
                    timer_id = tid
                    break

            if timer_id is not None:
                try:
                    timer.deinit()
                    del self.timers[timer_id]
                    self.used_ids.remove(timer_id)
                except Exception as e:
                    error(f"释放定时器{timer_id}失败: {e}", module=MODULE_NAME)


# 全局硬件定时器管理器实例
_hardware_timer_manager = HardwareTimerManager()


def get_hardware_timer_manager():
    """获取全局硬件定时器管理器实例。"""
    return _hardware_timer_manager
