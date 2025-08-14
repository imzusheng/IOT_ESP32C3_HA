# app/net/mqtt.py
# 简化版MQTT控制器，只提供基本的MQTT操作功能
from lib.lock.umqtt import MQTTClient
import utime as time
import machine
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS

class MqttController:
    """
    MQTT控制器
    
    只提供基本的MQTT操作功能：
    - 连接/断开连接
    - 发布/订阅消息
    - 消息回调处理
    - 基本的连接状态检查
    """
    
    def __init__(self, config=None):
        """
        初始化MQTT控制器
        :param config: MQTT配置字典（可选）
        """
        self.config = config or {}
        # 移除logger实例，直接使用全局日志函数
        self.client = None
        self._is_connected = False
        self.last_ping_time = 0
        # 移除事件总线，所有事件发布通过fsm.py统一处理
        self._state_callback = None  # 状态变化回调函数
        self._message_callback = None  # 消息回调函数
        
        # 添加失败计数器管理
        self.failure_count = 0
        
        self._setup_client()

    def _setup_client(self):
        """根据配置初始化MQTT客户端。"""
        try:
            self.client = MQTTClient(
                client_id="esp32c3_" + str(machine.unique_id())[-6:] if hasattr(machine, 'unique_id') else "esp32c3_device",
                server=self.config['broker'],
                port=self.config.get('port', 1883),
                user=self.config.get('user'),
                password=self.config.get('password'),
                keepalive=self.config.get('keepalive', 60)
            )
            self.client.set_callback(self._mqtt_callback)
        except Exception as e:
            error(f"创建MQTT客户端失败: {e}", module="MQTT")

    def _mqtt_callback(self, topic, msg):
        """
        MQTT消息回调函数
        当收到消息时，通过消息回调函数通知上层
        """
        try:
            topic_str = topic.decode('utf-8')
            msg_str = msg.decode('utf-8')
            info("收到消息: 主题='{}', 消息='{}'", topic_str, msg_str, module="MQTT")
            
            # 通过消息回调函数通知上层（fsm.py）
            if self._message_callback:
                self._message_callback(topic_str, msg_str)
            
        except Exception as e:
            error("处理MQTT消息失败: {}", e, module="MQTT")
    
    # set_event_bus方法已移除，所有事件发布通过fsm.py统一处理
    
    def set_state_callback(self, callback):
        """
        设置状态变化回调函数
        :param callback: 回调函数，接收状态变化通知
        """
        self._state_callback = callback
    
    def set_message_callback(self, callback):
        """
        设置消息回调函数
        :param callback: 回调函数，接收MQTT消息通知
        """
        self._message_callback = callback
    
    def reset_failure_count(self):
        """
        重置失败计数器
        """
        self.failure_count = 0
        debug("[MQTT-DEBUG] 失败计数器已重置", module="MQTT")
    

    
    def connect(self):
        """
        连接到MQTT Broker
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        info("MQTT控制器connect()被调用", module="MQTT")
        debug("[MQTT-DEBUG] MQTT连接流程开始", module="MQTT")
        
        if self._is_connected:
            info("MQTT已连接，跳过连接", module="MQTT")
            debug("[MQTT-DEBUG] MQTT连接状态检查：已连接，跳过连接流程", module="MQTT")
            return False
            
        if not self.client:
            error("MQTT客户端未初始化", module="MQTT")
            debug("[MQTT-DEBUG] MQTT客户端为None，可能原因：配置错误、初始化失败", module="MQTT")
            return False

        try:
            broker = self.config.get('broker', 'N/A')
            port = self.config.get('port', 1883)
            user = self.config.get('user', 'N/A')
            
            info("MQTT配置: broker={}, port={}, user={}", 
                           broker, port, user, module="MQTT")
            debug("[MQTT-DEBUG] MQTT连接参数 - Broker: {}, Port: {}, User: {}, Keepalive: {}s", 
                             broker, port, user, self.config.get('keepalive', 60), module="MQTT")
            
            # 使用同步连接（MicroPython umqtt 不支持异步连接）
            info("开始MQTT连接到 {}:{}", broker, port, module="MQTT")
            self.client.connect()
            info("MQTT连接命令执行完成", module="MQTT")
            debug("[MQTT-DEBUG] MQTT连接命令已发送，开始验证连接状态", module="MQTT")
            
            # 验证连接是否真正建立
            info("验证MQTT连接状态...", module="MQTT")
            if self.client.is_connected():
                self._is_connected = True
                self.failure_count = 0  # 连接成功时重置失败计数器
                info("MQTT连接验证成功", module="MQTT")
                debug("[MQTT-DEBUG] MQTT连接验证成功，连接状态已更新，失败计数器已重置", module="MQTT")
                # 通过回调函数报告连接成功
                if self._state_callback:
                    self._state_callback('connected')
                return True
            else:
                self._is_connected = False
                self.failure_count += 1
                error("MQTT连接验证失败 (失败次数: {})", self.failure_count, module="MQTT")
                debug("[MQTT-DEBUG] MQTT连接验证失败，可能原因：服务器未启动、网络不通、认证失败", module="MQTT")
                return False
            
        except Exception as e:
            self.failure_count += 1
            error("MQTT连接异常: {} (失败次数: {})", e, self.failure_count, module="MQTT")
            debug("[MQTT-DEBUG] MQTT连接异常详情 - 错误类型: {}, 错误信息: {}", type(e).__name__, str(e), module="MQTT")
            self._is_connected = False
            # 通过回调函数报告连接失败
            if self._state_callback:
                self._state_callback('disconnected', error=str(e))
            return False

    def is_connected(self):
        """检查MQTT是否已连接"""
        return self._is_connected

    def disconnect(self):
        """
        断开与MQTT Broker的连接
        
        Returns:
            bool: 断开成功返回True
        """
        if self._is_connected and self.client:
            try:
                self.client.disconnect()
            except Exception as e:
                error("MQTT断开失败: {}", e, module="MQTT")
                return False
        
        self._is_connected = False
        # 通过回调函数报告断开连接
        if self._state_callback:
            self._state_callback('disconnected')
        
        return True

    def publish(self, topic, msg, retain=False, qos=0):
        """
        发布消息
        
        Args:
            topic (str): 主题
            msg (str): 消息内容
            retain (bool): 是否保留消息
            qos (int): 服务质量等级
            
        Returns:
            bool: 发布成功返回True
        """
        if not self._is_connected or not self.client:
            return False

        try:
            self.client.publish(topic, msg, retain, qos)
            return True
        except Exception as e:
            error("MQTT发布失败: {}", e, module="NET")
            return False

    def subscribe(self, topic, qos=0):
        """
        订阅主题
        
        Args:
            topic (str): 主题
            qos (int): 服务质量等级
            
        Returns:
            bool: 订阅成功返回True
        """
        if not self._is_connected or not self.client:
            return False
        
        try:
            self.client.subscribe(topic, qos)
            return True
        except Exception as e:
            error("MQTT订阅失败: {}", e, module="NET")
            return False

    def loop(self):
        """
        在主循环中定期调用
        处理入站消息并维持连接
        """
        if not self.client:
            return

        try:
            # 检查入站消息
            self.client.check_msg()
            
            # 检查连接状态
            was_connected = self._is_connected
            # 使用is_connected方法检查连接状态
            try:
                actual_connected = self.client.is_connected()
                
                if actual_connected and not self._is_connected:
                    # 连接恢复
                    self._is_connected = True
                    info("MQTT连接恢复", module="MQTT")
                    debug("[MQTT-DEBUG] MQTT连接状态变化：断开 -> 连接，触发连接恢复流程", module="MQTT")
                    # 通过回调函数报告连接成功
                    if self._state_callback:
                        self._state_callback('connected')
                    # 自动订阅配置的主题
                    subscribe_topics = self.config.get('subscribe_topics', [])
                    debug("[MQTT-DEBUG] 连接恢复后重新订阅{}个主题", len(subscribe_topics), module="MQTT")
                    for topic in subscribe_topics:
                        debug("[MQTT-DEBUG] 重新订阅主题: {}", topic, module="MQTT")
                        self.subscribe(topic)
                elif not actual_connected and self._is_connected:
                    # 连接丢失
                    self._is_connected = False
                    debug("[MQTT-DEBUG] MQTT连接状态变化：连接 -> 断开，触发连接丢失流程", module="MQTT")
                    # 通过回调函数报告连接断开
                    if self._state_callback:
                        self._state_callback('disconnected')
            except Exception as e:
                # 检查连接状态时出错，认为连接已断开
                debug("[MQTT-DEBUG] MQTT连接状态检查异常: {}，假定连接已断开", e, module="MQTT")
                if self._is_connected:
                    self._is_connected = False
                    # 通过回调函数报告连接断开
                    if self._state_callback:
                        self._state_callback('disconnected')
            
            # 发送 PING 以保持连接活跃
            if self._is_connected:
                keepalive_ms = self.config.get('keepalive', 60) * 1000
                current_time = time.ticks_ms()
                time_since_ping = time.ticks_diff(current_time, self.last_ping_time)
                
                if time_since_ping > keepalive_ms / 2:
                    debug("[MQTT-DEBUG] 发送MQTT心跳包，距离上次心跳: {}ms", time_since_ping, module="MQTT")
                    self.client.ping()
                    self.last_ping_time = current_time

        except Exception as e:
            error("MQTT循环错误: {}", e, module="NET")
            debug("[MQTT-DEBUG] MQTT循环异常详情 - 错误类型: {}, 连接状态: {}", 
                             type(e).__name__, self._is_connected, module="MQTT")
            self._is_connected = False
