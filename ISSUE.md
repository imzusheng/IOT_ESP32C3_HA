```日志反映了两点问题
[WiFi] 网络 27: SSID='8551' | RSSI=-83 dBm | CH=13 | BSSID=9ca615c01b21
[WiFi] 网络 28: SSID='Topway_2.4G_419874' | RSSI=-84 dBm | CH=1 | BSSID=f4285300db80
[WiFi] 网络 29: SSID='CMCC-TmnT' | RSSI=-84 dBm | CH=10 | BSSID=9cf8b880fbf6
[WiFi] 网络 30: SSID='' | RSSI=-86 dBm | CH=2 | BSSID=6a77da3b841d
[WiFi] ! 发现相似网络: '' (目标: 'leju_software')
[WiFi] ! 发现相似网络: '' (目标: 'zsm60p')
[WiFi] 网络 31: SSID='midea_db_0143' | RSSI=-87 dBm | CH=1 | BSSID=d48457dfb7fa
[WiFi] 网络 32: SSID='' | RSSI=-87 dBm | CH=1 | BSSID=eed9d1c72808
[WiFi] ! 发现相似网络: '' (目标: 'leju_software')
[WiFi] ! 发现相似网络: '' (目标: 'zsm60p')
[WiFi] 网络 33: SSID='RHX-8Q10#duorunduoLED' | RSSI=-87 dBm | CH=1 | BSSID=9af4abcf51c2
[WiFi] 网络 34: SSID='8452' | RSSI=-87 dBm | CH=13 | BSSID=d076e73cae54
[WiFi] 网络 35: SSID='8420' | RSSI=-88 dBm | CH=13 | BSSID=d076e73cb206
[WiFi] 网络 36: SSID='Topway_2.4G_181276' | RSSI=-89 dBm | CH=1 | BSSID=f4285300dec6
[WiFi] 网络 37: SSID='CMCC-2EdA' | RSSI=-90 dBm | CH=3 | BSSID=9cf8b88163c6
[WiFi] 网络 38: SSID='8515' | RSSI=-90 dBm | CH=13 | BSSID=d076e73caaec
[WiFi] 匹配的网络数量: 0
[WiFi] 未找到配置的网络
[Main] WiFi连接失败
[Main] 网络连接失败，进入警告状态
[Daemon] 强制进入安全模式: 网络连接失败
[Daemon] 初始化LED控制器用于安全模式
[Daemon] LED控制器初始化完成，使用LED预设模块
[Daemon] LED已设置为安全模式（SOS模式）
[Daemon] 安全模式已激活，LED显示SOS模式
[MQTT] MQTT客户端创建完成，服务器: 192.168.3.15:1883, 主题: 'lzs/esp32c3'
[MQTT] 连接失败 (尝试 1/3): [Errno 118] EHOSTUNREACH
[Main] MQTT连接失败
[Main] MQTT客户端创建失败
[Daemon] 开始启动守护进程...
[Daemon] 初始化LED控制器，引脚: [12, 13]
[Daemon] LED控制器初始化完成，使用LED预设模块
[Daemon] 初始化定时器，间隔: 5000ms
[Daemon] 守护进程启动成功
[Main] 守护进程启动成功
[Main] 初始化完成，当前状态: ERROR
[Main] 开始状态机主循环
[Main] 处理错误状态...
[Main] 处理错误状态...
[Main] 处理错误状态...
[Main] 处理错误状态...
[Main] 处理错误状态...
[Main] 处理错误状态...
[Main] 处理错误状态...
```

1. 当前出现错误是因为MQTT未连接，这是正常的因为我切换了网络， 但是出现错误状态时，没有看到LED进入指定闪烁程序， 安全模式应该LED闪烁

2. WIFI 搜索会提示发现空字符串为相似网络