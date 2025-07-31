# -*- coding: utf-8 -*-
"""
增强守护进程模块

为ESP32C3设备提供高度可靠和内存优化的守护进程功能：
- 硬件监控（温度、内存、LED）
- 看门狗保护
- 安全模式管理
- 任务调度
- 状态管理
- 内存优化
"""

import time
import machine
import gc
import sys
from typing import Dict, List, Optional, Callable

try:
    import esp32
except ImportError:
    # 模拟esp32模块用于测试
    class MockESP32:
        @staticmethod
        def mcu_temperature():
            return 45.0
    esp32 = MockESP32()

# 导入配置和错误处理
try:
    import config
    import error_handler
except ImportError:
    # 如果导入失败，使用简化版本
    print("警告：无法导入配置和错误处理模块，使用简化配置")
    
    class MockConfig:
        DaemonConfig = type('DaemonConfig', (), {
            'LED_PINS': [12, 13],
            'TEMP_THRESHOLD': 60.0,
            'TEMP_HYSTERESIS': 10.0,
            'MEMORY_THRESHOLD': 90,
            'MEMORY_HYSTERESIS': 10,
            'WDT_TIMEOUT': 8000,
            'WDT_FEED_INTERVAL': 4000,
            'TIMER_ID': 0,
            'MONITOR_INTERVAL': 30000,
            'SAFE_MODE_COOLDOWN': 30000,
            'MAX_ERROR_COUNT': 5,
            'ERROR_RESET_INTERVAL': 60000,
            'GC_INTERVAL_NORMAL': 10000,
            'GC_INTERVAL_SAFE': 5000,
            'GC_FORCE_THRESHOLD': 95
        })()
    
    config = MockConfig()
    
    class MockErrorHandler:
        def debug(self, msg, module=""): print(f"[DEBUG] {msg}")
        def info(self, msg, module=""): print(f"[INFO] {msg}")
        def warning(self, msg, module=""): print(f"[WARNING] {msg}")
        def error(self, msg, module=""): print(f"[ERROR] {msg}")
        def critical(self, msg, module=""): print(f"[CRITICAL] {msg}")
    
    error_handler = MockErrorHandler()

# =============================================================================
# 状态管理类
# =============================================================================

class SystemState:
    """系统状态管理器"""
    
    def __init__(self):
        self._state = {
            'daemon_active': False,
            'safe_mode_active': False,
            'safe_mode_start_time': 0,
            'start_time': 0,
            'monitor_count': 0,
            'error_count': 0,
            'last_error_time': 0,
            'last_gc_time': 0,
            'temperature': None,
            'memory_usage': None,
            'led_status': 'off'
        }
        self._state_lock = None  # 简化版本，无锁
    
    def get(self, key: str, default=None):
        """获取状态值"""
        return self._state.get(key, default)
    
    def set(self, key: str, value):
        """设置状态值"""
        self._state[key] = value
    
    def increment(self, key: str):
        """递增状态值"""
        self._state[key] = self._state.get(key, 0) + 1
    
    def get_all(self) -> Dict:
        """获取所有状态"""
        return self._state.copy()
    
    def reset(self):
        """重置状态"""
        self._state.clear()
        gc.collect()

# =============================================================================
# 增强看门狗类
# =============================================================================

class EnhancedWatchdog:
    """增强看门狗"""
    
    def __init__(self, timeout_ms: int = None):
        self.timeout_ms = timeout_ms or config.DaemonConfig.WDT_TIMEOUT
        self.feed_interval_ms = config.DaemonConfig.WDT_FEED_INTERVAL
        self._wdt = None
        self._last_feed_time = 0
        self._feed_count = 0
        self._logger = error_handler.get_logger()
    
    def init(self):
        """初始化看门狗"""
        try:
            self._wdt = machine.WDT(timeout=self.timeout_ms)
            self._last_feed_time = time.ticks_ms()
            self._logger.info(f"看门狗初始化成功，超时: {self.timeout_ms}ms", "Watchdog")
            return True
        except Exception as e:
            self._logger.error(f"看门狗初始化失败: {e}", "Watchdog")
            return False
    
    def feed(self):
        """喂狗"""
        if not self._wdt:
            return False
        
        try:
            current_time = time.ticks_ms()
            
            # 检查是否需要喂狗
            if time.ticks_diff(current_time, self._last_feed_time) >= self.feed_interval_ms:
                self._wdt.feed()
                self._last_feed_time = current_time
                self._feed_count += 1
                
                # 每100次喂狗记录一次日志
                if self._feed_count % 100 == 0:
                    self._logger.debug(f"看门狗喂狗计数: {self._feed_count}", "Watchdog")
            
            return True
        except Exception as e:
            self._logger.error(f"看门狗喂狗失败: {e}", "Watchdog")
            return False
    
    def deinit(self):
        """释放看门狗"""
        if self._wdt:
            try:
                self._wdt.deinit()
                self._wdt = None
                self._logger.info("看门狗已释放", "Watchdog")
            except Exception as e:
                self._logger.error(f"看门狗释放失败: {e}", "Watchdog")
    
    def get_feed_count(self):
        """获取喂狗计数"""
        return self._feed_count

