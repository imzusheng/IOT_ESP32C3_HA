# app/net/mqtt.py
# 简化版MQTT控制器, 只提供基本的MQTT操作功能
from lib.lock.umqtt import MQTTClient
import machine
import utime as time
from lib.logger import error, warning, debug
from lib.lock.event_bus import EventBus, EVENTS

class MqttController:
    """
    MQTT控制器
    
    只提供基本的MQTT操作功能:
    - 连接/断开连接
    - 发布/订阅消息
    - 基本的连接状态检查
    """
    
    def __init__(self, config=None, event_bus=None):
        """
        初始化MQTT控制器
        :param config: MQTT配置字典
        :param event_bus: 事件总线实例
        """
        self.config = config or {}
        self.client = None
        self._is_connected = False
        self.event_bus = event_bus

        # 根据配置初始化MQTT客户端
        try:
            # 检查必需的配置项
            if not self.config.get('broker'):
                warning("MQTT配置缺少broker地址, MQTT功能将不可用", module="MQTT")
                return
                
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
            debug(f"创建MQTT客户端失败: {e}", module="MQTT")

    def _mqtt_callback(self, topic, msg):
        """MQTT消息回调函数"""
        try:
            topic_str = topic.decode('utf-8')
            msg_str = msg.decode('utf-8')
            debug(f"收到MQTT消息: 主题={topic_str}, 消息={msg_str}", module="MQTT")

            # 只有在event_bus存在时才发布事件
            if self.event_bus:
                self.event_bus.publish(EVENTS['MQTT_MESSAGE'], {
                    'topic': topic_str,
                    'message': msg_str,
                    'timestamp': time.ticks_ms()
                })
        except Exception as e:
            debug("处理MQTT消息失败: {}", e, module="MQTT")
    
    def connect(self):
        """
        连接到MQTT Broker
        
        Returns:
            bool: 连接成功返回True, 失败返回False
        """
        if self._is_connected:
            return True
            
        if not self.client:
            warning("MQTT客户端未初始化或配置不完整", module="MQTT")
            return False

        try:
            debug("尝试连接MQTT服务器: {}:{}", self.config['broker'], self.config.get('port', 1883), module="MQTT")
            self.client.connect()
            
            # 验证连接是否建立
            if hasattr(self.client, 'is_connected') and self.client.is_connected():
                self._is_connected = True
                debug("MQTT连接成功", module="MQTT")
                return True
            else:
                # 对于某些MQTT库,连接成功后没有is_connected方法
                # 尝试发送ping来验证连接
                try:
                    self.client.ping()
                    self._is_connected = True
                    debug("MQTT连接成功 (通过ping验证)", module="MQTT")
                    return True
                except:
                    self._is_connected = False
                    warning("MQTT连接状态验证失败", module="MQTT")
                    return False
            
        except OSError as e:
            # 只记录debug级别的日志，让上层决定是否记录错误
            if e.errno == 113:  # ECONNABORTED
                debug("MQTT连接被拒绝: 服务器{}:{}不可达或拒绝连接", 
                     self.config['broker'], self.config.get('port', 1883), module="MQTT")
            elif e.errno == 110:  # ETIMEDOUT
                debug("MQTT连接超时: 服务器{}:{}无响应", 
                     self.config['broker'], self.config.get('port', 1883), module="MQTT")
            else:
                debug("MQTT连接网络错误 [{}]: {}", e.errno, e, module="MQTT")
            self._is_connected = False
            return False
        except Exception as e:
            debug("MQTT连接异常: {}", e, module="MQTT")
            self._is_connected = False
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
                debug("MQTT断开失败: {}", e, module="MQTT")
                return False
        
        self._is_connected = False
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
            debug("MQTT发布失败: {}", e, module="MQTT")
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
            warning("MQTT未连接, 无法订阅主题", module="MQTT")
            return False
        
        try:
            self.client.subscribe(topic, qos)
            return True
        except Exception as e:
            debug("MQTT订阅失败: {}", e, module="MQTT")
            return False

    def check_msg(self):
        """检查是否有新消息"""
        if self._is_connected and self.client:
            try:
                self.client.check_msg()
            except Exception as e:
                debug("检查MQTT消息失败: {}", e, module="MQTT")
