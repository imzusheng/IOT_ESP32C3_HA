# app/net/mqtt.py
from lib.lock.umqtt import MQTTClient
import utime as time
import machine
from lib.logger import get_global_logger
from lib.event_bus import EVENTS

class MqttController:
    """
    MQTT控制器 (重构版本)
    
    管理MQTT连接和通信，通过事件总线与系统其他部分交互。
    支持指数退避重连策略、内存优化和心跳监控。
    
    特性:
    - 指数退避重连机制
    - 内存优化的消息处理
    - 心跳保持和超时检测
    - 事件驱动的状态报告
    """
    def __init__(self, event_bus, object_pool, config):
        """
        :param event_bus: EventBus 实例
        :param object_pool: ObjectPoolManager 实例
        :param config: MQTT 配置字典
        """
        self.event_bus = event_bus
        self.object_pool = object_pool
        self.config = config
        self.logger = get_global_logger()
        self.client = None
        self.is_connected = False
        self.last_ping_time = 0
        
        # 连接失败处理机制
        self.connection_failures = 0
        self.last_failure_time = 0
        self.last_disconnect_event_time = 0
        self.max_retries = config.get('max_retries', 5)
        self.backoff_multiplier = config.get('backoff_multiplier', 2)
        self.max_backoff_time = config.get('max_backoff_time', 300)
        
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
        MQTT消息回调函数。
        当收到消息时，发布一个事件。
        """
        try:
            topic_str = topic.decode('utf-8')
            msg_str = msg.decode('utf-8')
            self.logger.info("收到消息: 主题='{}', 消息='{}'", topic_str, msg_str, module="MQTT")
            
            # 按照事件契约发布 (topic, msg)，避免改变订阅方签名
            self.event_bus.publish(EVENTS.MQTT_MESSAGE, topic_str, msg_str)
            
        except Exception as e:
            self.logger.error("处理MQTT消息失败: {}", e, module="MQTT")

    def _should_throttle_disconnect_event(self):
        """检查是否应该限制断开事件的发布频率"""
        now = time.ticks_ms()
        # 最小间隔1秒，避免事件风暴
        if time.ticks_diff(now, self.last_disconnect_event_time) < 1000:
            return True
        return False
    
    def _calculate_backoff_delay(self):
        """计算指数退避延迟时间"""
        if self.connection_failures == 0:
            return 0
        
        # 指数退避计算
        delay = min(
            self.config.get('reconnect_delay', 5) * (self.backoff_multiplier ** (self.connection_failures - 1)),
            self.max_backoff_time
        )
        return int(delay)
    
    def connect(self):
        """连接到MQTT Broker。"""
        if self.is_connected or not self.client:
            return

        # 检查是否应该延迟重连
        if self.connection_failures > 0:
            backoff_delay = self._calculate_backoff_delay()
            if backoff_delay > 0:
                now = time.ticks_ms()
                if time.ticks_diff(now, self.last_failure_time) < backoff_delay * 1000:
                    # 还在退避期内，跳过连接尝试
                    return

        self.logger.info("连接到代理服务器{}...", self.config['broker'], module="MQTT")
        try:
            self.client.connect()
            self.is_connected = True
            self.connection_failures = 0  # 重置失败计数
            self.logger.info("MQTT连接成功", module="MQTT")
            self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="connected", broker=self.config['broker'])
            for topic in self.config.get('subscribe_topics', []):
                self.subscribe(topic)
            self.last_ping_time = time.ticks_ms()

        except Exception as e:
            self.connection_failures += 1
            self.last_failure_time = time.ticks_ms()
            
            self.logger.error(f"连接失败: {e}", module="MQTT")
            self.is_connected = False
            
            # 频率限制断开事件的发布，避免事件风暴
            if not self._should_throttle_disconnect_event():
                self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="disconnected", reason=str(e), broker=self.config['broker'])
                self.last_disconnect_event_time = time.ticks_ms()
            else:
                # 静默处理，避免过多事件
                self.logger.debug("MQTT断开连接事件被限流", module="MQTT")

    def disconnect(self):
        """断开与MQTT Broker的连接。"""
        if self.is_connected and self.client:
            try:
                self.client.disconnect()
            except Exception as e:
                self.logger.error(f"断开连接失败: {e}", module="MQTT")
        self.is_connected = False
        self.logger.info("MQTT已断开连接", module="MQTT")

    def publish(self, topic, msg, retain=False, qos=0):
        """发布消息。"""
        if not self.is_connected or not self.client:
            self.logger.warning("无法发布，MQTT未连接。", module="MQTT")
            return

        try:
            # 在发布前，尝试使用对象池预先构造消息上下文（用于调试/日志），在 object_pool 不可用时安全退化
            pub_obj = self.object_pool.acquire("mqtt_messages") if getattr(self, "object_pool", None) else None
            if pub_obj:
                pub_obj["topic"] = topic
                pub_obj["payload"] = msg
                pub_obj["retain"] = retain
                pub_obj["qos"] = qos
                # 执行实际的MQTT发布
                self.client.publish(topic, msg, retain, qos)
                # 可选：记录发布信息用于调试
                if getattr(self, "logger", None) and getattr(self.logger, "_level", 99) <= 1:  # DEBUG级别
                    self.logger.debug(f"已发布到主题 '{topic}', retain={retain}, qos={qos}", module="MQTT")
                # 释放对象
                if getattr(self, "object_pool", None):
                    self.object_pool.release(pub_obj)
            else:
                # 对象池不可用或耗尽时直接发布
                self.client.publish(topic, msg, retain, qos)
                
        except Exception as e:
            self.logger.error(f"发布失败: {e}", module="MQTT")
            self.is_connected = False
            # 频率限制断开事件的发布
            if not self._should_throttle_disconnect_event():
                self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="disconnected", reason="发布错误", broker=self.config['broker'])
                self.last_disconnect_event_time = time.ticks_ms()

    def subscribe(self, topic, qos=0):
        """订阅主题。"""
        if not self.is_connected or not self.client:
            self.logger.warning("无法订阅，MQTT未连接。", module="MQTT")
            return
        
        try:
            self.logger.info("订阅主题: {}", topic, module="MQTT")
            self.client.subscribe(topic, qos)
        except Exception as e:
            self.logger.error(f"订阅失败: {e}", module="MQTT")
            self.is_connected = False
            # 频率限制断开事件的发布
            if not self._should_throttle_disconnect_event():
                self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="disconnected", reason="订阅错误", broker=self.config['broker'])
                self.last_disconnect_event_time = time.ticks_ms()

    def loop(self):
        """
        在主循环中定期调用。
        处理入站消息并维持连接。
        """
        if not self.client:
            return

        if self.is_connected:
            try:
                # 检查入站消息
                self.client.check_msg()
                
                # 发送 PING 以保持连接活跃
                keepalive_ms = self.config.get('keepalive', 60) * 1000
                if time.ticks_diff(time.ticks_ms(), self.last_ping_time) > keepalive_ms / 2:
                    self.client.ping()
                    self.last_ping_time = time.ticks_ms()

            except Exception as e:
                self.logger.error(f"循环错误: {e}. 连接丢失。", module="MQTT")
                self.is_connected = False
                # 频率限制断开事件的发布
                if not self._should_throttle_disconnect_event():
                    self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="disconnected", reason="循环错误", broker=self.config['broker'])
                    self.last_disconnect_event_time = time.ticks_ms()
        else:
            # 如果未连接，则不执行任何操作。FSM将决定何时重连。
            pass
