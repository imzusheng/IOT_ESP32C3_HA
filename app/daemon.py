# -*- coding: utf-8 -*-
"""
app/daemon.py

独立守护服务(硬件定时器驱动)
- 使用 HardwareTimerManager 分配独立硬件定时器
- 周期性任务极轻量: 错误计数阈值检查与重启 + MCU温度阈值保护
- 完全自包含, 无外部配置依赖

注意:
- 本模块不在导入时启动任何逻辑, 仅提供 Daemon 类供外部按需使用
- 定时器回调仅做 schedule 调度, 真正逻辑在主上下文执行
"""

try:
    import machine
except Exception:  # 构建环境容错
    machine = None

try:
    import micropython
except Exception:
    micropython = None

from lib.logger import info, warning, error
from utils import get_hardware_timer_manager, get_temperature

MODULE_NAME = "DAEMON"


def _request_safe_mode():
    """创建安全模式标记文件, 供 boot.py 在下次启动时进入安全模式"""
    try:
        import os
        # 在根目录放置标记文件, boot.py 检测后会删除
        with open("/safemode.flag", "w") as f:
            f.write("1")
    except Exception:
        # 文件系统不可用时忽略, 继续执行重启
        pass


class Daemon:
    """守护服务

    功能:
    - 独立硬件定时器驱动的轻量任务
    - 错误计数达到阈值后触发重启
    - MCU 温度超过阈值时立即触发重启
    - 完全自包含, 无外部配置依赖
    """

    # 内置配置 - 避免外部依赖
    DEFAULT_CONFIG = {
        "max_error_count": 10,
        "period_ms": 1000,
        "temp_threshold_c": 30,  # 温度阈值, 单位: 摄氏度
    }

    def __init__(self):
        # 使用内置配置
        self.cfg = self.DEFAULT_CONFIG.copy()

        # 状态
        self._timer_mgr = None
        self._timer = None
        self._period_ms = self.cfg["period_ms"]
        self._running = False
        self._error_count = 0
        self._rebooting = False
        self._ticks = 0

    # --------------------------- 内部: 清理 ---------------------------

    def _deinit_timer(self):
        try:
            if self._timer_mgr and self._timer:
                self._timer_mgr.release_timer(self._timer)
        except Exception:
            pass
        finally:
            self._timer = None

    # --------------------------- 对外 API ---------------------------

    def start(self, period_ms: int = None) -> bool:
        """启动守护服务(硬件定时器驱动)。
        - period_ms: 定时周期, 默认使用内置配置
        返回是否成功创建定时器。
        """
        if self._running:
            return True

        if period_ms is not None and period_ms > 0:
            self._period_ms = int(period_ms)
        else:
            self._period_ms = self.cfg["period_ms"]

        try:
            self._timer_mgr = get_hardware_timer_manager()
            # 在 IRQ 中仅调度, 避免在中断中执行复杂逻辑
            def _irq_cb(_t):
                if micropython and hasattr(micropython, "schedule"):
                    try:
                        micropython.schedule(self._scheduled_tick, 0)
                    except Exception:
                        pass
                else:
                    # 降级: 在 IRQ 里直接执行, 限制逻辑足够轻量
                    try:
                        self._scheduled_tick(0)
                    except Exception:
                        pass

            self._timer = self._timer_mgr.create_timer(self._period_ms, _irq_cb)
            if not self._timer:
                warning("守护定时器创建失败(可能无可用硬件定时器)", module=MODULE_NAME)
                return False

            self._running = True
            info("守护服务已启动, period={}ms", self._period_ms, module=MODULE_NAME)
            return True
        except Exception as e:
            error("守护服务启动失败: {}", e, module=MODULE_NAME)
            self._deinit_timer()
            return False

    def stop(self):
        """停止守护服务并释放定时器。"""
        self._running = False
        self._deinit_timer()
        info("守护服务已停止", module=MODULE_NAME)

    def incr_error(self, delta: int = 1) -> int:
        """增加错误计数, 返回最新计数。"""
        try:
            self._error_count += int(delta)
        except Exception:
            self._error_count += 1
        return self._error_count

    def reset_error(self):
        """重置错误计数。"""
        self._error_count = 0

    def get_status(self) -> dict:
        """获取守护服务状态。"""
        return {
            "running": self._running,
            "period_ms": self._period_ms,
            "error_count": self._error_count,
            "ticks": self._ticks,
        }

    # --------------------------- 调度执行逻辑(主上下文) ---------------------------

    def _scheduled_tick(self, _):
        """由 IRQ 调度, 在主上下文执行的轻量维护逻辑。"""
        if not self._running:
            return
        self._ticks += 1

        # 1) 温度阈值检查, 立即触发
        try:
            temp_c = get_temperature()
            thr = int(self.cfg.get("temp_threshold_c", 50))
            if temp_c is not None and temp_c >= thr and not self._rebooting:
                self._rebooting = True
                warning("MCU温度过高: {}°C >= 阈值 {}°C, 触发安全模式并重启", temp_c, thr, module=MODULE_NAME)
                _request_safe_mode()
                if machine and hasattr(machine, "reset"):
                    try:
                        machine.reset()
                    except Exception:
                        pass
        except Exception:
            pass

        # 2) 错误阈值检查
        try:
            max_err = int(self.cfg["max_error_count"])
            if max_err > 0 and self._error_count >= max_err and not self._rebooting:
                self._rebooting = True
                warning("错误计数达阈值(max={}), 触发安全模式并重启", max_err, module=MODULE_NAME)
                _request_safe_mode()
                if machine and hasattr(machine, "reset"):
                    try:
                        machine.reset()
                    except Exception:
                        pass
        except Exception:
            pass


__all__ = ["Daemon"]