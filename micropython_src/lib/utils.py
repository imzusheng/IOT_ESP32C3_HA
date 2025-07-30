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

# 预分配内存信息字典模板以减少内存分配
_MEMORY_INFO_TEMPLATE = {
    'free': 0,
    'allocated': 0,
    'total': 0,
    'usage_percent': 0
}

def get_memory_info():
    """获取内存信息"""
    try:
        gc.collect()
        free = gc.mem_free()
        allocated = gc.mem_alloc()
        total = free + allocated

        # 复用模板字典以减少内存分配
        result = _MEMORY_INFO_TEMPLATE.copy()
        result['free'] = free
        result['allocated'] = allocated
        result['total'] = total
        result['usage_percent'] = round((allocated / total) * 100, 2) if total > 0 else 0
        return result
    except Exception as e:
        result = _MEMORY_INFO_TEMPLATE.copy()
        result['error'] = str(e)
        return result

# =============================================================================
# 系统状态工具
# =============================================================================

# 预分配系统状态字典模板
_SYSTEM_STATUS_TEMPLATE = {
    'wifi_connected': False,
    'memory': None,
    'temperature': None,
    'timestamp': 0
}

def get_system_status():
    """获取系统状态信息"""
    try:
        import network
        wlan = network.WLAN(network.STA_IF)
        wifi_connected = wlan.isconnected()

        memory_info = get_memory_info()

        # 尝试获取温度信息
        temp = None
        try:
            import esp32
            temp = esp32.raw_temperature()
        except:
            pass

        # 复用模板字典
        result = _SYSTEM_STATUS_TEMPLATE.copy()
        result['wifi_connected'] = wifi_connected
        result['memory'] = memory_info
        result['temperature'] = temp
        result['timestamp'] = time.time()
        return result
    except Exception as e:
        result = _SYSTEM_STATUS_TEMPLATE.copy()
        result['memory'] = get_memory_info()
        result['timestamp'] = time.time()
        result['error'] = str(e)
        return result

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
