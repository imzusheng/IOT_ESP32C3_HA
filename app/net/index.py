# app/net/index.py
# 网络统一控制器 - 模块化重构版

from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
from .wifi import WifiManager
from .ntp import NtpManager
from .mqtt import MqttController
from .modules import (
    ConfigManager, RetryManager, StateManager, ConnectionHandler
)

class NetworkManager:
    """网络统一控制器 - 模块化版本，使用专门的功能模块"""
    
    def __init__(self, event_bus, config=None):
        self.event_bus = event_bus
        
        # 初始化配置管理器
        self.config_manager = ConfigManager(config)
        
        # 初始化重试管理器
        connection_config = self.config_manager.get_connection_config()
        self.retry_manager = RetryManager(connection_config)
        
        # 初始化状态管理器
        self.state_manager = StateManager(event_bus)
        
        # 初始化网络组件
        self.wifi = WifiManager(self.config_manager.get_wifi_config())
        self.ntp = NtpManager(self.config_manager.get_ntp_config())
        self.mqtt = MqttController(self.config_manager.get_mqtt_config())
        
        # 初始化连接处理器
        self.connection_handler = ConnectionHandler(
            self.wifi, self.mqtt, self.ntp,
            self.state_manager, self.retry_manager, 
            self.config_manager, event_bus
        )

    # =============================================================================
    # 公共接口方法 - 模块化版本
    # =============================================================================

    def loop(self):
        """主循环处理"""
        try:
            self.connection_handler.update_connection_status()
            self.connection_handler.check_connection_success()
            self.connection_handler.check_timeouts()
        except Exception as e:
            error("网络管理器循环错误: {}", e, module="NET")
            self.connection_handler._handle_connection_failed()

    def connect(self):
        """启动网络连接"""
        current_state_name = self.state_manager.get_state_name()
        info("当前状态: {}", current_state_name, module="NET")
        
        if self.state_manager.is_disconnected():
            debug("启动网络连接", module="NET")
            self.state_manager.transition_to_state(1)  # STATE_CONNECTING
            self.retry_manager.reset()
            self.connection_handler.start_connection_process()
        else:
            warning("状态{}不允许启动连接", current_state_name, module="NET")

    def disconnect(self):
        """断开网络连接"""
        self.state_manager.transition_to_state(0)  # STATE_DISCONNECTED
        self.connection_handler.disconnect_all()

    def get_status(self):
        """获取网络状态 - 模块化版本"""
        return self.state_manager.get_detailed_status(self.retry_manager.get_retry_count())

    def is_connected(self):
        """检查是否已连接 - 基于WiFi状态"""
        return self.state_manager.is_connected()
    
    def is_fully_connected(self):
        """检查是否完全连接 - WiFi和MQTT都连接"""
        return self.state_manager.is_fully_connected()

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