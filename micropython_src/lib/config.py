# config.py
"""
系统配置管理模块 - 支持JSON外部配置文件

这个模块集中管理整个IoT系统的所有配置参数，包括：
- WiFi网络配置
- 硬件引脚配置
- 系统监控参数
- 定时器和间隔配置
- 安全和保护机制配置

优化特性：
1. 支持从外部JSON文件加载配置（config.json）
2. 保持向后兼容性，如果JSON文件不存在则使用默认配置
3. 配置热重载功能，支持运行时更新配置
4. 配置验证和错误处理机制
5. 避免硬编码配置散布在各个模块中
"""

import os

try:
    import ujson as json
except ImportError:
    import json

# =============================================================================
# 整数常量定义 - 代码体积优化
# =============================================================================

# 使用 micropython.const 进行编译时优化
try:
    from micropython import const
except ImportError:
    # 在标准Python环境中使用普通常量
    def const(x):
        return x

# === 事件类型常量 ===
# WiFi相关事件
EV_WIFI_CONNECTING = const(1)
EV_WIFI_CONNECTED = const(2)
EV_WIFI_DISCONNECTED = const(3)
EV_WIFI_TRYING = const(4)
EV_WIFI_TIMEOUT = const(5)
EV_WIFI_ERROR = const(6)
EV_WIFI_FAILED = const(7)
EV_WIFI_SCAN_FAILED = const(8)
EV_WIFI_DISCONNECTED_DETECTED = const(9)

# NTP相关事件
EV_NTP_SYNCING = const(10)
EV_NTP_SYNCED = const(11)
EV_NTP_FAILED = const(12)
EV_NTP_NO_WIFI = const(13)
EV_NTP_NOT_SYNCED_DETECTED = const(14)

# 系统相关事件
EV_MAIN_LOOP_STARTED = const(20)
EV_MAIN_LOOP_STOPPED = const(21)
EV_SYSTEM_HEARTBEAT = const(22)
EV_SYSTEM_STATUS_CHECK = const(23)
EV_MEMORY_STATUS = const(24)
EV_LOW_MEMORY_WARNING = const(25)
EV_LOOP_COUNTER_RESET = const(26)
EV_PERFORMANCE_REPORT = const(27)
EV_CONFIG_UPDATE = const(28)
EV_SYSTEM_STARTING = const(29)
EV_SYSTEM_STOPPED = const(30)
EV_SYSTEM_SHUTTING_DOWN = const(31)
EV_SYSTEM_SHUTDOWN_REQUESTED = const(32)
EV_SYSTEM_ERROR = const(33)
EV_SYSTEM_TASK_ERROR = const(34)

# 守护进程相关事件
EV_DAEMON_STARTED = const(40)
EV_DAEMON_START_FAILED = const(41)
EV_ENTER_SAFE_MODE = const(42)
EV_EXIT_SAFE_MODE = const(43)
EV_SCHEDULER_INTERVAL_ADJUSTED = const(44)

# LED相关事件
EV_LED_SET_EFFECT = const(50)
EV_LED_SET_BRIGHTNESS = const(51)
EV_LED_EMERGENCY_OFF = const(52)
EV_LED_EMERGENCY_OFF_COMPLETED = const(53)
EV_LED_INITIALIZED = const(54)
EV_LED_DEINITIALIZED = const(55)
EV_LED_EFFECT_CHANGED = const(56)

# 异步任务相关事件
EV_ASYNC_SYSTEM_STARTING = const(60)
EV_ASYNC_TASKS_STARTED = const(61)
EV_ASYNC_TASKS_CLEANUP_STARTED = const(62)
EV_ASYNC_TASKS_CLEANUP_COMPLETED = const(63)

# 日志相关事件
EV_LOGGER_INITIALIZED = const(70)

# === 日志级别常量 ===
LOG_LEVEL_CRITICAL = const(101)
LOG_LEVEL_WARNING = const(102)
LOG_LEVEL_INFO = const(103)
LOG_LEVEL_ERROR = const(104)

