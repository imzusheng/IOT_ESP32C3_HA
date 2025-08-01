# -*- coding: utf-8 -*-
"""
统一配置管理模块

为ESP32C3设备提供集中式配置管理，所有配置参数都在此文件中定义。
每个配置项都有详细说明，包括作用、推荐取值和内存影响。

内存优化说明：
- 使用类常量而非全局变量，减少内存占用
- 避免使用JSON文件，减少I/O操作和内存使用
- 配置验证器在启动时运行，运行时不再验证
- 移除运行时配置管理，减少复杂度和内存使用
"""

import gc

# =============================================================================
# MQTT配置类
# =============================================================================

class MQTTConfig:
    """
    MQTT通信配置
    
    作用：配置MQTT服务器的连接参数和通信行为
    内存影响：低（约200字节）
    推荐配置：
    - BROKER: MQTT服务器IP地址
    - PORT: 标准MQTT端口1883，如需安全连接使用8883
    - TOPIC: 设备唯一标识符，建议格式：location/device_type
    - KEEPALIVE: 保持连接的心跳间隔，建议30-120秒
    """
    
    # 服务器配置
    BROKER = "192.168.3.15"         # MQTT服务器地址，必须为有效IP或域名
    PORT = 1883                     # MQTT端口，标准端口1883，安全端口8883
    TOPIC = "lzs/esp32c3"          # 设备主题，用于MQTT消息路由
    
    # 连接配置
    KEEPALIVE = 60                 # 心跳间隔（秒），建议30-120秒
    CONNECT_TIMEOUT = 10            # 连接超时（秒），建议5-30秒
    RECONNECT_DELAY = 5            # 重连延迟（秒），建议3-10秒
    MAX_RETRIES = 3                # 最大重试次数，建议3-5次

# =============================================================================
# WiFi配置类
# =============================================================================

