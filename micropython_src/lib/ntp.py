# ntp.py
"""
NTP时间同步模块

从utils.py中分离出来的NTP时间同步功能，提供：
- 网络时间同步
- 时区处理
- 定期时间更新
- 事件驱动的同步触发
"""

import time
try:
    import ntptime
except ImportError:
    ntptime = None
try:
    import network
except ImportError:
    network = None
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
from .config import (
    get_event_id, DEBUG,
    get_ntp_retry_delay, get_timezone_offset,
    EV_WIFI_CONNECTED
)

class NTPManager:
    """精简的NTP时间同步管理器 - 减少依赖注入复杂性"""

    def __init__(self, event_bus=None, retry_delay=60, timezone_offset=8):
        # 简化依赖注入，事件总线可选
        self.event_bus = event_bus
        self.get_event_id = lambda x: x
        
        # 直接使用配置参数
        self.retry_delay = retry_delay
        self.timezone_offset = timezone_offset
        
        # NTP同步状态
        self.ntp_synced = False

    def get_local_time(self):
        """获取本地时间（考虑时区偏移）"""
        try:
            utc_time = time.localtime()
            # 计算时区偏移后的时间戳
            utc_timestamp = time.mktime(utc_time)
            local_timestamp = utc_timestamp + (self.timezone_offset * 3600)
            local_time = time.localtime(local_timestamp)
            return local_time
        except Exception as e:
            print(f"[TIME] [ERROR] 获取本地时间失败: {e}")
            return time.localtime()

    def format_time(self, time_tuple):
        """格式化时间显示"""
        try:
            year, month, day, hour, minute, second = time_tuple[:6]
            return f"{year}年{month:02d}月{day:02d}日 {hour:02d}:{minute:02d}:{second:02d}"
        except:
             return "时间格式错误"

    async def sync_ntp_time(self):
        """通过NTP同步设备的实时时钟（RTC）并显示本地时间 - 异步版本"""
        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            error_msg = "未连接到WiFi，无法同步时间"
            print(f"[NTP] [ERROR] {error_msg}。")
            # 简化事件发布
            if self.event_bus:
                self.event_bus.publish(self.get_event_id('ntp_no_wifi'))
                self.event_bus.publish(self.get_event_id('log_warning'), message=error_msg)
            return False

        try:
            print("[NTP] 正在尝试同步网络时间...")
            # 简化事件发布
            if self.event_bus:
                self.event_bus.publish(self.get_event_id('ntp_syncing'))
            ntptime.settime()

            if time.localtime()[0] > 2023:
                utc_time = time.localtime()
                local_time = self.get_local_time()

                print("[NTP] [SUCCESS] 时间同步成功！")
                print(f"[NTP] UTC时间: {self.format_time(utc_time)}")
                print(f"[NTP] 本地时间: {self.format_time(local_time)} (UTC+{self.timezone_offset})")
                self.ntp_synced = True
                # 简化事件发布
                if self.event_bus:
                    self.event_bus.publish(self.get_event_id('ntp_synced'),
                                utc_time=self.format_time(utc_time),
                                local_time=self.format_time(local_time),
                                timezone_offset=self.timezone_offset)
                    self.event_bus.publish(self.get_event_id('log_info'), message=f"时间同步成功: {self.format_time(local_time)}")
                return True
        except Exception as e:
            error_msg = f"时间同步失败: {e}"
            print(f"[NTP] [WARNING] {error_msg}")
            # 简化事件发布
            if self.event_bus:
                self.event_bus.publish(self.get_event_id('ntp_failed'), error=str(e))
                self.event_bus.publish(self.get_event_id('log_warning'), message=error_msg)
            return False

    def _on_wifi_connected(self, **kwargs):
        """WiFi连接成功时触发NTP同步"""
        if DEBUG:
            print("[NTP] 检测到WiFi连接成功，准备同步时间")

        # 创建异步任务来同步时间
        try:
            import uasyncio as asyncio
            asyncio.create_task(self.sync_ntp_time())
        except:
            # 如果无法创建异步任务，记录错误
            if self.event_bus:
                self.event_bus.publish(self.get_event_id('log_warning'), message="无法创建NTP同步任务")

    async def ntp_task(self):
        """NTP时间同步异步任务：负责定期同步时间"""
        print("[NTP] 启动NTP同步任务...")

        # 简化事件订阅
        if self.event_bus:
            try:
                self.event_bus.subscribe(self.get_event_id('wifi_connected'), self._on_wifi_connected)
            except:
                pass

        error_count = 0

        while True:
            try:
                # 定期检查并重新同步时间（每24小时）
                if self.ntp_synced:
                    # 如果已经同步过，等待24小时后重新同步
                    await asyncio.sleep(24 * 3600)  # 24小时

                    # 检查WiFi连接状态
                    wlan = network.WLAN(network.STA_IF)
                    if wlan.isconnected():
                        print("[NTP] 定期重新同步时间...")
                        self.ntp_synced = False  # 重置状态以允许重新同步
                        await self.sync_ntp_time()
                else:
                    # 如果还未同步，等待较短时间后重试
                    await asyncio.sleep(self.retry_delay)

                    # 检查WiFi连接状态
                    wlan = network.WLAN(network.STA_IF)
                    if wlan.isconnected() and not self.ntp_synced:
                        await self.sync_ntp_time()

            except Exception as e:
                error_count += 1
                error_msg = f"NTP任务错误 (第{error_count}次): {e}"
                print(f"[NTP] [ERROR] {error_msg}")
                # 简化事件发布
                if self.event_bus:
                    self.event_bus.publish(self.get_event_id('log_warning'), message=error_msg)

                # 如果错误次数过多，延长等待时间
                if error_count > 3:
                    await asyncio.sleep(300)  # 错误过多时等待5分钟
                    error_count = 0
                else:
                     await asyncio.sleep(60)  # 错误时等待1分钟

    def get_ntp_status(self):
        """获取NTP同步状态"""
        status = {
            'synced': self.ntp_synced,
            'current_time': None,
            'local_time': None
        }

        if self.ntp_synced:
            try:
                utc_time = time.localtime()
                local_time = self.get_local_time()
                status['current_time'] = self.format_time(utc_time)
                status['local_time'] = self.format_time(local_time)
            except:
                pass

        return status

    def is_ntp_synced(self):
        """检查NTP是否已同步"""
        return self.ntp_synced

