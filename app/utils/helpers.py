# app/utils/helpers.py
"""
通用辅助函数模块 (重构版本)
提供系统监控、内存检查、时间格式化等实用功能

为事件驱动架构提供系统级支持功能，包括内存监控、
温度检测、设备信息获取和网络辅助功能。

特性:
- 内存使用监控和统计
- 内部温度传感器读取
- 设备信息获取
- 网络参数验证
- 字符串缓存优化
"""

import gc
import utime as time
import machine
import sys
from lib.logger import get_global_logger

def check_memory():
    """
    检查系统内存使用情况
    返回包含内存统计信息的字典
    """
    try:
        # 获取内存信息
        mem_free = gc.mem_free()
        mem_alloc = gc.mem_alloc()
        mem_total = mem_free + mem_alloc
        
        # 计算使用百分比
        if mem_total > 0:
            percent_used = (mem_alloc / mem_total) * 100
        else:
            percent_used = 0
        
        return {
            'free': mem_free,
            'allocated': mem_alloc,
            'total': mem_total,
            'percent': percent_used,
            'free_kb': mem_free // 1024,
            'allocated_kb': mem_alloc // 1024,
            'total_kb': mem_total // 1024
        }
    except Exception as e:
        logger = get_global_logger()
        logger.error(f"内存检查失败: {e}", module="Utils")
        return {
            'free': 0,
            'allocated': 0,
            'total': 0,
            'percent': 0,
            'free_kb': 0,
            'allocated_kb': 0,
            'total_kb': 0
        }

def get_temperature():
    """
    获取ESP32-C3内部温度传感器读数
    返回摄氏度温度，如果失败则返回None
    """
    try:
        # ESP32-C3温度传感器实现
        temp_sensor = machine.ADC(4)  # GPIO4是温度传感器
        temp_sensor.width(12)
        temp_sensor.attenuation(11)  # 11dB衰减
        
        # 读取ADC值
        adc_value = temp_sensor.read()
        
        # 转换为温度（近似公式）
        # 注意：这是一个近似值，实际校准可能需要调整
        voltage = adc_value * 3.3 / 4095
        temperature = (voltage - 0.5) * 100  # 简化的转换公式
        
        return round(temperature, 1)
    except Exception as e:
        logger = get_global_logger()
        logger.error(f"温度读取失败: {e}", module="Utils")
        return None

def get_formatted_time():
    """
    获取格式化的时间字符串
    由于ESP32-C3没有实时时钟，返回运行时间
    """
    try:
        # 获取系统运行时间（毫秒）
        uptime_ms = time.ticks_ms()
        
        # 转换为秒
        uptime_sec = uptime_ms // 1000
        
        # 计算小时、分钟、秒
        hours = uptime_sec // 3600
        minutes = (uptime_sec % 3600) // 60
        seconds = uptime_sec % 60
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception as e:
        logger = get_global_logger()
        logger.error(f"时间格式化失败: {e}", module="Utils")
        return "00:00:00"

def get_uptime():
    """
    获取系统运行时间（秒）
    """
    try:
        return time.ticks_ms() // 1000
    except Exception:
        return 0

def format_bytes(bytes_value):
    """
    格式化字节大小为人类可读格式
    """
    try:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.1f}{unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.1f}TB"
    except Exception:
        return "0B"

def safe_reboot():
    """
    安全重启设备
    """
    try:
        logger = get_global_logger()
        logger.info("系统重启中...", module="Utils")
        time.sleep_ms(100)  # 给日志输出一些时间
        machine.reset()
    except Exception as e:
        logger = get_global_logger()
        logger.error(f"安全重启失败: {e}", module="Utils")
        # 尝试直接重启
        machine.reset()

def get_device_info():
    """
    获取设备基本信息
    """
    try:
        return {
            'machine': machine.__name__,
            'platform': sys.platform,
            'version': sys.version,
            'frequency': machine.freq(),
            'unique_id': machine.unique_id().hex() if hasattr(machine, 'unique_id') else 'unknown'
        }
    except Exception as e:
        logger = get_global_logger()
        logger.error(f"设备信息获取失败: {e}", module="Utils")
        return {
            'machine': '未知',
            'platform': '未知平台',
            'version': '未知版本',
            'frequency': 0,
            'unique_id': '未知ID'
        }

def validate_ip_address(ip_str):
    """
    验证IP地址格式
    """
    try:
        parts = ip_str.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            if not part.isdigit():
                return False
            num = int(part)
            if num < 0 or num > 255:
                return False
        
        return True
    except Exception:
        return False

def normalize_ssid(ssid):
    """
    规范化WiFi SSID字符串
    """
    try:
        # 移除首尾空格
        ssid = ssid.strip()
        
        # 如果SSID为空或只包含空格，返回None
        if not ssid:
            return None
        
        return ssid
    except Exception:
        return None

def calculate_rssi_percentage(rssi):
    """
    将WiFi RSSI值转换为百分比信号强度
    """
    try:
        # RSSI范围通常是-30（极强）到-90（极弱）
        if rssi >= -30:
            return 100
        elif rssi <= -90:
            return 0
        else:
            # 线性映射
            return int(((rssi + 90) / 60) * 100)
    except Exception:
        return 0

# 内存优化的字符串常量
class StringCache:
    """简单的字符串缓存，减少内存分配"""
    def __init__(self):
        self._cache = {}
    
    def get(self, text):
        if text not in self._cache:
            self._cache[text] = text
        return self._cache[text]
    
    def clear(self):
        self._cache.clear()

# 全局字符串缓存实例
_string_cache = StringCache()

def get_cached_string(text):
    """获取缓存的字符串实例"""
    return _string_cache.get(text)

# 模块初始化
# Helper module loaded