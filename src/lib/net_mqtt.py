# -*- coding: utf-8 -*-
"""
MQTT客户端模块

提供高效的MQTT通信功能，支持自动重连、内存优化和错误恢复。
使用集中配置管理，确保与系统其他模块的一致性。
"""
import sys

# 添加路径到系统路径，以便导入config模块和umqtt库
# MicroPython兼容的路径处理
current_dir = __file__.rpartition('/')[0] if '/' in __file__ else ''
if current_dir:
    sys.path.append(current_dir + '/umqtt')
else:
    sys.path.append('./umqtt')

from umqtt.simple import MQTTClient
import time
import gc
import config

# --- 新增代码：全局实例管理 ---
_global_mqtt_instance = None

def init_client(client_id, server, port=None, user=None, password=None, topic=None, keepalive=None):
    """
    初始化并注册全局唯一的MQTT客户端实例。
    这个函数应该在 main.py 中被调用一次。
    """
    global _global_mqtt_instance
    if _global_mqtt_instance is None:
        # 使用 MqttServer 类创建实例
        _global_mqtt_instance = MqttServer(
            client_id, server, port, user, password, topic, keepalive
        )
        print("[MQTT Service] Global MQTT client instance created.")
    else:
        print("[MQTT Service] Global MQTT client instance already exists.")
    return _global_mqtt_instance

def get_client():
    """
    获取全局的MQTT客户端实例。
    任何需要MQTT的模块都应该调用此函数。
    """
    if _global_mqtt_instance is None:
        # 理论上不应该发生，因为main会先调用init_client
        raise RuntimeError("MQTT client has not been initialized. Call init_client() first.")
    return _global_mqtt_instance

def is_ready():
    """检查客户端是否已初始化"""
    return _global_mqtt_instance is not None
# --- 新增代码结束 ---


# MQTT配置从config.py中获取

# 全局MQTT配置变量
_mqtt_config = {
    'reconnect_delay': config.get_config('mqtt', 'reconnect_delay', 5),
    'max_retries': config.get_config('mqtt', 'max_retries', 3),
    'exponential_backoff': config.get_config('mqtt', 'exponential_backoff', True),
    'max_backoff_time': config.get_config('mqtt', 'max_backoff_time', 300),
    'backoff_multiplier': config.get_config('mqtt', 'backoff_multiplier', 2)
}

def set_mqtt_config(config_dict=None, **kwargs):
    """设置MQTT配置"""
    global _mqtt_config
    if config_dict:
        _mqtt_config.update(config_dict)
    _mqtt_config.update(kwargs)
    print("[MQTT] MQTT configuration updated")

def load_mqtt_config_from_main(config_data):
    """从主配置文件加载MQTT配置"""
    global _mqtt_config
    
    try:
        # 获取MQTT配置部分
        mqtt_config = config_data.get('mqtt', {})
        
        # 获取MQTT配置中的config部分
        mqtt_subconfig = mqtt_config.get('config', {})
        
        # 更新全局配置
        _mqtt_config.update({
            'reconnect_delay': mqtt_subconfig.get('reconnect_delay', config.get_config('mqtt', 'reconnect_delay', 5)),
            'max_retries': mqtt_subconfig.get('max_retries', config.get_config('mqtt', 'max_retries', 3)),
            'exponential_backoff': mqtt_subconfig.get('exponential_backoff', config.get_config('mqtt', 'exponential_backoff', True)),
            'max_backoff_time': mqtt_subconfig.get('max_backoff_time', config.get_config('mqtt', 'max_backoff_time', 300)),
            'backoff_multiplier': mqtt_subconfig.get('backoff_multiplier', config.get_config('mqtt', 'backoff_multiplier', 2))
        })
        
        print("[MQTT] MQTT configuration loaded from main config file")
        return True
        
    except Exception as e:
        print(f"[MQTT] Failed to load MQTT configuration from main config: {e}")
        return False

