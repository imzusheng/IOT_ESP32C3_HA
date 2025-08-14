# app/net/index.py
# 极简网络统一控制器

import utime as time
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
from .wifi import WifiManager
from .ntp import NtpManager
from .mqtt import MqttController


class NetworkManager:
    """极简网络统一控制器 - 直接管理所有网络连接"""
    
    def __init__(self, event_bus, config=None):
        self.event_bus = event_bus
        self.config = config or {}
        
        # 初始化网络组件
        self.wifi = WifiManager(self.config.get('wifi', {}))
        self.ntp = NtpManager(self.config.get('ntp', {}))
        self.mqtt = MqttController(self.config.get('mqtt', {}))
        
        # 连接状态
        self.state = 'disconnected'  # disconnected, connecting, connected, error
        self.retry_count = 0
        self.max_retries = 3
        self.last_connection_attempt = 0
        self.retry_delay = 1000  # 1秒重试延迟
        
        # 连接时间戳
        self.last_status_check = 0
        self.status_check_interval = 5000  # 5秒检查一次
        
        info("网络管理器初始化完成", module="NET")
    
    def loop(self):
        """主循环处理"""
        try:
            current_time = time.ticks_ms()
            
            # 定期检查连接状态
            if current_time - self.last_status_check > self.status_check_interval:
                self._check_connections()
                self.last_status_check = current_time
            
            # 处理MQTT消息
            if self.mqtt.is_connected():
                self.mqtt.check_msg()
                
        except Exception as e:
            error("网络管理器循环错误: {}", e, module="NET")
            self._handle_error(e)
    
    def connect(self):
        """启动网络连接"""
        if self.state == 'disconnected':
            info("启动网络连接", module="NET")
            self.state = 'connecting'
            self.retry_count = 0
            self._connect_all()
        else:
            warning("当前状态{}不允许启动连接", self.state, module="NET")
    
    def disconnect(self):
        """断开网络连接"""
        info("断开网络连接", module="NET")
        self.state = 'disconnected'
        self._disconnect_all()
    
    def get_status(self):
        """获取网络状态"""
        return {
            'state': self.state,
            'wifi_connected': self.wifi.is_connected(),
            'mqtt_connected': self.mqtt.is_connected(),
            'ntp_synced': self.ntp.is_synced(),
            'retry_count': self.retry_count
        }
    
    def is_connected(self):
        """检查是否已连接 - 基于WiFi状态"""
        return self.wifi.get_is_connected()
    
    def is_fully_connected(self):
        """检查是否完全连接 - WiFi和MQTT都连接"""
        return self.wifi.get_is_connected() and self.mqtt.is_connected()
    
    # MQTT相关接口
    def publish_mqtt_message(self, topic, message, retain=False, qos=0):
        """发布MQTT消息"""
        return self.mqtt.publish(topic, message, retain, qos)
    
    def subscribe_mqtt_topic(self, topic, qos=0):
        """订阅MQTT主题"""
        return self.mqtt.subscribe(topic, qos)
    
    def get_mqtt_status(self):
        """获取MQTT状态"""
        return self.mqtt.is_connected()
    
    # =============================================================================
    # 内部方法
    # =============================================================================
    
    def _connect_all(self):
        """连接所有网络服务"""
        try:
            # 1. 连接WiFi
            info("连接WiFi...", module="NET")
            wifi_config = self.config.get('wifi', {})
            if 'ssid' not in wifi_config or 'password' not in wifi_config:
                raise Exception("WiFi配置缺少ssid或password")
            
            if not self.wifi.connect(wifi_config['ssid'], wifi_config['password']):
                raise Exception("WiFi连接失败")
            
            # 等待WiFi连接
            import time
            wait_start = time.ticks_ms()
            while not self.wifi.get_is_connected() and time.ticks_diff(time.ticks_ms(), wait_start) < 10000:
                time.sleep_ms(100)
            
            if not self.wifi.get_is_connected():
                raise Exception("WiFi连接超时")
            
            # 2. 同步NTP时间
            info("同步NTP时间...", module="NET")
            self.ntp.sync_time()
            
            # 3. 连接MQTT
            info("连接MQTT...", module="NET")
            if not self.mqtt.connect():
                raise Exception("MQTT连接失败")
            
            # 连接成功
            self.state = 'connected'
            self.retry_count = 0
            info("所有网络服务连接成功", module="NET")
            
            # 发布事件
            self.event_bus.publish(EVENTS['SYSTEM_STATE_CHANGE'], 
                                 state='NETWORKING', 
                                 message='网络连接成功')
            
        except Exception as e:
            error("网络连接失败: {}", e, module="NET")
            self._handle_connection_failed(e)
    
    def _disconnect_all(self):
        """断开所有网络服务"""
        try:
            self.mqtt.disconnect()
            self.wifi.disconnect()
            info("所有网络服务已断开", module="NET")
        except Exception as e:
            error("断开网络连接失败: {}", e, module="NET")
    
    def _check_connections(self):
        """检查连接状态"""
        try:
            wifi_ok = self.wifi.get_is_connected()
            mqtt_ok = self.mqtt.is_connected()
            
            # 如果WiFi断开，重新连接
            if not wifi_ok and self.state == 'connected':
                warning("WiFi连接断开，尝试重新连接", module="NET")
                self._handle_connection_failed(Exception("WiFi连接断开"))
            
            # 如果MQTT断开但WiFi正常，尝试重连MQTT
            elif wifi_ok and not mqtt_ok and self.state == 'connected':
                warning("MQTT连接断开，尝试重新连接", module="NET")
                if self.mqtt.connect():
                    info("MQTT重连成功", module="NET")
                else:
                    error("MQTT重连失败", module="NET")
                    
        except Exception as e:
            error("检查连接状态失败: {}", e, module="NET")
    
    def _handle_connection_failed(self, error_msg):
        """处理连接失败"""
        self.retry_count += 1
        error("连接失败，重试次数: {}/{}", self.retry_count, self.max_retries, module="NET")
        
        if self.retry_count >= self.max_retries:
            self.state = 'error'
            error("达到最大重试次数，连接失败", module="NET")
            
            # 发布系统错误事件
            self.event_bus.publish(EVENTS['SYSTEM_ERROR'], 
                                 error_type="network_connection_failed",
                                 error_message=str(error_msg))
        else:
            self.state = 'connecting'
            # 计算重试延迟（指数退避）
            delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 30000)
            info("{}秒后重试连接", delay // 1000, module="NET")
            
            # 简单的延迟重试
            time.sleep_ms(delay)
            self._connect_all()
    
    def _handle_error(self, error_msg):
        """处理错误"""
        error("网络管理器错误: {}", error_msg, module="NET")
        self.state = 'error'
        
        # 发布系统错误事件
        self.event_bus.publish(EVENTS['SYSTEM_ERROR'], 
                             error_type="network_manager_error",
                             error_message=str(error_msg))
    
    def reset(self):
        """重置网络管理器"""
        info("重置网络管理器", module="NET")
        self.state = 'disconnected'
        self.retry_count = 0
        self._disconnect_all()