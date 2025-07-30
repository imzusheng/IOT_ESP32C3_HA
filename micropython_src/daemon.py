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
import core
from lib import temp_optimizer
from config import get_event_id, DEBUG, EV_ENTER_SAFE_MODE, EV_EXIT_SAFE_MODE, EV_PERFORMANCE_REPORT, EV_SCHEDULER_INTERVAL_ADJUSTED

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

# === 重启计数器 (防止无限重启循环) ===
_restart_count = 0
_restart_count_file = '/restart_count.txt'
_max_restart_count = 5  # 最大重启次数
_restart_reset_interval_ms = 3600000  # 1小时后重置重启计数器

# === 硬件对象 (内部私有) ===
_wdt = None
_timer_scheduler = None  # 统一调度器定时器

# === 直接从config模块导入所需配置 ===
# 优化：移除CONFIG字典，直接使用config模块的配置
from config import DAEMON_CONFIG, SAFETY_CONFIG, LED_PIN_1, LED_PIN_2

# === 优化后的统一调度器配置 ===
# 统一调度器的动态间隔（毫秒）- 根据温度自动调整
SCHEDULER_INTERVAL_MS = 200  # 默认200ms，将根据温度动态调整
_current_scheduler_interval_ms = SCHEDULER_INTERVAL_MS  # 当前实际使用的调度器间隔
_last_temp_check_for_scheduler = 0  # 上次检查温度用于调度器调整的时间
_temp_check_interval_for_scheduler = 10000  # 每10秒检查一次温度来调整调度器间隔

# 各任务的上次执行时间戳
_last_watchdog_feed_ms = 0
_last_monitor_check_ms = 0
_last_perf_check_ms = 0

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
        core.publish(get_event_id('log_critical'), message=error_msg)
        
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

def _load_restart_count():
    """
    从文件加载重启计数器
    
    Returns:
        int: 重启次数
    """
    try:
        with open(_restart_count_file, 'r') as f:
            data = f.read().strip().split(',')
            count = int(data[0])
            last_restart_time = int(data[1]) if len(data) > 1 else 0
            
            # 检查是否需要重置计数器（超过1小时）
            current_time = time.ticks_ms()
            if time.ticks_diff(current_time, last_restart_time) > _restart_reset_interval_ms:
                print("[DAEMON] 重启计数器已过期，重置为0")
                return 0
            
            return count
    except:
        return 0

def _save_restart_count(count):
    """
    保存重启计数器到文件
    
    Args:
        count (int): 重启次数
    """
    try:
        current_time = time.ticks_ms()
        with open(_restart_count_file, 'w') as f:
            f.write(f"{count},{current_time}")
    except Exception as e:
        print(f"[DAEMON] [WARNING] 保存重启计数器失败: {e}")

def _check_restart_loop_protection():
    """
    检查重启循环保护
    
    Returns:
        bool: True表示可以重启，False表示应该进入安全模式
    """
    global _restart_count
    
    _restart_count = _load_restart_count()
    
    if _restart_count >= _max_restart_count:
        error_msg = f"检测到重启循环（{_restart_count}次），进入安全模式"
        print(f"[DAEMON] [CRITICAL] {error_msg}")
        core.publish(get_event_id('log_critical'), message=error_msg)
        _enter_safe_mode(error_msg)
        return False
    
    _restart_count += 1
    _save_restart_count(_restart_count)
    print(f"[DAEMON] 重启计数器: {_restart_count}/{_max_restart_count}")
    return True

def _emergency_hardware_reset():
    """
    紧急硬件重置（带重启循环保护）
    
    当系统出现严重错误时，执行硬件重置。
    包含重启循环保护机制，防止无限重启。
    """
    try:
        # 检查重启循环保护
        if not _check_restart_loop_protection():
            return  # 进入安全模式，不执行重启
        
        print(f"[EMERGENCY] 守护进程触发紧急硬件重置（第{_restart_count}次）...")
        core.publish(get_event_id('log_critical'), message=f"守护进程触发紧急硬件重置（第{_restart_count}次）")
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
        led1 = machine.Pin(LED_PIN_1, machine.Pin.OUT)
        led2 = machine.Pin(LED_PIN_2, machine.Pin.OUT)
        
        blink_cycle = SAFETY_CONFIG['blink_interval_ms'] * 2
        current_time = time.ticks_ms()
        cycle_position = time.ticks_diff(current_time, _safe_mode_start_time) % blink_cycle
        
        if cycle_position < SAFETY_CONFIG['blink_interval_ms']:
            led1.on()
            led2.off()
        else:
            led1.off()
            led2.on()
            
    except Exception as e:
        _log_critical_error(f"安全模式闪烁失败: {e}")

