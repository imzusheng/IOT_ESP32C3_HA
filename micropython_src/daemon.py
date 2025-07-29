# daemon.py
"""
关键系统守护进程模块 - 重构版本

这个模块实现了一个高度稳定和隔离的守护进程，负责系统的核心监控功能。
重构后的守护进程具有以下特点：

1. 完全独立：不依赖任何业务模块（如utils），避免循环依赖
2. 事件驱动：通过事件总线发布系统状态，而不是直接操作其他模块
3. 配置驱动：所有配置参数通过config模块获取，避免硬编码
4. 错误隔离：单个模块的错误不会影响守护进程的稳定性

主要功能：
- 看门狗管理：定期喂养看门狗，防止系统死锁
- 温度监控：监控MCU温度，超限时触发安全模式
- 系统监控：定期报告系统状态和性能信息
- 错误管理：统计和管理系统错误
- 安全模式：在异常情况下进入紧急安全模式
"""

import machine
import esp32
import time
import gc
import config
import event_bus

# === 全局守护进程状态 (内部私有) ===
_daemon_active = False
_safe_mode_active = False
_safe_mode_start_time = 0
_start_ticks_ms = 0
_last_monitor_check_ms = 0
_last_perf_check_ms = 0
_error_count = 0
_last_error_time = 0
_recovery_attempts = 0

# === 硬件对象 (内部私有) ===
_wdt = None
_timer_main = None
_timer_watchdog_monitor = None

# === 守护进程配置 (从config模块获取) ===
# 获取配置信息
_daemon_config = config.get_daemon_config()
_safety_config = config.get_safety_config()
_led_config = config.get_led_config()

# 合并配置为统一的CONFIG字典（保持向后兼容）
CONFIG = {
    # 定时器与任务间隔配置
    'main_interval_ms': _daemon_config['main_interval_ms'],
    'watchdog_interval_ms': _daemon_config['watchdog_interval_ms'],
    'monitor_interval_ms': _daemon_config['monitor_interval_ms'],
    'perf_report_interval_s': _daemon_config['perf_report_interval_s'],
    
    # 安全与保护机制配置
    'temperature_threshold': _safety_config['temperature_threshold'],
    'wdt_timeout_ms': _safety_config['wdt_timeout_ms'],
    'blink_interval_ms': _safety_config['blink_interval_ms'],
    'safe_mode_cooldown_ms': _safety_config['safe_mode_cooldown_ms'],
    'max_error_count': _safety_config['max_error_count'],
    'error_reset_interval_ms': _safety_config['error_reset_interval_ms'],
    'max_recovery_attempts': _safety_config['max_recovery_attempts'],
    
    # LED配置（用于安全模式闪烁）
    'led_pin_1': _led_config['pin_1'],
    'led_pin_2': _led_config['pin_2'],
}

# === 核心中断与辅助函数 (内部实现细节) ===

def _format_uptime(ms):
    """
    格式化运行时间
    
    Args:
        ms (int): 毫秒数
    
    Returns:
        str: 格式化的时间字符串
    """
    try:
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        return f"{d}天{h:02d}时{m:02d}分{s:02d}秒"
    except:
        return "时间计算错误"

def _get_internal_temperature():
    """
    获取MCU内部温度
    
    Returns:
        float: 温度值（摄氏度），失败时返回None
    """
    try:
        return esp32.mcu_temperature()
    except:
        return None

def _log_critical_error(error_msg):
    """
    记录关键错误并通过事件总线发布
    
    Args:
        error_msg (str): 错误消息
    """
    global _error_count, _last_error_time
    try:
        _error_count += 1
        _last_error_time = time.ticks_ms()
        
        # 通过事件总线发布日志事件，而不是直接操作日志队列
        event_bus.publish('log_critical', message=error_msg)
        
    except Exception as e:
        # 如果事件总线也失败了，至少打印到控制台
        print(f"[DAEMON] [CRITICAL] {error_msg}")
        print(f"[DAEMON] [ERROR] 日志发布失败: {e}")

def _get_system_time_info():
    """
    获取系统时间信息（不依赖utils模块）
    
    Returns:
        str: 格式化的时间字符串
    """
    try:
        local_time = time.localtime()
        time_str = f"{local_time[0]}-{local_time[1]:02d}-{local_time[2]:02d} {local_time[3]:02d}:{local_time[4]:02d}:{local_time[5]:02d}"
        return f"系统时间: {time_str}"
    except Exception as e:
        return f"系统时间: 获取失败 ({e})"

