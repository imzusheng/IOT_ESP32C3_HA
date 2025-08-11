# app/lib/event_bus/events_const.py
"""
事件常量模块
定义项目中所有的事件列表常量，采用简化的事件分类
在subscribe之前都需要从这里获取事件名称
"""

# 项目中所有事件的常量定义
class EVENTS:
    """统一事件常量，避免在代码中使用裸字符串"""
    
    # WiFi 网络事件 - 简化为状态变化事件
    # 参数state取值: 'connecting', 'connected', 'disconnected', 'scan_done'
    WIFI_STATE_CHANGE = "wifi.state.change"

    # MQTT 事件 - 简化为状态变化和消息事件
    # 参数state取值: 'connected', 'disconnected'
    MQTT_STATE_CHANGE = "mqtt.state.change"
    MQTT_MESSAGE = "mqtt.message"

    # 系统状态事件 - 简化为关键状态
    # 参数state取值: 'boot', 'init', 'running', 'warning', 'error', 'critical', 'shutdown'
    SYSTEM_STATE_CHANGE = "system.state.change"
    # 系统错误事件 - 统一的系统错误处理
    # 参数error_type取值: 'system_error', 'memory_critical', 'hardware_error'等
    # 参数error_context包含具体错误信息
    SYSTEM_ERROR = "system.error"
    
    # NTP 时间同步事件 - 简化为状态变化
    # 参数state取值: 'started', 'success', 'failed'
    NTP_STATE_CHANGE = "ntp.state.change"

    # 硬件事件 - 保持简洁
    SENSOR_DATA = "sensor.data"
    
    # 队列状态事件 - 新增队列满警告
    QUEUE_FULL_WARNING = "queue.full.warning"

# 获取所有事件名称的列表
def get_all_events():
    """获取所有定义的事件名称列表"""
    return [getattr(EVENTS, attr) for attr in dir(EVENTS) if not attr.startswith('_')]