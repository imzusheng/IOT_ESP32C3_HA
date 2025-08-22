# app/utils/helpers.py
"""
通用辅助函数模块 (重构版本)
提供系统监控、内存检查、时间格式化等实用功能

为事件驱动架构提供系统级支持功能, 包括内存监控、
温度检测、设备信息获取和网络辅助功能。

特性:
- 内存使用监控和统计
- 内部温度传感器读取
- 设备信息获取
- 网络参数验证
- 字符串缓存优化
- 节流器功能
"""

import gc
import utime as time
import machine
import sys
from lib.logger import info, error


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
            "free": mem_free,
            "allocated": mem_alloc,
            "total": mem_total,
            "percent": percent_used,
            "free_kb": mem_free // 1024,
            "allocated_kb": mem_alloc // 1024,
            "total_kb": mem_total // 1024,
        }
    except Exception as e:
        error(f"内存检查失败: {e}", module="Utils")
        return {
            "free": 0,
            "allocated": 0,
            "total": 0,
            "percent": 0,
            "free_kb": 0,
            "allocated_kb": 0,
            "total_kb": 0,
        }


def get_formatted_time():
    """
    获取格式化的时间字符串
    由于ESP32-C3没有实时时钟, 返回运行时间
    """
    try:
        # 获取系统运行时间(毫秒)
        uptime_ms = time.ticks_ms()

        # 转换为秒
        uptime_sec = uptime_ms // 1000

        # 计算小时、分钟、秒
        hours = uptime_sec // 3600
        minutes = (uptime_sec % 3600) // 60
        seconds = uptime_sec % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    except Exception as e:
        error(f"时间格式化失败: {e}", module="Utils")
        return "00:00:00"


def get_uptime():
    """
    获取系统运行时间(秒)
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
        for unit in ["B", "KB", "MB", "GB"]:
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
        info("系统重启中...", module="Utils")
        time.sleep_ms(100)  # 给日志输出一些时间
        machine.reset()
    except Exception as e:
        error(f"安全重启失败: {e}", module="Utils")
        # 尝试直接重启
        machine.reset()


def get_device_info():
    """
    获取设备基本信息
    """
    try:
        return {
            "machine": machine.__name__,
            "platform": sys.platform,
            "version": sys.version,
            "frequency": machine.freq(),
            "unique_id": (
                machine.unique_id().hex()
                if hasattr(machine, "unique_id")
                else "unknown"
            ),
        }
    except Exception as e:
        error(f"设备信息获取失败: {e}", module="Utils")
        return {
            "machine": "未知",
            "platform": "未知平台",
            "version": "未知版本",
            "frequency": 0,
            "unique_id": "未知ID",
        }


def validate_ip_address(ip_str):
    """
    验证IP地址格式
    """
    try:
        parts = ip_str.split(".")
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

        # 如果SSID为空或只包含空格, 返回None
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
        # RSSI范围通常是-30(极强)到-90(极弱)
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
    """简单的字符串缓存, 减少内存分配"""

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


# 节流器类
class Throttle:
    """
    节流器
    确保在指定时间窗口内最多触发一次

    使用场景：
    - WiFi重连频率控制
    - MQTT发布频率控制
    - 传感器采样频率控制
    - 按钮点击防连击
    """

    def __init__(self, throttle_ms):
        """
        初始化节流器

        :param throttle_ms: 节流时间窗口(毫秒)
        """
        self.throttle_ms = throttle_ms
        self.last_trigger = 0

    def should_trigger(self):
        """
        检查是否应该触发

        :return: True表示可以触发, False表示在节流期内
        """
        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_trigger) >= self.throttle_ms:
            self.last_trigger = now
            return True
        return False

    def reset(self):
        """重置节流器"""
        self.last_trigger = 0

    def set_throttle_time(self, throttle_ms):
        """
        设置节流时间

        :param throttle_ms: 新的节流时间窗口(毫秒)
        """
        self.throttle_ms = throttle_ms

    def time_until_next_trigger(self):
        """
        获取距离下次可触发的时间

        :return: 距离下次可触发的毫秒数
        """
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self.last_trigger)
        remaining = self.throttle_ms - elapsed
        return max(0, remaining)

    def is_ready(self):
        """
        检查是否已经准备好触发

        :return: True表示已过节流期, 可以触发
        """
        return self.time_until_next_trigger() == 0


def get_temperature():
    """
    读取 MCU内部温度 单位摄氏度

    仅使用 esp32.mcu_temperature()，这是 ESP32-C3/C6/S2/S3 平台提供的 MCU 温度读取接口。
    """
    try:
        import esp32
        # 直接读取 MCU 温度(摄氏度)，并保留一位小数
        temp_c = esp32.mcu_temperature()
        return round(temp_c, 1)
    except Exception as e:
        # 若底层不支持或读取异常，返回 None 并记录错误
        error(f"温度读取失败: {e}", module="Utils")
        return None


def emergency_cleanup():
    """执行紧急垃圾回收清理

    在系统内存不足或进入安全模式时调用,
    执行深度的垃圾回收以释放内存。
    """
    try:
        info("执行紧急垃圾回收...", module="Utils")

        # 深度垃圾回收
        for _ in range(3):
            gc.collect()
            time.sleep_ms(50)

        info("紧急垃圾回收完成", module="Utils")
    except Exception as e:
        error(f"紧急垃圾回收失败: {e}", module="Utils")


# 模块初始化
# Helper module loaded
