# daemon.py
import machine
import esp32
import time
import gc
import utils  # 新增导入

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
_log_queue = []
_MAX_LOG_QUEUE_SIZE = 20

# === 守护进程配置常量 (内部私有) ===
CONFIG = {
    # --- LED 和 PWM 相关配置已移至 utils.py ---

    # --- 定时器与任务间隔配置 ---
    'main_interval_ms': 1000,         # 主循环（灯效动画）的更新间隔 (毫秒)
    'watchdog_interval_ms': 3000,     # 看门狗喂养与监控任务的统一检查间隔 (毫秒)
    'monitor_interval_ms': 10000,     # 系统状态监控的实际执行间隔 (毫秒)
    'perf_report_interval_s': 10,     # 内部性能报告的打印间隔 (秒)

    # --- 安全与保护机制配置 ---
    'temperature_threshold': 60.0,    # 触发“紧急安全模式”的MCU内部温度阈值 (°C)
    'wdt_timeout_ms': 10000,          # 看门狗超时时间 (毫秒)
    'blink_interval_ms': 200,         # “紧急安全模式”下，LED交替闪烁的间隔时间 (毫秒)
    'safe_mode_cooldown_ms': 5000,    # 从“紧急安全模式”自动恢复所需的冷却时间 (毫秒)
    'max_error_count': 10,            # 在错误计数重置周期内，允许的最大错误次数
    'error_reset_interval_ms': 60000, # 错误计数器自动清零的时间周期 (毫秒)
    'max_recovery_attempts': 5        # 尝试恢复硬件失败的最大次数
}

# === 核心中断与辅助函数 (内部实现细节) ===

def _format_uptime(ms):
    try:
        s = ms // 1000
        m, s = divmod(s, 60); h, m = divmod(m, 60); d, h = divmod(h, 24)
        return f"{d}天{h:02d}时{m:02d}分{s:02d}秒"
    except: return "时间计算错误"

def _get_internal_temperature():
    try: return esp32.mcu_temperature()
    except: return None

def _log_critical_error(error_msg):
    global _error_count, _last_error_time
    try:
        _error_count += 1
        _last_error_time = time.ticks_ms()
        if len(_log_queue) < _MAX_LOG_QUEUE_SIZE:
            timestamp = time.localtime()
            log_entry = f"{timestamp[0]}-{timestamp[1]:02d}-{timestamp[2]:02d} {timestamp[3]:02d}:{timestamp[4]:02d}:{timestamp[5]:02d} - CRITICAL: {error_msg}\n"
            _log_queue.append(log_entry)
    except: pass

def _emergency_hardware_reset():
    try:
        print("[EMERGENCY] 守护进程触发紧急硬件重置...")
        machine.reset()
    except:
        while True: pass

def _safe_mode_emergency_blink():
    try:
        # 此函数保持不变，使用最简单的GPIO操作，确保在任何情况下都能闪烁
        led1 = machine.Pin(utils.LED_PIN_1, machine.Pin.OUT)
        led2 = machine.Pin(utils.LED_PIN_2, machine.Pin.OUT)
        blink_cycle = CONFIG['blink_interval_ms'] * 2
        if time.ticks_diff(time.ticks_ms(), _safe_mode_start_time) % blink_cycle < CONFIG['blink_interval_ms']:
            led1.on(); led2.off()
        else:
            led1.off(); led2.on()
    except Exception as e: _log_critical_error(f"安全模式闪烁失败: {e}")

def _daemon_main_interrupt(timer):
    if not _daemon_active: return
    try:
        if _safe_mode_active:
            _safe_mode_emergency_blink()
            _check_safe_mode_recovery()
            return
        
        # 核心逻辑极大简化：只调用 utils 中的更新函数。
        # 此函数内部有逻辑判断，仅在动画效果（如呼吸灯）模式下才消耗CPU。
        utils.update_led_effect()

    except Exception as e:
        _log_critical_error(f"主中断处理失败: {e}")
        if _error_count > CONFIG['max_error_count']: _emergency_hardware_reset()

def _watchdog_and_monitor_interrupt(timer):
    global _last_monitor_check_ms, _error_count, _last_perf_check_ms
    current_time = time.ticks_ms()
    try:
        if _wdt: _wdt.feed()
    except Exception as e: _log_critical_error(f"看门狗喂养失败: {e}"); _emergency_hardware_reset(); return

    if time.ticks_diff(current_time, _last_monitor_check_ms) < CONFIG['monitor_interval_ms']: return
    _last_monitor_check_ms = current_time
    try:
        temp = _get_internal_temperature()
        if temp and temp >= CONFIG['temperature_threshold']: _enter_safe_mode(f"温度超限: {temp:.1f}°C"); return
        if time.ticks_diff(current_time, _last_error_time) > CONFIG['error_reset_interval_ms']:
            if _error_count > 0: print(f"[INFO] 错误计数已自动重置: {_error_count} -> 0"); _error_count = 0
        if time.ticks_diff(current_time, _last_perf_check_ms) >= CONFIG['perf_report_interval_s'] * 1000:
            _print_performance_report()
            _last_perf_check_ms = current_time
    except Exception as e: _log_critical_error(f"合并监控中断失败: {e}")

