# app/event_const.py
class EVENT:
    """
    统一事件常量，避免在代码中使用裸字符串。
    """
    # 日志事件
    LOG_INFO = "log.info"
    LOG_WARN = "log.warn"
    LOG_ERROR = "log.error"
    LOG_DEBUG = "log.debug"

    # WiFi 网络事件
    WIFI_CONNECTING = "wifi.connecting"
    WIFI_CONNECTED = "wifi.connected"
    WIFI_DISCONNECTED = "wifi.disconnected"
    WIFI_SCAN_DONE = "wifi.scan.done"

    # MQTT 事件
    MQTT_CONNECTED = "mqtt.connected"
    MQTT_DISCONNECTED = "mqtt.disconnected"
    MQTT_MESSAGE = "mqtt.message"  # data: (topic, msg)

    # 系统状态事件
    SYSTEM_BOOT = "system.boot"
    SYSTEM_INIT = "system.init"
    SYSTEM_ERROR = "system.error"
    SYSTEM_HEARTBEAT = "system.heartbeat"
    SYSTEM_WARNING = "system.warning"
    SYSTEM_SHUTDOWN = "system.shutdown"
    MEMORY_CRITICAL = "memory.critical"
    RECOVERY_SUCCESS = "recovery.success"
    RECOVERY_FAILED = "recovery.failed"

    # NTP 时间同步事件
    NTP_SYNC_STARTED = "ntp.sync.started"
    NTP_SYNC_SUCCESS = "ntp.sync.success"
    NTP_SYNC_FAILED = "ntp.sync.failed"
    TIME_UPDATED = "time.updated"

    # 硬件事件
    BUTTON_PRESSED = "button.pressed"
    SENSOR_DATA = "sensor.data"  # data: (sensor_id, value)
