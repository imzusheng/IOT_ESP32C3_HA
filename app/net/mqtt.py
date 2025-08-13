# app/net/mqtt.py
# 简化版MQTT控制器，只提供基本的MQTT操作功能
from lib.lock.umqtt import MQTTClient
import utime as time
import machine
from lib.logger import get_global_logger
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
        self.logger = get_global_logger()
        self.client = None
        self._is_connected = False
        self.last_ping_time = 0
        # 移除事件总线，所有事件发布通过fsm.py统一处理
        self._state_callback = None  # 状态变化回调函数
        self._message_callback = None  # 消息回调函数
        
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
            self.logger.error(f"创建MQTT客户端失败: {e}", module="MQTT")

    def _mqtt_callback(self, topic, msg):
        """
        MQTT消息回调函数
        当收到消息时，通过消息回调函数通知上层
        """
        try:
            topic_str = topic.decode('utf-8')
            msg_str = msg.decode('utf-8')
            self.logger.info("收到消息: 主题='{}', 消息='{}'", topic_str, msg_str, module="MQTT")
            
            # 通过消息回调函数通知上层（fsm.py）
            if self._message_callback:
                self._message_callback(topic_str, msg_str)
            
        except Exception as e:
            self.logger.error("处理MQTT消息失败: {}", e, module="MQTT")
    
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
    

    
    def connect(self):
        """
        连接到MQTT Broker
        
        Returns:
            bool: 连接成功返回True，失败返回False
        """
        if self._is_connected or not self.client:
            return False

        try:
            # 使用同步连接（MicroPython umqtt 不支持异步连接）
            self.client.connect()
            
            # 验证连接是否真正建立
            if self.client.is_connected():
                self._is_connected = True
                return True
            else:
                self._is_connected = False
                return False
            
        except Exception as e:
            # 不在这里输出错误日志，让NetworkManager统一处理
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
                self.logger.error("MQTT断开失败: {}", e, module="MQTT")
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
            self.logger.error("MQTT发布失败: {}", e, module="NET")
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
            self.logger.error("MQTT订阅失败: {}", e, module="NET")
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
                    self.logger.info("MQTT连接恢复", module="MQTT")
                    # 通过回调函数报告连接成功
                    if self._state_callback:
                        self._state_callback('connected')
                    # 自动订阅配置的主题
                    for topic in self.config.get('subscribe_topics', []):
                        self.subscribe(topic)
                elif not actual_connected and self._is_connected:
                    # 连接丢失
                    self._is_connected = False
                    # 通过回调函数报告连接断开
                    if self._state_callback:
                        self._state_callback('disconnected')
            except Exception as e:
                # 检查连接状态时出错，认为连接已断开
                if self._is_connected:
                    self._is_connected = False
                    # 通过回调函数报告连接断开
                    if self._state_callback:
                        self._state_callback('disconnected')
            
            # 发送 PING 以保持连接活跃
            if self._is_connected:
                keepalive_ms = self.config.get('keepalive', 60) * 1000
                if time.ticks_diff(time.ticks_ms(), self.last_ping_time) > keepalive_ms / 2:
                    self.client.ping()
                    self.last_ping_time = time.ticks_ms()

        except Exception as e:
            self.logger.error("MQTT循环错误: {}", e, module="NET")
            self._is_connected = False
