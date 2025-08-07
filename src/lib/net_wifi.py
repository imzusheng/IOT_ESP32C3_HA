# -*- coding: utf-8 -*-
"""
WiFi管理器模块

提供健壮的WiFi连接管理和NTP时间同步功能。
支持多网络选择、RSSI排序、自动重连和错误恢复。
使用集中配置管理，确保系统一致性。
"""
import time
import network
import gc
import machine
import ntptime

# 全局WiFi网络配置
_wifi_networks = []
# WiFi配置从config.py中获取
import config

# 全局WiFi配置变量
_wifi_timeout = 15
_wifi_scan_interval = 30
_wifi_connection_retry_delay = 2
_wifi_max_connection_attempts = 3

def set_wifi_networks(networks):
    """设置WiFi网络配置"""
    global _wifi_networks
    _wifi_networks = networks
    print(f"[WiFi] 已设置 {len(networks)} 个WiFi网络配置")

def set_wifi_config(timeout=None, scan_interval=None, retry_delay=None, max_attempts=None):
    """设置WiFi连接参数（从config.py获取）"""
    global _wifi_timeout, _wifi_scan_interval, _wifi_connection_retry_delay, _wifi_max_connection_attempts
    _wifi_timeout = timeout
    _wifi_scan_interval = scan_interval
    _wifi_connection_retry_delay = retry_delay
    _wifi_max_connection_attempts = max_attempts
    print(f"[WiFi] 已设置WiFi连接参数")

def load_wifi_config_from_main(config_data):
    """从主配置文件加载WiFi配置"""
    global _wifi_timeout, _wifi_scan_interval, _wifi_connection_retry_delay, _wifi_max_connection_attempts
    
    try:
        # 获取WiFi配置部分
        wifi_config = config_data.get('wifi', {})
        
        # 获取WiFi配置中的config部分
        wifi_subconfig = wifi_config.get('config', {})
        
        # 更新全局配置
        _wifi_timeout = wifi_subconfig.get('timeout', config.get_config('wifi', 'timeout', 15))
        _wifi_scan_interval = wifi_subconfig.get('scan_interval', config.get_config('wifi', 'scan_interval', 30))
        _wifi_connection_retry_delay = wifi_subconfig.get('retry_delay', config.get_config('wifi', 'retry_delay', 2))
        _wifi_max_connection_attempts = wifi_subconfig.get('max_attempts', config.get_config('wifi', 'max_attempts', 3))
        
        print(f"[WiFi] 从主配置文件加载WiFi配置完成")
        return True
        
    except Exception as e:
        print(f"[WiFi] 从主配置文件加载WiFi配置失败: {e}")
        return False


def _scan_for_ssids(wlan):
    """
    扫描周围的WiFi网络并返回(ssid, rssi)列表
    
    参数：
    - wlan: WLAN接口对象
    
    返回：
    - list: [(ssid, rssi), ...] 匹配配置的网络列表
    """
    print("[WiFi] 正在扫描网络...")
    print(f"[WiFi] 配置的网络: {[c['ssid'] for c in _wifi_networks]}")
    
    scanned_networks = []
    target_ssids = {c['ssid'] for c in _wifi_networks}
    
    try:
        scan_results = wlan.scan()
        print(f"[WiFi] 扫描到 {len(scan_results)} 个网络")
        
        if not scan_results:
            print("[WiFi] 警告: 没有扫描到任何网络")
            return []
        
        for i, res in enumerate(scan_results):
            try:
                ssid_bytes = res[0]
                ssid = ssid_bytes.decode('utf-8')
                rssi = res[3]
                channel = res[2]
                bssid = res[1]
                
                print(f"[WiFi] 网络 {i+1}: SSID='{ssid}' | RSSI={rssi} dBm | CH={channel} | BSSID={bssid.hex()}")
                
                if ssid in target_ssids:
                    scanned_networks.append((ssid, rssi))
                    print(f"[WiFi] [OK] 发现配置网络: {ssid:<20} | RSSI: {rssi} dBm")
                else:
                    # 检查是否有相似的SSID（用于调试）
                    for target_ssid in target_ssids:
                        # 避免空字符串匹配和过短的字符串匹配
                        if (ssid and target_ssid and len(ssid.strip()) > 0 and len(target_ssid.strip()) > 0 and 
                            len(ssid) >= 3 and len(target_ssid) >= 3 and
                            (target_ssid.lower() in ssid.lower() or ssid.lower() in target_ssid.lower())):
                            print(f"[WiFi] 发现相似网络: '{ssid}' (目标: '{target_ssid}')")
                    
            except UnicodeError:
                try:
                    # 尝试其他编码
                    ssid = res[0].decode('latin-1')
                    print(f"[WiFi] 网络 {i+1}: SSID='{ssid}' (Latin-1编码) | RSSI={res[3]} dBm")
                    
                    if ssid in target_ssids:
                        scanned_networks.append((ssid, res[3]))
                        print(f"[WiFi] [OK] 发现配置网络(Latin-1): {ssid:<20} | RSSI: {res[3]} dBm")
                except:
                    print(f"[WiFi] 网络 {i+1}: 无法解码SSID")
            except Exception as e:
                print(f"[WiFi] 解析网络 {i+1} 失败: {e}")
                
        # 按RSSI强度排序
        scanned_networks.sort(key=lambda x: x[1], reverse=True)
        print(f"[WiFi] 匹配的网络数量: {len(scanned_networks)}")
        return scanned_networks
        
    except Exception as e:
        print(f"\033[1;31m[WiFi] 扫描网络失败: {e}\033[0m")
        return []


