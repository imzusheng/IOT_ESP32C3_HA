Rebooting...
ESP-ROM:esp32c3-api1-20210207
Build:Feb  7 2021
rst:0xc (RTC_SW_CPU_RST),boot:0xc (SPI_FAST_FLASH_BOOT)
Saved PC:0x4038066c
SPIWP:0xee
mode:DIO, clock div:1
load:0x3fcd5820,len:0xf28
load:0x403cc710,len:0x944
load:0x403ce710,len:0x2b1c
entry 0x403cc710
[Config] Configuration module loaded.
[LED] LED pattern module loaded
[Sensor] Sensor module loaded
=== ESP32-C3 IoT Device Starting ===
[Main] Configuration loaded
[Cache] Cache loaded from cache.json
INFO:ESP32C3:Logger setup complete. Subscribed to log events.
[WiFi] Activating WLAN interface...
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
[WiFi] Found best network: CMCC-pdRG (RSSI: -27)
[WiFi] Attempting to connect to 'CMCC-pdRG'...
INFO:ESP32C3:[WiFi] Attempting to connect to WiFi network: CMCC-pdRG
[FSM] State transition: BOOT -> INIT (Event: system.boot)
[FSM] Exiting state: BOOT
[FSM] Entering state: INIT
[Cache] Cache saved to cache.json
[WiFi] WiFi connected! IP: 192.168.1.9, SSID: CMCC-pdRG
INFO:ESP32C3:[WiFi] WiFi connected successfully! IP: 192.168.1.9, SSID: CMCC-pdRG
[Main] WiFi connected successfully! IP address: None
INFO:ESP32C3:WiFi connected successfully! IP address: None
[Main] Network ready, can start network services
[WiFi] Starting NTP sync with server: ntp1.aliyun.com
[Main] Starting NTP time synchronization...
INFO:ESP32C3:Starting NTP time sync: default
[WiFi] NTP sync successful after 1 attempts, timestamp: 808104281
[Main] NTP time sync successful! Server: unknown, attempts: unknown
INFO:ESP32C3:NTP time sync successful! Server: unknown, attempts: unknown
[Main] System time updated: 2025-08-10 01:24:41
INFO:ESP32C3:System time updated: 2025-08-10 01:24:41
[Main] System time updated to: 2025-08-10 01:24:41 (timestamp: 808104281), other modules can start time-dependent functions
INFO:ESP32C3:System time updated to: 2025-08-10 01:24:41 (timestamp: 808104281), other modules can start time-dependent functions
[FSM] State transition: INIT -> NETWORKING (Event: system.init)
[FSM] Exiting state: INIT
[FSM] Entering state: NETWORKING
[Cache] Cache saved to cache.json


