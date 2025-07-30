# utils.py
"""
系统工具函数模块

提供通用的系统工具函数：
- 内存信息获取
- 系统状态检查
- 时间格式化
- 其他通用工具函数
"""

import gc
import time
from .config import DEBUG

# =============================================================================
# 内存管理工具
# =============================================================================

def get_memory_info():
    """获取内存信息"""
    try:
        gc.collect()
        free = gc.mem_free()
        allocated = gc.mem_alloc()
        total = free + allocated
        return {
            'free': free,
            'allocated': allocated,
            'total': total,
            'percent_used': (allocated / total) * 100 if total > 0 else 0
        }
    except:
        return {'free': 0, 'allocated': 0, 'total': 0, 'percent_used': 0}

# =============================================================================
# 系统状态工具
# =============================================================================

def get_system_status():
    """获取系统状态"""
    try:
        # 检查WiFi状态
        import network
        wlan = network.WLAN(network.STA_IF)
        wifi_connected = wlan.isconnected()
        
        # 获取内存信息
        mem_info = get_memory_info()
        
        # 获取温度（如果支持）
        temp = None
        try:
            import esp32
            temp = esp32.mcu_temperature()
        except:
            pass
        
        return {
            'wifi_connected': wifi_connected,
            'memory': mem_info,
            'temperature': temp,
            'timestamp': time.time()
        }
    except Exception as e:
        if DEBUG:
            print(f"[Utils] 获取系统状态失败: {e}")
        return {}

# =============================================================================
# 时间工具
# =============================================================================

def format_time(timestamp=None):
    """格式化时间"""
    try:
        if timestamp is None:
            timestamp = time.time()
        
        local_time = time.localtime(timestamp)
        return f"{local_time[0]}-{local_time[1]:02d}-{local_time[2]:02d} {local_time[3]:02d}:{local_time[4]:02d}:{local_time[5]:02d}"
    except:
        return "时间格式化失败"

# =============================================================================
# 其他通用工具
# =============================================================================

def safe_import(module_name, default=None):
    """安全导入模块"""
    try:
        return __import__(module_name)
    except ImportError:
        if DEBUG:
            print(f"[Utils] 模块 {module_name} 导入失败，使用默认值")
        return default

def clamp(value, min_val, max_val):
    """限制数值在指定范围内"""
    return max(min_val, min(value, max_val))

def map_range(value, in_min, in_max, out_min, out_max):
    """将数值从一个范围映射到另一个范围"""
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min