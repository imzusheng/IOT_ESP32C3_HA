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
# 新增: 双击复位进入安全模式, 无需专用按键
DOUBLE_RESET_WINDOW_MS = 1500  # 双击复位间隔窗口
DOUBLE_RESET_FLAG_PATH = "/dr.flag"

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


def _check_double_reset() -> bool:
    """检测是否为双击复位以进入安全模式。
    机制: 第一次上电创建标记并等待窗口期, 若在窗口内第二次复位重启, 将检测到标记并进入安全模式。
    不使用定时器, 仅使用短暂的 sleep_ms。
    """
    try:
        import os
        # 如果标记已存在, 视为第二次复位, 消费并进入安全模式
        if DOUBLE_RESET_FLAG_PATH.lstrip("/") in os.listdir("/"):
            try:
                os.remove(DOUBLE_RESET_FLAG_PATH)
            except Exception:
                pass
            print("Double reset detected")
            return True
        # 首次进入窗口: 写入标记并等待窗口结束后移除
        try:
            with open(DOUBLE_RESET_FLAG_PATH, "w") as f:
                f.write("1")
        except Exception:
            return False
        utime.sleep_ms(DOUBLE_RESET_WINDOW_MS)
        try:
            os.remove(DOUBLE_RESET_FLAG_PATH)
        except Exception:
            pass
        return False
    except Exception:
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
                    # 引脚松开, 放弃安全模式
                    # 继续后续方案
                    break
                utime.sleep_ms(50)
            else:
                # 循环未被 break, 即持续按住到超时
                return True
    except Exception as e:
        print(f"Safe mode check failed: {e}")

    # 3) 双击复位检测
    if _check_double_reset():
        return True

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
