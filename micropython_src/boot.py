"""MicroPython启动脚本

该模块在系统启动时自动执行，负责初始化垃圾回收机制。
启用垃圾回收并执行一次垃圾回收以释放内存。
"""

import gc

gc.enable()
gc.collect()
