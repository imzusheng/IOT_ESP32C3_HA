# app/lib/event_bus/events_const.py
"""
事件常量模块
定义项目中所有的事件列表常量，采用简化的事件分类
在subscribe之前都需要从这里获取事件名称
"""

# 项目中所有事件的常量定义
class EVENTS:
    """统一事件常量"""
    
    # WiFi 网络状态变化事件 - 通过参数传递具体状态
    WIFI_STATE_CHANGE = "wifi.state_change"  # data: (state, info) state可以是: connecting, connected, disconnected, scan_done
    
    # MQTT 状态变化事件 - 通过参数传递具体状态
    MQTT_STATE_CHANGE = "mqtt.state_change"  # data: (state, info) state可以是: connected, disconnected
    MQTT_MESSAGE = "mqtt.message"  # data: (topic, msg)
    
    # 系统状态变化事件 - 通过参数传递具体状态
    SYSTEM_STATE_CHANGE = "system.state_change"  # data: (state, info) state可以是: boot, init, error, warning, shutdown等
    SYSTEM_ERROR = "system.error"  # 统一的系统错误事件，通过参数区分错误类型
    
    # NTP 时间同步状态变化事件 - 通过参数传递具体状态
    NTP_STATE_CHANGE = "ntp.state_change"  # data: (state, info) state可以是: started, success, failed

# 高优先级事件列表 - 优先处理
HIGH_PRIORITY_EVENTS = {
    EVENTS.SYSTEM_ERROR,
    EVENTS.SYSTEM_STATE_CHANGE,
}

# 低优先级事件列表 - 正常处理
LOW_PRIORITY_EVENTS = {
    EVENTS.MQTT_MESSAGE,
    EVENTS.WIFI_STATE_CHANGE,
    EVENTS.MQTT_STATE_CHANGE,
    EVENTS.NTP_STATE_CHANGE,
}

def get_all_events():
    """获取所有事件名称
    
    Returns:
        list: 所有事件名称的列表
    """
    return list(HIGH_PRIORITY_EVENTS | LOW_PRIORITY_EVENTS)


def is_high_priority_event(event_name):
    """检查是否为高优先级事件
    
    Args:
        event_name: 事件名称
    Returns:
        bool: 是高优先级事件返回True
    """
    return event_name in HIGH_PRIORITY_EVENTS