def _emergency_hardware_reset():
    """
    紧急硬件重置
    
    当系统出现严重错误时，执行硬件重置。
    """
    try:
        print("[EMERGENCY] 守护进程触发紧急硬件重置...")
        event_bus.publish('log_critical', message="守护进程触发紧急硬件重置")
        time.sleep(0.1)  # 给事件处理一点时间
        machine.reset()
    except:
        # 如果连重置都失败了，进入死循环
        while True:
            pass

def _safe_mode_emergency_blink():
    """
    安全模式下的紧急LED闪烁
    
    使用最简单的GPIO操作，确保在任何情况下都能闪烁。
    不依赖utils模块，直接操作GPIO。
    """
    try:
        # 使用配置中的LED引脚
        led1 = machine.Pin(CONFIG['led_pin_1'], machine.Pin.OUT)
        led2 = machine.Pin(CONFIG['led_pin_2'], machine.Pin.OUT)
        
        blink_cycle = CONFIG['blink_interval_ms'] * 2
        current_time = time.ticks_ms()
        cycle_position = time.ticks_diff(current_time, _safe_mode_start_time) % blink_cycle
        
        if cycle_position < CONFIG['blink_interval_ms']:
            led1.on()
            led2.off()
        else:
            led1.off()
            led2.on()
            
    except Exception as e:
        _log_critical_error(f"安全模式闪烁失败: {e}")

def _daemon_main_interrupt(timer):
    """
    守护进程主中断处理函数
    
    这个函数在定时器中断中被调用，负责处理安全模式下的LED闪烁。
    重构后，这个函数不再处理业务逻辑，只专注于安全模式管理。
    
    Args:
        timer: 定时器对象
    """
    if not _daemon_active:
        return
        
    try:
        if _safe_mode_active:
            _safe_mode_emergency_blink()
            _check_safe_mode_recovery()
            return
        
        # 正常模式下，守护进程主中断不做任何业务处理
        # 所有业务逻辑都通过事件总线和异步任务处理
        pass

    except Exception as e:
        _log_critical_error(f"主中断处理失败: {e}")
        if _error_count > CONFIG['max_error_count']:
            _emergency_hardware_reset()

def _watchdog_and_monitor_interrupt(timer):
    """
    看门狗喂养和系统监控中断处理函数
    
    这个函数负责：
    1. 定期喂养看门狗
    2. 监控系统温度
    3. 管理错误计数
    4. 生成性能报告
    
    Args:
        timer: 定时器对象
    """
    global _last_monitor_check_ms, _error_count, _last_perf_check_ms
    current_time = time.ticks_ms()
    
    # 首先喂养看门狗（最高优先级）
    try:
        if _wdt:
            _wdt.feed()
    except Exception as e:
        _log_critical_error(f"看门狗喂养失败: {e}")
        _emergency_hardware_reset()
        return

    # 检查是否到了监控检查时间
    if time.ticks_diff(current_time, _last_monitor_check_ms) < CONFIG['monitor_interval_ms']:
        return
        
    _last_monitor_check_ms = current_time
    
    try:
        # 温度监控
        temp = _get_internal_temperature()
        if temp and temp >= CONFIG['temperature_threshold']:
            _enter_safe_mode(f"温度超限: {temp:.1f}°C")
            return
        
        # 错误计数管理
        if time.ticks_diff(current_time, _last_error_time) > CONFIG['error_reset_interval_ms']:
            if _error_count > 0:
                print(f"[INFO] 错误计数已自动重置: {_error_count} -> 0")
                _error_count = 0
        
        # 性能报告
        if time.ticks_diff(current_time, _last_perf_check_ms) >= CONFIG['perf_report_interval_s'] * 1000:
            _print_performance_report()
            _last_perf_check_ms = current_time
            
    except Exception as e:
        _log_critical_error(f"监控中断处理失败: {e}")

def _enter_safe_mode(reason):
    """
    进入紧急安全模式
    
    当检测到系统异常时，进入安全模式。通过事件总线通知其他模块。
    
    Args:
        reason (str): 进入安全模式的原因
    """
    global _safe_mode_active, _safe_mode_start_time
    
    if not _safe_mode_active:
        try:
            print("\n" + "!"*60 + f"\n!!! 关键警告：系统进入紧急安全模式 (原因: {reason})\n" + "!"*60 + "\n")
            
            # 通过事件总线通知其他模块进入安全模式
            event_bus.publish('enter_safe_mode', reason=reason)
            
            _safe_mode_active = True
            _safe_mode_start_time = time.ticks_ms()
            
            # 记录日志
            _log_critical_error(f"系统进入安全模式: {reason}")
            
        except Exception as e:
            _log_critical_error(f"进入安全模式失败: {e}")
            # 即使发布事件失败，也要设置安全模式状态
            _safe_mode_active = True
            _safe_mode_start_time = time.ticks_ms()

