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
    import time
except Exception:  # 构建环境容错
    machine = None
    time = None

try:
    import micropython
except Exception:
    micropython = None

from lib.logger import info, warning, error, debug
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
    - MCU 温度超过阈值时重启进入安全模式
    - 完全自包含, 无外部配置依赖
    """

    # 配置常量 - 提取硬编码值到顶部
    TEMP_THRESHOLD_C = 50          # 温度阈值, 单位: 摄氏度
    TEMP_MIN_VALID = 0           # 最小有效温度
    TEMP_MAX_VALID = 125           # 最大有效温度
    TEMP_DEBOUNCE_COUNT = 5        # 温度防抖动: 连续N次超阈值才触发
    MAX_ERROR_COUNT = 10           # 最大错误计数
    ERROR_WINDOW_MINUTES = 5       # 错误计数时间窗口(分钟)
    PERIOD_MS = 1000              # 默认定时周期(毫秒)
    REBOOT_DELAY_MS = 2000        # 重启前延迟(毫秒)
    SAFE_MODE_TEMP_LOG_INTERVAL = 3  # 安全模式下温度日志间隔(秒)
    DEBUG_LOG_INTERVAL = 3         # 调试日志间隔(ticks)

    # 内置配置 - 避免外部依赖(向后兼容)
    DEFAULT_CONFIG = {
        "max_error_count": MAX_ERROR_COUNT,
        "period_ms": PERIOD_MS,
        "temp_threshold_c": TEMP_THRESHOLD_C,
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
        self._ticks = 0
        
        # 温度防抖动: 记录最近3次温度读数
        self._temp_history = []
        
        # 错误时间窗口: 记录错误发生时间
        self._error_timestamps = []
        
        # 安全模式状态
        self._in_safe_mode = False

    # --------------------------- 内部: 工具方法 ---------------------------
    
    def _cleanup_old_errors(self, current_time):
        """清理超出时间窗口的错误记录"""
        try:
            # 计算时间窗口(毫秒)
            window_ms = self.ERROR_WINDOW_MINUTES * 60 * 1000
            cutoff_time = current_time - window_ms
            
            # 过滤超时错误
            self._error_timestamps = [
                ts for ts in self._error_timestamps 
                if time.ticks_diff(current_time, ts) <= window_ms
            ]
        except Exception:
            # 容错: 清空所有错误记录
            self._error_timestamps.clear()
    
    def _is_valid_temperature(self, temp_c):
        """验证温度读数合理性"""
        if temp_c is None:
            return False
        try:
            return self.TEMP_MIN_VALID <= float(temp_c) <= self.TEMP_MAX_VALID
        except (ValueError, TypeError):
            return False
    
    def _add_temp_sample(self, temp_c):
        """添加温度样本到历史记录"""
        if self._is_valid_temperature(temp_c):
            self._temp_history.append(temp_c)
            # 保持最近N次记录
            if len(self._temp_history) > self.TEMP_DEBOUNCE_COUNT:
                self._temp_history.pop(0)
    
    def _check_temp_threshold(self):
        """检查温度是否连续超过阈值"""
        if len(self._temp_history) < self.TEMP_DEBOUNCE_COUNT:
            return False
        
        # 检查最近N次读数是否都超阈值
        threshold = self.TEMP_THRESHOLD_C
        return all(temp >= threshold for temp in self._temp_history[-self.TEMP_DEBOUNCE_COUNT:])

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
            info("守护服务已启动, period={}ms, 温度阈值={}°C", 
                 self._period_ms, self.TEMP_THRESHOLD_C, module=MODULE_NAME)
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
        """增加错误计数(带时间窗口), 返回最新计数。"""
        try:
            current_time = time.ticks_ms() if time else 0
            # 添加新错误时间戳
            for _ in range(int(delta)):
                self._error_timestamps.append(current_time)
            
            # 清理超出时间窗口的错误
            self._cleanup_old_errors(current_time)
            
            # 更新错误计数
            self._error_count = len(self._error_timestamps)
            
        except Exception:
            # 容错处理
            self._error_count += 1
            
        return self._error_count

    def reset_error(self):
        """重置错误计数和时间窗口。"""
        self._error_count = 0
        self._error_timestamps.clear()

    def get_status(self) -> dict:
        """获取守护服务状态。"""
        return {
            "running": self._running,
            "period_ms": self._period_ms,
            "error_count": self._error_count,
            "ticks": self._ticks,
        }

    # --------------------------- 核心守护逻辑 ---------------------------

    def _scheduled_tick(self, _):
        """由 IRQ 调度, 在主上下文执行的轻量维护逻辑。"""
        if not self._running:
            return
            
        self._ticks += 1

        # 1) 温度阈值检查(带防抖动和数据验证)
        try:
            temp_c = get_temperature()
            
            # 添加温度样本到历史记录
            self._add_temp_sample(temp_c)
            
            # 安全模式下仅记录温度,不触发重启
            if self._in_safe_mode:
                if self._ticks % self.SAFE_MODE_TEMP_LOG_INTERVAL == 0:
                    if self._is_valid_temperature(temp_c):
                        info("安全模式 - MCU温度: {}°C", temp_c, module=MODULE_NAME)
                    else:
                        warning("安全模式 - 温度读取失败或异常", module=MODULE_NAME)
                return
            
            # 调试信息：每3秒记录一次温度检查
            if self._ticks % self.DEBUG_LOG_INTERVAL == 0:
                if self._is_valid_temperature(temp_c):
                    debug("守护温度检查: {}°C (阈值: {}°C, 历史:{}次)", 
                          temp_c, self.TEMP_THRESHOLD_C, len(self._temp_history), module=MODULE_NAME)
                else:
                    warning("温度读取异常: {} (应在{}-{}°C范围内)", 
                           temp_c, self.TEMP_MIN_VALID, self.TEMP_MAX_VALID, module=MODULE_NAME)
            
            # 检查是否连续超阈值
            if self._check_temp_threshold():
                warning("温度保护触发: 连续{}次超过{}°C阈值 (最近温度: {})", 
                       self.TEMP_DEBOUNCE_COUNT, self.TEMP_THRESHOLD_C, self._temp_history[-3:], module=MODULE_NAME)
                self._request_safe_mode_and_reboot()
                return  # 重启前不再执行其他逻辑
                    
        except Exception as e:
            error("温度检查异常: {}", e, module=MODULE_NAME)

        # 2) 错误阈值检查(带时间窗口)
        try:
            # 清理超时错误
            current_time = time.ticks_ms() if time else 0
            self._cleanup_old_errors(current_time)
            
            max_err = self.MAX_ERROR_COUNT
            if max_err > 0 and self._error_count >= max_err:
                warning("错误计数达阈值(窗口内max={}), 触发安全模式并重启", max_err, module=MODULE_NAME)
                self._request_safe_mode_and_reboot()
                return
        except Exception:
            pass

    # --------------------------- 安全模式重启 ---------------------------

    def _request_safe_mode_and_reboot(self):
        """请求安全模式并重启设备"""
        # 标记进入安全模式
        self._in_safe_mode = True
        
        # 创建安全模式标记
        _request_safe_mode()
        
        # 延迟重启,给系统留出清理时间
        try:
            if machine and hasattr(machine, "reset"):
                # 延迟重启,让日志输出完成
                import time
                time.sleep_ms(self.REBOOT_DELAY_MS)
                machine.reset()
        except Exception:
            pass


__all__ = ["Daemon"]