# =============================================================================
# LED控制器类
# =============================================================================

class LEDController:
    """LED控制器"""
    
    def __init__(self, pins: List[int]):
        self.pins = pins
        self.leds = []
        self._logger = error_handler.get_logger()
        
        # 初始化LED
        for pin in pins:
            try:
                led = machine.Pin(pin, machine.Pin.OUT)
                led.off()
                self.leds.append(led)
            except Exception as e:
                self._logger.error(f"LED {pin} 初始化失败: {e}", "LEDController")
                self.leds.append(None)
        
        self._logger.info(f"LED控制器初始化完成，引脚: {pins}", "LEDController")
    
    def set_status(self, status: str):
        """设置LED状态"""
        valid_statuses = ['normal', 'warning', 'error', 'safe_mode', 'off']
        if status not in valid_statuses:
            self._logger.error(f"无效LED状态: {status}", "LEDController")
            return False
        
        try:
            if status == 'normal':
                self.leds[0].on() if self.leds[0] else None
                self.leds[1].off() if self.leds[1] else None
            elif status == 'warning':
                self.leds[0].on() if self.leds[0] else None
                self.leds[1].on() if self.leds[1] else None
            elif status == 'error':
                self.leds[0].off() if self.leds[0] else None
                self.leds[1].on() if self.leds[1] else None
            elif status == 'safe_mode':
                self._blink_alternating()
            elif status == 'off':
                for led in self.leds:
                    if led:
                        led.off()
            
            return True
        except Exception as e:
            self._logger.error(f"设置LED状态失败: {e}", "LEDController")
            return False
    
    def _blink_alternating(self):
        """交替闪烁LED（安全模式）"""
        safe_mode_start = error_handler.get_logger()._log_buffer._buffer[-1].get('timestamp', time.time()) if error_handler.get_logger()._log_buffer._buffer else time.time()
        current_time = time.time()
        cycle_time = 0.5  # 500ms周期
        position = (current_time - safe_mode_start) % cycle_time
        
        if position < cycle_time / 2:
            self.leds[0].on() if self.leds[0] else None
            self.leds[1].off() if self.leds[1] else None
        else:
            self.leds[0].off() if self.leds[0] else None
            self.leds[1].on() if self.leds[1] else None
    
    def deinit(self):
        """释放LED资源"""
        for led in self.leds:
            if led:
                try:
                    led.off()
                except:
                    pass
        self.leds.clear()
        gc.collect()

# =============================================================================
# 智能垃圾回收器
# =============================================================================

class SmartGarbageCollector:
    """智能垃圾回收器"""
    
    def __init__(self):
        self._last_collection = 0
        self._collection_count = 0
        self._logger = error_handler.get_logger()
        self._config = config.DaemonConfig
    
    def collect_if_needed(self, force: bool = False):
        """按需执行垃圾回收"""
        current_time = time.ticks_ms()
        
        # 获取当前状态
        state = error_handler.get_logger()._log_buffer._buffer[-1] if error_handler.get_logger()._log_buffer._buffer else {}
        safe_mode = state.get('level') == 'CRITICAL'
        
        # 选择回收间隔
        interval = self._config.GC_INTERVAL_SAFE if safe_mode else self._config.GC_INTERVAL_NORMAL
        
        # 检查是否需要回收
        if (force or 
            time.ticks_diff(current_time, self._last_collection) >= interval):
            
            # 执行垃圾回收
            collected = self._collect()
            self._collection_count += 1
            self._last_collection = current_time
            
            self._logger.debug(f"垃圾回收 #{self._collection_count}, 释放: {collected}字节", "GC")
            
            return True
        
        return False
    
    def _collect(self):
        """执行垃圾回收"""
        try:
            before = gc.mem_free()
            gc.collect()
            after = gc.mem_free()
            return after - before
        except:
            return 0
    
    def get_collection_count(self):
        """获取回收计数"""
        return self._collection_count

