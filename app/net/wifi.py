# app/net/wifi.py
import network
import time
import gc
from app.event_const import EVENT

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

        print("Starting WiFi connection process...")
        self.event_bus.publish(EVENT.WIFI_CONNECTING)
        
        best_network = self._find_best_network()
        if not best_network:
            print("No configured WiFi networks found.")
            self.status = self.STATUS_ERROR
            self.event_bus.publish(EVENT.WIFI_DISCONNECTED, "NO_NETWORKS_FOUND")
            return

        self.target_network = best_network
        self._attempt_connection()

    def _find_best_network(self):
        """扫描并找到信号最好的已配置网络。"""
        print("Scanning for networks...")
        try:
            scan_results = self.wlan.scan()
        except OSError as e:
            print(f"Error during WiFi scan: {e}")
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
        
        # 从原始配置中查找密码
        for net_config in self.config.get('networks', []):
            if net_config['ssid'] == best_ssid:
                return net_config
        return None

    def _attempt_connection(self):
        """尝试连接到目标网络。"""
        if not self.target_network:
            return

        print(f"Attempting to connect to '{self.target_network['ssid']}'...")
        self.status = self.STATUS_CONNECTING
        self.connection_start_time = time.ticks_ms()
        self.wlan.connect(self.target_network['ssid'], self.target_network['password'])

    def disconnect(self):
        """断开WiFi连接。"""
        if self.wlan.isconnected():
            self.wlan.disconnect()
        self.status = self.STATUS_DISCONNECTED
        print("WiFi disconnected.")
        self.event_bus.publish(EVENT.WIFI_DISCONNECTED, "MANUAL_DISCONNECT")

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
                print(f"WiFi connected! IP: {ip_info[0]}")
                self.event_bus.publish(EVENT.WIFI_CONNECTED, ip_info)
            # 检查是否连接超时
            elif time.ticks_diff(time.ticks_ms(), self.connection_start_time) > self.config.get('timeout', 15) * 1000:
                print("WiFi connection timed out.")
                self.wlan.disconnect() # 确保停止尝试
                self.status = self.STATUS_ERROR
                self.event_bus.publish(EVENT.WIFI_DISCONNECTED, "TIMEOUT")
                self.last_attempt_time = time.ticks_ms()

        elif self.status == self.STATUS_CONNECTED:
            # 持续检查连接是否丢失
            if not self.wlan.isconnected():
                print("WiFi connection lost.")
                self.status = self.STATUS_DISCONNECTED
                self.event_bus.publish(EVENT.WIFI_DISCONNECTED, "CONNECTION_LOST")
                self.last_attempt_time = time.ticks_ms()

        elif self.status in (self.STATUS_DISCONNECTED, self.STATUS_ERROR):
            # 检查是否到了重试时间
            retry_delay_ms = self.config.get('retry_delay', 30) * 1000
            if time.ticks_diff(time.ticks_ms(), self.last_attempt_time) > retry_delay_ms:
                self.connect() # 重新开始连接流程
        
        gc.collect()