def _adjust_scheduler_interval_by_temperature():
    """
    根据温度动态调整调度器间隔
    
    这是温度优化的核心功能，根据当前MCU温度自动调整调度器的中断频率，
    从而在高温时降低功耗和发热。
    """
    global _current_scheduler_interval_ms, _last_temp_check_for_scheduler, _timer_scheduler
    
    current_time = time.ticks_ms()
    
    # 检查是否需要调整调度器间隔（每10秒检查一次）
    if time.ticks_diff(current_time, _last_temp_check_for_scheduler) >= _temp_check_interval_for_scheduler:
        _last_temp_check_for_scheduler = current_time
        
        try:
            # 获取当前温度
            current_temp = _get_internal_temperature()
            if current_temp is None:
                return  # 温度读取失败，保持当前间隔
            
            # 根据温度获取推荐的调度器间隔
            temp_config = temp_optimizer.get_optimized_config_for_temp(current_temp)
            recommended_interval = temp_config['scheduler_interval_ms']
            
            # 如果推荐间隔与当前间隔不同，则需要重新初始化定时器
            if recommended_interval != _current_scheduler_interval_ms:
                old_interval = _current_scheduler_interval_ms
                _current_scheduler_interval_ms = recommended_interval
                
                # 重新初始化定时器
                if _timer_scheduler:
                    try:
                        _timer_scheduler.deinit()
                        _timer_scheduler.init(
                            period=_current_scheduler_interval_ms,
                            mode=machine.Timer.PERIODIC,
                            callback=_scheduler_interrupt
                        )
                        
                        temp_level = temp_optimizer.get_temperature_level(current_temp)
                        print(f"[DAEMON] [TEMP_OPT] 温度: {current_temp:.1f}°C, 级别: {temp_level}")
                        print(f"[DAEMON] [TEMP_OPT] 调度器间隔调整: {old_interval}ms -> {_current_scheduler_interval_ms}ms")
                        
                        # 通过事件总线发布调度器间隔调整事件
                        core.publish(EV_SCHEDULER_INTERVAL_ADJUSTED, 
                                        old_interval=old_interval,
                                        new_interval=_current_scheduler_interval_ms,
                                        temperature=current_temp,
                                        temp_level=temp_level)
                        
                    except Exception as e:
                        _log_critical_error(f"调度器间隔调整失败: {e}")
                        # 调整失败时恢复原间隔
                        _current_scheduler_interval_ms = old_interval
                        
        except Exception as e:
            _log_critical_error(f"温度检查用于调度器调整失败: {e}")