def _check_safe_mode_recovery():
    """
    检查是否可以从安全模式恢复
    
    当系统条件恢复正常时，尝试退出安全模式。
    """
    global _safe_mode_active
    
    try:
        temp = _get_internal_temperature()
        
        # 检查恢复条件：温度降低且冷却时间足够
        if (temp and temp < CONFIG['temperature_threshold'] - 5.0 and
            time.ticks_diff(time.ticks_ms(), _safe_mode_start_time) > CONFIG['safe_mode_cooldown_ms']):
            
            print("[RECOVERY] 系统条件恢复，尝试退出安全模式...")
            
            # 通过事件总线通知其他模块退出安全模式
            event_bus.publish('exit_safe_mode', temperature=temp)
            
            _safe_mode_active = False
            
            print("[RECOVERY] 成功退出安全模式，恢复正常运行")
            event_bus.publish('log_info', message="系统成功退出安全模式")
            
    except Exception as e:
        _log_critical_error(f"安全模式恢复检查失败: {e}")

def _print_performance_report():
    """
    打印系统性能报告
    
    生成并显示系统状态信息，包括运行时间、温度、内存使用等。
    """
    try:
        current_time = time.ticks_ms()
        gc.collect()
        
        # 计算运行时间
        uptime_str = _format_uptime(time.ticks_diff(current_time, _start_ticks_ms))
        
        # 获取温度
        temp = _get_internal_temperature()
        
        # 计算内存使用
        mem_alloc_kb = gc.mem_alloc() / 1024
        mem_free_kb = gc.mem_free() / 1024
        mem_total_kb = mem_alloc_kb + mem_free_kb
        mem_percent = (mem_alloc_kb / mem_total_kb) * 100 if mem_total_kb > 0 else 0
        
        # 获取系统时间信息
        time_info = _get_system_time_info()
        
        # 打印报告
        print("\n" + "="*50 + "\n        关键系统守护进程状态报告\n" + "="*50)
        print(time_info)
        print(f"运行时间: {uptime_str}")
        print(f"内部温度: {temp:.2f} °C" if temp else "温度读取失败")
        print(f"内存使用: {mem_alloc_kb:.2f}KB / {mem_total_kb:.2f}KB ({mem_percent:.1f}%)")
        print(f"运行模式: {'紧急安全模式' if _safe_mode_active else '正常运行模式'}")
        print(f"错误计数: {_error_count}")
        print("="*50 + "\n")
        
        # 通过事件总线发布性能信息
        event_bus.publish('log_info', message=f"系统状态报告 - 温度:{temp:.1f}°C 内存:{mem_percent:.1f}% 错误:{_error_count}")
        
    except Exception as e:
        _log_critical_error(f"性能报告失败: {e}")

