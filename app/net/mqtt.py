# app/net/mqtt.py
from lib.lock.umqtt import MQTTClient
import utime as time
import machine
from lib.logger import get_global_logger
from event_const import EVENT

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
            self.logger.error(f"Error creating MQTT client: {e}", module="MQTT")
            self.event_bus.publish(EVENT.LOG_ERROR, "MQTT client setup failed: {}", e, module="MQTT")

    def _mqtt_callback(self, topic, msg):
        """
        MQTT消息回调函数。
        当收到消息时，发布一个事件。
        """
        try:
            topic_str = topic.decode('utf-8')
            msg_str = msg.decode('utf-8')
            self.logger.info("Message received: topic='{}', msg='{}'", topic_str, msg_str, module="MQTT")
            
            # 按照事件契约发布 (topic, msg)，避免改变订阅方签名
            self.event_bus.publish(EVENT.MQTT_MESSAGE, topic_str, msg_str)
            
        except Exception as e:
            self.event_bus.publish(EVENT.LOG_ERROR, "Error processing MQTT message: {}", e, module="MQTT")

    def connect(self):
        """连接到MQTT Broker。"""
        if self.is_connected or not self.client:
            return

        self.logger.info("Connecting to broker at {}...", self.config['broker'], module="MQTT")
        try:
            self.client.connect()
            self.is_connected = True
            self.logger.info("MQTT connected successfully", module="MQTT")
            self.event_bus.publish(EVENT.MQTT_CONNECTED)
            for topic in self.config.get('subscribe_topics', []):
                self.subscribe(topic)
            self.last_ping_time = time.ticks_ms()

        except Exception as e:
            self.logger.error(f"Error connecting: {e}", module="MQTT")
            self.event_bus.publish(EVENT.LOG_ERROR, "MQTT connect failed: {}", e, module="MQTT")
            self.is_connected = False
            self.event_bus.publish(EVENT.MQTT_DISCONNECTED, str(e))

    def disconnect(self):
        """断开与MQTT Broker的连接。"""
        if self.is_connected and self.client:
            try:
                self.client.disconnect()
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}", module="MQTT")
                self.event_bus.publish(EVENT.LOG_WARN, "MQTT disconnect error: {}", e, module="MQTT")
        self.is_connected = False
        self.logger.info("MQTT disconnected", module="MQTT")

    def publish(self, topic, msg, retain=False, qos=0):
        """发布消息。"""
        if not self.is_connected or not self.client:
            self.event_bus.publish(EVENT.LOG_WARN, "Cannot publish, MQTT not connected.", module="MQTT")
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
                    self.logger.debug(f"Published to topic '{topic}', retain={retain}, qos={qos}", module="MQTT")
                # 释放对象
                if getattr(self, "object_pool", None):
                    self.object_pool.release(pub_obj)
            else:
                # 对象池不可用或耗尽时直接发布
                self.client.publish(topic, msg, retain, qos)
                
        except Exception as e:
            self.logger.error(f"Publish error: {e}", module="MQTT")
            self.event_bus.publish(EVENT.LOG_ERROR, "MQTT publish error: {}", e, module="MQTT")
            self.is_connected = False
            self.event_bus.publish(EVENT.MQTT_DISCONNECTED, "PUBLISH_ERROR")

    def subscribe(self, topic, qos=0):
        """订阅主题。"""
        if not self.is_connected or not self.client:
            self.event_bus.publish(EVENT.LOG_WARN, "Cannot subscribe, MQTT not connected.", module="MQTT")
            return
        
        try:
            self.logger.info("Subscribing topic: {}", topic, module="MQTT")
            self.client.subscribe(topic, qos)
        except Exception as e:
            self.logger.error(f"Subscribe error: {e}", module="MQTT")
            self.event_bus.publish(EVENT.LOG_ERROR, "MQTT subscribe error: {}", e, module="MQTT")
            self.is_connected = False
            self.event_bus.publish(EVENT.MQTT_DISCONNECTED, "SUBSCRIBE_ERROR")

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
                self.logger.error(f"Loop error: {e}. Connection lost.", module="MQTT")
                self.event_bus.publish(EVENT.LOG_WARN, "MQTT loop error: {}", e, module="MQTT")
                self.is_connected = False
                self.event_bus.publish(EVENT.MQTT_DISCONNECTED, "LOOP_ERROR")
        else:
            # 如果未连接，则不执行任何操作。FSM将决定何时重连。
            pass