def _enter_safe_mode(reason):
    global _safe_mode_active, _safe_mode_start_time
    if not _safe_mode_active:
        try:
            print("\n" + "!"*60 + f"\n!!! 关键警告：系统进入紧急安全模式 (原因: {reason})\n" + "!"*60 + "\n")
            # 调用 utils 来安全地关闭 PWM 硬件
            utils.deinit_leds()
            _safe_mode_active = True
            _safe_mode_start_time = time.ticks_ms()
        except Exception as e:
            _log_critical_error(f"进入安全模式失败: {e}")
            _safe_mode_active = True; _safe_mode_start_time = time.ticks_ms()

def _check_safe_mode_recovery():
    global _safe_mode_active
    try:
        temp = _get_internal_temperature()
        if (temp and temp < CONFIG['temperature_threshold'] - 5.0 and
            time.ticks_diff(time.ticks_ms(), _safe_mode_start_time) > CONFIG['safe_mode_cooldown_ms']):
            print("[RECOVERY] 系统条件恢复，尝试退出安全模式...")
            # 重新初始化 LED 硬件
            if utils.init_leds():
                _safe_mode_active = False
                # 恢复为默认的低功耗灯效
                utils.set_effect('single_on', led_num=1)
                print("[RECOVERY] 成功退出安全模式，恢复正常运行")
            else:
                print("[ERROR] LED硬件重新初始化失败，保持安全模式")
    except Exception as e: _log_critical_error(f"安全模式恢复检查失败: {e}")

def _print_performance_report():
    global _last_perf_check_ms
    try:
        current_time = time.ticks_ms(); gc.collect()
        uptime_str = _format_uptime(time.ticks_diff(current_time, _start_ticks_ms))
        temp = _get_internal_temperature()
        mem_alloc_kb = gc.mem_alloc() / 1024; mem_free_kb = gc.mem_free() / 1024
        mem_total_kb = mem_alloc_kb + mem_free_kb
        mem_percent = (mem_alloc_kb / mem_total_kb) * 100 if mem_total_kb > 0 else 0
        print("\n" + "="*50 + "\n        关键系统守护进程状态报告\n" + "="*50)
        print(f"运行时间: {uptime_str}")
        print(f"内部温度: {temp:.2f} °C" if temp else "温度读取失败")
        print(f"内存使用: {mem_alloc_kb:.2f}KB / {mem_total_kb:.2f}KB ({mem_percent:.1f}%)")
        print(f"运行模式: {'紧急安全模式' if _safe_mode_active else '正常运行模式'}")
        print(f"错误计数: {_error_count}\n" + "="*50 + "\n")
        _last_perf_check_ms = current_time
    except Exception as e: _log_critical_error(f"性能报告失败: {e}")

class CriticalSystemDaemon:
    def __init__(self): self._initialized = False
    
    def _initialize_critical_hardware(self):
        global _wdt
        for attempt in range(3):
            try:
                # 调用 utils.init_leds() 来初始化LED
                if not utils.init_leds():
                    raise Exception("LED PWM 初始化失败")
                _wdt = machine.WDT(timeout=CONFIG['wdt_timeout_ms'])
                return True
            except Exception as e:
                print(f"[ERROR] 硬件初始化失败 (尝试 {attempt + 1}): {e}")
                if attempt < 2: time.sleep_ms(1000)
                else: print("[CRITICAL] 硬件初始化完全失败，执行紧急重启"); _emergency_hardware_reset()
        return False

    def start(self):
        global _daemon_active, _start_ticks_ms, _last_monitor_check_ms, _last_perf_check_ms, _timer_main, _timer_watchdog_monitor
        if self._initialized: return True
        
        print("[INIT] 启动关键系统守护进程...")
        if not self._initialize_critical_hardware(): print("[CRITICAL] 硬件初始化失败，系统无法启动"); return False
        
        _start_ticks_ms = time.ticks_ms()
        _last_monitor_check_ms = _start_ticks_ms
        _last_perf_check_ms = _start_ticks_ms
        try:
            _timer_main = machine.Timer(0)
            _timer_main.init(period=CONFIG['main_interval_ms'], mode=machine.Timer.PERIODIC, callback=_daemon_main_interrupt)
            _timer_watchdog_monitor = machine.Timer(1)
            _timer_watchdog_monitor.init(period=CONFIG['watchdog_interval_ms'], mode=machine.Timer.PERIODIC, callback=_watchdog_and_monitor_interrupt)
            _daemon_active = True; self._initialized = True
            print("[SUCCESS] 关键系统守护进程已激活并于后台独立运行。")
            return True
        except Exception as e:
            _log_critical_error(f"守护进程启动失败: {e}"); _emergency_hardware_reset(); return False

def get_log_queue():
    return _log_queue

_critical_daemon_instance = None

def start_critical_daemon():
    global _critical_daemon_instance
    if _critical_daemon_instance is None:
        _critical_daemon_instance = CriticalSystemDaemon()
    return _critical_daemon_instance.start()