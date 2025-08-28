"""
boot.py - 启动控制, 支持安全模式检测
"""

import sys
import gc
import machine
import utime

# 添加 lib 目录到 Python 搜索路径
sys.path.append("/lib")

# 安全模式配置
SAFE_BOOT_PIN = 12  # P12 pin for safe boot detection
SAFE_BOOT_DELAY_MS = 3000  # Hold duration to trigger safe mode
SAFE_MODE_FLAG_PATH = "/safemode.flag"  # 文件标记, 由 Daemon 在异常时置位

# 初始化垃圾回收
gc.collect()


def _consume_safemode_flag() -> bool:
    """检查并消费安全模式标记文件"""
    try:
        import os
        if SAFE_MODE_FLAG_PATH.lstrip("/") in os.listdir("/"):
            # 删除标记文件以避免下次继续进入
            try:
                os.remove(SAFE_MODE_FLAG_PATH)
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False


def check_safe_mode() -> bool:
    """检测是否需要进入安全模式"""
    # 1) 优先检查文件标记
    if _consume_safemode_flag():
        print("Safe mode flag detected")
        return True

    # 2) 其次检查引脚按住
    try:
        pin = machine.Pin(SAFE_BOOT_PIN, machine.Pin.IN, machine.Pin.PULL_DOWN)
        if pin.value() == 1:
            print("Safe mode pin detected, waiting for confirmation...")
            start_time = utime.ticks_ms()
            while utime.ticks_diff(utime.ticks_ms(), start_time) < SAFE_BOOT_DELAY_MS:
                if pin.value() == 0:
                    return False
                utime.sleep_ms(50)
            return True
        return False
    except Exception as e:
        print(f"Safe mode check failed: {e}")
        return False


def enter_safe_mode():
    """进入安全模式: 仅运行LED SOS模式"""
    print("Entering safe mode - LED SOS only")

    try:
        from hw.led import play
        play("sos")
        print("Safe mode active: LED SOS running. Please reset manually.")
        while True:
            utime.sleep(1)
    except Exception as e:
        print(f"Safe mode initialization failed: {e}")
        while True:
            utime.sleep(1)


# 检查安全模式
if check_safe_mode():
    enter_safe_mode()

# 正常启动流程继续
print("Normal boot sequence continuing...")
