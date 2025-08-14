# app/net/modules/connection_handler.py
"""连接处理模块"""

import utime as time
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
from .wifi_connector import WifiConnector

class ConnectionHandler:
    """连接处理器 - 负责主要连接流程和MQTT/NTP连接"""
    
    def __init__(self, wifi_manager, mqtt_controller, ntp_manager, 
                 state_manager, retry_manager, config_manager, event_bus):
        """
        初始化连接处理器
        :param wifi_manager: WiFi管理器实例
        :param mqtt_controller: MQTT控制器实例
        :param ntp_manager: NTP管理器实例
        :param state_manager: 状态管理器实例
        :param retry_manager: 重试管理器实例
        :param config_manager: 配置管理器实例
        :param event_bus: 事件总线实例
        """
        self.wifi_manager = wifi_manager
        self.mqtt_controller = mqtt_controller
        self.ntp_manager = ntp_manager
        self.state_manager = state_manager
        self.retry_manager = retry_manager
        self.config_manager = config_manager
        self.event_bus = event_bus
        
        # 连接配置
        connection_config = config_manager.get_connection_config()
        self.connection_timeout = connection_config.get('connection_timeout', 20000)
        
        # WiFi连接器
        self.wifi_connector = WifiConnector(wifi_manager, state_manager, event_bus)
    
    def start_connection_process(self):
        """开始连接流程"""
        self.state_manager.state_start_time = time.ticks_ms()
        return self._connect_wifi()
    
    def _connect_wifi(self):
        """连接WiFi"""
        wifi_config = self.config_manager.get_wifi_config()
        
        if self.state_manager.wifi_connected:
            info("WiFi已连接, 直接连接MQTT", module="NET")
            self._connect_mqtt()
            return True
        
        # 使用WiFi连接器处理连接逻辑
        if not self.wifi_connector.connect_wifi(wifi_config):
            self._handle_connection_failed()
            return False
        
        # WiFi连接成功后同步时间并连接MQTT
        self._sync_ntp()
        self._connect_mqtt()
        return True
    
        
    def _connect_mqtt(self):
        """MQTT连接逻辑"""
        if self.state_manager.mqtt_connected:
            return
        
        info("开始MQTT连接", module="NET")
        self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="connecting")
        
        try:
            if self.mqtt_controller.connect():
                info("MQTT连接成功", module="NET")
            else:
                warning("MQTT连接失败", module="NET")
                self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], 
                                     state="disconnected", error="连接失败")
        except Exception as e:
            warning("MQTT连接异常: {}", e, module="NET")
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], 
                                 state="disconnected", error=str(e))
    
    def _sync_ntp(self):
        """NTP时间同步"""
        if not self.state_manager.wifi_connected:
            return
        
        try:
            info("开始NTP同步...", module="NET")
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state="started")
            
            success = self.ntp_manager.sync_time()
            state = "success" if success else "failed"
            
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state=state)
            info("NTP同步{}", "成功" if success else "失败", module="NET")
            
        except Exception as e:
            warning("NTP同步异常: {}", e, module="NET")
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], 
                                 state="failed", error=str(e))
    
    def update_connection_status(self):
        """更新连接状态"""
        wifi_status = self.wifi_manager.get_is_connected()
        mqtt_status = self.mqtt_controller.is_connected()
        
        self.state_manager.update_wifi_status(wifi_status)
        self.state_manager.update_mqtt_status(mqtt_status)
    
    def check_connection_success(self):
        """检查连接是否成功"""
        if self.state_manager.get_current_state() == 1:  # STATE_CONNECTING
            # WiFi连接成功后认为网络基本可用
            if self.state_manager.wifi_connected:
                self.state_manager.transition_to_state(2)  # STATE_CONNECTED
                self.retry_manager.record_success()
                
                if self.state_manager.wifi_connected and self.state_manager.mqtt_connected:
                    info("网络连接完成 (WiFi+MQTT)", module="NET")
                else:
                    info("网络连接完成 (仅WiFi)", module="NET")
    
    def check_timeouts(self):
        """检查超时"""
        if self.state_manager.get_current_state() != 1:  # STATE_CONNECTING
            return
        
        elapsed = self.state_manager.get_elapsed_time()
        
        # 连接超时检查
        if elapsed > self.connection_timeout:
            warning("连接超时({}ms)", elapsed, module="NET")
            self._handle_connection_failed()
            return
        
        # 重试检查
        if self.retry_manager.is_ready_to_retry():
            info("重试时间到达, 开始重试", module="NET")
            self.start_connection_process()
    
    def _handle_connection_failed(self):
        """处理连接失败"""
        self.retry_manager.record_attempt()
        
        if self.retry_manager.should_retry():
            delay = self.retry_manager.get_retry_delay()
            info("连接失败, {}秒后重试 (第{}/{}次)", 
                 delay // 1000, 
                 self.retry_manager.get_retry_count(), 
                 self.retry_manager.max_retries, module="NET")
        else:
            error("达到最大重试次数, 断开连接", module="NET")
            self.state_manager.transition_to_state(0)  # STATE_DISCONNECTED
            self.disconnect_all()
    
    def disconnect_all(self):
        """断开所有连接"""
        try:
            if self.state_manager.mqtt_connected:
                self.mqtt_controller.disconnect()
            if self.state_manager.wifi_connected:
                self.wifi_connector.disconnect_wifi()
                
            # 重置连接状态
            self.state_manager.reset_connection_status()
            
            # 重置重试状态
            self.retry_manager.reset()
                
            # 发布断开事件
            for event in [EVENTS['WIFI_STATE_CHANGE'], EVENTS['MQTT_STATE_CHANGE']]:
                self.event_bus.publish(event, state="disconnected")
                
            info("所有网络已断开", module="NET")
        except Exception as e:
            error("断开连接错误: {}", e, module="NET")