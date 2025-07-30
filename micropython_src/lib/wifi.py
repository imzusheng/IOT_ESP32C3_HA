# wifi.py
"""
WiFi管理模块

从utils.py中分离出来的WiFi连接管理功能，提供：
- WiFi连接状态管理
- 网络扫描和连接
- 状态机驱动的连接流程
- 事件驱动的状态通知
"""

import network
import time
import esp32
import uasyncio as asyncio
from enum import Enum
from lib import core
from config import (
    get_event_id, DEBUG, 
    EV_WIFI_CONNECTING, EV_WIFI_CONNECTED, EV_WIFI_ERROR, EV_WIFI_TIMEOUT,
    WIFI_CONNECT_TIMEOUT_S, WIFI_RETRY_INTERVAL_S, WIFI_CONFIGS
)

# WiFi状态机枚举
class WifiState(Enum):
    """WiFi连接状态机的状态定义"""
    DISCONNECTED = 1  # 未连接状态
    SCANNING = 2      # 扫描网络状态
    CONNECTING = 3    # 正在连接状态
    CONNECTED = 4     # 已连接状态
    RETRY_WAIT = 5    # 重试等待状态

# WiFi模块内部状态变量
_wifi_connected = False
_wifi_check_interval_s = 30  # 动态配置变量（用于温度优化）

def _on_config_update(**kwargs):
    """处理配置更新事件（温度优化）"""
    global _wifi_check_interval_s
    
    new_config = kwargs.get('config', {})
    temp_level = kwargs.get('temp_level', 'normal')
    source = kwargs.get('source', 'unknown')
    
    if source == 'temp_optimizer':
        if DEBUG:
            print(f"[WiFi] 收到温度优化配置更新，温度级别: {temp_level}")
        
        # 更新WiFi检查间隔
        if 'wifi_check_interval_s' in new_config:
            _wifi_check_interval_s = max(30, new_config['wifi_check_interval_s'])
            if DEBUG:
                print(f"[WiFi] 更新连接检查间隔为: {_wifi_check_interval_s}秒")

async def scan_available_networks():
    """扫描可用的WiFi网络 - 异步版本"""
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
        await asyncio.sleep_ms(1000)
    
    print("[WiFi] 正在扫描可用网络...")
    try:
        networks = wlan.scan()
        if networks:
            available_ssids = [net[0].decode('utf-8') for net in networks]
            print(f"[WiFi] 发现 {len(available_ssids)} 个网络")
            return available_ssids
        else:
            print("[WiFi] 扫描结果为空")
            return []
    except Exception as e:
        print(f"[WiFi] [ERROR] 扫描网络失败: {e}")
        return []

async def scan_available_networks_for_config():
    """扫描并返回配置中可用的网络"""
    available_networks = await scan_available_networks()
    if not available_networks:
        return []
    
    # 返回配置中可用的网络
    available_configs = []
    for config in WIFI_CONFIGS:
        if config["ssid"] in available_networks:
            available_configs.append(config)
    
    return available_configs

async def _wait_for_connection(wlan, ssid):
    """内部辅助函数：等待WiFi连接完成"""
    start_time = time.time()
    blink_count = 0
    
    while not wlan.isconnected():
        if time.time() - start_time > WIFI_CONNECT_TIMEOUT_S:
            error_msg = f"连接 {ssid} 超时"
            print(f"\n[WiFi] [ERROR] {error_msg}！")
            core.publish(EV_WIFI_TIMEOUT, ssid=ssid)
            return False
        
        # 每2秒发布连接中事件（用于LED闪烁）
        blink_count += 1
        if blink_count % 40 == 0:  # 50ms * 40 = 2秒
            core.publish(get_event_id('wifi_connecting_blink'))
        
        await asyncio.sleep_ms(50)
    
    return True

