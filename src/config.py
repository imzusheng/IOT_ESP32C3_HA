# -*- coding: utf-8 -*-
"""
统一配置管理模块

为ESP32C3设备提供集中式配置管理：
- MQTT配置
- WiFi配置  
- 守护进程配置
- 系统配置
- 配置验证和运行时管理
"""

import json
import time
import gc

# =============================================================================
# 核心配置常量
# =============================================================================

class MQTTConfig:
    """MQTT相关配置"""
    BROKER = "192.168.1.2"
    PORT = 1883
    TOPIC = "lzs/esp32c3"
    KEEPALIVE = 60
    CONNECT_TIMEOUT = 10
    RECONNECT_DELAY = 5
    MAX_RETRIES = 3

class WiFiConfig:
    """WiFi相关配置"""
    TIMEOUT_S = 15
    SCAN_INTERVAL = 30
    CONNECTION_RETRY_DELAY = 2
    MAX_CONNECTION_ATTEMPTS = 3
    
    # WiFi网络配置列表
    NETWORKS = [
        {"ssid": "zsm60p", "password": "25845600"},
        {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
        {"ssid": "leju_software", "password": "leju123456"}
    ]

class DaemonConfig:
    """守护进程配置"""
    # LED配置
    LED_PINS = [12, 13]
    
    # 温度监控配置
    TEMP_THRESHOLD = 60.0  # 温度阈值（摄氏度）
    TEMP_HYSTERESIS = 10.0  # 温度滞回（摄氏度）
    
    # 内存监控配置
    MEMORY_THRESHOLD = 90  # 内存使用阈值（百分比）
    MEMORY_HYSTERESIS = 10  # 内存滞回（百分比）
    
    # 看门狗配置
    WDT_TIMEOUT = 8000  # 看门狗超时时间（毫秒）
    WDT_FEED_INTERVAL = 4000  # 看门狗喂狗间隔（毫秒）
    
    # 定时器配置
    TIMER_ID = 0  # 监控定时器编号
    MONITOR_INTERVAL = 30000  # 监控间隔（毫秒）
    
    # 安全模式配置
    SAFE_MODE_COOLDOWN = 30000  # 安全模式冷却时间（毫秒）
    
    # 错误处理配置
    MAX_ERROR_COUNT = 5
    ERROR_RESET_INTERVAL = 60000
    ERROR_CLASSIFY_ENABLED = True
    
    # 垃圾回收配置
    GC_INTERVAL_NORMAL = 10000  # 正常情况垃圾回收间隔（毫秒）
    GC_INTERVAL_SAFE = 5000  # 安全模式垃圾回收间隔（毫秒）
    GC_FORCE_THRESHOLD = 95  # 强制垃圾回收阈值（百分比）

class SystemConfig:
    """系统配置"""
    # NTP配置
    NTP_HOST = 'ntp.aliyun.com'
    TIMEZONE_OFFSET_H = 8
    
    # 调试配置
    DEBUG_MODE = False
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    
    # 性能配置
    MAIN_LOOP_DELAY = 300  # 主循环延迟（毫秒）
    STATUS_REPORT_INTERVAL = 30  # 状态报告间隔（循环次数）

# =============================================================================
# 配置验证器
# =============================================================================

class ConfigValidator:
    """配置验证器"""
    
    @staticmethod
    def validate_all():
        """验证所有配置"""
        errors = []
        
        # 验证MQTT配置
        errors.extend(ConfigValidator._validate_mqtt())
        
        # 验证WiFi配置
        errors.extend(ConfigValidator._validate_wifi())
        
        # 验证守护进程配置
        errors.extend(ConfigValidator._validate_daemon())
        
        # 验证系统配置
        errors.extend(ConfigValidator._validate_system())
        
        return errors
    
    @staticmethod
    def _validate_mqtt():
        """验证MQTT配置"""
        errors = []
        
        if not MQTTConfig.BROKER:
            errors.append("MQTT broker地址不能为空")
        
        if not (1 <= MQTTConfig.PORT <= 65535):
            errors.append("MQTT端口必须在1-65535之间")
        
        if not MQTTConfig.TOPIC:
            errors.append("MQTT主题不能为空")
        
        if MQTTConfig.KEEPALIVE < 10:
            errors.append("MQTT keepalive必须大于等于10秒")
        
        return errors
    
    @staticmethod
    def _validate_wifi():
        """验证WiFi配置"""
        errors = []
        
        if not WiFiConfig.NETWORKS:
            errors.append("WiFi网络配置不能为空")
        
        for i, network in enumerate(WiFiConfig.NETWORKS):
            if not network.get('ssid'):
                errors.append(f"WiFi网络{i+1}的SSID不能为空")
            if 'password' not in network:
                errors.append(f"WiFi网络{i+1}的密码不能为空")
        
        if WiFiConfig.TIMEOUT_S < 5:
            errors.append("WiFi超时时间必须大于等于5秒")
        
        return errors
    
    @staticmethod
    def _validate_daemon():
        """验证守护进程配置"""
        errors = []
        
        # 验证LED引脚
        if len(DaemonConfig.LED_PINS) != 2:
            errors.append("必须配置2个LED引脚")
        
        for pin in DaemonConfig.LED_PINS:
            if not (0 <= pin <= 39):  # ESP32C3引脚范围
                errors.append(f"LED引脚{pin}超出有效范围")
        
        # 验证温度配置
        if not (0 < DaemonConfig.TEMP_THRESHOLD < 100):
            errors.append("温度阈值必须在0-100之间")
        
        if DaemonConfig.TEMP_HYSTERESIS < 0:
            errors.append("温度滞回必须大于等于0")
        
        # 验证内存配置
        if not (50 <= DaemonConfig.MEMORY_THRESHOLD <= 98):
            errors.append("内存阈值必须在50-98之间")
        
        if DaemonConfig.MEMORY_HYSTERESIS < 0:
            errors.append("内存滞回必须大于等于0")
        
        # 验证看门狗配置
        if not (1000 <= DaemonConfig.WDT_TIMEOUT <= 32000):
            errors.append("看门狗超时必须在1000-32000毫秒之间")
        
        if DaemonConfig.WDT_FEED_INTERVAL >= DaemonConfig.WDT_TIMEOUT:
            errors.append("看门狗喂狗间隔必须小于超时时间")
        
        # 验证定时器配置
        if not (0 <= DaemonConfig.TIMER_ID <= 3):
            errors.append("定时器ID必须在0-3之间")
        
        if DaemonConfig.MONITOR_INTERVAL < 1000:
            errors.append("监控间隔必须大于等于1000毫秒")
        
        # 验证安全模式配置
        if DaemonConfig.SAFE_MODE_COOLDOWN < 10000:
            errors.append("安全模式冷却时间必须大于等于10秒")
        
        # 验证错误处理配置
        if DaemonConfig.MAX_ERROR_COUNT < 1:
            errors.append("最大错误计数必须大于等于1")
        
        if DaemonConfig.ERROR_RESET_INTERVAL < 10000:
            errors.append("错误重置间隔必须大于等于10秒")
        
        # 验证垃圾回收配置
        if DaemonConfig.GC_INTERVAL_NORMAL < 1000:
            errors.append("正常垃圾回收间隔必须大于等于1秒")
        
        if DaemonConfig.GC_FORCE_THRESHOLD < 80:
            errors.append("强制垃圾回收阈值必须大于等于80%")
        
        return errors
    
    @staticmethod
    def _validate_system():
        """验证系统配置"""
        errors = []
        
        if SystemConfig.TIMEZONE_OFFSET_H < -12 or SystemConfig.TIMEZONE_OFFSET_H > 14:
            errors.append("时区偏移必须在-12到14之间")
        
        if SystemConfig.MAIN_LOOP_DELAY < 10:
            errors.append("主循环延迟必须大于等于10毫秒")
        
        if SystemConfig.STATUS_REPORT_INTERVAL < 1:
            errors.append("状态报告间隔必须大于等于1")
        
        return errors

# =============================================================================
# 运行时配置管理器
# =============================================================================

class RuntimeConfig:
    """运行时配置管理器"""
    
    def __init__(self):
        self._config = {}
        self._last_modified = 0
        self._load_config()
    
    def _load_config(self):
        """从文件加载配置"""
        try:
            with open('config.json', 'r') as f:
                self._config = json.load(f)
            self._last_modified = time.time()
        except:
            # 如果文件不存在或读取失败，使用默认配置
            self._config = self._get_default_config()
    
    def _get_default_config(self):
        """获取默认配置"""
        return {
            'mqtt': {
                'broker': MQTTConfig.BROKER,
                'port': MQTTConfig.PORT,
                'topic': MQTTConfig.TOPIC,
                'keepalive': MQTTConfig.KEEPALIVE
            },
            'daemon': {
                'temp_threshold': DaemonConfig.TEMP_THRESHOLD,
                'memory_threshold': DaemonConfig.MEMORY_THRESHOLD,
                'monitor_interval': DaemonConfig.MONITOR_INTERVAL
            },
            'system': {
                'debug_mode': SystemConfig.DEBUG_MODE,
                'log_level': SystemConfig.LOG_LEVEL
            }
        }
    
    def get(self, key: str, default=None):
        """获取配置值"""
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value):
        """设置配置值"""
        keys = key.split('.')
        config = self._config
        
        # 导航到目标位置
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        # 设置值
        config[keys[-1]] = value
        self._last_modified = time.time()
        
        # 保存到文件
        self._save_config()
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            with open('config.json', 'w') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get_modified_time(self):
        """获取最后修改时间"""
        return self._last_modified
    
    def reload(self):
        """重新加载配置"""
        self._load_config()

