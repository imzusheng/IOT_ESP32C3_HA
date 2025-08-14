# app/net/modules/wifi_connector.py
"""WiFi连接模块"""

import utime as time
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS

class WifiConnector:
    """WiFi连接器 - 负责WiFi扫描和连接逻辑"""
    
    def __init__(self, wifi_manager, state_manager, event_bus):
        """
        初始化WiFi连接器
        :param wifi_manager: WiFi管理器实例
        :param state_manager: 状态管理器实例
        :param event_bus: 事件总线实例
        """
        self.wifi_manager = wifi_manager
        self.state_manager = state_manager
        self.event_bus = event_bus
    
    def connect_wifi(self, wifi_config):
        """WiFi连接逻辑"""
        if self.state_manager.wifi_connected:
            info("WiFi已连接, 直接连接MQTT", module="NET")
            return True
        
        # 发布连接状态
        self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state="connecting")
        
        # 扫描并连接网络
        return self._scan_and_connect_wifi(wifi_config)
    
    def _scan_and_connect_wifi(self, wifi_config):
        """扫描并尝试连接WiFi网络"""
        info("扫描WiFi网络...", module="NET")
        networks = self.wifi_manager.scan_networks(timeout_ms=5000)
        
        if not networks:
            error("未找到可用WiFi网络", module="NET")
            return False
        
        # 尝试连接已配置的网络
        available_ssids = {net['ssid']: net.get('rssi', 'N/A') for net in networks}
        configured_networks = wifi_config.get('networks', [])
        
        info("发现{}个网络,配置{}个", len(networks), len(configured_networks), module="NET")
        
        for config in configured_networks:
            ssid = config['ssid']
            if ssid in available_ssids:
                debug("尝试连接WiFi: {} (RSSI: {})", ssid, available_ssids[ssid], module="NET")
                
                if self._attempt_wifi_connection(ssid, config.get('password')):
                    return True
        
        error("所有WiFi网络连接失败", module="NET")
        return False
    
    def _attempt_wifi_connection(self, ssid, password):
        """尝试连接单个WiFi网络"""
        if not self.wifi_manager.connect(ssid, password):
            error("WiFi连接命令失败: {}", ssid, module="NET")
            return False
        
        # 等待连接建立(10秒超时)
        info("WiFi连接命令已发送, 等待连接建立...", module="NET")
        start_time = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), start_time) < 10000:
            if self.wifi_manager.get_is_connected():
                info("WiFi连接成功: {}", ssid, module="NET")
                return True
            time.sleep_ms(200)
        
        warning("WiFi连接超时: {}", ssid, module="NET")
        return False
    
    def disconnect_wifi(self):
        """断开WiFi连接"""
        try:
            self.wifi_manager.disconnect()
            return True
        except Exception as e:
            error("WiFi断开失败: {}", e, module="NET")
            return False