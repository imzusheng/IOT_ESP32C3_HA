"""
boot.py - 平台相关启动，可做最小化硬件初始化
"""

import gc
import machine

# 垃圾回收
gc.collect()

# 最小化硬件初始化
def hardware_init():
    """最小化硬件初始化"""
    # 禁用看门狗定时器，防止意外重启
    try:
        wdt = machine.WDT()
        wdt.deinit()
    except:
        pass

hardware_init()