# =============================================================================
# 监控任务类
# =============================================================================

class MonitoringTask:
    """监控任务基类"""
    
    def __init__(self, name: str, priority: int, interval_ms: int):
        self.name = name
        self.priority = priority
        self.interval_ms = interval_ms
        self.last_execution = 0
        self.execution_count = 0
        self.error_count = 0
        self.enabled = True
    
    def should_execute(self) -> bool:
        """检查是否应该执行"""
        if not self.enabled:
            return False
        
        current_time = time.ticks_ms()
        return time.ticks_diff(current_time, self.last_execution) >= self.interval_ms
    
    def execute(self) -> bool:
        """执行任务"""
        try:
            self.last_execution = time.ticks_ms()
            result = self._execute_task()
            if result:
                self.execution_count += 1
            return result
        except Exception as e:
            self.error_count += 1
            error_handler.log_error(error_handler.ErrorType.SYSTEM, e, f"Task[{self.name}]")
            return False
    
    def _execute_task(self) -> bool:
        """子类实现具体任务"""
        raise NotImplementedError
    
    def get_stats(self) -> Dict:
        """获取任务统计"""
        return {
            'name': self.name,
            'priority': self.priority,
            'execution_count': self.execution_count,
            'error_count': self.error_count,
            'enabled': self.enabled
        }

# =============================================================================
# 具体监控任务
# =============================================================================

class TemperatureTask(MonitoringTask):
    """温度监控任务"""
    
    def __init__(self):
        super().__init__("temperature", 1, 5000)  # 高优先级，5秒间隔
    
    def _execute_task(self) -> bool:
        """执行温度监控"""
        try:
            temp = esp32.mcu_temperature()
            state = error_handler.get_logger()._log_buffer._buffer[-1] if error_handler.get_logger()._log_buffer._buffer else {}
            
            # 更新状态
            state['temperature'] = temp
            
            # 检查温度阈值
            threshold = config.DaemonConfig.TEMP_THRESHOLD
            if temp >= threshold:
                error_handler.critical(f"温度过高: {temp:.1f}°C", "TemperatureTask")
                return False
            
            # 检查警告阈值
            warning_threshold = threshold - config.DaemonConfig.TEMP_HYSTERESIS
            if temp >= warning_threshold:
                error_handler.warning(f"温度警告: {temp:.1f}°C", "TemperatureTask")
            
            return True
        except Exception as e:
            error_handler.log_error(error_handler.ErrorType.HARDWARE, e, "TemperatureTask")
            return False

class MemoryTask(MonitoringTask):
    """内存监控任务"""
    
    def __init__(self):
        super().__init__("memory", 2, 10000)  # 中优先级，10秒间隔
    
    def _execute_task(self) -> bool:
        """执行内存监控"""
        try:
            alloc = gc.mem_alloc()
            free = gc.mem_free()
            total = alloc + free
            percent = (alloc / total) * 100 if total > 0 else 0
            
            # 更新状态
            state = error_handler.get_logger()._log_buffer._buffer[-1] if error_handler.get_logger()._log_buffer._buffer else {}
            state['memory_usage'] = percent
            
            # 检查内存阈值
            threshold = config.DaemonConfig.MEMORY_THRESHOLD
            if percent >= threshold:
                error_handler.critical(f"内存使用过高: {percent:.1f}%", "MemoryTask")
                return False
            
            # 检查警告阈值
            warning_threshold = threshold - config.DaemonConfig.MEMORY_HYSTERESIS
            if percent >= warning_threshold:
                error_handler.warning(f"内存警告: {percent:.1f}%", "MemoryTask")
            
            return True
        except Exception as e:
            error_handler.log_error(error_handler.ErrorType.MEMORY, e, "MemoryTask")
            return False

class WatchdogTask(MonitoringTask):
    """看门狗任务"""
    
    def __init__(self, watchdog: EnhancedWatchdog):
        super().__init__("watchdog", 0, 2000)  # 最高优先级，2秒间隔
        self.watchdog = watchdog
    
    def _execute_task(self) -> bool:
        """执行看门狗喂狗"""
        return self.watchdog.feed()

