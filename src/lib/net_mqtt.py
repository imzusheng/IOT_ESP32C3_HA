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

# 全局MQTT配置变量
_mqtt_config = {
    'reconnect_delay': 5,
    'max_retries': 3
}

def set_mqtt_config(config_dict=None, **kwargs):
    """设置MQTT配置"""
    global _mqtt_config
    if config_dict:
        _mqtt_config.update(config_dict)
    _mqtt_config.update(kwargs)
    print("[MQTT] MQTT配置已更新")

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
            'reconnect_delay': mqtt_subconfig.get('reconnect_delay', 5),
            'max_retries': mqtt_subconfig.get('max_retries', 3)
        })
        
        print("[MQTT] 从主配置文件加载MQTT配置完成")
        return True
        
    except Exception as e:
        print(f"[MQTT] 从主配置文件加载MQTT配置失败: {e}")
        return False

class MqttServer:
    """
    MQTT服务器客户端
    
    特性：
    - 自动重连机制
    - 内存优化的日志发送
    - 连接状态监控
    - 错误恢复机制
    """
    
    def __init__(self, client_id, server, port=1883, user=None, password=None, topic='micropython/logs', keepalive=60):
        """
        初始化MQTT客户端
        
        参数：
        - client_id: 客户端唯一标识
        - server: MQTT服务器地址
        - port: 端口号，默认1883
        - user: 用户名（可选）
        - password: 密码（可选）
        - topic: 发布主题，默认'micropython/logs'
        - keepalive: 心跳间隔，默认60秒
        """
        self.server = server
        self.port = port
        self.topic = topic
        self.user = user
        self.password = password
        self.client_id = client_id
        
        # 创建MQTT客户端
        self.client = MQTTClient(client_id, server, port, user, password, keepalive=keepalive)
        self.is_connected = False
        self.connection_attempts = 0
        self.last_connect_time = 0
        
        print(f"[MQTT] MQTT客户端创建完成，服务器: {server}:{port}, 主题: '{topic}'")

    def connect(self):
        """
        连接到MQTT代理
        
        返回：
        - True: 连接成功
        - False: 连接失败
        """
        if self.is_connected:
            return True
            
        # 检查重连间隔
        current_time = time.time()
        if (current_time - self.last_connect_time < _mqtt_config['reconnect_delay'] and 
            self.connection_attempts > 0):
            return False
            
        try:
            self.client.connect()
            self.is_connected = True
            self.connection_attempts = 0
            self.last_connect_time = current_time
            print("\033[1;32m[MQTT] MQTT连接成功\033[0m")
            self.log("INFO", f"设备在线，ID: {self.client_id}")
            return True
            
        except Exception as e:
            self.connection_attempts += 1
            self.last_connect_time = current_time
            print(f"\033[1;31m[MQTT] 连接失败 (尝试 {self.connection_attempts}/{_mqtt_config['max_retries']}): {e}\033[0m")
            self.is_connected = False
            
            # 如果超过最大重试次数，执行垃圾回收
            if self.connection_attempts >= _mqtt_config['max_retries']:
                gc.collect()
                self.connection_attempts = 0
                
            return False

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
            print(f"\033[1;31m[MQTT] 发送日志失败: {e}\033[0m")
            # 连接失败时清理状态
            self._cleanup_connection()
            gc.collect()

    def disconnect(self):
        """断开MQTT连接"""
        if self.is_connected:
            try:
                self.client.disconnect()
                self.is_connected = False
                print("\033[1;33m[MQTT] MQTT连接已断开\033[0m")
            except Exception as e:
                print(f"\033[1;31m[MQTT] 断开连接失败: {e}\033[0m")

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
                print(f"\033[1;31m[MQTT] 连接丢失: {e}\033[0m")
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
        """获取连接状态信息"""
        return {
            'connected': self.is_connected,
            'server': self.server,
            'port': self.port,
            'topic': self.topic,
            'attempts': self.connection_attempts,
            'client_id': self.client_id
        }