# === 调试开关 ===
# 发布版本时设为 False 可移除所有调试信息
DEBUG = True  # 开发时设为 True, 发布时设为 False
# === 事件常量映射表 ===
# 用于字符串到整数的转换
EVENT_MAP = {
    # WiFi相关事件
    'wifi_connecting': EV_WIFI_CONNECTING,
    'wifi_connected': EV_WIFI_CONNECTED,
    'wifi_disconnected': EV_WIFI_DISCONNECTED,
    'wifi_trying': EV_WIFI_TRYING,
    'wifi_timeout': EV_WIFI_TIMEOUT,
    'wifi_error': EV_WIFI_ERROR,
    'wifi_failed': EV_WIFI_FAILED,
    'wifi_scan_failed': EV_WIFI_SCAN_FAILED,
    'wifi_disconnected_detected': EV_WIFI_DISCONNECTED_DETECTED,
    
    # NTP相关事件
    'ntp_syncing': EV_NTP_SYNCING,
    'ntp_synced': EV_NTP_SYNCED,
    'ntp_failed': EV_NTP_FAILED,
    'ntp_no_wifi': EV_NTP_NO_WIFI,
    'ntp_not_synced_detected': EV_NTP_NOT_SYNCED_DETECTED,
    
    # 系统相关事件
    'main_loop_started': EV_MAIN_LOOP_STARTED,
    'main_loop_stopped': EV_MAIN_LOOP_STOPPED,
    'system_heartbeat': EV_SYSTEM_HEARTBEAT,
    'system_status_check': EV_SYSTEM_STATUS_CHECK,
    'memory_status': EV_MEMORY_STATUS,
    'low_memory_warning': EV_LOW_MEMORY_WARNING,
    'loop_counter_reset': EV_LOOP_COUNTER_RESET,
    'performance_report': EV_PERFORMANCE_REPORT,
    'config_update': EV_CONFIG_UPDATE,
    'system_starting': EV_SYSTEM_STARTING,
    'system_stopped': EV_SYSTEM_STOPPED,
    'system_shutting_down': EV_SYSTEM_SHUTTING_DOWN,
    'system_shutdown_requested': EV_SYSTEM_SHUTDOWN_REQUESTED,
    'system_error': EV_SYSTEM_ERROR,
    'system_task_error': EV_SYSTEM_TASK_ERROR,
    
    # 守护进程相关事件
    'daemon_started': EV_DAEMON_STARTED,
    'daemon_start_failed': EV_DAEMON_START_FAILED,
    'enter_safe_mode': EV_ENTER_SAFE_MODE,
    'exit_safe_mode': EV_EXIT_SAFE_MODE,
    'scheduler_interval_adjusted': EV_SCHEDULER_INTERVAL_ADJUSTED,
    
    # LED相关事件
    'led_set_effect': EV_LED_SET_EFFECT,
    'led_set_brightness': EV_LED_SET_BRIGHTNESS,
    'led_emergency_off': EV_LED_EMERGENCY_OFF,
    'led_emergency_off_completed': EV_LED_EMERGENCY_OFF_COMPLETED,
    'led_initialized': EV_LED_INITIALIZED,
    'led_deinitialized': EV_LED_DEINITIALIZED,
    'led_effect_changed': EV_LED_EFFECT_CHANGED,
    
    # 异步任务相关事件
    'async_system_starting': EV_ASYNC_SYSTEM_STARTING,
    'async_tasks_started': EV_ASYNC_TASKS_STARTED,
    'async_tasks_cleanup_started': EV_ASYNC_TASKS_CLEANUP_STARTED,
    'async_tasks_cleanup_completed': EV_ASYNC_TASKS_CLEANUP_COMPLETED,
    
    # 日志相关事件
    'logger_initialized': EV_LOGGER_INITIALIZED,
}

# === 日志级别映射表 ===
LOG_LEVEL_MAP = {
    'log_critical': LOG_LEVEL_CRITICAL,
    'log_warning': LOG_LEVEL_WARNING,
    'log_info': LOG_LEVEL_INFO,
    'log_error': LOG_LEVEL_ERROR,
}

# === 辅助函数 ===
def get_event_id(event_name):
    """获取事件ID，支持字符串和整数输入"""
    if isinstance(event_name, int):
        return event_name
    return EVENT_MAP.get(event_name, event_name)

def get_log_level_id(level_name):
    """获取日志级别ID，支持字符串和整数输入"""
    if isinstance(level_name, int):
        return level_name
    return LOG_LEVEL_MAP.get(level_name, level_name)

# =============================================================================
# JSON配置文件管理
# =============================================================================

# 配置文件路径
CONFIG_FILE_PATH = 'config.json'

# 全局配置存储
_loaded_config = None
_config_load_time = 0

class ConfigFileNotFoundError(Exception):
    """配置文件不存在异常"""
    pass

class ConfigLoadError(Exception):
    """配置加载失败异常"""
    pass

def _load_json_config():
    """
    从JSON文件加载配置
    
    Returns:
        dict: 配置字典
    
    Raises:
        ConfigFileNotFoundError: 配置文件不存在
        ConfigLoadError: 配置文件加载失败
    """
    try:
        if CONFIG_FILE_PATH not in os.listdir():
            raise ConfigFileNotFoundError(f"配置文件 {CONFIG_FILE_PATH} 不存在，请先创建配置文件")
        
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f)
        print(f"[CONFIG] 成功从 {CONFIG_FILE_PATH} 加载配置")
        return config_data
    except ConfigFileNotFoundError:
        raise  # 重新抛出配置文件不存在异常
    except Exception as e:
        raise ConfigLoadError(f"加载JSON配置失败: {e}")

