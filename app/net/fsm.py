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
        self.connection_timeout = config.get('connection_timeout', 45) * 1000  # 毫秒，改为45秒
        
        # 设置MQTT状态回调和消息回调
        self.mqtt.set_state_callback(self._on_mqtt_callback)
        self.mqtt.set_message_callback(self._on_mqtt_message)
        
        # 订阅事件
        self._setup_event_subscriptions()
        
        self.logger.info("网络状态机已初始化", module="NET_FSM")
    
    def _setup_event_subscriptions(self):
        """设置事件订阅"""
        self.event_bus.subscribe(EVENTS['WIFI_STATE_CHANGE'], self._on_wifi_state_change)
        self.event_bus.subscribe(EVENTS['NTP_STATE_CHANGE'], self._on_ntp_state_change)
    
    def _on_wifi_state_change(self, state, info=None):
        """处理WiFi状态变化"""
        self.logger.debug("[FSM-DEBUG] WiFi状态变化: {} -> {}, 当前FSM状态: {}", 
                         'connected' if self.wifi_connected else 'disconnected', 
                         state, STATE_NAMES[self.current_state], module="NET_FSM")
        
        if state == 'connected':
            self.wifi_connected = True
            self.logger.info("WiFi连接成功", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] WiFi连接成功，准备进入MQTT连接阶段", module="NET_FSM")
            # WiFi连接成功，继续MQTT连接
            if self.current_state == STATE_CONNECTING:
                self._connect_mqtt()
        elif state == 'disconnected':
            self.wifi_connected = False
            self.mqtt_connected = False  # WiFi断开时MQTT也断开
            self.logger.debug("[FSM-DEBUG] WiFi断开，同时标记MQTT为断开状态", module="NET_FSM")
            if self.current_state == STATE_CONNECTED:
                self._handle_event('connection_lost')
    
    def _on_mqtt_callback(self, state, error=None):
        """处理MQTT状态回调"""
        self.logger.debug("[FSM-DEBUG] MQTT状态回调: {} -> {}, 错误: {}, 当前FSM状态: {}", 
                         'connected' if self.mqtt_connected else 'disconnected', 
                         state, error, STATE_NAMES[self.current_state], module="NET_FSM")
        
        # 发布MQTT状态变化事件（统一事件发布点）
        if error:
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state=state, error=error)
        else:
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state=state)
        
        # 原有的状态处理逻辑
        if state == 'connected':
            self.mqtt_connected = True
            self.logger.info("MQTT连接成功", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] MQTT连接成功，网络连接完成", module="NET_FSM")
            if self.current_state == STATE_CONNECTING:
                self._handle_event('connection_success')
        elif state == 'disconnected':
            self.mqtt_connected = False
            self.logger.debug("[FSM-DEBUG] MQTT断开，WiFi状态: {}, FSM状态: {}", 
                             self.wifi_connected, STATE_NAMES[self.current_state], module="NET_FSM")
            # 如果WiFi已连接但MQTT断开，只重连MQTT，不重新连接WiFi
            if self.wifi_connected:
                if self.current_state == STATE_CONNECTED:
                    self.logger.info("MQTT断开但WiFi正常，只重连MQTT", module="NET_FSM")
                    self.logger.debug("[FSM-DEBUG] 智能重连策略：保持WiFi连接，仅重连MQTT", module="NET_FSM")
                    self._reconnect_mqtt_only()
                elif self.current_state == STATE_CONNECTING:
                    self.logger.info("MQTT连接失败但WiFi正常，只重连MQTT", module="NET_FSM")
                    self.logger.debug("[FSM-DEBUG] 连接阶段MQTT失败，启用智能重连", module="NET_FSM")
                    # 在连接过程中MQTT失败，只重连MQTT，不触发整个网络流程失败
                    self._reconnect_mqtt_only()
            elif self.current_state == STATE_CONNECTED:
                # WiFi也断开了，触发连接丢失
                self.logger.debug("[FSM-DEBUG] WiFi和MQTT都断开，触发连接丢失事件", module="NET_FSM")
                self._handle_event('connection_lost')
    
    def _on_mqtt_message(self, topic, message):
        """MQTT消息回调"""
        self.logger.info("收到MQTT消息: 主题={}, 消息={}", topic, message, module="NET_FSM")
        
        # 发布MQTT消息事件
        self.event_bus.publish(EVENTS['MQTT_MESSAGE'], {
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
        self.logger.info("处理事件: {} (当前状态: {})", event, STATE_NAMES[self.current_state], module="NET_FSM")
        
        next_state = STATE_TRANSITIONS.get(self.current_state, {}).get(event)
        
        if next_state is not None and next_state != self.current_state:
            self.logger.info("状态转换: {} → {} (事件: {})", 
                           STATE_NAMES[self.current_state], STATE_NAMES[next_state], event, module="NET_FSM")
            self._transition_to(next_state)
        elif next_state is None:
            self.logger.warning("事件 {} 在状态 {} 中没有定义转换", event, STATE_NAMES[self.current_state], module="NET_FSM")
        else:
            self.logger.debug("事件 {} 在状态 {} 中不会触发状态转换", event, STATE_NAMES[self.current_state], module="NET_FSM")
    
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
        
        self.logger.debug("[FSM-DEBUG] 进入CONNECTING状态，当前WiFi状态: {}, MQTT状态: {}", 
                         self.wifi_connected, self.mqtt_connected, module="NET_FSM")
        
        # 智能连接策略：如果WiFi已连接，只重连MQTT
        if self.wifi_connected:
            self.logger.info("WiFi已连接，直接连接MQTT", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] 智能连接策略：跳过WiFi连接，直接连接MQTT", module="NET_FSM")
            self._connect_mqtt()
        else:
            self.logger.info("WiFi未连接，开始完整连接流程", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] 完整连接流程：先连接WiFi，再连接MQTT", module="NET_FSM")
            self._connect_wifi()
    
    def _on_enter_connected(self):
        """进入已连接状态"""
        self.retry_count = 0
        self.logger.info("网络连接完成", module="NET_FSM")
    
    def _on_enter_error(self):
        """进入错误状态"""
        self.logger.error("网络连接失败", module="NET_FSM")
        
        self.logger.debug("[FSM-DEBUG] 进入ERROR状态，WiFi: {}, MQTT: {}, 重试次数: {}/{}", 
                         self.wifi_connected, self.mqtt_connected, self.retry_count, self.max_retries, module="NET_FSM")
        
        # 区分错误类型，决定重连策略
        if self.wifi_connected and not self.mqtt_connected:
            # 只有MQTT失败，WiFi正常
            self.logger.info("WiFi连接正常，仅MQTT连接失败，准备重连MQTT", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] MQTT连接失败详情 - 可能原因：服务器未启动、网络不通、认证失败", module="NET_FSM")
            # 设置更短的重连延迟
            delay = min(self.backoff_delay * (2 ** self.retry_count), 30)  # MQTT重连延迟更短
        else:
            # WiFi或其他网络连接失败
            self.logger.debug("[FSM-DEBUG] WiFi连接失败详情 - 可能原因：信号弱、密码错误、路由器问题", module="NET_FSM")
            delay = min(self.backoff_delay * (2 ** self.retry_count), 60)
        
        self.logger.info("{}秒后尝试重连", delay, module="NET_FSM")
        self.logger.debug("[FSM-DEBUG] 重连延迟计算：基础时间={}s, 当前延迟={}s", 
                         self.backoff_delay, delay, module="NET_FSM")
        
        # 设置重连定时器
        self.retry_time = time.ticks_ms() + delay * 1000
    
    def _on_enter_disconnected(self):
        """进入断开状态"""
        self._disconnect_all()
        self.logger.info("网络已断开", module="NET_FSM")
    
    def _connect_wifi(self):
        """连接WiFi"""
        if self.wifi_connected:
            self.logger.info("WiFi已连接，跳过连接过程", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] WiFi状态检查：已连接，跳过WiFi连接流程", module="NET_FSM")
            return
        
        self.logger.info("开始连接WiFi", module="NET_FSM")
        self.logger.debug("[FSM-DEBUG] WiFi连接流程开始，准备扫描网络", module="NET_FSM")
        self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state="connecting")
        
        # 扫描网络
        self.logger.info("扫描WiFi网络...", module="NET_FSM")
        networks = self.wifi.scan_networks()
        self.logger.info("找到 {} 个WiFi网络", len(networks) if networks else 0, module="NET_FSM")
        
        if not networks:
            self.logger.error("未找到可用WiFi网络", module="NET_FSM")
            self._handle_event('connection_failed')
            return
        
        # 尝试连接配置中的网络
        # 注意：WiFi配置在config.py的wifi段中，不是在network段中
        wifi_config = self.config.get('wifi', {})
        wifi_networks = wifi_config.get('networks', [])
        self.logger.info("配置了 {} 个WiFi网络", len(wifi_networks), module="NET_FSM")
        
        connected = False
        for network in networks:
            ssid = network['ssid']
            rssi = network.get('rssi', 'N/A')
            self.logger.debug("发现WiFi网络: {} (RSSI: {})", ssid, rssi, module="NET_FSM")
            
            for network_config in wifi_networks:
                if network_config.get('ssid') == ssid:
                    password = network_config.get('password')
                    
                    self.logger.info("尝试连接WiFi: {} (RSSI: {})", ssid, rssi, module="NET_FSM")
                    
                    if self.wifi.connect(ssid, password):
                        self.logger.info("WiFi连接命令已发送，等待连接建立...", module="NET_FSM")
                        # 等待连接建立
                        wait_start = time.ticks_ms()
                        while time.ticks_diff(time.ticks_ms(), wait_start) < 10000:  # 10秒超时
                            if self.wifi.get_is_connected():
                                connected = True
                                break
                            time.sleep_ms(200)
                        
                        if connected:
                            self.logger.info("WiFi连接成功: {}", ssid, module="NET_FSM")
                            self.logger.debug("[FSM-DEBUG] WiFi连接成功，继续执行MQTT连接", module="NET_FSM")
                            self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state="connected", ssid=ssid)
                            # WiFi连接成功后，继续连接MQTT
                            self._connect_mqtt()
                            return
                        else:
                            self.logger.warning("WiFi连接超时: {}", ssid, module="NET_FSM")
                    else:
                        self.logger.error("WiFi连接命令失败: {}", ssid, module="NET_FSM")
        
        # 所有网络都连接失败
        self.logger.error("所有WiFi网络连接失败", module="NET_FSM")
        self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state="disconnected", error="连接失败")
        self._handle_event('connection_failed')
    
    def _connect_mqtt(self):
        """连接MQTT - 优化连接策略"""
        if self.mqtt_connected:
            self.logger.info("MQTT已连接，跳过连接过程", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] MQTT状态检查：已连接，跳过MQTT连接流程", module="NET_FSM")
            return
        
        self.logger.info("开始连接MQTT", module="NET_FSM")
        self.logger.debug("[FSM-DEBUG] MQTT连接流程开始，WiFi状态: {}", self.wifi_connected, module="NET_FSM")
        
        # 发布MQTT连接状态
        self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="connecting")
        
        # 同步NTP时间（可选）
        self._sync_ntp()
        
        # MQTT连接由mqtt控制器自己处理
        # 这里只是启动连接，实际的连接状态通过事件回调处理
        try:
            self.logger.info("调用MQTT控制器连接方法...", module="NET_FSM")
            result = self.mqtt.connect()
            self.logger.info("MQTT连接方法调用完成，结果: {}", result, module="NET_FSM")
            
            # 如果连接方法返回False，记录失败但不立即重连
            if not result:
                self.logger.error("MQTT连接方法返回失败", module="NET_FSM")
                self.logger.debug("[FSM-DEBUG] MQTT连接失败，WiFi状态: {}，等待超时处理", self.wifi_connected, module="NET_FSM")
                # 发布MQTT状态为disconnected，让超时机制处理重连
                self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="disconnected", error="连接失败")
            else:
                self.logger.info("MQTT连接启动成功，等待连接建立...", module="NET_FSM")
                self.logger.debug("[FSM-DEBUG] MQTT连接方法调用成功，等待连接回调", module="NET_FSM")
                
        except Exception as e:
            self.logger.error("MQTT连接启动失败: {}", e, module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] MQTT连接异常，WiFi状态: {}，等待超时处理", self.wifi_connected, module="NET_FSM")
            # 发布MQTT状态为disconnected，让超时机制处理重连
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="disconnected", error=str(e))
    
    def _sync_ntp(self):
        """同步NTP时间"""
        if not self.wifi_connected:
            return
        
        try:
            self.logger.debug("开始NTP同步", module="NET_FSM")
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state="started")
            
            if self.ntp.sync_time():
                self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state="success")
            else:
                self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state="failed")
        except Exception as e:
            self.logger.debug("NTP同步异常: {}", e, module="NET_FSM")
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state="failed", error=str(e))
    
    def _reconnect_mqtt_only(self):
        """只重连MQTT，不重新连接WiFi"""
        try:
            self.logger.info("开始MQTT重连（保持WiFi连接）", module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] MQTT独立重连开始 - WiFi状态: {}, FSM状态: {}", 
                             self.wifi_connected, STATE_NAMES[self.current_state], module="NET_FSM")
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="connecting")
            
            # 重置MQTT连接状态
            self.mqtt_connected = False
            
            # 重置MQTT连接计数器
            if hasattr(self.mqtt, 'reset_failure_count'):
                self.mqtt.reset_failure_count()
                self.logger.debug("[FSM-DEBUG] MQTT失败计数器已重置", module="NET_FSM")
            
            # 启动MQTT连接
            self.logger.debug("[FSM-DEBUG] 调用MQTT控制器连接方法", module="NET_FSM")
            result = self.mqtt.connect()
            if not result:
                self.logger.error("MQTT重连启动失败", module="NET_FSM")
                self.logger.debug("[FSM-DEBUG] MQTT重连失败，但不影响WiFi连接和FSM状态", module="NET_FSM")
                self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="disconnected", error="连接失败")
            else:
                self.logger.info("MQTT重连启动成功", module="NET_FSM")
                self.logger.debug("[FSM-DEBUG] MQTT重连启动成功，等待连接建立", module="NET_FSM")
                # 重置状态开始时间，给MQTT连接更多时间
                self.state_start_time = time.ticks_ms()
        except Exception as e:
            self.logger.error("MQTT重连异常: {}", e, module="NET_FSM")
            self.logger.debug("[FSM-DEBUG] MQTT重连异常，但不影响WiFi连接和FSM状态", module="NET_FSM")
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="disconnected", error=str(e))
    
    def _disconnect_all(self):
        """断开所有连接"""
        try:
            if self.mqtt_connected:
                self.mqtt.disconnect()
            self.mqtt_connected = False
            
            if self.wifi_connected:
                self.wifi.disconnect()
            self.wifi_connected = False
            
            self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state="disconnected")
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="disconnected")
        except Exception as e:
            self.logger.error("断开连接时发生错误: {}", e, module="NET_FSM")
    
    def _publish_state_change(self):
        """发布状态变化事件"""
        state_name = STATE_NAMES[self.current_state]
        self.event_bus.publish("network_state_change", state=state_name.lower())
    
    def _check_connection_timeout(self):
        """检查连接超时 - 优化超时策略"""
        if self.current_state == STATE_CONNECTING:
            elapsed = time.ticks_diff(time.ticks_ms(), self.state_start_time)
            
            self.logger.debug("[FSM-DEBUG] 连接超时检查，已耗时: {}ms，WiFi: {}, MQTT: {}", 
                             elapsed, self.wifi_connected, self.mqtt_connected, module="NET_FSM")
            
            # 分阶段超时检查
            if not self.wifi_connected:
                # WiFi连接超时：15秒
                wifi_timeout = 15000
                if elapsed > wifi_timeout:
                    self.logger.warning("WiFi连接超时（{}ms）", elapsed, module="NET_FSM")
                    self.logger.debug("[FSM-DEBUG] WiFi连接超时详情 - 超时阈值: {}ms，实际耗时: {}ms", 
                                     wifi_timeout, elapsed, module="NET_FSM")
                    self._handle_event('connection_failed')
            elif self.wifi_connected and not self.mqtt_connected:
                # MQTT连接超时：WiFi连接成功后给30秒时间
                mqtt_timeout = 30000
                if elapsed > mqtt_timeout:
                    self.logger.warning("MQTT连接超时（{}ms），WiFi连接正常", elapsed, module="NET_FSM")
                    self.logger.debug("[FSM-DEBUG] MQTT连接超时详情 - 超时阈值: {}ms，实际耗时: {}ms，WiFi状态正常", 
                                     mqtt_timeout, elapsed, module="NET_FSM")
                    # WiFi已连接，转换到ERROR状态，让重连机制处理MQTT重连
                    self.logger.debug("[FSM-DEBUG] MQTT超时，转换到ERROR状态进行智能重连", module="NET_FSM")
                    self._handle_event('connection_failed')
            else:
                # 全部连接成功，不应该还在CONNECTING状态
                if elapsed > self.connection_timeout:
                    self.logger.warning("连接状态异常，触发重连", module="NET_FSM")
                    self.logger.debug("[FSM-DEBUG] 连接状态异常详情 - WiFi: {}, MQTT: {}, 但仍在CONNECTING状态", 
                                     self.wifi_connected, self.mqtt_connected, module="NET_FSM")
                    self._handle_event('connection_failed')
    
    def _check_retry_timeout(self):
        """检查重连超时"""
        if self.current_state == STATE_ERROR:
            if hasattr(self, 'retry_time'):
                current_time = time.ticks_ms()
                time_diff = time.ticks_diff(current_time, self.retry_time)
                
                self.logger.debug("[FSM-DEBUG] 重连超时检查，当前时间差: {}ms，重试次数: {}/{}", 
                                 time_diff, self.retry_count, self.max_retries, module="NET_FSM")
                
                if time_diff >= 0:
                    self.retry_count += 1
                    self.logger.debug("[FSM-DEBUG] 重连时间到达，开始第{}次重试", self.retry_count, module="NET_FSM")
                    
                    if self.retry_count <= self.max_retries:
                        self.logger.info("开始第{}次重连尝试", self.retry_count, module="NET_FSM")
                        self._handle_event('retry')
                    else:
                        self.logger.error("达到最大重试次数", module="NET_FSM")
                        self.logger.debug("[FSM-DEBUG] 重试次数已达上限 {}/{}，执行重置操作", 
                                         self.retry_count, self.max_retries, module="NET_FSM")
                        self._handle_event('reset')
    
    # =============================================================================
    # 公共接口
    # =============================================================================
    
    def connect(self):
        """启动网络连接"""
        self.logger.info("NetworkFSM.connect() 被调用", module="NET_FSM")
        self.logger.info("当前状态: {}", STATE_NAMES[self.current_state], module="NET_FSM")
        
        if self.current_state == STATE_DISCONNECTED:
            self.logger.info("从DISCONNECTED状态启动连接", module="NET_FSM")
            self._handle_event('connect')
        elif self.current_state == STATE_ERROR:
            self.logger.info("从ERROR状态重试连接", module="NET_FSM")
            self.retry_count = 0
            self._handle_event('retry')
        else:
            self.logger.warning("当前状态{}不允许启动连接", STATE_NAMES[self.current_state], module="NET_FSM")
    
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
        connected = self.current_state == STATE_CONNECTED
        self.logger.debug("[FSM-DEBUG] 连接状态检查 - FSM状态: {}, WiFi: {}, MQTT: {}, 最终结果: {}", 
                         STATE_NAMES[self.current_state], self.wifi_connected, self.mqtt_connected, connected, module="NET_FSM")
        return connected
    
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
            self.logger.debug("[FSM-DEBUG] 状态机循环异常详情 - 当前状态: {}, WiFi: {}, MQTT: {}, 错误: {}", 
                             STATE_NAMES[self.current_state], self.wifi_connected, self.mqtt_connected, str(e), module="NET_FSM")
            self._handle_event('connection_failed')