class WiFiConfig:
    """
    WiFi网络配置
    
    作用：配置WiFi连接参数和网络选择策略
    内存影响：中等（约500字节，取决于网络数量）
    推荐配置：
    - TIMEOUT_S: 连接超时时间，建议10-30秒
    - SCAN_INTERVAL: 网络扫描间隔，建议30-60秒
    - NETWORKS: 按优先级排序的WiFi网络列表
    """
    
    # 连接参数
    TIMEOUT_S = 15                 # 连接超时（秒），建议10-30秒
    SCAN_INTERVAL = 30             # 网络扫描间隔（秒），建议30-60秒
    CONNECTION_RETRY_DELAY = 2      # 连接重试延迟（秒），建议2-5秒
    MAX_CONNECTION_ATTEMPTS = 3     # 最大连接尝试次数，建议3-5次
    
    # WiFi网络列表（按优先级排序）
    NETWORKS = [
        {"ssid": "zsm60p", "password": "25845600"},
        {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
        {"ssid": "leju_software", "password": "leju123456"}
    ]

# =============================================================================
# 守护进程配置类
# =============================================================================

class DaemonConfig:
    """
    守护进程配置
    
    作用：配置系统监控、LED控制、温度监控等守护进程参数
    内存影响：低（约300字节）
    推荐配置：
    - LED_PINS: ESP32C3可用GPIO引脚（0-19, 21-23, 26-33）
    - TEMP_THRESHOLD: 温度报警阈值，ESP32C3正常工作温度<85°C
    - MEMORY_THRESHOLD: 内存报警阈值，建议85-95%
    - MONITOR_INTERVAL: 监控间隔，建议30-60秒
    """
    
    # LED配置
    LED_PINS = [12, 13]            # LED引脚列表，必须是ESP32C3有效GPIO
    
    # 温度监控配置
    TEMP_THRESHOLD = 60.0          # 温度报警阈值（°C），ESP32C3最高85°C
    TEMP_HYSTERESIS = 10.0         # 温度滞回（°C），避免频繁报警
    
    # 内存监控配置
    MEMORY_THRESHOLD = 90          # 内存使用报警阈值（%），建议85-95%
    MEMORY_HYSTERESIS = 10         # 内存滞回（%），避免频繁报警
    
    # 看门狗配置
    WDT_TIMEOUT = 10000            # 看门狗超时（毫秒），增加到10秒提供更多安全裕度
    # WDT_FEED_INTERVAL 已移除，因为喂狗操作现在在主循环中执行
    
    # 定时器配置
    TIMER_ID = 0                   # 监控定时器编号（0-3）
    MONITOR_INTERVAL = 30000       # 监控间隔（毫秒），建议30-60秒
    
    # 安全模式配置
    SAFE_MODE_COOLDOWN = 30000     # 安全模式冷却时间（毫秒），建议30秒
    
    # 错误处理配置
    MAX_ERROR_COUNT = 5            # 最大错误计数，超过后进入安全模式
    ERROR_RESET_INTERVAL = 60000   # 错误重置间隔（毫秒），建议60秒
    ERROR_CLASSIFY_ENABLED = True  # 启用错误分类，增强错误处理
    
    # 垃圾回收配置
    GC_INTERVAL_NORMAL = 10000     # 正常模式垃圾回收间隔（毫秒），建议10秒
    GC_INTERVAL_SAFE = 5000        # 安全模式垃圾回收间隔（毫秒），建议5秒
    GC_FORCE_THRESHOLD = 95         # 强制垃圾回收阈值（%），建议95%

# =============================================================================
# 系统配置类
# =============================================================================

class SystemConfig:
    """
    系统配置
    
    作用：配置系统级参数，包括调试、性能、错误恢复等
    内存影响：低（约200字节）
    推荐配置：
    - DEBUG_MODE: 生产环境设为False，调试时设为True
    - LOG_LEVEL: 生产环境建议INFO，调试时DEBUG
    - MAIN_LOOP_DELAY: 主循环延迟，建议100-500毫秒
    - AUTO_RESTART_ENABLED: 生产环境建议启用
    """
    
    # NTP配置
    NTP_HOST = 'ntp.aliyun.com'     # NTP服务器地址
    TIMEZONE_OFFSET_H = 8          # 时区偏移（小时），中国为+8
    
    # 调试配置
    DEBUG_MODE = False             # 调试模式，生产环境建议False
    LOG_LEVEL = "INFO"             # 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
    
    # 性能配置
    MAIN_LOOP_DELAY = 300          # 主循环延迟（毫秒），建议100-500毫秒
    STATUS_REPORT_INTERVAL = 30    # 状态报告间隔（循环次数），建议30次
    
    # 错误恢复配置
    ERROR_RECOVERY_ENABLED = True  # 启用错误恢复，建议True
    AUTO_RESTART_ENABLED = False   # 启用自动重启，生产环境建议True
    HEALTH_CHECK_INTERVAL = 60000  # 健康检查间隔（毫秒），建议60秒
    MAX_RECOVERY_ATTEMPTS = 3      # 最大恢复尝试次数，建议3次
    RECOVERY_COOLDOWN = 30000      # 恢复冷却时间（毫秒），建议30秒
    CRITICAL_ERROR_THRESHOLD = 5   # 严重错误阈值，超过后重启，建议3-5次
    
    # 状态监控配置
    STATUS_MONITOR_INTERVAL = 30000     # 状态监控间隔（毫秒），建议30秒
    LOG_BUFFER_SIZE = 50                # 日志缓冲区大小，建议50-100条
    METRICS_HISTORY_SIZE = 100          # 指标历史大小，建议100-200条
    REMOTE_MONITORING_ENABLED = True    # 启用远程监控，根据需求设置
    DIAGNOSTIC_ENABLED = True           # 启用诊断功能，建议True

# =============================================================================
# 配置验证器
# =============================================================================

class ConfigValidator:
    """
    配置验证器
    
    作用：在系统启动时验证所有配置参数的有效性
    内存影响：低（验证完成后释放内存）
    使用方式：系统启动时自动调用，验证失败会输出错误信息
    """
    
    @staticmethod
    def validate_all():
        """验证所有配置，返回错误列表"""
        errors = []
        errors.extend(ConfigValidator._validate_mqtt())
        errors.extend(ConfigValidator._validate_wifi())
        errors.extend(ConfigValidator._validate_daemon())
        errors.extend(ConfigValidator._validate_system())
        return errors
    
    @staticmethod
    def _validate_mqtt():
        """验证MQTT配置"""
        errors = []
        
        if not MQTTConfig.BROKER or not isinstance(MQTTConfig.BROKER, str):
            errors.append("MQTT broker地址必须是非空字符串")
        
        if not isinstance(MQTTConfig.PORT, int) or not (1 <= MQTTConfig.PORT <= 65535):
            errors.append("MQTT端口必须是1-65535之间的整数")
        
        if not MQTTConfig.TOPIC or not isinstance(MQTTConfig.TOPIC, str):
            errors.append("MQTT主题必须是非空字符串")
        
        if not isinstance(MQTTConfig.KEEPALIVE, int) or MQTTConfig.KEEPALIVE < 10:
            errors.append("MQTT keepalive必须大于等于10秒")
        
        return errors
    
    @staticmethod
    def _validate_wifi():
        """验证WiFi配置"""
        errors = []
        
        if not isinstance(WiFiConfig.NETWORKS, list) or not WiFiConfig.NETWORKS:
            errors.append("WiFi网络配置必须是非空列表")
        
        for i, network in enumerate(WiFiConfig.NETWORKS):
            if not isinstance(network, dict):
                errors.append(f"WiFi网络{i+1}必须是字典")
                continue
            
            if not network.get('ssid') or not isinstance(network['ssid'], str):
                errors.append(f"WiFi网络{i+1}的SSID必须是非空字符串")
            
            if 'password' not in network or not isinstance(network['password'], str):
                errors.append(f"WiFi网络{i+1}必须有密码字段")
        
        if not isinstance(WiFiConfig.TIMEOUT_S, int) or WiFiConfig.TIMEOUT_S < 5:
            errors.append("WiFi超时时间必须大于等于5秒")
        
        return errors
    
    @staticmethod
    def _validate_daemon():
        """验证守护进程配置"""
        errors = []
        
        # 验证LED引脚
        if not isinstance(DaemonConfig.LED_PINS, list) or len(DaemonConfig.LED_PINS) != 2:
            errors.append("必须配置2个LED引脚")
        
        for pin in DaemonConfig.LED_PINS:
            if not isinstance(pin, int) or not (0 <= pin <= 39):
                errors.append(f"LED引脚{pin}必须是0-39之间的整数")
        
        # 验证温度配置
        if not isinstance(DaemonConfig.TEMP_THRESHOLD, (int, float)) or not (0 < DaemonConfig.TEMP_THRESHOLD < 100):
            errors.append("温度阈值必须在0-100之间")
        
        if not isinstance(DaemonConfig.TEMP_HYSTERESIS, (int, float)) or DaemonConfig.TEMP_HYSTERESIS < 0:
            errors.append("温度滞回必须大于等于0")
        
        # 验证内存配置
        if not isinstance(DaemonConfig.MEMORY_THRESHOLD, int) or not (50 <= DaemonConfig.MEMORY_THRESHOLD <= 98):
            errors.append("内存阈值必须在50-98之间")
        
        if not isinstance(DaemonConfig.MEMORY_HYSTERESIS, int) or DaemonConfig.MEMORY_HYSTERESIS < 0:
            errors.append("内存滞回必须大于等于0")
        
        # 验证看门狗配置
        if not isinstance(DaemonConfig.WDT_TIMEOUT, int) or not (1000 <= DaemonConfig.WDT_TIMEOUT <= 32000):
            errors.append("看门狗超时必须在1000-32000毫秒之间")
        
        # 验证定时器配置
        if not isinstance(DaemonConfig.TIMER_ID, int) or not (0 <= DaemonConfig.TIMER_ID <= 3):
            errors.append("定时器ID必须在0-3之间")
        
        if not isinstance(DaemonConfig.MONITOR_INTERVAL, int) or DaemonConfig.MONITOR_INTERVAL < 1000:
            errors.append("监控间隔必须大于等于1000毫秒")
        
        return errors
    
    @staticmethod
    def _validate_system():
        """验证系统配置"""
        errors = []
        
        if not isinstance(SystemConfig.TIMEZONE_OFFSET_H, int) or not (-12 <= SystemConfig.TIMEZONE_OFFSET_H <= 14):
            errors.append("时区偏移必须在-12到14之间")
        
        if not isinstance(SystemConfig.MAIN_LOOP_DELAY, int) or SystemConfig.MAIN_LOOP_DELAY < 10:
            errors.append("主循环延迟必须大于等于10毫秒")
        
        if not isinstance(SystemConfig.STATUS_REPORT_INTERVAL, int) or SystemConfig.STATUS_REPORT_INTERVAL < 1:
            errors.append("状态报告间隔必须大于等于1")
        
        return errors

# =============================================================================
# 配置管理器
# =============================================================================

class ConfigManager:
    """
    配置管理器
    
    作用：提供配置验证和打印功能
    内存影响：低（约100字节）
    """
    
    def __init__(self):
        self._validation_errors = []
        self._validated = False
    
    def validate(self):
        """验证配置，返回是否有效"""
        self._validation_errors = ConfigValidator.validate_all()
        self._validated = len(self._validation_errors) == 0
        return self._validated
    
    def get_validation_errors(self):
        """获取验证错误列表"""
        return self._validation_errors
    
    def is_valid(self):
        """检查配置是否有效"""
        return self._validated
    
    def print_config(self):
        """打印当前配置信息"""
        print("=== ESP32C3 配置信息 ===")
        
        print("\n--- MQTT配置 ---")
        print(f"服务器: {MQTTConfig.BROKER}:{MQTTConfig.PORT}")
        print(f"主题: {MQTTConfig.TOPIC}")
        print(f"心跳: {MQTTConfig.KEEPALIVE}秒")
        
        print("\n--- WiFi配置 ---")
        print(f"网络数量: {len(WiFiConfig.NETWORKS)}")
        print(f"连接超时: {WiFiConfig.TIMEOUT_S}秒")
        for i, net in enumerate(WiFiConfig.NETWORKS):
            print(f"  网络{i+1}: {net['ssid']}")
        
        print("\n--- 守护进程配置 ---")
        print(f"LED引脚: {DaemonConfig.LED_PINS}")
        print(f"温度阈值: {DaemonConfig.TEMP_THRESHOLD}°C")
        print(f"内存阈值: {DaemonConfig.MEMORY_THRESHOLD}%")
        print(f"监控间隔: {DaemonConfig.MONITOR_INTERVAL//1000}秒")
        
        print("\n--- 系统配置 ---")
        print(f"调试模式: {SystemConfig.DEBUG_MODE}")
        print(f"日志级别: {SystemConfig.LOG_LEVEL}")
        print(f"主循环延迟: {SystemConfig.MAIN_LOOP_DELAY}ms")
        
        if self._validation_errors:
            print(f"\n--- 配置错误 ({len(self._validation_errors)}个) ---")
            for error in self._validation_errors[:5]:  # 只显示前5个错误
                print(f"  ✗ {error}")
            if len(self._validation_errors) > 5:
                print(f"  ... 还有{len(self._validation_errors)-5}个错误")
        else:
            print("\n[✓] 配置验证通过")

# =============================================================================
# 全局配置管理器实例
# =============================================================================

# 创建全局配置管理器
_config_manager = ConfigManager()

# 模块加载时自动验证配置
_is_valid_config = _config_manager.validate()

def validate_config():
    """验证配置，返回是否有效"""
    return _config_manager.validate()

def get_config_errors():
    """获取配置验证错误"""
    return _config_manager.get_validation_errors()

def is_config_valid():
    """检查配置是否有效"""
    return _config_manager.is_valid()

def print_config():
    """打印配置信息"""
    _config_manager.print_config()

# =============================================================================
# 配置初始化输出
# =============================================================================

if _is_valid_config:
    print("[✓] 配置加载成功")
else:
    print(f"[✗] 配置验证失败 ({len(get_config_errors())}个错误)")
    if SystemConfig.DEBUG_MODE:
        print_config()

# 执行垃圾回收，释放配置验证使用的内存
gc.collect()