async def connect_wifi_attempt(wifi_configs):
    """尝试连接WiFi网络（支持多个网络尝试）"""
    global _wifi_connected
    
    if not wifi_configs:
        return False
    
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    
    # 尝试连接所有可用网络
    for config in wifi_configs:
        ssid = config["ssid"]
        password = config["password"]
        
        print(f"[WiFi] 尝试连接到: {ssid}")
        core.publish(get_event_id('wifi_trying'), ssid=ssid)
        
        try:
            # 断开之前的连接
            if wlan.isconnected():
                wlan.disconnect()
                await asyncio.sleep_ms(500)
            
            # 开始连接过程
            wlan.connect(ssid, password)
            
            if await _wait_for_connection(wlan, ssid):
                # 连接成功处理
                ip_info = wlan.ifconfig()
                ip = ip_info[0]
                print(f"\n[WiFi] [SUCCESS] 成功连接到: {ssid}")
                print(f"[WiFi] IP地址: {ip}")
                _wifi_connected = True
                core.publish(EV_WIFI_CONNECTED, ssid=ssid, ip=ip, reconnect=True)
                core.publish(get_event_id('log_info'), message=f"WiFi连接成功: {ssid} ({ip})")
                return True
            else:
                error_msg = f"连接 {ssid} 超时"
                print(f"[WiFi] [WARNING] {error_msg}")
                core.publish(EV_WIFI_ERROR, ssid=ssid, error=error_msg)
                continue
                
        except Exception as e:
            error_msg = f"连接 {ssid} 异常: {e}"
            print(f"[WiFi] [WARNING] {error_msg}")
            core.publish(EV_WIFI_ERROR, ssid=ssid, error=error_msg)
            continue
    
    # 所有网络都尝试失败
    error_msg = "所有WiFi网络连接失败"
    print(f"[WiFi] [ERROR] {error_msg}")
    _wifi_connected = False
    core.publish(get_event_id('wifi_failed'))
    core.publish(get_event_id('log_warning'), message=error_msg)
    return False

async def connect_wifi():
    """WiFi智能连接函数 - 异步版本，单次尝试"""
    global _wifi_connected
    
    print("[WiFi] 开始智能WiFi连接...")
    core.publish(EV_WIFI_CONNECTING)
    wlan = network.WLAN(network.STA_IF)
    
    if not wlan.active():
        wlan.active(True)

    # 检查是否已连接
    if wlan.isconnected():
        ssid = wlan.config('essid')
        ip = wlan.ifconfig()[0]
        print("[WiFi] 网络已连接。")
        print(f"[WiFi] IP地址: {ip}")
        if not _wifi_connected:
            _wifi_connected = True
            core.publish(EV_WIFI_CONNECTED, ssid=ssid, ip=ip, reconnect=False)
        return True

    # 扫描可用网络
    available_networks = await scan_available_networks()
    if not available_networks:
        error_msg = "未发现任何可用网络"
        print(f"[WiFi] [ERROR] {error_msg}")
        core.publish(get_event_id('wifi_scan_failed'))
        core.publish(get_event_id('log_warning'), message=error_msg)
        return False

    # 尝试连接配置中的第一个可用网络
    for config in WIFI_CONFIGS:
        ssid = config["ssid"]
        password = config["password"]
        
        if ssid in available_networks:
            print(f"[WiFi] 尝试连接到: {ssid}")
            core.publish(get_event_id('wifi_trying'), ssid=ssid)
            
            # 开始连接过程
            wlan.connect(ssid, password)
            
            if await _wait_for_connection(wlan, ssid):
                ip_info = wlan.ifconfig()
                ip = ip_info[0]
                print(f"\n[WiFi] [SUCCESS] 成功连接到: {ssid}")
                print(f"[WiFi] IP地址: {ip}")
                _wifi_connected = True
                core.publish(EV_WIFI_CONNECTED, ssid=ssid, ip=ip, reconnect=True)
                core.publish(get_event_id('log_info'), message=f"WiFi连接成功: {ssid} ({ip})")
                return True
            else:
                error_msg = f"连接 {ssid} 失败"
                print(f"[WiFi] [WARNING] {error_msg}")
                core.publish(EV_WIFI_ERROR, ssid=ssid, error=error_msg)
                break
    
    error_msg = "WiFi连接失败"
    print(f"[WiFi] [ERROR] {error_msg}")
    _wifi_connected = False
    core.publish(get_event_id('wifi_failed'))
    core.publish(get_event_id('log_warning'), message=error_msg)
    return False