class CriticalSystemDaemon:
    """
    关键系统守护进程类
    
    这个类封装了守护进程的初始化和管理功能。
    """
    
    def __init__(self):
        """
        初始化守护进程实例
        """
        self._initialized = False
    
    def _initialize_critical_hardware(self):
        """
        初始化关键硬件（看门狗）
        
        Returns:
            bool: 初始化是否成功
        """
        global _wdt
        
        for attempt in range(3):
            try:
                print(f"[DAEMON] 尝试初始化看门狗 (第{attempt + 1}次)...")
                
                # 如果已有看门狗实例，先释放
                if _wdt:
                    try:
                        _wdt.deinit()
                    except:
                        pass
                
                # 创建新的看门狗实例
                _wdt = machine.WDT(timeout=CONFIG['wdt_timeout_ms'])
                _wdt.feed()
                
                print(f"[DAEMON] 看门狗初始化成功，超时时间: {CONFIG['wdt_timeout_ms']}ms")
                return True
                
            except Exception as e:
                print(f"[DAEMON] [ERROR] 看门狗初始化失败 (第{attempt + 1}次): {e}")
                time.sleep(0.5)
        
        print("[DAEMON] [CRITICAL] 看门狗初始化完全失败！")
        return False
    
    def _initialize_timers(self):
        """
        初始化定时器
        
        Returns:
            bool: 初始化是否成功
        """
        global _timer_main, _timer_watchdog_monitor
        
        try:
            # 初始化主定时器
            _timer_main = machine.Timer(0)
            _timer_main.init(
                period=CONFIG['main_interval_ms'],
                mode=machine.Timer.PERIODIC,
                callback=_daemon_main_interrupt
            )
            
            # 初始化看门狗和监控定时器
            _timer_watchdog_monitor = machine.Timer(1)
            _timer_watchdog_monitor.init(
                period=CONFIG['watchdog_interval_ms'],
                mode=machine.Timer.PERIODIC,
                callback=_watchdog_and_monitor_interrupt
            )
            
            print("[DAEMON] 定时器初始化成功")
            return True
            
        except Exception as e:
            print(f"[DAEMON] [ERROR] 定时器初始化失败: {e}")
            return False
    
    def start(self):
        """
        启动守护进程
        
        Returns:
            bool: 启动是否成功
        """
        global _daemon_active, _start_ticks_ms, _last_monitor_check_ms, _last_perf_check_ms
        
        if self._initialized:
            print("[DAEMON] [WARNING] 守护进程已经启动")
            return True
        
        print("[DAEMON] 正在启动关键系统守护进程...")
        
        try:
            # 记录启动时间
            _start_ticks_ms = time.ticks_ms()
            _last_monitor_check_ms = _start_ticks_ms
            _last_perf_check_ms = _start_ticks_ms
            
            # 初始化硬件
            if not self._initialize_critical_hardware():
                return False
            
            # 初始化定时器
            if not self._initialize_timers():
                return False
            
            # 激活守护进程
            _daemon_active = True
            self._initialized = True
            
            print("[DAEMON] 关键系统守护进程启动成功")
            event_bus.publish('log_info', message="关键系统守护进程启动成功")
            
            return True
            
        except Exception as e:
            print(f"[DAEMON] [ERROR] 守护进程启动失败: {e}")
            event_bus.publish('log_critical', message=f"守护进程启动失败: {e}")
            return False
    
    def stop(self):
        """
        停止守护进程
        """
        global _daemon_active, _timer_main, _timer_watchdog_monitor, _wdt
        
        print("[DAEMON] 正在停止守护进程...")
        
        try:
            _daemon_active = False
            
            # 停止定时器
            if _timer_main:
                _timer_main.deinit()
                _timer_main = None
            
            if _timer_watchdog_monitor:
                _timer_watchdog_monitor.deinit()
                _timer_watchdog_monitor = None
            
            # 注意：不停止看门狗，让它继续运行以保护系统
            
            self._initialized = False
            print("[DAEMON] 守护进程已停止")
            
        except Exception as e:
            print(f"[DAEMON] [ERROR] 停止守护进程时出错: {e}")
    
    def is_active(self):
        """
        检查守护进程是否活跃
        
        Returns:
            bool: 守护进程是否活跃
        """
        return _daemon_active
    
    def is_safe_mode(self):
        """
        检查是否处于安全模式
        
        Returns:
            bool: 是否处于安全模式
        """
        return _safe_mode_active
    
    def get_status(self):
        """
        获取守护进程状态信息
        
        Returns:
            dict: 状态信息字典
        """
        return {
            'active': _daemon_active,
            'safe_mode': _safe_mode_active,
            'error_count': _error_count,
            'uptime_ms': time.ticks_diff(time.ticks_ms(), _start_ticks_ms) if _daemon_active else 0,
            'temperature': _get_internal_temperature(),
        }

# === 全局守护进程实例 ===
_global_daemon = CriticalSystemDaemon()

# === 公共接口函数 ===

def start_critical_daemon():
    """
    启动关键系统守护进程的便捷函数
    
    Returns:
        bool: 启动是否成功
    """
    return _global_daemon.start()

def stop_critical_daemon():
    """
    停止关键系统守护进程的便捷函数
    """
    _global_daemon.stop()

def is_daemon_active():
    """
    检查守护进程是否活跃的便捷函数
    
    Returns:
        bool: 守护进程是否活跃
    """
    return _global_daemon.is_active()

def is_safe_mode():
    """
    检查是否处于安全模式的便捷函数
    
    Returns:
        bool: 是否处于安全模式
    """
    return _global_daemon.is_safe_mode()

def get_daemon_status():
    """
    获取守护进程状态的便捷函数
    
    Returns:
        dict: 状态信息字典
    """
    return _global_daemon.get_status()

def get_daemon_instance():
    """
    获取全局守护进程实例（用于高级操作）
    
    Returns:
        CriticalSystemDaemon: 守护进程实例
    """
    return _global_daemon

# 为了向后兼容，保留原有的get_log_queue函数
# 但现在它返回空列表，因为日志系统已经改为事件驱动
def get_log_queue():
    """
    获取日志队列（向后兼容函数）
    
    注意：在新的事件驱动架构中，日志系统不再使用队列，
    而是通过事件总线处理。这个函数保留是为了向后兼容。
    
    Returns:
        list: 空列表
    """
    print("[DAEMON] [WARNING] get_log_queue() 已废弃，请使用事件总线进行日志处理")
    return []