def _scheduler_interrupt(timer):
    """
    统一的调度器中断处理函数
    
    这个函数在动态调整的定时器中断中被调用，负责调度所有守护进程任务：
    1. 看门狗喂养（最高优先级）
    2. 系统监控（温度检查、错误管理）
    3. 性能报告
    4. 安全模式管理
    5. 动态调度器间隔调整（温度优化）
    
    通过时间戳比较来控制各任务的执行频率，实现资源优化。
    
    Args:
        timer: 定时器对象
    """
    global _last_watchdog_feed_ms, _last_monitor_check_ms, _last_perf_check_ms, _error_count
    
    if not _daemon_active:
        return
        
    current_time = time.ticks_ms()
    
    try:
        # 任务0：动态调度器间隔调整（温度优化，最高优先级）
        _adjust_scheduler_interval_by_temperature()
        
        # 任务1：看门狗喂养（最高优先级，按配置间隔执行）
        if time.ticks_diff(current_time, _last_watchdog_feed_ms) >= DAEMON_CONFIG['watchdog_interval_ms']:
            _last_watchdog_feed_ms = current_time
            try:
                if _wdt:
                    _wdt.feed()
                    # 每10次喂养记录一次状态，避免过多日志
                    if DEBUG and current_time % 30000 < 3000:  # 大约每30秒记录一次
                        print(f"[DAEMON] 看门狗正常喂养，当前调度器间隔: {_current_scheduler_interval_ms}ms")
            except Exception as e:
                _log_critical_error(f"看门狗喂养失败: {e}")
                print(f"[DAEMON] [CRITICAL] 看门狗喂养失败，准备重置系统: {e}")
                _emergency_hardware_reset()
                return
        
        # 任务2：系统监控（按配置间隔执行）
        if time.ticks_diff(current_time, _last_monitor_check_ms) >= DAEMON_CONFIG['monitor_interval_ms']:
            _last_monitor_check_ms = current_time
            
            # 温度监控
            temp = _get_internal_temperature()
            if temp and temp >= SAFETY_CONFIG['temperature_threshold']:
                _enter_safe_mode(f"温度超限: {temp:.1f}°C")
                return
            
            # 错误计数管理
            if time.ticks_diff(current_time, _last_error_time) > SAFETY_CONFIG['error_reset_interval_ms']:
                if _error_count > 0:
                    print(f"[INFO] 错误计数已自动重置: {_error_count} -> 0")
                    _error_count = 0
        
        # 任务3：性能报告（按配置间隔执行）
        if time.ticks_diff(current_time, _last_perf_check_ms) >= DAEMON_CONFIG['perf_report_interval_s'] * 1000:
            _last_perf_check_ms = current_time
            _print_performance_report()
        
        # 任务4：安全模式管理（每次调度都检查）
        if _safe_mode_active:
            _safe_mode_emergency_blink()
            _check_safe_mode_recovery()
            
    except Exception as e:
        _log_critical_error(f"统一调度器中断处理失败: {e}")
        if _error_count > SAFETY_CONFIG['max_error_count']:
            _emergency_hardware_reset()

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
            if DEBUG:
                print("\n" + "!"*60 + f"\n!!! 关键警告：系统进入紧急安全模式 (原因: {reason})\n" + "!"*60 + "\n")
            
            # 通过事件总线通知其他模块进入安全模式
            core.publish(EV_ENTER_SAFE_MODE, reason=reason)
            
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
        if (temp and temp < SAFETY_CONFIG['temperature_threshold'] - 5.0 and
            time.ticks_diff(time.ticks_ms(), _safe_mode_start_time) > SAFETY_CONFIG['safe_mode_cooldown_ms']):
            
            if DEBUG:
                print("[RECOVERY] 系统条件恢复，尝试退出安全模式...")
            
            # 通过事件总线通知其他模块退出安全模式
            core.publish(EV_EXIT_SAFE_MODE, temperature=temp)
            
            _safe_mode_active = False
            
            if DEBUG:
                print("[RECOVERY] 成功退出安全模式，恢复正常运行")
            core.publish(get_event_id('log_info'), message="系统成功退出安全模式")
            
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
        
        # 获取温度级别信息
        temp_level = "未知"
        if temp:
            temp_level = temp_optimizer.get_temperature_level(temp)
        
        # 打印报告
        if DEBUG:
            print("\n" + "="*50 + "\n        关键系统守护进程状态报告\n" + "="*50)
            print(time_info)
            print(f"运行时间: {uptime_str}")
            print(f"内部温度: {temp:.2f} °C (级别: {temp_level})" if temp else "温度读取失败")
            print(f"内存使用: {mem_alloc_kb:.2f}KB / {mem_total_kb:.2f}KB ({mem_percent:.1f}%)")
            print(f"运行模式: {'紧急安全模式' if _safe_mode_active else '正常运行模式'}")
            print(f"调度器间隔: {_current_scheduler_interval_ms}ms (温度优化)")
            print(f"错误计数: {_error_count}")
            print("="*50 + "\n")
        
        # 通过事件总线发布性能信息
        core.publish(get_event_id('log_info'), message=f"系统状态报告 - 温度:{temp:.1f}°C 内存:{mem_percent:.1f}% 错误:{_error_count}")
        
        # 发布性能报告事件，供温度优化器使用
        try:
            core.publish(EV_PERFORMANCE_REPORT, 
                             temperature=temp, 
                             mem_percent=mem_percent, 
                             error_count=_error_count,
                             uptime_ms=time.ticks_diff(current_time, _start_ticks_ms))
        except Exception as e:
            _log_critical_error(f"性能报告事件发布失败: {e}")
        
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
                if DEBUG:
                    print(f"[DAEMON] 尝试初始化看门狗 (第{attempt + 1}次)...")
                
                # 如果已有看门狗实例，先释放
                if _wdt:
                    try:
                        _wdt.deinit()
                    except:
                        pass
                
                # 创建新的看门狗实例
                _wdt = machine.WDT(timeout=SAFETY_CONFIG['wdt_timeout_ms'])
                _wdt.feed()
                
                if DEBUG:
                    print(f"[DAEMON] 看门狗初始化成功，超时时间: {SAFETY_CONFIG['wdt_timeout_ms']}ms")
                return True
                
            except Exception as e:
                print(f"[DAEMON] [ERROR] 看门狗初始化失败 (第{attempt + 1}次): {e}")
                time.sleep(0.5)
        
        print("[DAEMON] [CRITICAL] 看门狗初始化完全失败！")
        return False
    
    def _initialize_timers(self):
        """
        初始化统一调度器定时器
        
        优化后只使用一个动态调整间隔的定时器来调度所有任务，
        节省硬件定时器资源，提高系统资源利用率，并支持温度优化。
        
        Returns:
            bool: 初始化是否成功
        """
        global _timer_scheduler, _current_scheduler_interval_ms
        
        try:
            # 初始化统一调度器定时器
            _timer_scheduler = machine.Timer(0)
            _timer_scheduler.init(
                period=_current_scheduler_interval_ms,  # 使用动态调度间隔
                mode=machine.Timer.PERIODIC,
                callback=_scheduler_interrupt  # 使用统一的调度器回调
            )
            
            if DEBUG:
                print(f"[DAEMON] 统一调度器定时器初始化成功，初始调度间隔: {_current_scheduler_interval_ms}ms")
                print("[DAEMON] [优化] 已将两个定时器合并为一个，节省硬件资源")
                print("[DAEMON] [温度优化] 调度器间隔将根据温度自动调整")
            return True
            
        except Exception as e:
            print(f"[DAEMON] [ERROR] 统一调度器定时器初始化失败: {e}")
            return False
    
    def start(self):
        """
        启动守护进程
        
        Returns:
            bool: 启动是否成功
        """
        global _daemon_active, _start_ticks_ms, _last_monitor_check_ms, _last_perf_check_ms, _last_watchdog_feed_ms, _last_temp_check_for_scheduler
        
        if self._initialized:
            print("[DAEMON] [WARNING] 守护进程已经启动")
            return True
        
        if DEBUG:
            print("[DAEMON] 正在启动关键系统守护进程...")
        
        try:
            # 记录启动时间并初始化所有时间戳
            _start_ticks_ms = time.ticks_ms()
            _last_monitor_check_ms = _start_ticks_ms
            _last_perf_check_ms = _start_ticks_ms
            _last_watchdog_feed_ms = _start_ticks_ms  # 初始化看门狗时间戳
            _last_temp_check_for_scheduler = _start_ticks_ms  # 初始化温度检查时间戳
            
            # 初始化硬件
            if not self._initialize_critical_hardware():
                return False
            
            # 初始化统一调度器定时器
            if not self._initialize_timers():
                return False
            
            # 激活守护进程
            _daemon_active = True
            self._initialized = True
            
            if DEBUG:
                print("[DAEMON] 关键系统守护进程启动成功（温度优化版本）")
            core.publish(get_event_id('log_info'), message="关键系统守护进程启动成功（温度优化版本）")
            
            return True
            
        except Exception as e:
            print(f"[DAEMON] [ERROR] 守护进程启动失败: {e}")
            core.publish(get_event_id('log_critical'), message=f"守护进程启动失败: {e}")
            return False
    
    def stop(self):
        """
        停止守护进程
        """
        global _daemon_active, _timer_scheduler, _wdt
        
        if DEBUG:
            print("[DAEMON] 正在停止守护进程...")
        
        try:
            _daemon_active = False
            
            # 停止统一调度器定时器
            if _timer_scheduler:
                _timer_scheduler.deinit()
                _timer_scheduler = None
                if DEBUG:
                    print("[DAEMON] 统一调度器定时器已停止")
            
            # 注意：不停止看门狗，让它继续运行以保护系统
            
            self._initialized = False
            if DEBUG:
                print("[DAEMON] 守护进程已停止（优化版本）")
            
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