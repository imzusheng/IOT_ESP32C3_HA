# lib/__init__.py
"""
lib包初始化文件

这个包包含了重构后的模块：
- wifi.py: WiFi管理功能
- ntp.py: NTP时间同步功能
- led.py: LED控制功能（增强版）
- temp_optimizer.py: 温度优化功能
- core.py: 事件总线核心功能（已移到上级目录）
"""

# 导入核心模块（从上级目录）
import sys
import os

# 添加上级目录到路径，以便导入core模块
parent_dir = os.path.dirname(os.path.dirname(__file__))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# 导入core模块
import core

# 版本信息
__version__ = "2.0.0"
__author__ = "IoT ESP32C3 Project"
__description__ = "重构后的模块化IoT系统库"

# 模块列表
__all__ = [
    'wifi',
    'ntp', 
    'led',
    'temp_optimizer',
    'core'  # 从上级目录导入
]

print(f"[LIB] 模块化IoT系统库 v{__version__} 已加载")