# 全局NTP管理器实例（向后兼容）
_global_ntp_manager = None

def _ensure_global_ntp_manager():
    """确保全局NTP管理器已初始化（向后兼容）"""
    global _global_ntp_manager
    if _global_ntp_manager is None:
        # 导入core和config以保持向后兼容性
        try:
            from . import core
            from . import config
            _global_ntp_manager = NTPManager(event_bus=core, config_getter=config)
        except ImportError:
            _global_ntp_manager = NTPManager()
    return _global_ntp_manager

# 向后兼容的全局函数
def get_local_time():
    """获取本地时间（考虑时区偏移）"""
    manager = _ensure_global_ntp_manager()
    return manager.get_local_time()

def format_time(time_tuple):
    """格式化时间显示"""
    manager = _ensure_global_ntp_manager()
    return manager.format_time(time_tuple)

async def sync_ntp_time():
    """通过NTP同步设备的实时时钟（RTC）并显示本地时间 - 异步版本"""
    manager = _ensure_global_ntp_manager()
    return await manager.sync_ntp_time()

async def ntp_task():
    """NTP时间同步异步任务：负责定期同步时间"""
    manager = _ensure_global_ntp_manager()
    return await manager.ntp_task()

def get_ntp_status():
    """获取NTP同步状态"""
    manager = _ensure_global_ntp_manager()
    return manager.get_ntp_status()

def is_ntp_synced():
    """检查NTP是否已同步"""
    manager = _ensure_global_ntp_manager()
    return manager.is_ntp_synced()

# 简化的工厂函数
def create_ntp_manager(event_bus=None, config_getter=None, **kwargs):
    """创建NTP管理器实例 - 简化版本"""
    # 直接从配置获取参数，减少依赖
    if config_getter:
        try:
            retry_delay = config_getter.get_ntp_retry_delay()
            timezone_offset = config_getter.get_timezone_offset()
        except:
            # 如果配置获取失败，使用默认值
            retry_delay = kwargs.get('retry_delay', 60)
            timezone_offset = kwargs.get('timezone_offset', 8)
    else:
        # 使用传入的参数或默认值
        retry_delay = kwargs.get('retry_delay', 60)
        timezone_offset = kwargs.get('timezone_offset', 8)
    
    manager = NTPManager(event_bus=event_bus, retry_delay=retry_delay, timezone_offset=timezone_offset)
    
    # 设置事件总线（可选）
    if event_bus:
        try:
            manager.get_event_id = config_getter.get_event_id if config_getter else lambda x: x
        except:
            manager.get_event_id = lambda x: x
    
    return manager
