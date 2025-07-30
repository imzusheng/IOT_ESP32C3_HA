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
from . import core
from .config import (
    get_event_id, DEBUG,
    NTP_RETRY_DELAY_S, TIMEZONE_OFFSET_HOURS,
    EV_WIFI_CONNECTED
)

# NTP模块内部状态变量
_ntp_synced = False

def get_local_time():
    """获取本地时间（考虑时区偏移）"""
    try:
        utc_time = time.localtime()
        # 计算时区偏移后的时间戳
        utc_timestamp = time.mktime(utc_time)
        local_timestamp = utc_timestamp + (TIMEZONE_OFFSET_HOURS * 3600)
        local_time = time.localtime(local_timestamp)
        return local_time
    except Exception as e:
        print(f"[TIME] [ERROR] 获取本地时间失败: {e}")
        return time.localtime()

def format_time(time_tuple):
    """格式化时间显示"""
    try:
        year, month, day, hour, minute, second = time_tuple[:6]
        return f"{year}年{month:02d}月{day:02d}日 {hour:02d}:{minute:02d}:{second:02d}"
    except:
        return "时间格式错误"

async def sync_ntp_time():
    """通过NTP同步设备的实时时钟（RTC）并显示本地时间 - 异步版本"""
    global _ntp_synced
    
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        error_msg = "未连接到WiFi，无法同步时间"
        print(f"[NTP] [ERROR] {error_msg}。")
        core.publish(get_event_id('ntp_no_wifi'))
        core.publish(get_event_id('log_warning'), message=error_msg)
        return False

    try:
        print("[NTP] 正在尝试同步网络时间...")
        core.publish(get_event_id('ntp_syncing'))
        ntptime.settime()
        
        if time.localtime()[0] > 2023:
            utc_time = time.localtime()
            local_time = get_local_time()
            
            print("[NTP] [SUCCESS] 时间同步成功！")
            print(f"[NTP] UTC时间: {format_time(utc_time)}")
            print(f"[NTP] 本地时间: {format_time(local_time)} (UTC+{TIMEZONE_OFFSET_HOURS})")
            _ntp_synced = True
            core.publish(get_event_id('ntp_synced'), 
                        utc_time=format_time(utc_time),
                        local_time=format_time(local_time),
                        timezone_offset=TIMEZONE_OFFSET_HOURS)
            core.publish(get_event_id('log_info'), message=f"时间同步成功: {format_time(local_time)}")
            return True
    except Exception as e:
        error_msg = f"时间同步失败: {e}"
        print(f"[NTP] [WARNING] {error_msg}")
        core.publish(get_event_id('ntp_failed'), error=str(e))
        core.publish(get_event_id('log_warning'), message=error_msg)
        return False

def _on_wifi_connected(**kwargs):
    """WiFi连接成功时触发NTP同步"""
    if DEBUG:
        print("[NTP] 检测到WiFi连接成功，准备同步时间")
    
    # 创建异步任务来同步时间
    try:
        import uasyncio as asyncio
        asyncio.create_task(sync_ntp_time())
    except:
        # 如果无法创建异步任务，记录错误
        core.publish(get_event_id('log_warning'), message="无法创建NTP同步任务")

async def ntp_task():
    """NTP时间同步异步任务：负责定期同步时间"""
    global _ntp_synced
    
    print("[NTP] 启动NTP同步任务...")
    
    # 订阅WiFi连接事件
    core.subscribe(EV_WIFI_CONNECTED, _on_wifi_connected)
    
    error_count = 0
    
    while True:
        try:
            # 定期检查并重新同步时间（每24小时）
            if _ntp_synced:
                # 如果已经同步过，等待24小时后重新同步
                await asyncio.sleep(24 * 3600)  # 24小时
                
                # 检查WiFi连接状态
                wlan = network.WLAN(network.STA_IF)
                if wlan.isconnected():
                    print("[NTP] 定期重新同步时间...")
                    _ntp_synced = False  # 重置状态以允许重新同步
                    await sync_ntp_time()
            else:
                # 如果还未同步，等待较短时间后重试
                await asyncio.sleep(NTP_RETRY_DELAY_S)
                
                # 检查WiFi连接状态
                wlan = network.WLAN(network.STA_IF)
                if wlan.isconnected() and not _ntp_synced:
                    await sync_ntp_time()
                    
        except Exception as e:
            error_count += 1
            error_msg = f"NTP任务错误 (第{error_count}次): {e}"
            print(f"[NTP] [ERROR] {error_msg}")
            core.publish(get_event_id('log_warning'), message=error_msg)
            
            # 如果错误次数过多，延长等待时间
            if error_count > 3:
                await asyncio.sleep(300)  # 错误过多时等待5分钟
                error_count = 0
            else:
                await asyncio.sleep(60)  # 错误时等待1分钟

def get_ntp_status():
    """获取NTP同步状态"""
    status = {
        'synced': _ntp_synced,
        'current_time': None,
        'local_time': None
    }
    
    if _ntp_synced:
        try:
            utc_time = time.localtime()
            local_time = get_local_time()
            status['current_time'] = format_time(utc_time)
            status['local_time'] = format_time(local_time)
        except:
            pass
    
    return status

def is_ntp_synced():
    """检查NTP是否已同步"""
    return _ntp_synced