class MqttServer:
    """
    MQTT服务器客户端
    
    特性：
    - 智能指数退避重连机制
    - 内存优化的日志发送
    - 连接状态监控
    - 错误恢复机制
    - 重连冷却时间管理
    - 自动重置计数器
    
    重连策略：
    - 第1轮：立即重试3次
    - 第2轮：等待5秒后重试3次
    - 第3轮：等待10秒后重试3次
    - 第4轮：等待20秒后重试3次
    - 第5轮：等待40秒后重试3次
    - 第6轮：等待80秒后重试3次
    - 第7轮：等待160秒后重试3次
    - 第8轮及以后：等待300秒（最大值）后重试3次
    """
    
    def __init__(self, client_id, server, port=None, user=None, password=None, topic=None, keepalive=None):
        """
        初始化MQTT客户端
        
        参数：
        - client_id: 客户端唯一标识
        - server: MQTT服务器地址（从config.py获取）
        - port: 端口号（从config.py获取）
        - user: 用户名（可选）
        - password: 密码（可选）
        - topic: 发布主题（从config.py获取）
        - keepalive: 心跳间隔（从config.py获取）
        """
        self.server = server
        self.port = port if port is not None else config.get_config('mqtt', 'port', 1883)
        self.topic = topic if topic is not None else config.get_config('mqtt', 'topic', 'lzs/esp32c3')
        self.user = user
        self.password = password
        self.client_id = client_id
        
        # 创建MQTT客户端
        self.client = MQTTClient(client_id, server, self.port, user, password, keepalive=keepalive if keepalive is not None else config.get_config('mqtt', 'keepalive', 60))
        self.is_connected = False
        self.connection_attempts = 0          # 当前重连周期内的重试次数
        self.last_connect_time = 0            # 上次连接尝试时间
        self.backoff_time = 0                 # 当前退避等待时间
        self.total_retry_cycles = 0           # 总重连周期数
        
        print(f"[MQTT] MQTT client created, server: {server}:{port}, topic: '{topic}'")

    def connect(self):
        """
        连接到MQTT代理 - 支持指数退避策略
        
        指数退避策略：
        1. 立即重试3次
        2. 如果都失败，启动指数退避：5s → 10s → 20s → 40s → 80s → 160s → 300s(max)
        3. 每个退避周期内重试3次
        4. 连接成功后重置所有计数器
        
        返回：
        - True: 连接成功
        - False: 连接失败（可能在退避期）
        """
        if self.is_connected:
            return True
            
        current_time = time.time()
        
        # 检查退避时间（如果在退避期内，则跳过本次连接尝试）
        if self.backoff_time > 0 and current_time - self.last_connect_time < self.backoff_time:
            return False
            
        try:
            self.client.connect()
            self.is_connected = True
            self.reset_backoff()
            self.last_connect_time = current_time
            self.log("INFO", f"设备在线，ID: {self.client_id}")
            return True
            
        except Exception as e:
            self.connection_attempts += 1
            self.last_connect_time = current_time
            print(f"\033[1;31m[MQTT] Connection failed (attempt {self.connection_attempts}/{_mqtt_config['max_retries']}): {e}\033[0m")
            self.is_connected = False
            
            # 如果超过最大重试次数，启动指数退避
            if self.connection_attempts >= _mqtt_config['max_retries']:
                self._start_exponential_backoff()
                
            return False
    
    def _start_exponential_backoff(self):
        """
        启动指数退避策略
        
        计算逻辑：
        - base_delay * (multiplier ^ (cycle - 1))
        - 限制最大退避时间避免过长等待
        - 执行垃圾回收释放内存
        """
        self.total_retry_cycles += 1
        
        if _mqtt_config['exponential_backoff']:
            # 计算指数退避时间: base_delay * (multiplier ^ (cycle - 1))
            base_delay = _mqtt_config['reconnect_delay']
            multiplier = _mqtt_config['backoff_multiplier']
            max_delay = _mqtt_config['max_backoff_time']
            
            # 计算退避时间
            backoff = base_delay * (multiplier ** (self.total_retry_cycles - 1))
            # 限制最大退避时间
            self.backoff_time = min(backoff, max_delay)
            
            print(f"\033[1;33m[MQTT] Starting exponential backoff: waiting {self.backoff_time}s (cycle {self.total_retry_cycles})\033[0m")
        else:
            # 固定延迟模式
            self.backoff_time = _mqtt_config['reconnect_delay']
            print(f"\033[1;33m[MQTT] Starting fixed delay: waiting {self.backoff_time}s (cycle {self.total_retry_cycles})\033[0m")
        
        # 重置当前重试计数
        self.connection_attempts = 0
        
        # 执行垃圾回收
        gc.collect()
    
    def reset_backoff(self):
        """
        重置退避计数器（连接成功后调用）
        
        重置内容：
        - 总重连周期数
        - 当前退避等待时间
        - 当前重连周期内的重试次数
        """
        self.total_retry_cycles = 0
        self.backoff_time = 0
        self.connection_attempts = 0

    def log(self, level, message):
        """
        格式化并发送日志消息 - 优化内存使用
        
        参数：
        - level: 日志级别 (INFO, WARNING, ERROR, DEBUG)
        - message: 日志消息内容
        """
        if not self.is_connected:
            return
            
        try:
            # 计算时间戳 - 使用更简洁的格式
            t = time.localtime(time.time())
            
            # 使用预分配的字符串格式，减少字符串创建
            # 使用更紧凑的时间格式以节省内存
            time_str = f"{t[0]}{t[1]:02d}{t[2]:02d}{t[3]:02d}{t[4]:02d}{t[5]:02d}"
            
            # 使用bytearray进行内存优化的字符串拼接
            log_ba = bytearray()
            log_ba.extend(f"[{level}]".encode())
            log_ba.extend(f"[{time_str}]".encode())
            log_ba.extend(f"{message}".encode())
            
            # 发布消息
            self.client.publish(self.topic, log_ba)
            
        except Exception as e:
            print(f"\033[1;31m[MQTT] Failed to send log: {e}\033[0m")
            # 连接失败时清理状态
            self._cleanup_connection()
            gc.collect()

    def disconnect(self):
        """断开MQTT连接"""
        if self.is_connected:
            try:
                self.client.disconnect()
                self.is_connected = False
                print("\033[1;33m[MQTT] MQTT connection disconnected\033[0m")
            except Exception as e:
                print(f"\033[1;31m[MQTT] Disconnection failed: {e}\033[0m")

    def check_connection(self):
        """
        检查MQTT连接状态和心跳
        
        返回：
        - True: 连接正常
        - False: 连接异常
        """
        try:
            self.client.check_msg()
            return True
        except Exception as e:
            if self.is_connected:
                print(f"\033[1;31m[MQTT] Connection lost: {e}\033[0m")
            self.is_connected = False
            return False
    
    def _cleanup_connection(self):
        """清理连接状态"""
        self.is_connected = False
        try:
            self.client.disconnect()
        except:
            pass
            
    def get_connection_status(self):
        """
        获取连接状态信息
        
        返回字典包含：
        - connected: 是否已连接
        - server: 服务器地址
        - port: 端口号
        - topic: 主题
        - attempts: 当前重试次数
        - client_id: 客户端ID
        - backoff_time: 当前退避时间
        - total_retry_cycles: 总重连周期数
        """
        return {
            'connected': self.is_connected,
            'server': self.server,
            'port': self.port,
            'topic': self.topic,
            'attempts': self.connection_attempts,
            'client_id': self.client_id,
            'backoff_time': self.backoff_time,
            'total_retry_cycles': self.total_retry_cycles
        }