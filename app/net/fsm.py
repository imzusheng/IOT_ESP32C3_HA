# app/net/fsm.py
"""
极简网络状态机
单一文件实现所有状态机功能，封装网络连接内部流程
"""

import utime as time
from lib.logger import get_global_logger
from lib.lock.event_bus import EVENTS

# =============================================================================
# 状态常量定义
# =============================================================================

STATE_DISCONNECTED = 0
STATE_CONNECTING = 1
STATE_CONNECTED = 2
STATE_ERROR = 3

# 状态名称映射
STATE_NAMES = {
    STATE_DISCONNECTED: "DISCONNECTED",
    STATE_CONNECTING: "CONNECTING", 
    STATE_CONNECTED: "CONNECTED",
    STATE_ERROR: "ERROR"
}

# 状态转换表
STATE_TRANSITIONS = {
    STATE_DISCONNECTED: {
        'connect': STATE_CONNECTING,
        'error': STATE_ERROR
    },
    STATE_CONNECTING: {
        'connection_success': STATE_CONNECTED,
        'connection_failed': STATE_ERROR,
        'disconnect': STATE_DISCONNECTED
    },
    STATE_CONNECTED: {
        'connection_lost': STATE_ERROR,
        'disconnect': STATE_DISCONNECTED
    },
    STATE_ERROR: {
        'retry': STATE_CONNECTING,
        'disconnect': STATE_DISCONNECTED,
        'reset': STATE_DISCONNECTED
    }
}

# =============================================================================
# 网络状态机类
# =============================================================================