# =============================================================================
# 配置管理器主类
# =============================================================================

class ConfigManager:
    """配置管理器主类"""
    
    def __init__(self):
        self.runtime_config = RuntimeConfig()
        self._validated = False
        self._validation_errors = []
    
    def validate(self):
        """验证所有配置"""
        self._validation_errors = ConfigValidator.validate_all()
        self._validated = len(self._validation_errors) == 0
        return self._validated
    
    def get_validation_errors(self):
        """获取验证错误"""
        return self._validation_errors
    
    def is_valid(self):
        """检查配置是否有效"""
        return self._validated
    
    def get_runtime_config(self):
        """获取运行时配置管理器"""
        return self.runtime_config
    
    def print_config(self):
        """打印当前配置"""
        print("=== 当前配置 ===")
        
        print("\n--- MQTT配置 ---")
        print(f"Broker: {MQTTConfig.BROKER}")
        print(f"Port: {MQTTConfig.PORT}")
        print(f"Topic: {MQTTConfig.TOPIC}")
        print(f"Keepalive: {MQTTConfig.KEEPALIVE}")
        
        print("\n--- WiFi配置 ---")
        print(f"Timeout: {WiFiConfig.TIMEOUT_S}s")
        print(f"Networks: {len(WiFiConfig.NETWORKS)}个")
        
        print("\n--- 守护进程配置 ---")
        print(f"LED Pins: {DaemonConfig.LED_PINS}")
        print(f"Temp Threshold: {DaemonConfig.TEMP_THRESHOLD}°C")
        print(f"Memory Threshold: {DaemonConfig.MEMORY_THRESHOLD}%")
        print(f"WDT Timeout: {DaemonConfig.WDT_TIMEOUT}ms")
        print(f"Monitor Interval: {DaemonConfig.MONITOR_INTERVAL}ms")
        
        print("\n--- 系统配置 ---")
        print(f"Debug Mode: {SystemConfig.DEBUG_MODE}")
        print(f"Log Level: {SystemConfig.LOG_LEVEL}")
        print(f"Main Loop Delay: {SystemConfig.MAIN_LOOP_DELAY}ms")
        
        if self._validation_errors:
            print(f"\n--- 配置验证错误 ---")
            for error in self._validation_errors:
                print(f"❌ {error}")
        else:
            print(f"\n✅ 配置验证通过")

# =============================================================================
# 全局配置管理器实例
# =============================================================================

# 创建全局配置管理器实例
_config_manager = ConfigManager()

def get_config_manager():
    """获取全局配置管理器实例"""
    return _config_manager

def validate_config():
    """验证配置"""
    return _config_manager.validate()

def get_config(key: str, default=None):
    """获取配置值"""
    return _config_manager.runtime_config.get(key, default)

def set_config(key: str, value):
    """设置配置值"""
    _config_manager.runtime_config.set(key, value)

def print_current_config():
    """打印当前配置"""
    _config_manager.print_config()

# =============================================================================
# 初始化验证
# =============================================================================

# 模块加载时自动验证配置
if not validate_config():
    print("⚠️  配置验证失败，请检查配置")
    print_current_config()
else:
    print("✅ 配置验证通过")

# 执行垃圾回收
gc.collect()