# lib/__init__.py
"""
lib包初始化文件

这个包包含了重构后的模块：
- wifi.py: WiFi管理功能
- ntp.py: NTP时间同步功能
- led.py: LED控制功能（增强版）
- temp_optimizer.py: 温度优化功能
- core.py: 事件总线核心功能
- config.py: 系统配置管理
- daemon.py: 系统守护进程
- logger.py: 日志系统
- utils.py: 通用工具函数
"""

# 版本信息
__version__ = "2.1.0"
__author__ = "IoT ESP32C3 Project"
__description__ = "重构后的模块化IoT系统库"

# 模块列表
__all__ = [
    'config',
    'core',
    'daemon',
    'logger',
    'utils',
    'wifi',
    'ntp', 
    'led',
    'temp_optimizer'
]

print(f"[LIB] 模块化IoT系统库 v{__version__} 已加载")