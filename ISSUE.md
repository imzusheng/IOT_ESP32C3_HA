- 运行 main.py 时遇到下面异常,分析项目和下方的日志
  - 找出异常信息，哪一步出现了问题， 深入分析代码找出问题并修复， 同时举一反三
  - 仍有一些打印信息没有模块名称，需要在打印时添加模块名称
  - 我注意日志中似乎有的流程在重复执行， 我需要知道是什么
  - 当前的日志不是线性的，我需要梳理基础逻辑，初始化后 需要连接上WIFI+NTP校准时间+MQTT连接成功...（后续逻辑）
  - 日志各种模块交叉打印不好观察， 减少正常的日志打印， 只需要关键节点和错误时打印

- 以event_bus为基础， 分析当前总体架构和情况， 更新 docs/architecture.md

>>> %Run -c $EDITOR_CONTENT

MPY: soft reboot
[Config] Configuration module loaded.
[LED] LED pattern module loaded
[Sensor] Sensor module loaded
=== ESP32-C3 IoT Device Starting ===
[Main] Configuration loaded
[Cache] Cache loaded from cache.json
INFO:ESP32C3:Logger setup complete. Subscribed to log events.
[LED] Controller initialized for pins: [12, 13]
[Sensor] Internal temperature sensor initialized
[FSM] Watchdog enabled with timeout: 120000 ms
[FSM] System state machine initialized
[Main] System event subscriptions registered
[Main] Starting ESP32-C3 IoT device...
[Main] Object pools configured
[Main] Starting system state machine...
[FSM] Starting state machine main loop
[WiFi] Starting WiFi connection process...
[Main] WiFi connecting...
INFO:ESP32C3:Starting WiFi connection
[WiFi] Scanning for networks...
[WiFi] Found best network: CMCC-pdRG (RSSI: -20)
[WiFi] Attempting to connect to 'CMCC-pdRG'...
INFO:ESP32C3:[WiFi] Attempting to connect to WiFi network: CMCC-pdRG
[WiFi] WiFi connected! IP: 192.168.1.9
INFO:ESP32C3:[WiFi] WiFi connected successfully! IP: 192.168.1.9
[Main] WiFi connected successfully! IP address: ('192.168.1.9', '255.255.255.0', '192.168.1.1', '192.168.1.1')
INFO:ESP32C3:WiFi connected successfully! IP address: ('192.168.1.9', '255.255.255.0', '192.168.1.1', '192.168.1.1')
[Main] Network ready, can start network services
[Main] Starting NTP time synchronization...
INFO:ESP32C3:Starting NTP time sync: ntp1.aliyun.com
INFO:ESP32C3:[WiFi] Starting NTP sync with server: ntp1.aliyun.com
[Main] NTP time sync successful! Server: ntp1.aliyun.com, attempts: 1
INFO:ESP32C3:NTP time sync successful! Server: ntp1.aliyun.com, attempts: 1
[Main] System time updated: 2025-08-09 18:43:56
INFO:ESP32C3:System time updated: 2025-08-09 18:43:56
INFO:ESP32C3:[WiFi] NTP sync successful after 1 attempts
[Main] System time updated to: 2025-08-09 18:43:56 (timestamp: 808080236), other modules can start time-dependent functions
INFO:ESP32C3:System time updated to: 2025-08-09 18:43:56 (timestamp: 808080236), other modules can start time-dependent functions
[WiFi] NTP time synchronized successfully, timestamp: 808080236
[FSM] State transition: BOOT -> INIT (Event: system.boot)
[FSM] Exiting state: BOOT
[FSM] Entering state: INIT
[Cache] Cache saved to cache.json
[FSM] State transition: INIT -> NETWORKING (Event: system.init)
[FSM] Exiting state: INIT
[FSM] Entering state: NETWORKING
[FSM] State transition: NETWORKING -> RUNNING (Event: wifi.connected)
[FSM] Exiting state: NETWORKING
[FSM] Entering state: RUNNING
[MQTT] Connecting to broker at 192.168.3.15...
[MQTT] Error connecting: [Errno 113] ECONNABORTED
Error in scheduled callback for 'log.error': schedule queue full
Error in scheduled callback for 'system.error': schedule queue full
Error in scheduled callback for 'system.error': schedule queue full
Error in scheduled callback for 'mqtt.disconnected': schedule queue full
Error in scheduled callback for 'system.error': schedule queue full
Error in scheduled callback for 'system.error': schedule queue full
Error in scheduled callback for 'mqtt.disconnected': schedule queue full
Error in scheduled callback for 'system.error': schedule queue full
Error in scheduled callback for 'system.error': schedule queue full
[Main] WiFi connected successfully! IP address: None
INFO:ESP32C3:WiFi connected successfully! IP address: None
[Main] Network ready, can start network services
[Cache] Cache saved to cache.json




