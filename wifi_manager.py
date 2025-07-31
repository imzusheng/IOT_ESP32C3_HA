# -*- coding: utf-8 -*-
#
# 文件名: wifi_manager.py
# 功能: 一个健壮的 MicroPython WiFi 连接和NTP时间同步模块
# 版本: 3.2 (模块化版本)
#
import time
import network
import gc
import webrepl
import machine
import ntptime

# --- 配置区 ---
# 在此列表中按顺序添加你希望连接的WiFi网络
WIFI_CONFIGS = [
    {"ssid": "zsm60p", "password": "25845600"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
    {"ssid": "leju_software", "password": "leju123456"},
    {"ssid": "office-wifi", "password": "another_password"}
]
# WebREPL 服务的密码
WEBREPL_PASSWORD = "123456"

# 连接单个网络时的超时时间（秒）
CONNECT_TIMEOUT_S = 15

# [已根据您的位置优化] NTP和时区配置
# NTP服务器地址, 日本推荐使用 ntp.nict.jp
NTP_HOST = 'ntp.nict.jp'
# 时区偏移（小时）。日本标准时间为东九区，应设置为 9
TIMEZONE_OFFSET_H = 9


def _scan_for_ssids(wlan):
    """扫描周围的WiFi网络并返回(ssid, rssi)列表。"""
    print("[WiFi] 正在扫描周围的网络...")
    scanned_networks = []
    try:
        scan_results = wlan.scan()
        print("[WiFi] 扫描完成，发现以下网络:")
        for res in scan_results:
            try:
                ssid = res[0].decode('utf-8')
                rssi = res[3]
                print(f"  - SSID: {ssid:<20} | RSSI: {rssi} dBm")
                scanned_networks.append((ssid, rssi))
            except UnicodeError:
                pass
        return scanned_networks
    except Exception as e:
        print(f"[WiFi] 扫描时发生错误: {e}")
        return []


def sync_and_set_time():
    """使用NTP同步设备时间，设置RTC，并考虑时区。"""
    print("\n[NTP] 开始时间同步...")
    ntptime.host = NTP_HOST
    for i in range(5):
        try:
            ntptime.settime()
            print("[NTP] ✅ 成功从NTP服务器获取时间。")
            utc_tuple = time.localtime()
            rtc = machine.RTC()
            rtc.datetime((utc_tuple[0], utc_tuple[1], utc_tuple[2], utc_tuple[6] + 1, utc_tuple[3], utc_tuple[4], utc_tuple[5], 0))
            local_time_tuple = time.localtime(time.time() + TIMEZONE_OFFSET_H * 3600)
            print(f"[NTP] 当前UTC时间:    {utc_tuple[0]}-{utc_tuple[1]:02d}-{utc_tuple[2]:02d} {utc_tuple[3]:02d}:{utc_tuple[4]:02d}:{utc_tuple[5]:02d}")
            print(f"[NTP] 当前本地时间 (UTC+{TIMEZONE_OFFSET_H}): {local_time_tuple[0]}-{local_time_tuple[1]:02d}-{local_time_tuple[2]:02d} {local_time_tuple[3]:02d}:{local_time_tuple[4]:02d}:{local_time_tuple[5]:02d}")
            gc.collect()
            return True
        except Exception as e:
            print(f"[NTP] ❌ 时间同步出错 (尝试 {i+1}/5): {e}, 3秒后重试...")
            time.sleep(3)
    print("[NTP] ❌ 经过多次尝试，时间同步失败。")
    return False


def _start_webrepl_safe():
    """安全地启动WebREPL。"""
    print("\n")
    try:
        webrepl.start(password=WEBREPL_PASSWORD)
        print(f"[WebREPL] 服务已启动。")
    except Exception as e:
        if "EADDRINUSE" in str(e):
             print("[WebREPL] 服务已在运行中。")
        else:
            print(f"[WebREPL] 启动失败! 错误: {e}")


def connect_wifi():
    """
    模块主函数：连接WiFi, 同步时间, 启动服务。
    返回: True (成功) 或 False (失败)
    """
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        wlan.disconnect()
    if not wlan.active():
        wlan.active(True)

    scanned_networks = _scan_for_ssids(wlan)
    if not scanned_networks:
        print("[WiFi] 未扫描到任何网络。")
        wlan.active(False)
        return False

    available_ssids = {net[0] for net in scanned_networks}
    rssi_map = {net[0]: net[1] for net in scanned_networks}
    connectable_configs = [c for c in WIFI_CONFIGS if c['ssid'] in available_ssids]

    if not connectable_configs:
        print("[WiFi] 扫描到的网络与配置中的网络均不匹配。")
        wlan.active(False)
        return False

    connectable_configs.sort(key=lambda c: rssi_map[c['ssid']], reverse=True)
    print("\n[WiFi] 发现匹配的网络，将按信号强度尝试连接:")
    for config in connectable_configs:
        print(f"  - {config['ssid']} (RSSI: {rssi_map[config['ssid']]} dBm)")

    for config in connectable_configs:
        ssid = config["ssid"]
        password = config["password"]
        print(f"\n[WiFi] 正在尝试连接: {ssid}")
        wlan.connect(ssid, password)
        start_time = time.time()
        while not wlan.isconnected():
            if time.time() - start_time > CONNECT_TIMEOUT_S:
                print(f"[WiFi] ❌ 连接 {ssid} 超时。")
                break
            time.sleep(1)

        if wlan.isconnected():
            ip_address = wlan.ifconfig()[0]
            print(f"[WiFi] ✅ 成功连接到: {ssid}")
            print(f"[WiFi] IP地址: {ip_address}")
            sync_and_set_time()
            _start_webrepl_safe()
            gc.collect()
            return True

    print("\n[WiFi] ❌ 尝试了所有匹配的网络，但均连接失败。")
    wlan.active(False)
    return False

   
if __name__ == "__main__":
    connection_successful = connect_wifi()

    if connection_successful:
        print("\n=== 网络设置与时间同步任务完成。 ===")
    else:
        print("\n=== 网络连接失败，设备将进入低功耗模式。 ===")
