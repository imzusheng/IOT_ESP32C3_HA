# app/net/network_manager.py
"""
网络管理器
职责：
- 顺序编排 WiFi → NTP → MQTT 的连接流程，替代早期的独立 NET FSM
- 在主循环中持续检查 WiFi/MQTT 状态并触发必要的事件
- 对外暴露 connect()/disconnect()/loop()/get_status()/force_reconnect() 等接口

事件约定：
- 当 WiFi 状态变化时发布 EVENTS["WIFI_STATE_CHANGE"]，state ∈ {"connected","disconnected"}
- 当 MQTT 状态变化时发布 EVENTS["MQTT_STATE_CHANGE"]，state ∈ {"connected","disconnected"}

设计边界与约束：
- 不实现指数退避与重试策略（由上层 FSM 或后续版本统一治理）
- NTP 同步失败不会阻塞后续 MQTT 连接
- WifiManager/NtpManager/MqttController 由本模块聚合管理，配置来自 app/config.py

扩展建议：
- 可在不破坏接口的前提下引入退避/重试策略
- 可将连接状态与统计指标上报到事件总线或系统状态接口
"""

import utime as time
# 移除不必要的导入: network, gc
from lib.logger import info, warning, error, debug
from lib.lock.event_bus import EVENTS

class NetworkManager:
    """
    网络管理器
    直接管理WiFi→NTP→MQTT连接流程，无需独立的NET FSM
    """
    
    def __init__(self, config, event_bus):
        """初始化网络管理器"""
        self.config = config
        self.event_bus = event_bus
        
        # 子配置缓存，避免硬编码与重复取值
        self.wifi_config = (self.config or {}).get("wifi", {})
        self.ntp_config = (self.config or {}).get("ntp", {})
        self.mqtt_config = (self.config or {}).get("mqtt", {})
        
        # 网络组件
        self.wifi_manager = None
        self.ntp_manager = None
        self.mqtt_controller = None
        
        # 连接状态
        self.wifi_connected = False
        self.ntp_synced = False
        self.mqtt_connected = False
        
        # 初始化组件
        self._init_components()
        
    def _init_components(self):
        """初始化网络组件"""
        try:
            # 使用包内相对导入，保持与现有文件结构一致
            from .wifi import WifiManager
            from .ntp import NtpManager
            from .mqtt import MqttController

            # 按子配置实例化
            self.wifi_manager = WifiManager(self.wifi_config)
            self.ntp_manager = NtpManager(self.ntp_config)
            self.mqtt_controller = MqttController(self.mqtt_config, self.event_bus)
            
            info("网络组件初始化完成", module="NET")
            
        except Exception as e:
            error("网络组件初始化失败: {}", e, module="NET")
            raise
            
    def connect(self):
        """
        启动网络连接流程
        返回: bool - 是否成功启动连接流程
        """
        info("开始网络连接流程", module="NET")
        
        try:
            # 步骤1: 连接WiFi
            if not self._connect_wifi():
                return False
                
            # 步骤2: 同步NTP时间
            if not self._sync_ntp():
                warning("NTP同步失败，但继续连接MQTT", module="NET")
                
            # 步骤3: 连接MQTT
            if not self._connect_mqtt():
                return False
                
            info("网络连接流程启动成功", module="NET")
            return True
            
        except Exception as e:
            error("网络连接流程失败: {}", e, module="NET")
            return False
    
    def _scan_and_match_networks(self, configured_networks):
        """扫描并匹配配置的网络"""
        try:
            # 扫描可用网络
            info("扫描可用WiFi网络...", module="NET")
            scanned_networks = self.wifi_manager.scan_networks()
            
            if not scanned_networks:
                warning("未扫描到任何WiFi网络", module="NET")
                return []
            
            info("扫描到{}个WiFi网络", len(scanned_networks), module="NET")
            
            # 匹配配置的网络
            matched_networks = []
            for config_net in configured_networks:
                config_ssid = config_net.get("ssid")
                if not config_ssid:
                    continue
                    
                # 在扫描结果中查找匹配的SSID
                for scanned_net in scanned_networks:
                    if scanned_net.get("ssid") == config_ssid:
                        matched_networks.append({
                            "ssid": config_ssid,
                            "password": config_net.get("password", ""),
                            "rssi": scanned_net.get("rssi", -100),
                            "bssid": scanned_net.get("bssid", "")
                        })
                        break
            
            # 按RSSI降序排序（信号强度从高到低）
            matched_networks.sort(key=lambda x: x["rssi"], reverse=True)
            
            info("匹配到{}个配置的WiFi网络", len(matched_networks), module="NET")
            for net in matched_networks:
                debug("匹配网络: {} (RSSI: {})", net["ssid"], net["rssi"], module="NET")
            
            return matched_networks
            
        except Exception as e:
            error("扫描和匹配网络失败: {}", e, module="NET")
            return []
    
    def _attempt_wifi_connection(self, ssid, password):
        """尝试连接指定的WiFi网络"""
        try:
            # 调用WiFi管理器连接
            started = self.wifi_manager.connect(ssid, password)
            if not started:
                return False
            
            # 等待连接结果
            timeout_ms = int(self.wifi_config.get("connect_timeout_ms", 10000))
            poll_interval = 200
            start_ms = time.ticks_ms()
            
            while not self.wifi_manager.get_is_connected():
                if time.ticks_diff(time.ticks_ms(), start_ms) > timeout_ms:
                    break
                time.sleep_ms(poll_interval)
            
            return self.wifi_manager.get_is_connected()
            
        except Exception as e:
            error("WiFi连接尝试异常: {}", e, module="NET")
            return False
                
            # 步骤2: 同步NTP
            if not self._sync_ntp():
                return False
                
            # 步骤3: 连接MQTT
            if not self._connect_mqtt():
                return False
                
            # 连接成功
            info("网络连接流程完成", module="NET")
            return True
            
        except Exception as e:
            error("网络连接流程失败: {}", e, module="NET")
            return False
            
    def _connect_wifi(self):
        """连接WiFi - 支持多网络选择"""
        try:
            if self.wifi_connected and self.wifi_manager and self.wifi_manager.get_is_connected():
                debug("WiFi已连接", module="NET")
                return True
            
            # 获取网络配置列表
            networks = self.wifi_config.get("networks", [])
            if not networks:
                # 兼容旧配置格式
                ssid = self.wifi_config.get("ssid")
                password = self.wifi_config.get("password")
                if ssid:
                    networks = [{"ssid": ssid, "password": password}]
                else:
                    warning("缺少WiFi配置: networks或ssid", module="NET")
                    return False
            
            info("开始多网络WiFi连接流程，配置了{}个网络", len(networks), module="NET")
            
            # 扫描可用网络
            available_networks = self._scan_and_match_networks(networks)
            if not available_networks:
                warning("未找到任何配置的WiFi网络", module="NET")
                return False
            
            # 按RSSI降序尝试连接
            for network in available_networks:
                ssid = network["ssid"]
                password = network["password"]
                rssi = network.get("rssi", "未知")
                
                info("尝试连接WiFi: {} (信号强度: {})", ssid, rssi, module="NET")
                
                if self._attempt_wifi_connection(ssid, password):
                    self.wifi_connected = True
                    info("WiFi连接成功: {}", ssid, module="NET")
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="connected")
                    return True
                else:
                    warning("WiFi连接失败: {}", ssid, module="NET")
            
            warning("所有配置的WiFi网络连接均失败", module="NET")
            return False
                
        except Exception as e:
            error("WiFi连接异常: {}", e, module="NET")
            return False
            
    def _sync_ntp(self):
        """同步NTP时间"""
        try:
            if self.ntp_synced:
                debug("NTP已同步", module="NET")
                return True
                
            info("正在同步NTP时间...", module="NET")
            success = self.ntp_manager.sync_time()
            
            if success:
                self.ntp_synced = True
                info("NTP时间同步成功", module="NET")
                return True
            else:
                warning("NTP时间同步失败（忽略，继续MQTT连接）", module="NET")
                return True  # NTP失败不阻止MQTT连接
                
        except Exception as e:
            error("NTP同步异常: {}", e, module="NET")
            return True  # NTP失败不阻止MQTT连接
            
    def _connect_mqtt(self):
        """连接MQTT"""
        try:
            if self.mqtt_connected and self.mqtt_controller and self.mqtt_controller.is_connected():
                debug("MQTT已连接", module="NET")
                return True
                
            info("正在连接MQTT...", module="NET")
            success = self.mqtt_controller.connect()
            
            if success:
                self.mqtt_connected = True
                info("MQTT连接成功", module="NET")
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                return True
            else:
                warning("MQTT连接失败", module="NET")
                return False
                
        except Exception as e:
            error("MQTT连接异常: {}", e, module="NET")
            return False
            
    def disconnect(self):
        """断开所有网络连接"""
        info("断开网络连接", module="NET")
        
        try:
            # 断开MQTT
            if self.mqtt_controller and self.mqtt_connected:
                self.mqtt_controller.disconnect()
                self.mqtt_connected = False
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                
            # 断开WiFi
            if self.wifi_manager and self.wifi_connected:
                self.wifi_manager.disconnect()
                self.wifi_connected = False
                self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
                
            # 重置状态
            self.ntp_synced = False
            
            info("网络连接已断开", module="NET")
            
        except Exception as e:
            error("断开网络连接失败: {}", e, module="NET")
            
    def is_connected(self):
        """检查网络连接状态"""
        return self.wifi_connected and self.mqtt_connected
        
    def get_status(self):
        """获取网络状态"""
        return {
            "wifi": self.wifi_connected,
            "ntp": self.ntp_synced,
            "mqtt": self.mqtt_connected
        }
        
    def loop(self):
        """网络管理器主循环"""
        try:
            # 检查WiFi状态
            self._check_wifi_status()
            
            # 检查MQTT状态
            self._check_mqtt_status()
            
            # MQTT消息处理
            if self.mqtt_controller and self.mqtt_connected:
                self.mqtt_controller.check_msg()
                
        except Exception as e:
            error("网络管理器循环异常: {}", e, module="NET")
            
    def _check_wifi_status(self):
        """检查WiFi连接状态"""
        try:
            if not self.wifi_manager:
                return
                
            # 使用WifiManager封装的接口检查连接状态
            is_connected = self.wifi_manager.get_is_connected()
            
            if self.wifi_connected and not is_connected:
                # WiFi连接丢失
                warning("WiFi连接丢失", module="NET")
                self.wifi_connected = False
                self.mqtt_connected = False  # WiFi断开时MQTT也会断开
                self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
                
            elif not self.wifi_connected and is_connected:
                # WiFi重新连接
                info("WiFi重新连接", module="NET")
                self.wifi_connected = True
                self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="connected")
                
        except Exception as e:
            error("检查WiFi状态失败: {}", e, module="NET")
            
    def _check_mqtt_status(self):
        """检查MQTT连接状态"""
        try:
            if not self.mqtt_controller:
                return
                
            # 检查MQTT连接状态
            is_connected = self.mqtt_controller.is_connected()
            
            if self.mqtt_connected and not is_connected:
                # MQTT连接丢失
                warning("MQTT连接丢失", module="NET")
                self.mqtt_connected = False
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                
            elif not self.mqtt_connected and is_connected:
                # MQTT重新连接
                info("MQTT重新连接", module="NET")
                self.mqtt_connected = True
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                
        except Exception as e:
            error("检查MQTT状态失败: {}", e, module="NET")
            
    def force_reconnect(self):
        """强制重新连接"""
        info("强制重新连接网络", module="NET")
        self.disconnect()
        time.sleep_ms(1000)  # 等待1秒
        return self.connect()


# 兼容性函数
def create_network_manager(config, event_bus):
    """创建网络管理器实例（保持兼容性）"""
    return NetworkManager(config, event_bus)


# 全局实例管理（保持兼容性）
_network_manager_instance = None

def get_network_manager():
    """获取全局网络管理器实例"""
    return _network_manager_instance

def create_global_network_manager(config, event_bus):
    """创建全局网络管理器实例"""
    global _network_manager_instance
    _network_manager_instance = NetworkManager(config, event_bus)
    return _network_manager_instance