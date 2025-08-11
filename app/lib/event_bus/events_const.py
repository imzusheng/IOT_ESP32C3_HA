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
    
    # 硬件传感器数据事件
    SENSOR_DATA = "sensor.data"  # data: (sensor_id, value)

def get_all_events():
    """获取所有事件名称
    
    Returns:
        list: 所有事件名称的列表-共7个核心事件
    """
    return [
        EVENTS.WIFI_STATE_CHANGE,
        EVENTS.MQTT_STATE_CHANGE,
        EVENTS.MQTT_MESSAGE,
        EVENTS.SYSTEM_STATE_CHANGE,
        EVENTS.SYSTEM_ERROR,
        EVENTS.NTP_STATE_CHANGE,
        EVENTS.SENSOR_DATA
    ]


# 向后兼容性支持
# 采用简化的事件系统，通过事件回调参数传递具体状态信息
# 项目中的所有文件已经从 'from event_const import EVENT' 迁移到 'from lib.event_bus import EVENTS'

def validate_event_count():
    """验证事件数量是否为7个核心事件
    
    Returns:
        bool: 如果事件数量为7个返回True，否则返回False
    """
    return len(get_all_events()) == 7