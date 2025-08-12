# app/fsm/state_const.py
"""
状态常量定义模块 - 合并版本
整合所有状态相关的定义，简化导入路径
"""

# 状态常量 - 使用整数常量提高性能
STATE_BOOT = 0
STATE_INIT = 1
STATE_NETWORKING = 2
STATE_RUNNING = 3
STATE_WARNING = 4
STATE_ERROR = 5
STATE_SAFE_MODE = 6
STATE_RECOVERY = 7
STATE_SHUTDOWN = 8

# 状态名称映射
STATE_NAMES = {
    STATE_BOOT: "BOOT",
    STATE_INIT: "INIT",
    STATE_NETWORKING: "NETWORKING",
    STATE_RUNNING: "RUNNING",
    STATE_WARNING: "WARNING",
    STATE_ERROR: "ERROR",
    STATE_SAFE_MODE: "SAFE_MODE",
    STATE_RECOVERY: "RECOVERY",
    STATE_SHUTDOWN: "SHUTDOWN"
}

# 状态转换表：当前状态 x 事件 -> 下一状态
STATE_TRANSITIONS = {
    STATE_BOOT: {
        'boot_complete': STATE_INIT
    },
    STATE_INIT: {
        'init_complete': STATE_NETWORKING,
        'error': STATE_ERROR
    },
    STATE_NETWORKING: {
        'wifi_connected': STATE_RUNNING,
        'wifi_disconnected': STATE_WARNING,
        'error': STATE_ERROR
    },
    STATE_RUNNING: {
        'wifi_disconnected': STATE_NETWORKING,
        'mqtt_disconnected': STATE_WARNING,
        'warning': STATE_WARNING,
        'error': STATE_ERROR,
        'safe_mode': STATE_SAFE_MODE
    },
    STATE_WARNING: {
        'wifi_connected': STATE_RUNNING,
        'mqtt_connected': STATE_RUNNING,
        'recovery_success': STATE_RUNNING,
        'error': STATE_ERROR,
        'safe_mode': STATE_SAFE_MODE
    },
    STATE_ERROR: {
        'warning': STATE_WARNING,
        'recovery_success': STATE_WARNING,
        'safe_mode': STATE_SAFE_MODE,
        'shutdown': STATE_SHUTDOWN
    },
    STATE_SAFE_MODE: {
        'warning': STATE_WARNING,
        'recovery_success': STATE_WARNING,
        'shutdown': STATE_SHUTDOWN
    },
    STATE_RECOVERY: {
        'recovery_success': STATE_RUNNING,
        'error': STATE_ERROR,
        'safe_mode': STATE_SAFE_MODE
    },
    STATE_SHUTDOWN: {}  # 终止状态，无转换
}

# LED模式映射
LED_PATTERNS = {
    STATE_BOOT: 'off',
    STATE_INIT: 'blink',
    STATE_NETWORKING: 'pulse',
    STATE_RUNNING: 'cruise',
    STATE_WARNING: 'blink',
    STATE_ERROR: 'blink',
    STATE_SAFE_MODE: 'sos',
    STATE_RECOVERY: 'blink',
    STATE_SHUTDOWN: 'off'
}

# 为了保持兼容性，创建SystemState类
class SystemState:
    """系统状态定义 - 兼容性类"""
    BOOT = "BOOT"
    INIT = "INIT"
    NETWORKING = "NETWORKING"
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SAFE_MODE = "SAFE_MODE"
    RECOVERY = "RECOVERY"
    SHUTDOWN = "SHUTDOWN"

# 工具函数
def get_state_name(state):
    """获取状态名称"""
    return STATE_NAMES.get(state, "UNKNOWN")

def get_next_state(current_state, event):
    """获取下一个状态"""
    return STATE_TRANSITIONS.get(current_state, {}).get(event)

def get_led_pattern(state):
    """获取LED模式"""
    return LED_PATTERNS.get(state, 'off')

def get_all_states():
    """获取所有状态列表"""
    return list(STATE_NAMES.keys())