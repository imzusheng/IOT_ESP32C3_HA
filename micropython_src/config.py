# config.py
"""
系统配置管理模块

这个模块集中管理整个IoT系统的所有配置参数，包括：
- WiFi网络配置
- 硬件引脚配置
- 系统监控参数
- 定时器和间隔配置
- 安全和保护机制配置

通过集中配置管理，可以：
1. 避免硬编码配置散布在各个模块中
2. 方便统一修改和维护配置
3. 提高代码的可维护性和可扩展性
4. 支持不同环境的配置切换
"""

# =============================================================================
# WiFi 网络配置
# =============================================================================

# WiFi网络配置列表
# 系统会按顺序尝试连接这些网络，连接到第一个可用的网络后停止尝试
WIFI_CONFIGS = [
    {"ssid": "Lejurobot", "password": "Leju2022"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
    # 可以继续添加更多网络配置
    # {"ssid": "你的网络名称", "password": "你的密码"},
]

# WiFi连接超时时间（秒）
# 单次WiFi连接尝试的最大等待时间
WIFI_CONNECT_TIMEOUT_S = 15

# WiFi重连间隔时间（秒）
# WiFi连接失败后，下次重试前的等待时间
WIFI_RETRY_INTERVAL_S = 60

# =============================================================================
# NTP 时间同步配置
# =============================================================================

# NTP重试间隔（秒）
# 每次NTP同步重试之间的等待时间
NTP_RETRY_DELAY_S = 60

# 时区偏移（小时）
# 将UTC时间转换为本地时间的小时偏移量
# 中国：8，美东：-5/-4，欧洲：1/2等
TIMEZONE_OFFSET_HOURS = 8

# =============================================================================
# LED 硬件配置
# =============================================================================

# LED引脚配置
# 定义控制LED的GPIO引脚号
LED_PIN_1 = 12  # LED 1 的主控引脚
LED_PIN_2 = 13  # LED 2 的主控引脚

# PWM频率配置（Hz）
# 控制PWM信号的频率，影响LED的闪烁和调光效果
PWM_FREQ = 60

# LED最大亮度配置
# 定义PWM占空比的最大值，控制LED的最大亮度
# ESP32的PWM范围：0-65535
MAX_BRIGHTNESS = 20000

# 呼吸灯渐变步长配置
# 控制呼吸灯效果中每次亮度变化的幅度
FADE_STEP = 256

# =============================================================================
# 守护进程配置
# =============================================================================

# 定时器与任务间隔配置（毫秒）
DAEMON_CONFIG = {
    # 主循环更新间隔
    'main_interval_ms': 5000,
    
    # 看门狗喂养与监控任务的统一检查间隔 - 减少到3秒确保及时喂养
    'watchdog_interval_ms': 3000,
    
    # 系统状态监控的实际执行间隔
    'monitor_interval_ms': 30000,
    
    # 内部性能报告的打印间隔（秒）
    'perf_report_interval_s': 30,
}

# 安全与保护机制配置
SAFETY_CONFIG = {
    # 触发"紧急安全模式"的MCU内部温度阈值（°C）
    'temperature_threshold': 45.0,
    
    # 看门狗超时时间（毫秒）- 增加到30秒以提供更大安全边际
    'wdt_timeout_ms': 30000,
    
    # "紧急安全模式"下，LED交替闪烁的间隔时间（毫秒）
    'blink_interval_ms': 200,
    
    # 从"紧急安全模式"自动恢复所需的冷却时间（毫秒）
    'safe_mode_cooldown_ms': 5000,
    
    # 在错误计数重置周期内，允许的最大错误次数
    'max_error_count': 10,
    
    # 错误计数器自动清零的时间周期（毫秒）
    'error_reset_interval_ms': 60000,
    
    # 尝试恢复硬件失败的最大次数
    'max_recovery_attempts': 5,
}

# =============================================================================
# 日志配置
# =============================================================================

# 日志文件配置
LOG_CONFIG = {
    # 日志文件名
    'log_file': 'error.log',
    
    # 日志文件最大大小（字节）
    'max_log_size': 10 * 1024,  # 10 KB
    
    # 日志队列最大大小
    'max_log_queue_size': 20,
}

# =============================================================================
# 系统配置
# =============================================================================

# 通用系统配置
GENERAL_CONFIG = {
    # 主业务循环间隔（秒）
    'main_loop_interval': 5,
    
    # 垃圾回收间隔（循环次数）
    'gc_interval_loops': 20,
    
    # 状态检查间隔（循环次数）
    'status_check_interval_loops': 12,
    
    # 低内存警告阈值（字节）
    'low_memory_threshold': 10000,
}

# =============================================================================
# 配置验证和获取函数
# =============================================================================

def validate_config():
    """
    验证配置的有效性
    
    Returns:
        bool: 配置是否有效
    """
    try:
        # 验证WiFi配置
        if not WIFI_CONFIGS or not isinstance(WIFI_CONFIGS, list):
            print("[CONFIG] [ERROR] WiFi配置无效")
            return False
        
        for wifi_config in WIFI_CONFIGS:
            if not isinstance(wifi_config, dict) or 'ssid' not in wifi_config or 'password' not in wifi_config:
                print("[CONFIG] [ERROR] WiFi配置格式无效")
                return False
        
        # 验证引脚配置
        if not isinstance(LED_PIN_1, int) or not isinstance(LED_PIN_2, int):
            print("[CONFIG] [ERROR] LED引脚配置无效")
            return False
        
        # 验证温度阈值
        if not isinstance(SAFETY_CONFIG['temperature_threshold'], (int, float)):
            print("[CONFIG] [ERROR] 温度阈值配置无效")
            return False
        
        print("[CONFIG] 配置验证通过")
        return True
        
    except Exception as e:
        print(f"[CONFIG] [ERROR] 配置验证失败: {e}")
        return False

def get_wifi_configs():
    """
    获取WiFi配置列表
    
    Returns:
        list: WiFi配置列表
    """
    return WIFI_CONFIGS.copy()

def get_led_config():
    """
    获取LED配置
    
    Returns:
        dict: LED配置字典
    """
    return {
        'pin_1': LED_PIN_1,
        'pin_2': LED_PIN_2,
        'pwm_freq': PWM_FREQ,
        'max_brightness': MAX_BRIGHTNESS,
        'fade_step': FADE_STEP,
    }

def get_daemon_config():
    """
    获取守护进程配置
    
    Returns:
        dict: 守护进程配置字典
    """
    return DAEMON_CONFIG.copy()

def get_safety_config():
    """
    获取安全配置
    
    Returns:
        dict: 安全配置字典
    """
    return SAFETY_CONFIG.copy()

def get_log_config():
    """
    获取日志配置
    
    Returns:
        dict: 日志配置字典
    """
    return LOG_CONFIG.copy()

def get_general_config():
    """
    获取通用系统配置
    
    Returns:
        dict: 通用系统配置字典
    """
    return GENERAL_CONFIG.copy()

def get_network_config():
    """
    获取网络配置
    
    Returns:
        dict: 网络配置字典
    """
    return {
        'wifi_connect_timeout_s': WIFI_CONNECT_TIMEOUT_S,
        'wifi_retry_interval_s': WIFI_RETRY_INTERVAL_S,
        'ntp_retry_delay_s': NTP_RETRY_DELAY_S,
        'timezone_offset_hours': TIMEZONE_OFFSET_HOURS,
    }

def load_all_configs():
    """
    加载并验证所有配置
    
    Returns:
        bool: 配置加载是否成功
    """
    try:
        print("[CONFIG] 正在加载系统配置...")
        
        # 验证配置有效性
        if not validate_config():
            print("[CONFIG] [ERROR] 配置验证失败")
            return False
        
        print("[CONFIG] 系统配置加载完成")
        return True
        
    except Exception as e:
        print(f"[CONFIG] [ERROR] 配置加载失败: {e}")
        return False

# 在模块加载时验证配置
if __name__ == "__main__":
    validate_config()
else:
    # 模块被导入时也进行验证
    validate_config()