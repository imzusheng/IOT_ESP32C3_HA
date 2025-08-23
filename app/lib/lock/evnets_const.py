"""
事件常量集中管理模块
集中管理系统状态和事件名称常量, 便于全局复用与维护。
"""

# 系统状态常量
SYSTEM_STATUS = {
    "NORMAL": "normal",
    "WARNING": "warning",
    "CRITICAL": "critical",
}

# 事件常量
EVENTS = {
    # WiFi 网络状态变化事件
    "WIFI_STATE_CHANGE": "wifi.state_change",  # data: (state, info) e.g., scanning, connecting, connected, disconnected
    # MQTT 状态变化事件
    "MQTT_STATE_CHANGE": "mqtt.state_change",  # data: (state, info) e.g., connected, disconnected
    # MQTT 消息事件
    "MQTT_MESSAGE": "mqtt.message",  # data: (topic, message)
    # 系统状态变化事件
    "SYSTEM_STATE_CHANGE": "system.state_change",  # data: (state, info) e.g., 1.init, 2.running, 3.error, 4.shutdown
    # 系统错误事件
    "SYSTEM_ERROR": "system.error",  # data: (error_type, error_info)
    # NTP 时间同步状态变化事件
    "NTP_STATE_CHANGE": "ntp.state_change",  # data: (state, info) e.g., success, failed, syncing
    # 传感器数据事件
    "SENSOR_DATA": "sensor.data",  # data: (sensor_id, value)
}