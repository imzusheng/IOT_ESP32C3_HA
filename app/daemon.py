# -*- coding: utf-8 -*-
"""
app/daemon.py

系统守护进程 - 完整功能
- 错误计数与重启
- 温度监控与保护
- 安全模式检测与处理
"""

try:
    import machine
    import utime
    import esp32
except Exception:
    machine = None
    utime = None 
    esp32 = None

# 配置
CONFIG = {
    # 守护进程配置
    "error_threshold": 5,           # 错误计数阈值, 达到后重启进入安全模式
    "temp_threshold": 30,           # MCU 温度阈值(°C), 超过后进入安全模式
    "temp_check_interval": 30000,   # 温度检查间隔(ms)
    
    # 安全模式触发配置
    "safe_boot_pin": 12,            # 安全模式触发引脚号
    "safe_boot_delay_ms": 3000,     # 引脚长按确认时间(ms)
    "double_reset_window_ms": 1500, # 双击识别窗口期(ms)
    
    # NVS 存储配置  
    "nvs_ns": "boot",               # NVS 命名空间
    "nvs_key_safe": "safe",         # 安全模式标记键名
    "nvs_key_dr": "dr"              # 双击复位标记键名
}

class Daemon:
    """系统守护进程"""
    
    def __init__(self):
        self.error_count = 0
        self.last_temp_check = 0
        
    def start(self):
        """启动守护进程服务"""
        print("Daemon service started")
        
    def log_error(self, error_msg: str):
        """记录错误并检查阈值"""
        self.error_count += 1
        print(f"Error #{self.error_count}: {error_msg}")
        
        if self.error_count >= CONFIG["error_threshold"]:
            print(f"Error threshold reached ({CONFIG['error_threshold']}), requesting safe mode")
            self._request_safe_mode_and_reboot()
    
    def check_temperature(self):
        """检查 MCU 温度"""
        if not esp32:
            return
            
        try:
            now = utime.ticks_ms() if utime else 0
            if utime.ticks_diff(now, self.last_temp_check) < CONFIG["temp_check_interval"]:
                return
            self.last_temp_check = now
            
            temp = (esp32.raw_temperature() - 32) * 5 / 9
            if temp > CONFIG["temp_threshold"]:
                print(f"MCU temperature too high: {temp:.1f}°C, requesting safe mode")
                self._request_safe_mode_and_reboot()
        except Exception as e:
            print(f"Temperature check failed: {e}")
    
    def _request_safe_mode_and_reboot(self):
        """请求安全模式并重启"""
        try:
            request_safe_mode()
            print("Rebooting in 2 seconds...")
            if utime:
                utime.sleep(2)
            if machine:
                machine.reset()
        except Exception as e:
            print(f"Failed to reboot: {e}")
    
    def run_check(self):
        """运行一次检查周期"""
        self.check_temperature()

# 安全模式功能
def request_safe_mode():
    """请求下次启动进入安全模式"""
    try:
        nvs = esp32.NVS(CONFIG["nvs_ns"])
        nvs.set_i32(CONFIG["nvs_key_safe"], 1)
        nvs.commit()
    except Exception:
        pass

def _consume_safemode_flag() -> bool:
    """检查并消费安全模式标记"""
    try:
        nvs = esp32.NVS(CONFIG["nvs_ns"])
        if nvs.get_i32(CONFIG["nvs_key_safe"]) == 1:
            nvs.erase_key(CONFIG["nvs_key_safe"])
            nvs.commit()
            return True
    except Exception:
        pass
    return False

def _check_double_reset() -> bool:
    """双击复位检测"""
    if not utime or not esp32:
        return False
        
    try:
        nvs = esp32.NVS(CONFIG["nvs_ns"])
        try:
            if nvs.get_i32(CONFIG["nvs_key_dr"]) == 1:
                nvs.erase_key(CONFIG["nvs_key_dr"])
                nvs.commit()
                print("Double reset detected")
                return True
        except Exception:
            pass
            
        nvs.set_i32(CONFIG["nvs_key_dr"], 1)
        nvs.commit()
        utime.sleep_ms(CONFIG["double_reset_window_ms"])
        
        try:
            nvs.erase_key(CONFIG["nvs_key_dr"])
            nvs.commit()
        except Exception:
            pass
    except Exception:
        pass
    return False

def _check_pin_hold() -> bool:
    """检查引脚长按"""
    if not machine or not utime:
        return False
        
    try:
        pin = machine.Pin(CONFIG["safe_boot_pin"], machine.Pin.IN, machine.Pin.PULL_DOWN)
        if pin.value() != 1:
            return False
            
        print("Safe mode pin detected, waiting for confirmation...")
        start_time = utime.ticks_ms()
        while utime.ticks_diff(utime.ticks_ms(), start_time) < CONFIG["safe_boot_delay_ms"]:
            if pin.value() == 0:
                return False
            utime.sleep_ms(50)
        return True
    except Exception as e:
        print(f"Safe mode pin check failed: {e}")
        return False

def check_safe_mode() -> bool:
    """检测是否需要进入安全模式"""
    if _consume_safemode_flag():
        print("Safe mode flag detected")
        return True
    
    if _check_pin_hold():
        return True
        
    if _check_double_reset():
        return True
        
    return False

def enter_safe_mode():
    """进入安全模式: LED SOS 循环"""
    print("Entering safe mode - LED SOS only")
    
    try:
        from hw.led import play
        play("sos")
        print("Safe mode active: LED SOS running. Please reset manually.")
        while True:
            if utime:
                utime.sleep(1)
    except Exception as e:
        print(f"Safe mode initialization failed: {e}")

def boot_safe_mode_check():
    """boot.py 调用的统一入口"""
    try:
        if check_safe_mode():
            enter_safe_mode()
            return True
    except Exception as e:
        print("Safe mode check fatal error:", e)
    return False

# 全局实例
_daemon_instance = None

def get_daemon():
    """获取守护进程单例"""
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = Daemon()
    return _daemon_instance

def log_error(error_msg: str):
    """记录系统错误"""
    get_daemon().log_error(error_msg)

def run_daemon_check():
    """执行守护检查"""
    get_daemon().run_check()

__all__ = ["log_error", "run_daemon_check", "get_daemon", "boot_safe_mode_check", "request_safe_mode"]