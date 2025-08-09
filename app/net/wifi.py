# app/net/wifi.py
import network
import time
import gc
try:
    import ntptime  # MicroPython NTP 客户端
except Exception:
    ntptime = None
from event_const import EVENT

class WifiManager:
    """
    WiFi连接管理器 (重构版本)
    
    管理WiFi连接，采用非阻塞模式，通过事件总线报告状态。
    支持多网络选择、RSSI排序、自动重连和健壮的错误处理。
    
    特性:
    - 非阻塞连接模式
    - 自动信号强度排序
    - 指数退避重连策略
    - 事件驱动状态报告
    - 联网成功后自动执行 NTP 同步（使用阿里云时间源）
    """
    # 连接状态
    STATUS_DISCONNECTED = 0
    STATUS_CONNECTING = 1
    STATUS_CONNECTED = 2
    STATUS_ERROR = 3

    def __init__(self, event_bus, config):
        """
        :param event_bus: EventBus 实例
        :param config: WiFi 配置字典，包含 'networks', 'timeout', 'retry_delay'
        """
        self.event_bus = event_bus
        self.config = config
        
        self.wlan = network.WLAN(network.STA_IF)
        self.status = self.STATUS_DISCONNECTED
        self.last_attempt_time = 0
        self.connection_start_time = 0
        self.target_network = None
        
        # NTP 同步标记，避免重复同步
        self._ntp_synced = False
        self._ntp_attempts = 0
        self._last_connect_event = 0  # 防止重复连接事件
        
        # 激活WLAN接口
        if not self.wlan.active():
            print("[WiFi] Activating WLAN interface...")
            self.wlan.active(True)

    def is_connected(self):
        """检查WiFi是否已连接。"""
        return self.status == self.STATUS_CONNECTED and self.wlan.isconnected()

    def connect(self):
        """开始连接到最佳可用WiFi网络，非阻塞。"""
        if self.status == self.STATUS_CONNECTING or self.status == self.STATUS_CONNECTED:
            return

        print("[WiFi] Starting WiFi connection process...")
        self.event_bus.publish(EVENT.WIFI_CONNECTING, module="WiFi")
        
        best_network = self._find_best_network()
        if not best_network:
            print("[WiFi] No configured WiFi networks found.")
            self.status = self.STATUS_ERROR
            self.event_bus.publish(EVENT.WIFI_DISCONNECTED, reason="NO_NETWORKS_FOUND", module="WiFi")
            return

        self.target_network = best_network
        self._attempt_connection()

    def _find_best_network(self):
        """扫描并找到信号最好的已配置网络。"""
        print("[WiFi] Scanning for networks...")
        try:
            scan_results = self.wlan.scan()
        except OSError as e:
            print(f"[WiFi] Error during WiFi scan: {e}")
            self.event_bus.publish(EVENT.LOG_ERROR, "Error during WiFi scan: {}", e, module="WiFi")
            return None
            
        configured_ssids = {net['ssid'] for net in self.config.get('networks', [])}
        
        found_networks = []
        for ssid_bytes, _, _, rssi, _, _ in scan_results:
            try:
                ssid = ssid_bytes.decode('utf-8')
                if ssid in configured_ssids:
                    found_networks.append({'ssid': ssid, 'rssi': rssi})
            except UnicodeError:
                continue # 忽略无法解码的SSID
        
        if not found_networks:
            return None
            
        # 按RSSI排序
        found_networks.sort(key=lambda x: x['rssi'], reverse=True)
        best_ssid = found_networks[0]['ssid']
        print(f"[WiFi] Found best network: {best_ssid} (RSSI: {found_networks[0]['rssi']})")
        
        # 从原始配置中查找密码并返回整个网络配置
        for net_config in self.config.get('networks', []):
            if net_config['ssid'] == best_ssid:
                return net_config
        return None

    def _attempt_connection(self):
        """尝试连接到目标网络。"""
        if not self.target_network:
            return

        print(f"[WiFi] Attempting to connect to '{self.target_network['ssid']}'...")
        self.event_bus.publish(EVENT.LOG_INFO, "Attempting to connect to WiFi network: {}", self.target_network['ssid'], module="WiFi")
        self.status = self.STATUS_CONNECTING
        self.connection_start_time = time.ticks_ms()
        self.wlan.connect(self.target_network['ssid'], self.target_network['password'])

    def disconnect(self):
        """断开WiFi连接。"""
        if self.wlan.isconnected():
            self.wlan.disconnect()
        self.status = self.STATUS_DISCONNECTED
        print("[WiFi] WiFi disconnected.")
        self.event_bus.publish(EVENT.LOG_INFO, "WiFi manually disconnected", module="WiFi")
        # 断开连接后重置 NTP 状态，便于下次成功后再次同步
        self._ntp_synced = False
        self._ntp_attempts = 0
        self._last_connect_event = 0
        self.event_bus.publish(EVENT.WIFI_DISCONNECTED, reason="MANUAL_DISCONNECT", module="WiFi")

    def update(self):
        """
        在主循环中定期调用，处理连接状态变化。
        """
        # 状态机逻辑
        if self.status == self.STATUS_CONNECTING:
            # 检查是否连接成功
            if self.wlan.isconnected():
                self.status = self.STATUS_CONNECTED
                ip_info = self.wlan.ifconfig()
                
                # 检查 IP 地址是否有效
                if ip_info and ip_info[0] and ip_info[0] != "0.0.0.0":
                    ip_address = ip_info[0]
                    ssid = self.target_network.get('ssid', 'unknown')
                    
                    # 防止重复连接事件
                    now = time.ticks_ms()
                    if time.ticks_diff(now, self._last_connect_event) > 5000:  # 5秒防重复
                        self._last_connect_event = now
                        
                        print(f"[WiFi] WiFi connected! IP: {ip_address}, SSID: {ssid}")
                        self.event_bus.publish(EVENT.LOG_INFO, "WiFi connected successfully! IP: {}, SSID: {}", ip_address, ssid, module="WiFi")
                        self.event_bus.publish(EVENT.WIFI_CONNECTED, ip=ip_address, ssid=ssid, module="WiFi")
                        
                        # 联网成功后尝试进行 NTP 时间同步
                        self._try_ntp_sync()
                else:
                    print("[WiFi] WiFi connected but no valid IP address obtained, retrying...")
                    self.wlan.disconnect()
                    # 重新开始连接过程，不改变状态
                    self.connection_start_time = time.ticks_ms()
                    
            # 检查是否连接超时
            elif time.ticks_diff(time.ticks_ms(), self.connection_start_time) > self.config.get('timeout', 15) * 1000:
                print("[WiFi] WiFi connection timed out.")
                self.event_bus.publish(EVENT.LOG_WARN, "WiFi connection timeout for network: {}", self.target_network['ssid'], module="WiFi")
                self.wlan.disconnect() # 确保停止尝试
                self.status = self.STATUS_ERROR
                self.event_bus.publish(EVENT.WIFI_DISCONNECTED, reason="TIMEOUT", ssid=self.target_network.get('ssid'), module="WiFi")
                self.last_attempt_time = time.ticks_ms()

        elif self.status == self.STATUS_CONNECTED:
            # 持续检查连接是否丢失
            if not self.wlan.isconnected():
                print("[WiFi] WiFi connection lost.")
                self.event_bus.publish(EVENT.LOG_WARN, "WiFi connection lost", module="WiFi")
                self.status = self.STATUS_DISCONNECTED
                self.event_bus.publish(EVENT.WIFI_DISCONNECTED, reason="CONNECTION_LOST", module="WiFi")
                self.last_attempt_time = time.ticks_ms()
                # 重置 NTP 同步状态
                self._ntp_synced = False
                self._ntp_attempts = 0
                self._last_connect_event = 0

        elif self.status in (self.STATUS_DISCONNECTED, self.STATUS_ERROR):
            # 检查是否到了重试时间
            retry_delay_ms = self.config.get('retry_delay', 30) * 1000
            if time.ticks_diff(time.ticks_ms(), self.last_attempt_time) > retry_delay_ms:
                self.connect() # 重新开始连接流程
        
        gc.collect()

    # --------------------------- NTP 同步逻辑 ---------------------------
    def _try_ntp_sync(self):
        """尝试执行 NTP 时间同步（带重试与事件上报）。"""
        if self._ntp_synced:
            return
        if not self.wlan.isconnected():
            return
        if ntptime is None:
            # 环境不支持 ntptime（可能是PC端），跳过但报告失败事件
            self.event_bus.publish(EVENT.NTP_SYNC_FAILED, reason="NTP_MODULE_NOT_AVAILABLE", module="WiFi")
            self.event_bus.publish(EVENT.LOG_WARN, "NTP module not available, skipping time sync", module="WiFi")
            return
        
        # 通过配置允许自定义 NTP 服务器，默认使用阿里云 NTP 池
        ntp_server = self.config.get('ntp_server', 'ntp1.aliyun.com')
        max_attempts = int(self.config.get('ntp_max_attempts', 3))
        retry_interval = int(self.config.get('ntp_retry_interval', 2))  # 秒
        
        try:
            if hasattr(ntptime, 'host'):
                ntptime.host = ntp_server  # 设置 NTP 服务器
        except Exception:
            # 某些端口的 ntptime 不支持设置 host，忽略
            pass
        
        # 发布开始事件（只发布一次）
        print(f"[WiFi] Starting NTP sync with server: {ntp_server}")
        self.event_bus.publish(EVENT.NTP_SYNC_STARTED, ntp_server=ntp_server, module="WiFi")
        
        for i in range(max_attempts):
            self._ntp_attempts = i + 1
            try:
                # ntptime.settime() 会从 NTP 获取时间并设置 RTC
                ntptime.settime()
                # 成功
                self._ntp_synced = True
                timestamp = time.time()  # 获取当前时间戳
                
                print(f"[WiFi] NTP sync successful after {self._ntp_attempts} attempts, timestamp: {timestamp}")
                
                # 发布成功事件
                self.event_bus.publish(EVENT.NTP_SYNC_SUCCESS, ntp_server=ntp_server, attempts=self._ntp_attempts, timestamp=timestamp, module="WiFi")
                
                # 广播 TIME_UPDATED 事件，包含时间戳载荷供其它模块感知
                self.event_bus.publish(EVENT.TIME_UPDATED, timestamp=timestamp, module="WiFi")
                break
            except Exception as e:
                # 失败则等待后重试
                print(f"[WiFi] NTP sync failed, attempt {self._ntp_attempts}/{max_attempts}: {e}")
                self.event_bus.publish(EVENT.LOG_WARN, "NTP sync failed, attempt {}/{}: {}", self._ntp_attempts, max_attempts, str(e), module="WiFi")
                
                # 最后一次尝试失败才发布失败事件
                if i == max_attempts - 1:
                    self.event_bus.publish(EVENT.NTP_SYNC_FAILED, error=str(e), attempts=self._ntp_attempts, ntp_server=ntp_server, module="WiFi")
                else:
                    time.sleep(retry_interval)