class StatusReportTask(MonitoringTask):
    """状态报告任务"""
    
    def __init__(self):
        super().__init__("status_report", 3, 30000)  # 低优先级，30秒间隔
    
    def _execute_task(self) -> bool:
        """执行状态报告"""
        try:
            # 获取系统状态
            uptime = time.ticks_diff(time.ticks_ms(), state.get('start_time', 0)) // 1000
            temp = state.get('temperature', '未知')
            memory = state.get('memory_usage', '未知')
            errors = error_handler.get_error_stats()
            
            # 构建状态消息
            msg_parts = [
                f"运行时间: {uptime}s",
                f"温度: {temp}°C" if temp != '未知' else "温度: 未知",
                f"内存: {memory}%" if memory != '未知' else "内存: 未知",
                f"错误: {sum(stats.get('count', 0) for stats in errors.values())}"
            ]
            
            status_msg = ", ".join(msg_parts)
            error_handler.info(status_msg, "StatusReportTask")
            
            return True
        except Exception as e:
            error_handler.log_error(error_handler.ErrorType.SYSTEM, e, "StatusReportTask")
            return False

# =============================================================================
# 任务调度器
# =============================================================================

class TaskScheduler:
    """任务调度器"""
    
    def __init__(self):
        self._tasks = []
        self._logger = error_handler.get_logger()
    
    def add_task(self, task: MonitoringTask):
        """添加任务"""
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority, reverse=True)
        self._logger.info(f"添加任务: {task.name}", "TaskScheduler")
    
    def execute_tasks(self):
        """执行所有应该执行的任务"""
        executed_count = 0
        
        for task in self._tasks:
            if task.should_execute():
                task.execute()
                executed_count += 1
        
        return executed_count
    
    def get_task_stats(self) -> List[Dict]:
        """获取所有任务统计"""
        return [task.get_stats() for task in self._tasks]
    
    def enable_task(self, task_name: str, enabled: bool):
        """启用/禁用任务"""
        for task in self._tasks:
            if task.name == task_name:
                task.enabled = enabled
                break

# =============================================================================
# 增强守护进程类
# =============================================================================

