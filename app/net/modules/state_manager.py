# app/net/modules/state_manager.py
"""状态管理模块"""

import utime as time
from lib.logger import debug, info, warning, error

# 状态常量
STATE_DISCONNECTED, STATE_CONNECTING, STATE_CONNECTED = 0, 1, 2
STATE_NAMES = ["DISCONNECTED", "CONNECTING", "CONNECTED"]

class StateManager:
    """状态管理器 - 负责网络状态管理和事件发布"""
    
    def __init__(self, event_bus):
        """
        初始化状态管理器
        :param event_bus: 事件总线实例
        """
        self.event_bus = event_bus
        
        # 状态管理
        self.current_state = STATE_DISCONNECTED
        self.state_start_time = time.ticks_ms()
        
        # 连接状态跟踪
        self.wifi_connected = False
        self.mqtt_connected = False
        self.last_wifi_state = False
        self.last_mqtt_state = False
    
    def transition_to_state(self, new_state):
        """状态转换"""
        if new_state != self.current_state:
            self.current_state = new_state
            self.state_start_time = time.ticks_ms()
            self._publish_state_change()
    
    def get_elapsed_time(self):
        """获取状态持续时间"""
        return time.ticks_diff(time.ticks_ms(), self.state_start_time)
    
    def get_current_state(self):
        """获取当前状态"""
        return self.current_state
    
    def get_state_name(self):
        """获取当前状态名称"""
        return STATE_NAMES[self.current_state]
    
    def is_disconnected(self):
        """检查是否处于断开状态"""
        return self.current_state == STATE_DISCONNECTED
    
        
    def update_wifi_status(self, connected):
        """更新WiFi连接状态并发布事件"""
        if connected != self.last_wifi_state:
            self.wifi_connected = connected
            self.last_wifi_state = connected
            
            state = 'connected' if connected else 'disconnected'
            debug("WiFi状态变化: {}", state, module="NET")
            
            from lib.lock.event_bus import EVENTS
            self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state=state)
    
    def update_mqtt_status(self, connected):
        """更新MQTT连接状态并发布事件"""
        if connected != self.last_mqtt_state:
            self.mqtt_connected = connected
            self.last_mqtt_state = connected
            
            state = 'connected' if connected else 'disconnected'
            debug("MQTT状态变化: {}", state, module="NET")
            
            from lib.lock.event_bus import EVENTS
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state=state)
    
        
    def is_connected(self):
        """检查是否已连接 - 基于WiFi状态"""
        return (
            self.current_state == STATE_CONNECTED and 
            self.wifi_connected
        )
    
    def is_fully_connected(self):
        """检查是否完全连接 - WiFi和MQTT都连接"""
        return (
            self.current_state == STATE_CONNECTED and 
            self.wifi_connected and self.mqtt_connected
        )
    
    def get_detailed_status(self, retry_count=0):
        """获取详细状态"""
        return {
            'state': STATE_NAMES[self.current_state],
            'wifi_connected': self.wifi_connected,
            'mqtt_connected': self.mqtt_connected,
            'retry_count': retry_count,
            'network_available': self.wifi_connected,
            'full_connectivity': self.wifi_connected and self.mqtt_connected
        }
    
    def _publish_state_change(self):
        """发布状态变化事件"""
        state_name = STATE_NAMES[self.current_state].lower()
        self.event_bus.publish("network_state_change", state=state_name)
    
    def reset_connection_status(self):
        """重置连接状态"""
        self.wifi_connected = False
        self.mqtt_connected = False
        self.last_wifi_state = False
        self.last_mqtt_state = False