async def wifi_task():
    """WiFi连接异步任务：基于状态机的重构版本"""
    global _wifi_connected
    
    print("[WiFi] 启动WiFi连接任务（状态机版本）...")
    
    # 订阅配置更新事件
    core.subscribe(get_event_id('config_update'), _on_config_update)
    
    wlan = network.WLAN(network.STA_IF)
    state = WifiState.DISCONNECTED
    available_configs = []
    error_count = 0
    
    while True:
        try:
            if DEBUG:
                print(f"[WiFi] 当前状态: {state.name}")
            
            # 温度检查（所有状态都需要检查）
            try:
                temp = esp32.mcu_temperature()
                if temp and temp > 42.0:
                    print(f"[WiFi] 温度过高 ({temp:.1f}°C)，暂停WiFi操作")
                    await asyncio.sleep(60)
                    continue
            except:
                pass
            
            # 状态机逻辑
            if state == WifiState.DISCONNECTED:
                if not wlan.active():
                    wlan.active(True)
                    await asyncio.sleep_ms(1000)
                
                if wlan.isconnected():
                    state = WifiState.CONNECTED
                else:
                    _wifi_connected = False
                    core.publish(get_event_id('led_set_effect'), mode='slow_blink')
                    state = WifiState.SCANNING
            
            elif state == WifiState.SCANNING:
                print("[WiFi] 扫描可用网络...")
                available_configs = await scan_available_networks_for_config()
                if not available_configs:
                    print("[WiFi] 未发现配置中的网络，等待重试")
                    state = WifiState.RETRY_WAIT
                else:
                    print(f"[WiFi] 发现 {len(available_configs)} 个可连接网络")
                    state = WifiState.CONNECTING
            
            elif state == WifiState.CONNECTING:
                print("[WiFi] 尝试连接网络...")
                success = await connect_wifi_attempt(available_configs)
                if success:
                    state = WifiState.CONNECTED
                else:
                    print("[WiFi] 连接失败，进入重试等待")
                    state = WifiState.RETRY_WAIT
            
            elif state == WifiState.CONNECTED:
                if not _wifi_connected:
                    _wifi_connected = True
                    print("[WiFi] WiFi连接状态已确认")
                    core.publish(get_event_id('led_set_effect'), mode='single_on', led_num=1)
                
                # 使用动态WiFi检查间隔（支持温度优化）
                await asyncio.sleep(_wifi_check_interval_s)
                
                # 检查连接状态
                if not wlan.isconnected():
                    print("[WiFi] 检测到连接丢失")
                    _wifi_connected = False
                    state = WifiState.DISCONNECTED
            
            elif state == WifiState.RETRY_WAIT:
                print(f"[WiFi] 连接失败，{WIFI_RETRY_INTERVAL_S}秒后重试...")
                await asyncio.sleep(WIFI_RETRY_INTERVAL_S)
                state = WifiState.SCANNING
            
            # 状态间的短暂延迟，避免过于频繁的状态切换
            if state != WifiState.CONNECTED and state != WifiState.RETRY_WAIT:
                await asyncio.sleep_ms(500)
                
        except Exception as e:
            error_count += 1
            error_msg = f"WiFi任务错误 (第{error_count}次): {e}"
            print(f"[WiFi] [ERROR] {error_msg}")
            core.publish(get_event_id('log_warning'), message=error_msg)
            
            # 如果错误次数过多，延长等待时间
            if error_count > 5:
                await asyncio.sleep(30)
                error_count = 0
            else:
                await asyncio.sleep(10)
            
            state = WifiState.RETRY_WAIT

def get_wifi_status():
    """获取WiFi状态"""
    try:
        wlan = network.WLAN(network.STA_IF)
        status = {
            'connected': _wifi_connected,
            'active': wlan.active(),
            'ip_address': None,
            'ssid': None
        }
        
        if wlan.isconnected():
            status['ip_address'] = wlan.ifconfig()[0]
            status['ssid'] = wlan.config('essid')
        
        return status
    except Exception as e:
        if DEBUG:
            print(f"[WiFi] 获取状态失败: {e}")
        return {'connected': False, 'active': False, 'ip_address': None, 'ssid': None}

def is_wifi_connected():
    """检查WiFi是否已连接"""
    return _wifi_connected