class EnhancedDaemon:
    """增强守护进程"""
    
    def __init__(self):
        self._state = SystemState()
        self._watchdog = None
        self._led_controller = None
        self._task_scheduler = None
        self._garbage_collector = None
        self._timer = None
        self._logger = error_handler.get_logger()
        self._initialized = False
    
    def start(self) -> bool:
        """启动守护进程"""
        if self._initialized:
            return True
        
        try:
            self._logger.info("启动守护进程...", "EnhancedDaemon")
            
            # 初始化看门狗
            self._watchdog = EnhancedWatchdog()
            if not self._watchdog.init():
                return False
            
            # 初始化LED控制器
            self._led_controller = LEDController(config.DaemonConfig.LED_PINS)
            
            # 初始化垃圾回收器
            self._garbage_collector = SmartGarbageCollector()
            
            # 初始化任务调度器
            self._task_scheduler = TaskScheduler()
            self._setup_tasks()
            
            # 初始化定时器
            self._timer = machine.Timer(config.DaemonConfig.TIMER_ID)
            self._timer.init(
                period=config.DaemonConfig.MONITOR_INTERVAL,
                mode=machine.Timer.PERIODIC,
                callback=self._timer_callback
            )
            
            # 设置状态
            self._state.set('start_time', time.ticks_ms())
            self._state.set('daemon_active', True)
            self._initialized = True
            
            # 设置LED状态
            self._led_controller.set_status('normal')
            
            self._logger.info("守护进程启动成功", "EnhancedDaemon")
            return True
            
        except Exception as e:
            self._logger.error(f"守护进程启动失败: {e}", "EnhancedDaemon")
            self._cleanup()
            return False
    
    def _setup_tasks(self):
        """设置监控任务"""
        self._task_scheduler.add_task(WatchdogTask(self._watchdog))
        self._task_scheduler.add_task(TemperatureTask())
        self._task_scheduler.add_task(MemoryTask())
        self._task_scheduler.add_task(StatusReportTask())
    
    def _timer_callback(self, timer):
        """定时器回调"""
        if not self._state.get('daemon_active'):
            return
        
        try:
            # 执行垃圾回收
            self._garbage_collector.collect_if_needed()
            
            # 执行监控任务
            executed_count = self._task_scheduler.execute_tasks()
            
            # 更新监控计数
            self._state.increment('monitor_count')
            
            # 检查系统状态
            self._check_system_health()
            
            # 更新LED状态
            self._update_led_status()
            
        except Exception as e:
            self._state.increment('error_count')
            self._state.set('last_error_time', time.ticks_ms())
            error_handler.log_error(error_handler.ErrorType.SYSTEM, e, "DaemonTimer")
    
    def _check_system_health(self):
        """检查系统健康状态"""
        # 检查错误计数
        error_count = self._state.get('error_count', 0)
        last_error_time = self._state.get('last_error_time', 0)
        
        if error_count > config.DaemonConfig.MAX_ERROR_COUNT:
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_error_time) < config.DaemonConfig.ERROR_RESET_INTERVAL:
                self._enter_safe_mode("错误过多")
    
    def _update_led_status(self):
        """更新LED状态"""
        try:
            temp = self._state.get('temperature')
            memory = self._state.get('memory_usage')
            
            if self._state.get('safe_mode_active'):
                self._led_controller.set_status('safe_mode')
            elif temp and temp >= config.DaemonConfig.TEMP_THRESHOLD - config.DaemonConfig.TEMP_HYSTERESIS:
                self._led_controller.set_status('warning')
            elif memory and memory >= config.DaemonConfig.MEMORY_THRESHOLD - config.DaemonConfig.MEMORY_HYSTERESIS:
                self._led_controller.set_status('warning')
            else:
                self._led_controller.set_status('normal')
        except Exception as e:
            self._logger.error(f"更新LED状态失败: {e}", "EnhancedDaemon")
    
    def _enter_safe_mode(self, reason: str):
        """进入安全模式"""
        if not self._state.get('safe_mode_active'):
            self._state.set('safe_mode_active', True)
            self._state.set('safe_mode_start_time', time.ticks_ms())
            
            self._logger.critical(f"进入安全模式: {reason}", "EnhancedDaemon")
            
            # 强制垃圾回收
            self._garbage_collector.collect_if_needed(force=True)
    
    def stop(self):
        """停止守护进程"""
        self._logger.info("停止守护进程...", "EnhancedDaemon")
        
        self._state.set('daemon_active', False)
        self._cleanup()
        
        self._logger.info("守护进程已停止", "EnhancedDaemon")
    
    def _cleanup(self):
        """清理资源"""
        # 停止定时器
        if self._timer:
            try:
                self._timer.deinit()
            except:
                pass
            self._timer = None
        
        # 释放看门狗
        if self._watchdog:
            self._watchdog.deinit()
            self._watchdog = None
        
        # 释放LED
        if self._led_controller:
            self._led_controller.deinit()
            self._led_controller = None
        
        # 垃圾回收
        gc.collect()
    
    def get_status(self) -> Dict:
        """获取守护进程状态"""
        uptime = 0
        if self._state.get('start_time'):
            uptime = time.ticks_diff(time.ticks_ms(), self._state.get('start_time')) // 1000
        
        return {
            'active': self._state.get('daemon_active', False),
            'safe_mode': self._state.get('safe_mode_active', False),
            'temperature': self._state.get('temperature'),
            'memory_usage': self._state.get('memory_usage'),
            'error_count': self._state.get('error_count', 0),
            'monitor_count': self._state.get('monitor_count', 0),
            'uptime': uptime,
            'task_stats': self._task_scheduler.get_task_stats() if self._task_scheduler else [],
            'watchdog_feed_count': self._watchdog.get_feed_count() if self._watchdog else 0,
            'gc_count': self._garbage_collector.get_collection_count() if self._garbage_collector else 0
        }

# =============================================================================
# 全局实例和接口
# =============================================================================

# 创建全局守护进程实例
_daemon = EnhancedDaemon()
state = _daemon._state  # 全局状态访问

def start_daemon() -> bool:
    """启动守护进程"""
    return _daemon.start()

def stop_daemon():
    """停止守护进程"""
    _daemon.stop()

def get_daemon_status() -> Dict:
    """获取守护进程状态"""
    return _daemon.get_status()

def is_daemon_active() -> bool:
    """检查守护进程是否活跃"""
    return state.get('daemon_active', False)

def is_safe_mode() -> bool:
    """检查是否处于安全模式"""
    return state.get('safe_mode_active', False)

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()