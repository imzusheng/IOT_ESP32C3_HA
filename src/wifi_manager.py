# -*- coding: utf-8 -*-
#
# wifi_manager.py
# 一个健壮的 MicroPython WiFi 连接和NTP时间同步模块
#
import time
import network
import gc
import machine
import ntptime

# --- 配置区 ---

# 在此列表中按顺序添加你希望连接的WiFi网络
WIFI_CONFIGS = [
    {"ssid": "zsm60p", "password": "25845600"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
    {"ssid": "leju_software", "password": "leju123456"}
]

# WebREPL 服务的密码
WEBREPL_PASSWORD = "123456"

# 连接单个网络时的超时时间（秒）
CONNECT_TIMEOUT_S = 15

# NTP服务器地址
NTP_HOST = 'ntp.aliyun.com'

# 时区偏移（小时）
TIMEZONE_OFFSET_H = 8


def _scan_for_ssids(wlan):
    """扫描周围的WiFi网络并返回(ssid, rssi)列表。"""
    print("[WiFi] Scanning for networks...")
    scanned_networks = []
    target_ssids = {c['ssid'] for c in WIFI_CONFIGS}
    try:
        scan_results = wlan.scan()
        for res in scan_results:
            try:
                ssid = res[0].decode('utf-8')
                if ssid in target_ssids:
                    rssi = res[3]
                    scanned_networks.append((ssid, rssi))
                    print(f"[WiFi] Match Config network: {ssid:<20} | RSSI: {rssi} dBm")
            except UnicodeError:
                pass
        return scanned_networks
    except Exception as e:
        print(f"\033[1;31m[WiFi] Error Scanning Networks: {e}\033[0m")
        return []


def sync_and_set_time():
    """使用NTP同步设备时间、设置RTC并考虑时区。"""
    print("\n[NTP] Starting time synchronization...")
    ntptime.host = NTP_HOST
    for i in range(3):
        try:
            ntptime.settime()
            utc = time.localtime()
            local = time.localtime(time.time() + TIMEZONE_OFFSET_H * 3600)
            machine.RTC().datetime((utc[0], utc[1], utc[2], utc[6]+1, utc[3], utc[4], utc[5], 0))
            print(f"[NTP] Local Time: {local[0]}-{local[1]:02d}-{local[2]:02d} {local[3]:02d}:{local[4]:02d}")
            gc.collect()
            return True
        except Exception as e:
            print(f"[NTP] retry {i+1}/3: {e}")
            time.sleep_ms(3000)
    print("\033[1;31m[NTP] Time synchronization failed after multiple attempts.\033[0m")
    gc.collect()
    return False


# def _start_webrepl_safe():
#     """安全地启动WebREPL。"""
#     try:
#         webrepl.start(password=WEBREPL_PASSWORD)
#         print(f"[WebREPL] Service started successfully.")
#     except Exception as e:
#         if "EADDRINUSE" in str(e):
#              print("\033[1;33m[WebREPL] Service is already running.\033[0m")
#         else:
#             print(f"\033[1;31m[WebREPL] Failed to start service! Error: {e}\033[0m")


def connect_wifi():
    """
    模块主函数: 连接WiFi, 同步时间, 启动服务。
    返回: True (成功) 或 False (失败)
    """
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        # wlan.disconnect()
        sync_and_set_time()
        return True
    if not wlan.active():
        wlan.active(True)

    scanned_networks = _scan_for_ssids(wlan)
    if not scanned_networks:
        print("\033[1;31m[WiFi] No networks found.\033[0m")
        wlan.active(False)
        return False

    available_ssids = {net[0] for net in scanned_networks}
    rssi_map = {net[0]: net[1] for net in scanned_networks}
    connectable_configs = [c for c in WIFI_CONFIGS if c['ssid'] in available_ssids]

    if not connectable_configs:
        print("\033[1;31m[WiFi] No matching networks found.\033[0m")
        wlan.active(False)
        return False

    connectable_configs.sort(key=lambda c: rssi_map[c['ssid']], reverse=True)
    for config in connectable_configs:
        print(f"  - {config['ssid']} (RSSI: {rssi_map[config['ssid']]} dBm)")

    for config in connectable_configs:
        ssid = config["ssid"]
        password = config["password"]
        print(f"\n[WiFi] Connecting to: {ssid}")
        wlan.connect(ssid, password)
        start_time = time.time()
        while not wlan.isconnected():
            if time.time() - start_time > CONNECT_TIMEOUT_S:
                print(f"\033[1;31m[WiFi] Connection to {ssid} timed out.\033[0m")
                break
            time.sleep(1)

        if wlan.isconnected():
            ip_address = wlan.ifconfig()[0]
            print(f"\033[1;32m[WiFi] Successfully connected to: {ssid}\033[0m")
            print(f"\033[1;34m[WiFi] IP address: {ip_address}\033[0m")
            sync_and_set_time()
            # _start_webrepl_safe()
            gc.collect()
            return True

    print("\n\033[1;31m[WiFi] Failed to connect to any of the matching networks.\033[0m")
    wlan.active(False)
    return False

   
if __name__ == "__main__":
    connection_successful = connect_wifi()

    if connection_successful:
        print("\n=== Network setup and time synchronization tasks completed. ===")
    else:
        print("\n=== Network connection failed, device will enter low power mode. ===")