def _save_json_config(config_data):
    """
    保存配置到JSON文件
    
    Args:
        config_data (dict): 要保存的配置数据
    
    Returns:
        bool: 保存是否成功
    """
    try:
        with open(CONFIG_FILE_PATH, 'w') as f:
            json.dump(config_data, f, indent=2)
        print(f"[CONFIG] 配置已保存到 {CONFIG_FILE_PATH}")
        return True
    except Exception as e:
        print(f"[CONFIG] [ERROR] 保存JSON配置失败: {e}")
        return False

def reload_config():
    """
    重新加载配置文件
    
    Returns:
        bool: 重载是否成功
    """
    global _loaded_config, _config_load_time
    
    try:
        old_config = _loaded_config.copy() if _loaded_config else {}
        _loaded_config = _load_json_config()
        _config_load_time = time.ticks_ms() if 'time' in globals() else 0
        
        if _loaded_config:
            print("[CONFIG] 配置重载成功")
            
            # 配置模块只负责加载配置，不发布事件
            # 事件发布由调用者负责
            if DEBUG:
                # 检查哪些配置部分发生了变化
                changed_sections = []
                for section in ['led', 'wifi', 'logging', 'daemon', 'ntp', 'general']:
                    if old_config.get(section, {}) != _loaded_config.get(section, {}):
                        changed_sections.append(section)
                
                if changed_sections:
                    print(f"[CONFIG] 配置变更部分: {', '.join(changed_sections)}")
            
            return True
        else:
            print("[CONFIG] 配置重载失败，使用默认配置")
            return False
            
    except Exception as e:
        print(f"[CONFIG] [ERROR] 配置重载失败: {e}")
        return False

def _get_config_value(section, key):
    """
    从配置中获取值，要求配置文件必须存在
    
    Args:
        section (str): 配置节名称
        key (str): 配置键名称，如果为None则返回整个配置节
    
    Returns:
        配置值或配置节
    
    Raises:
        ConfigFileNotFoundError: 配置文件不存在
        ConfigLoadError: 配置加载失败
        KeyError: 配置项不存在
    """
    global _loaded_config
    
    # 如果还没有加载过配置，先尝试加载
    if _loaded_config is None:
        _loaded_config = _load_json_config()
    
    # 检查配置节是否存在
    if section not in _loaded_config:
        raise KeyError(f"配置节 '{section}' 不存在")
    
    # 如果key为None，返回整个配置节
    if key is None:
        return _loaded_config[section]
    
    # 检查配置项是否存在
    if key not in _loaded_config[section]:
        raise KeyError(f"配置项 '{section}.{key}' 不存在")
    
    return _loaded_config[section][key]

# =============================================================================
# WiFi 网络配置
# =============================================================================

def get_wifi_configs():
    """获取WiFi配置列表"""
    return _get_config_value('wifi', 'configs')

def get_wifi_connect_timeout():
    """获取WiFi连接超时时间"""
    return _get_config_value('wifi', 'connect_timeout_s')

def get_wifi_retry_interval():
    """获取WiFi重连间隔时间"""
    return _get_config_value('wifi', 'retry_interval_s')

def get_wifi_check_interval():
    """获取WiFi连接检查间隔时间"""
    try:
        return _get_config_value('wifi', 'check_interval_s')
    except KeyError:
        return 30  # 默认30秒



# =============================================================================
# NTP 时间同步配置
# =============================================================================

def get_ntp_retry_delay():
    """获取NTP重试间隔"""
    return _get_config_value('ntp', 'retry_delay_s')

def get_timezone_offset():
    """获取时区偏移"""
    return _get_config_value('ntp', 'timezone_offset_hours')



# =============================================================================
# LED 硬件配置
# =============================================================================

def get_led_pin_1():
    """获取LED1引脚"""
    return _get_config_value('led', 'pin_1')

def get_led_pin_2():
    """获取LED2引脚"""
    return _get_config_value('led', 'pin_2')

def get_pwm_freq():
    """获取PWM频率"""
    return _get_config_value('led', 'pwm_freq')

def get_max_brightness():
    """获取最大亮度"""
    return _get_config_value('led', 'max_brightness')

def get_fade_step():
    """获取渐变步长"""
    return _get_config_value('led', 'fade_step')

# 向后兼容的常量（延迟加载）
def _get_led_constants():
    """获取LED常量，用于向后兼容"""
    try:
        return {
            'LED_PIN_1': get_led_pin_1(),
            'LED_PIN_2': get_led_pin_2(),
            'PWM_FREQ': get_pwm_freq(),
            'MAX_BRIGHTNESS': get_max_brightness(),
            'FADE_STEP': get_fade_step()
        }
    except (ConfigFileNotFoundError, ConfigLoadError, KeyError):
        # 如果配置文件不存在，返回None，让调用者处理
        return None

