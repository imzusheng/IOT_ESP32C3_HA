# app/net/modules/config_manager.py
"""配置管理模块"""

from lib.logger import debug, info, warning, error

class ConfigManager:
    """配置管理器 - 负责网络相关配置的默认值设置和管理"""
    
    def __init__(self, config=None):
        """
        初始化配置管理器
        :param config: 外部配置字典
        """
        self.config = config or {}
        self._setup_default_config()
    
    def _setup_default_config(self):
        """设置默认配置"""
        # WiFi配置默认值
        if 'wifi' not in self.config:
            self.config['wifi'] = {}
        
        wifi_config = self.config['wifi']
        if 'networks' not in wifi_config or not wifi_config['networks']:
            wifi_config['networks'] = [
                {"ssid": "zsm60p", "password": "25845600"},
                {"ssid": "leju_software", "password": "leju123456"},
                {"ssid": "CMCC-pdRG", "password": "7k77ed5p"}
            ]
            
        # MQTT配置默认值
        if 'mqtt' not in self.config:
            self.config['mqtt'] = {}
            
        mqtt_config = self.config['mqtt']
        mqtt_config.setdefault('broker', '192.168.3.15')
        mqtt_config.setdefault('port', 1883)
        mqtt_config.setdefault('user', '')
        mqtt_config.setdefault('password', '')
        mqtt_config.setdefault('keepalive', 60)
        
        # NTP配置默认值
        if 'ntp' not in self.config:
            self.config['ntp'] = {}
            
        ntp_config = self.config['ntp']
        ntp_config.setdefault('ntp_server', 'ntp1.aliyun.com')
        ntp_config.setdefault('ntp_max_attempts', 3)
        ntp_config.setdefault('ntp_retry_interval', 2)
        
        # 连接配置默认值
        if 'connection' not in self.config:
            self.config['connection'] = {}
            
        conn_config = self.config['connection']
        conn_config.setdefault('max_retries', 3)
        conn_config.setdefault('base_retry_delay', 1000)
        conn_config.setdefault('connection_timeout', 20000)
    
    def get_config(self):
        """获取完整配置"""
        return self.config
    
    def get_wifi_config(self):
        """获取WiFi配置"""
        return self.config.get('wifi', {})
    
    def get_mqtt_config(self):
        """获取MQTT配置"""
        return self.config.get('mqtt', {})
    
    def get_ntp_config(self):
        """获取NTP配置"""
        return self.config.get('ntp', {})
    
    def get_connection_config(self):
        """获取连接配置"""
        return self.config.get('connection', {})