class NetworkFSM:
    """
    极简网络状态机
    封装网络连接内部流程，外部只需调用简单接口
    """
    
    def __init__(self, event_bus, config, wifi_manager, mqtt_manager, ntp_manager):
        """
        初始化网络状态机
        
        Args:
            event_bus: 事件总线实例
            config: 网络配置
            wifi_manager: WiFi管理器实例
            mqtt_manager: MQTT管理器实例  
            ntp_manager: NTP管理器实例
        """
        self.event_bus = event_bus
        self.config = config
        self.wifi = wifi_manager
        self.mqtt = mqtt_manager
        self.ntp = ntp_manager
        self.logger = get_global_logger()
        
        # 状态机状态
        self.current_state = STATE_DISCONNECTED
        self.state_start_time = 0
        
        # 连接状态
        self.wifi_connected = False
        self.mqtt_connected = False
        
        # 重连配置
        self.retry_count = 0
        self.max_retries = config.get('max_retries', 5)
        self.backoff_delay = config.get('backoff_delay', 2)
        
        # 连接配置
        self.connection_timeout = config.get('connection_timeout', 120) * 1000  # 毫秒
        
        # 设置MQTT状态回调和消息回调
        self.mqtt.set_state_callback(self._on_mqtt_callback)
        self.mqtt.set_message_callback(self._on_mqtt_message)
        
        # 订阅事件
        self._setup_event_subscriptions()
        
        self.logger.info("网络状态机已初始化", module="NET_FSM")
    
    def _setup_event_subscriptions(self):
        """设置事件订阅"""
        self.event_bus.subscribe(EVENTS.WIFI_STATE_CHANGE, self._on_wifi_state_change)
        self.event_bus.subscribe(EVENTS.NTP_STATE_CHANGE, self._on_ntp_state_change)
    
    def _on_wifi_state_change(self, state, info=None):
        """处理WiFi状态变化"""
        if state == 'connected':
            self.wifi_connected = True
            self.logger.info("WiFi连接成功", module="NET_FSM")
            # WiFi连接成功，继续MQTT连接
            if self.current_state == STATE_CONNECTING:
                self._connect_mqtt()
        elif state == 'disconnected':
            self.wifi_connected = False
            self.mqtt_connected = False  # WiFi断开时MQTT也断开
            if self.current_state == STATE_CONNECTED:
                self._handle_event('connection_lost')
    
    def _on_mqtt_callback(self, state, error=None):
        """处理MQTT状态回调"""
        # 发布MQTT状态变化事件（统一事件发布点）
        if error:
            self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state=state, error=error)
        else:
            self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state=state)
        
        # 原有的状态处理逻辑
        if state == 'connected':
            self.mqtt_connected = True
            self.logger.info("MQTT连接成功", module="NET_FSM")
            if self.current_state == STATE_CONNECTING:
                self._handle_event('connection_success')
        elif state == 'disconnected':
            self.mqtt_connected = False
            if self.current_state == STATE_CONNECTED:
                self._handle_event('connection_lost')
    
    def _on_mqtt_message(self, topic, message):
        """MQTT消息回调"""
        self.logger.info("收到MQTT消息: 主题={}, 消息={}", topic, message, module="NET_FSM")
        
        # 发布MQTT消息事件
        self.event_bus.publish(EVENTS.MQTT_MESSAGE, {
            'topic': topic,
            'message': message,
            'timestamp': time.ticks_ms()
        })
    

    def _on_ntp_state_change(self, state, **kwargs):
        """处理NTP状态变化"""
        if state == 'success':
            self.logger.debug("NTP同步成功", module="NET_FSM")
        elif state == 'failed':
            self.logger.debug("NTP同步失败", module="NET_FSM")
    
    def _handle_event(self, event):
        """处理内部事件"""
        next_state = STATE_TRANSITIONS.get(self.current_state, {}).get(event)
        
        if next_state is not None and next_state != self.current_state:
            self._transition_to(next_state)
    
    def _transition_to(self, new_state):
        """转换到新状态"""
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = time.ticks_ms()
        
        self.logger.info("网络状态转换: {} → {}", 
                        STATE_NAMES[old_state], STATE_NAMES[new_state], module="NET_FSM")
        
        # 执行状态进入操作
        if new_state == STATE_CONNECTING:
            self._on_enter_connecting()
        elif new_state == STATE_CONNECTED:
            self._on_enter_connected()
        elif new_state == STATE_ERROR:
            self._on_enter_error()
        elif new_state == STATE_DISCONNECTED:
            self._on_enter_disconnected()
        
        # 发布状态变化事件
        self._publish_state_change()
    
    def _on_enter_connecting(self):
        """进入连接状态"""
        self.retry_count = 0
        self._connect_wifi()
    
    def _on_enter_connected(self):
        """进入已连接状态"""
        self.retry_count = 0
        self.logger.info("网络连接完成", module="NET_FSM")
    
    def _on_enter_error(self):
        """进入错误状态"""
        self.logger.error("网络连接失败", module="NET_FSM")
        
        # 计算重连延迟
        delay = min(self.backoff_delay * (2 ** self.retry_count), 60)
        self.logger.info("{}秒后尝试重连", delay, module="NET_FSM")
        
        # 设置重连定时器
        self.retry_time = time.ticks_ms() + delay * 1000
    
    def _on_enter_disconnected(self):
        """进入断开状态"""
        self._disconnect_all()
        self.logger.info("网络已断开", module="NET_FSM")
    
    def _connect_wifi(self):
        """连接WiFi"""
        if self.wifi_connected:
            return
        
        self.logger.info("开始连接WiFi", module="NET_FSM")
        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="connecting")
        
        # 扫描网络
        networks = self.wifi.scan_networks()
        if not networks:
            self.logger.error("未找到可用WiFi网络", module="NET_FSM")
            self._handle_event('connection_failed')
            return
        
        # 尝试连接配置中的网络
        wifi_config = self.config.get('wifi', {})
        wifi_networks = wifi_config.get('networks', [])
        
        connected = False
        for network in networks:
            ssid = network['ssid']
            
            for network_config in wifi_networks:
                if network_config.get('ssid') == ssid:
                    password = network_config.get('password')
                    
                    self.logger.info("尝试连接WiFi: {}", ssid, module="NET_FSM")
                    
                    if self.wifi.connect(ssid, password):
                        # 等待连接建立
                        wait_start = time.ticks_ms()
                        while time.ticks_diff(time.ticks_ms(), wait_start) < 10000:  # 10秒超时
                            if self.wifi.get_is_connected():
                                connected = True
                                break
                            time.sleep_ms(200)
                        
                        if connected:
                            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="connected", ssid=ssid)
                            return
        
        # 所有网络都连接失败
        self.logger.error("WiFi连接失败", module="NET_FSM")
        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", error="连接失败")
        self._handle_event('connection_failed')
    
    def _connect_mqtt(self):
        """连接MQTT"""
        if self.mqtt_connected:
            return
        
        self.logger.info("开始连接MQTT", module="NET_FSM")
        
        # 发布MQTT连接状态
        self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="connecting")
        
        # 同步NTP时间（可选）
        self._sync_ntp()
        
        # MQTT连接由mqtt控制器自己处理
        # 这里只是启动连接，实际的连接状态通过事件回调处理
        try:
            self.mqtt.connect()
        except Exception as e:
            self.logger.error("MQTT连接启动失败: {}", e, module="NET_FSM")
            self._handle_event('connection_failed')
    
    def _sync_ntp(self):
        """同步NTP时间"""
        if not self.wifi_connected:
            return
        
        try:
            self.logger.debug("开始NTP同步", module="NET_FSM")
            self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="started")
            
            if self.ntp.sync_time():
                self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="success")
            else:
                self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="failed")
        except Exception as e:
            self.logger.debug("NTP同步异常: {}", e, module="NET_FSM")
            self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="failed", error=str(e))
    
    def _disconnect_all(self):
        """断开所有连接"""
        try:
            if self.mqtt_connected:
                self.mqtt.disconnect()
            self.mqtt_connected = False
            
            if self.wifi_connected:
                self.wifi.disconnect()
            self.wifi_connected = False
            
            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected")
            self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="disconnected")
        except Exception as e:
            self.logger.error("断开连接时发生错误: {}", e, module="NET_FSM")
    
    def _publish_state_change(self):
        """发布状态变化事件"""
        state_name = STATE_NAMES[self.current_state]
        self.event_bus.publish("network_state_change", state=state_name.lower())
    
    def _check_connection_timeout(self):
        """检查连接超时"""
        if self.current_state == STATE_CONNECTING:
            elapsed = time.ticks_diff(time.ticks_ms(), self.state_start_time)
            if elapsed > self.connection_timeout:
                self.logger.warning("网络连接超时", module="NET_FSM")
                self._handle_event('connection_failed')
    
    def _check_retry_timeout(self):
        """检查重连超时"""
        if self.current_state == STATE_ERROR:
            if hasattr(self, 'retry_time'):
                if time.ticks_diff(time.ticks_ms(), self.retry_time) >= 0:
                    self.retry_count += 1
                    if self.retry_count <= self.max_retries:
                        self._handle_event('retry')
                    else:
                        self.logger.error("达到最大重试次数", module="NET_FSM")
                        self._handle_event('reset')
    
    # =============================================================================
    # 公共接口
    # =============================================================================
    
    def connect(self):
        """启动网络连接"""
        if self.current_state == STATE_DISCONNECTED:
            self._handle_event('connect')
        elif self.current_state == STATE_ERROR:
            self.retry_count = 0
            self._handle_event('retry')
    
    def disconnect(self):
        """断开网络连接"""
        self._handle_event('disconnect')
    
    def get_status(self):
        """获取网络状态"""
        return {
            'state': STATE_NAMES[self.current_state],
            'wifi_connected': self.wifi_connected,
            'mqtt_connected': self.mqtt_connected,
            'retry_count': self.retry_count
        }
    
    def is_connected(self):
        """检查是否已连接"""
        return self.current_state == STATE_CONNECTED
    
    def loop(self):
        """主循环调用"""
        try:
            # 运行MQTT循环
            if self.mqtt:
                self.mqtt.loop()
            
            # 检查超时
            self._check_connection_timeout()
            self._check_retry_timeout()
            
        except Exception as e:
            self.logger.error("网络状态机循环错误: {}", e, module="NET_FSM")
            self._handle_event('connection_failed')