# =============================================================================
# 守护进程配置
# =============================================================================

def get_daemon_config():
    """获取守护进程配置"""
    return _get_config_value('daemon', None)  # 返回整个daemon配置节

def get_safety_config():
    """获取安全配置"""
    return _get_config_value('safety', None)  # 返回整个safety配置节

# =============================================================================
# 日志配置
# =============================================================================

def get_log_config():
    """获取日志配置"""
    return _get_config_value('logging', None)

# =============================================================================
# 系统配置
# =============================================================================

def get_general_config():
    """获取通用系统配置"""
    return _get_config_value('general', None)

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
        wifi_configs = get_wifi_configs()
        if not wifi_configs or not isinstance(wifi_configs, list):
            print("[CONFIG] [ERROR] WiFi配置无效")
            return False
        
        for wifi_config in wifi_configs:
            if not isinstance(wifi_config, dict) or 'ssid' not in wifi_config or 'password' not in wifi_config:
                print("[CONFIG] [ERROR] WiFi配置格式无效")
                return False
        
        # 验证引脚配置
        led_pin_1 = get_led_pin_1()
        led_pin_2 = get_led_pin_2()
        if not isinstance(led_pin_1, int) or not isinstance(led_pin_2, int):
            print("[CONFIG] [ERROR] LED引脚配置无效")
            return False
        
        # 验证温度阈值
        safety_config = get_safety_config()
        if not isinstance(safety_config.get('temperature_threshold'), (int, float)):
            print("[CONFIG] [ERROR] 温度阈值配置无效")
            return False
        
        print("[CONFIG] 配置验证通过")
        return True
        
    except Exception as e:
        print(f"[CONFIG] [ERROR] 配置验证失败: {e}")
        return False

def get_led_config():
    """
    获取LED配置
    
    Returns:
        dict: LED配置字典
    """
    return {
        'pin_1': get_led_pin_1(),
        'pin_2': get_led_pin_2(),
        'pwm_freq': get_pwm_freq(),
        'max_brightness': get_max_brightness(),
        'fade_step': get_fade_step(),
    }

def get_network_config():
    """
    获取网络配置
    
    Returns:
        dict: 网络配置字典
    """
    return {
        'wifi_connect_timeout_s': get_wifi_connect_timeout(),
        'wifi_retry_interval_s': get_wifi_retry_interval(),
        'ntp_retry_delay_s': get_ntp_retry_delay(),
        'timezone_offset_hours': get_timezone_offset(),
    }

def load_all_configs():
    """
    加载并验证所有配置
    
    Returns:
        bool: 配置加载是否成功
    
    Raises:
        ConfigFileNotFoundError: 配置文件不存在
        ConfigLoadError: 配置加载失败
        KeyError: 配置项不存在
    """
    print("[CONFIG] 正在加载系统配置...")
    
    # 强制加载配置文件，如果失败会抛出异常
    global _loaded_config
    _loaded_config = _load_json_config()
    
    # 验证配置有效性
    if not validate_config():
        raise ConfigLoadError("配置验证失败")
    
    print("[CONFIG] 系统配置加载完成")
    return True

# =============================================================================
# 向后兼容的常量定义（延迟加载）
# =============================================================================

def _get_wifi_constants():
    """获取WiFi常量，用于向后兼容"""
    try:
        return {
            'WIFI_CONFIGS': get_wifi_configs(),
            'WIFI_CONNECT_TIMEOUT_S': get_wifi_connect_timeout(),
            'WIFI_RETRY_INTERVAL_S': get_wifi_retry_interval(),
            'WIFI_CHECK_INTERVAL_S': get_wifi_check_interval()
        }
    except (ConfigFileNotFoundError, ConfigLoadError, KeyError):
        # 如果配置文件不存在，返回None，让调用者处理
        return None

# 延迟加载的全局常量
_wifi_constants = None

def _ensure_wifi_constants():
    """确保WiFi常量已加载"""
    global _wifi_constants
    if _wifi_constants is None:
        _wifi_constants = _get_wifi_constants()
    return _wifi_constants

# 向后兼容的属性访问
def __getattr__(name):
    """动态属性访问，用于向后兼容"""
    wifi_constants = _ensure_wifi_constants()
    if wifi_constants and name in wifi_constants:
        return wifi_constants[name]
    
    led_constants = _get_led_constants()
    if led_constants and name in led_constants:
        return led_constants[name]
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# 在模块加载时验证配置
if __name__ == "__main__":
    validate_config()
else:
    # 模块被导入时也进行验证
    try:
        validate_config()
    except (ConfigFileNotFoundError, ConfigLoadError, KeyError):
        # 如果配置文件不存在或有问题，不阻止模块加载
        # 让调用者处理这些异常
        pass