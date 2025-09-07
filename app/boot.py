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
    # 仅检查文件标记 - 由daemon.py在温度阈值或错误计数触发
    if _consume_safemode_flag():
        print("Safe mode flag detected")
        return True

    return False


def enter_safe_mode():
    """进入安全模式: 运行LED SOS模式并启动守护服务监控温度"""
    print("Entering safe mode - LED SOS only")

    try:
        # 启动LED SOS模式
        from hw.led import play
        play("sos")
        print("Safe mode active: LED SOS running. Please reset manually.")
        
        # 启动守护服务以监控温度(安全模式下)
        try:
            from daemon import Daemon
            daemon = Daemon()
            # 启动守护服务但标记为安全模式
            daemon._in_safe_mode = True
            daemon.start()
            print("Safe mode daemon started for temperature monitoring")
        except Exception as e:
            print(f"Safe mode daemon failed: {e}")
        
        # 主循环: LED已由硬件定时器驱动,仅需保持系统运行
        while True:
            utime.sleep(1)  # 1秒间隔
            
    except Exception as e:
        print(f"Safe mode initialization failed: {e}")
        while True:
            utime.sleep(1)


# 检查安全模式
if check_safe_mode():
    enter_safe_mode()