def sync_and_set_time():
    """
    使用NTP同步设备时间、设置RTC并考虑时区
    
    返回：
    - True: 时间同步成功
    - False: 时间同步失败
    """
    print("\n[NTP] 开始时间同步...")
    ntptime.host = 'ntp.aliyun.com'  # 默认NTP服务器
    print(f"[NTP] 使用NTP服务器: {ntptime.host}")
    
    # 看门狗已移至主循环统一管理，NTP模块不再需要单独处理
    
    for i in range(3):  # 最多重试3次
        try:
            
            ntptime.settime()
            utc = time.localtime()
            local_time = time.localtime(time.time() + 8 * 3600)  # 中国时区 UTC+8
            
            # 设置RTC
            machine.RTC().datetime((utc[0], utc[1], utc[2], utc[6]+1, utc[3], utc[4], utc[5], 0))
            
            print(f"[NTP] 本地时间: {local_time[0]}-{local_time[1]:02d}-{local_time[2]:02d} {local_time[3]:02d}:{local_time[4]:02d}")
            gc.collect()
            return True
            
        except Exception as e:
            print(f"[NTP] 重试 {i+1}/3: {e}")
            # 等待重试
            time.sleep(3)
    
    print("\033[1;31m[NTP] 时间同步失败\033[0m")
    gc.collect()
    return False


def connect_wifi():
    """
    连接WiFi并同步时间
    
    功能：
    - 扫描可用的WiFi网络
    - 按信号强度排序并连接最优网络
    - 同步NTP时间
    - 错误恢复和重试机制
    
    返回：
    - True: WiFi连接成功
    - False: WiFi连接失败
    """
    print("[WiFi] 开始连接WiFi...")
    
    # 看门狗已移至主循环统一管理，WiFi模块不再需要单独处理
    
    # 蓝牙功能已移除，不再需要蓝牙资源管理
    print("[WiFi] 蓝牙功能已移除，跳过蓝牙资源管理")
    
    wlan = network.WLAN(network.STA_IF)
    
    # 如果已连接，直接同步时间并返回
    if wlan.isconnected():
        sync_and_set_time()
        return True
    
    # 激活WLAN接口，添加错误处理
    try:
        if not wlan.active():
            print("[WiFi] 激活WLAN接口...")
            wlan.active(True)
            time.sleep_ms(1000)  # 增加等待时间确保接口完全激活
            
            # 验证接口是否成功激活
            if not wlan.active():
                print("\033[1;31m[WiFi] WLAN接口激活失败\033[0m")
                return False
    except Exception as e:
        print(f"\033[1;31m[WiFi] WLAN接口激活异常: {e}\033[0m")
        return False

    # 扫描网络
    scanned_networks = _scan_for_ssids(wlan)
    if not scanned_networks:
        print("\033[1;31m[WiFi] 未找到配置的网络\033[0m")
        wlan.active(False)
        return False

    # 获取可连接的网络配置
    available_ssids = {net[0] for net in scanned_networks}
    rssi_map = {net[0]: net[1] for net in scanned_networks}
    connectable_configs = [c for c in _wifi_networks if c['ssid'] in available_ssids]

    if not connectable_configs:
        print("\033[1;31m[WiFi] 没有匹配的网络配置\033[0m")
        wlan.active(False)
        return False

    # 按信号强度排序
    connectable_configs.sort(key=lambda c: rssi_map[c['ssid']], reverse=True)
    
    print("[WiFi] 可用网络（按信号强度排序）:")
    for network_config in connectable_configs:
        print(f"  - {network_config['ssid']} (RSSI: {rssi_map[network_config['ssid']]} dBm)")

    # 尝试连接每个网络
    for network_config in connectable_configs:
        ssid = network_config["ssid"]
        password = network_config["password"]
        
        print(f"\n[WiFi] 正在连接: {ssid}")
        wlan.connect(ssid, password)
        
        start_time = time.time()
        connection_timeout = _wifi_timeout
        
        while not wlan.isconnected():
            # 看门狗已移至主循环统一管理
            
            if time.time() - start_time > connection_timeout:
                print(f"\033[1;31m[WiFi] 连接 {ssid} 超时\033[0m")
                break
            time.sleep(1)

        if wlan.isconnected():
            ip_address = wlan.ifconfig()[0]
            print(f"\033[1;32m[WiFi] 成功连接: {ssid}\033[0m")
            print(f"\033[1;34m[WiFi] IP地址: {ip_address}\033[0m")
            
            # 同步时间
            sync_and_set_time()
            
            # 清理内存
            gc.collect()
            return True

    print("\n\033[1;31m[WiFi] 所有网络连接失败\033[0m")
    wlan.active(False)
    return False


def get_wifi_status():
    """
    获取WiFi连接状态
    
    返回：
    - dict: 包含连接状态信息的字典
    """
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        ip_config = wlan.ifconfig()
        return {
            'connected': True,
            'ip_address': ip_config[0],
            'subnet_mask': ip_config[1],
            'gateway': ip_config[2],
            'dns_server': ip_config[3]
        }
    else:
        return {
            'connected': False,
            'ip_address': None,
            'subnet_mask': None,
            'gateway': None,
            'dns_server': None
        }


def disconnect_wifi():
    """断开WiFi连接"""
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        wlan.disconnect()
        wlan.active(False)
        print("[WiFi] WiFi连接已断开")
        return True
    return False

   
if __name__ == "__main__":
    connection_successful = connect_wifi()

    if connection_successful:
        print("\n=== 网络设置和时间同步完成 ===")
    else:
        print("\n=== 网络连接失败，设备将进入低功耗模式 ===")