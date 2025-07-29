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
DEBUG = False  # 开发时设为 True, 发布时设为 False
# === 事件常量映射表 ===
# 用于向后兼容和字符串到整数的转换
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

def _load_json_config():
    """
    从JSON文件加载配置
    
    Returns:
        dict: 配置字典，如果加载失败则返回None
    """
    try:
        if CONFIG_FILE_PATH in os.listdir():
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
            print(f"[CONFIG] 成功从 {CONFIG_FILE_PATH} 加载配置")
            return config_data
        else:
            print(f"[CONFIG] 配置文件 {CONFIG_FILE_PATH} 不存在，使用默认配置")
            return None
    except Exception as e:
        print(f"[CONFIG] [ERROR] 加载JSON配置失败: {e}")
        return None

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
        _loaded_config = _load_json_config()
        _config_load_time = time.ticks_ms() if 'time' in globals() else 0
        
        if _loaded_config:
            print("[CONFIG] 配置重载成功")
            return True
        else:
            print("[CONFIG] 配置重载失败，使用默认配置")
            return False
            
    except Exception as e:
        print(f"[CONFIG] [ERROR] 配置重载失败: {e}")
        return False

def _get_config_value(section, key, default_value):
    """
    从配置中获取值，支持JSON配置和默认值回退
    
    Args:
        section (str): 配置节名称
        key (str): 配置键名称
        default_value: 默认值
    
    Returns:
        配置值或默认值
    """
    global _loaded_config
    
    # 如果还没有加载过配置，先尝试加载
    if _loaded_config is None:
        _loaded_config = _load_json_config()
    
    # 如果有JSON配置，优先使用
    if _loaded_config and section in _loaded_config and key in _loaded_config[section]:
        return _loaded_config[section][key]
    
    # 否则使用默认值
    return default_value

# =============================================================================
# WiFi 网络配置
# =============================================================================

# WiFi网络配置列表（默认值）
# 系统会按顺序尝试连接这些网络，连接到第一个可用的网络后停止尝试
_DEFAULT_WIFI_CONFIGS = [
    {"ssid": "Lejurobot", "password": "Leju2022"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
    # 可以继续添加更多网络配置
    # {"ssid": "你的网络名称", "password": "你的密码"},
]

# WiFi连接超时时间（秒）- 默认值
_DEFAULT_WIFI_CONNECT_TIMEOUT_S = 15

# WiFi重连间隔时间（秒）- 默认值
_DEFAULT_WIFI_RETRY_INTERVAL_S = 60

# 动态配置获取函数
def get_wifi_configs():
    """获取WiFi配置列表（支持JSON配置）"""
    return _get_config_value('wifi', 'configs', _DEFAULT_WIFI_CONFIGS)

def get_wifi_connect_timeout():
    """获取WiFi连接超时时间（支持JSON配置）"""
    return _get_config_value('wifi', 'connect_timeout_s', _DEFAULT_WIFI_CONNECT_TIMEOUT_S)

def get_wifi_retry_interval():
    """获取WiFi重连间隔时间（支持JSON配置）"""
    return _get_config_value('wifi', 'retry_interval_s', _DEFAULT_WIFI_RETRY_INTERVAL_S)

# 向后兼容的常量（从动态配置获取）
WIFI_CONFIGS = property(lambda: get_wifi_configs())
WIFI_CONNECT_TIMEOUT_S = property(lambda: get_wifi_connect_timeout())
WIFI_RETRY_INTERVAL_S = property(lambda: get_wifi_retry_interval())

# =============================================================================
# NTP 时间同步配置
# =============================================================================

# NTP重试间隔（秒）- 默认值
_DEFAULT_NTP_RETRY_DELAY_S = 60

# 时区偏移（小时）- 默认值
_DEFAULT_TIMEZONE_OFFSET_HOURS = 8

# 动态配置获取函数
def get_ntp_retry_delay():
    """获取NTP重试间隔（支持JSON配置）"""
    return _get_config_value('ntp', 'retry_delay_s', _DEFAULT_NTP_RETRY_DELAY_S)

def get_timezone_offset():
    """获取时区偏移（支持JSON配置）"""
    return _get_config_value('ntp', 'timezone_offset_hours', _DEFAULT_TIMEZONE_OFFSET_HOURS)

# 向后兼容的常量
NTP_RETRY_DELAY_S = property(lambda: get_ntp_retry_delay())
TIMEZONE_OFFSET_HOURS = property(lambda: get_timezone_offset())

# =============================================================================
# LED 硬件配置
# =============================================================================

# LED引脚配置 - 默认值
_DEFAULT_LED_PIN_1 = 12  # LED 1 的主控引脚
_DEFAULT_LED_PIN_2 = 13  # LED 2 的主控引脚

# PWM频率配置（Hz）- 默认值
_DEFAULT_PWM_FREQ = 60

# LED最大亮度配置 - 默认值
_DEFAULT_MAX_BRIGHTNESS = 20000

# 呼吸灯渐变步长配置 - 默认值
_DEFAULT_FADE_STEP = 256

# 动态配置获取函数
def get_led_pin_1():
    """获取LED1引脚（支持JSON配置）"""
    return _get_config_value('led', 'pin_1', _DEFAULT_LED_PIN_1)

def get_led_pin_2():
    """获取LED2引脚（支持JSON配置）"""
    return _get_config_value('led', 'pin_2', _DEFAULT_LED_PIN_2)

def get_pwm_freq():
    """获取PWM频率（支持JSON配置）"""
    return _get_config_value('led', 'pwm_freq', _DEFAULT_PWM_FREQ)

def get_max_brightness():
    """获取最大亮度（支持JSON配置）"""
    return _get_config_value('led', 'max_brightness', _DEFAULT_MAX_BRIGHTNESS)

def get_fade_step():
    """获取渐变步长（支持JSON配置）"""
    return _get_config_value('led', 'fade_step', _DEFAULT_FADE_STEP)

# 向后兼容的常量
LED_PIN_1 = property(lambda: get_led_pin_1())
LED_PIN_2 = property(lambda: get_led_pin_2())
PWM_FREQ = property(lambda: get_pwm_freq())
MAX_BRIGHTNESS = property(lambda: get_max_brightness())
FADE_STEP = property(lambda: get_fade_step())

# =============================================================================
# 守护进程配置
# =============================================================================

# 定时器与任务间隔配置（毫秒）- 默认值
_DEFAULT_DAEMON_CONFIG = {
    # 主循环更新间隔
    'main_interval_ms': 5000,
    
    # 看门狗喂养与监控任务的统一检查间隔 - 减少到3秒确保及时喂养
    'watchdog_interval_ms': 3000,
    
    # 系统状态监控的实际执行间隔
    'monitor_interval_ms': 30000,
    
    # 内部性能报告的打印间隔（秒）
    'perf_report_interval_s': 30,
    
    # 统一调度器间隔（优化后新增）
    'scheduler_interval_ms': 100,
}

# 动态配置获取函数
def get_daemon_config():
    """获取守护进程配置（支持JSON配置）"""
    if _loaded_config and 'daemon' in _loaded_config:
        # 合并JSON配置和默认配置
        config = _DEFAULT_DAEMON_CONFIG.copy()
        config.update(_loaded_config['daemon'])
        return config
    return _DEFAULT_DAEMON_CONFIG.copy()

# 向后兼容的常量
DAEMON_CONFIG = property(lambda: get_daemon_config())

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