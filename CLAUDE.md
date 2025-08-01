# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 始终使用中文
- 只允许编辑 ./src 一级目录的代码, 因为这是 micropython 项目的代码， 也是 ESP32C3 的代码根目录
- 代码是在嵌入式设备运行， 需要时刻注意代码的RAM使用情况以及内存泄漏问题
- 完成时移除所有测试代码和文件
- 不要擅自添加说明文档
- 不需要添加本地测试的代码

## Project Overview

This is a MicroPython project for ESP32C3 IoT devices that connects to WiFi networks and publishes data via MQTT to a Home Assistant system. The project implements a robust network manager with automatic failover and comprehensive logging capabilities.

## Architecture

### Core Components

1. **Main Application** (`src/main.py`)
   - Entry point that orchestrates WiFi connection and MQTT communication
   - Implements main loop with periodic connection checks and memory management
   - Configures MQTT broker, topic, and client ID using device's unique ID

2. **WiFi Manager** (`src/wifi_manager.py`)
   - Robust WiFi connection manager with multi-network support
   - Automatic network scanning and RSSI-based selection
   - NTP time synchronization with timezone support
   - Connection timeout handling and error recovery

3. **MQTT Client** (`src/mqtt.py`)
   - Custom MQTT wrapper using umqtt.simple library
   - Connection management with automatic reconnection
   - Structured logging with timestamps and memory-efficient message formatting
   - Heartbeat monitoring and connection state tracking

4. **Boot Sequence** (`src/boot.py`)
   - Garbage collection initialization for memory management
   - Minimal startup script for MicroPython environment

### Key Features

- **Multi-network WiFi support**: Automatically connects to the strongest available configured network
- **MQTT logging**: Publishes structured logs with timestamps to MQTT topics
- **Memory management**: Implements garbage collection and memory monitoring
- **Connection resilience**: Automatic reconnection for both WiFi and MQTT
- **Time synchronization**: NTP-based time sync with timezone offset support

## Configuration

### WiFi Configuration
Located in `src/wifi_manager.py:15-19`:
```python
WIFI_CONFIGS = [
    {"ssid": "zsm60p", "password": "25845600"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
    {"ssid": "leju_software", "password": "leju123456"}
]
```

### MQTT Configuration
Located in `src/main.py:7-10`:
```python
MQTT_BROKER = "192.168.1.2"
MQTT_TOPIC = "lzs/esp32c3"
CLIENT_ID = f"esp32c3-client-{machine.unique_id().hex()}"
```

### NTP Configuration
Located in `src/wifi_manager.py:28-31`:
```python
NTP_HOST = 'ntp.aliyun.com'
TIMEZONE_OFFSET_H = 8
```

## Dependencies

- **umqtt.simple**: Lightweight MQTT client library for MicroPython
- **MicroPython standard libraries**: network, time, machine, ntptime, socket, struct, binascii

## Development Workflow

### File Upload to Device
Use MicroPython tools to upload files to ESP32C3:
```bash
# Using rshell or similar tools
rshell cp src/main.py /pyboard/main.py
rshell cp src/mqtt.py /pyboard/mqtt.py
rshell cp src/wifi_manager.py /pyboard/wifi_manager.py
rshell cp src/boot.py /pyboard/boot.py
```

### Device Testing
The main application includes memory monitoring and logs loop count every 30 iterations. Check device serial output for:
- WiFi connection status
- MQTT connection state
- Memory usage reports
- System logs

## Memory Management

The project implements careful memory management:
- Periodic garbage collection (`gc.collect()`)
- Memory monitoring with `gc.mem_free()`
- Efficient string concatenation using `bytearray` for MQTT messages
- Minimal memory footprint design for constrained ESP32C3 environment

## Error Handling

- WiFi connection timeouts with automatic retry
- MQTT connection loss detection and reconnection
- Network scanning failures with graceful degradation
- Memory allocation monitoring and recovery
- Color-coded console output for different log levels

## Network Behavior

1. **Boot sequence**: Initialize garbage collection, attempt WiFi connection
2. **WiFi selection**: Scan for available networks, connect to strongest configured network
3. **Time sync**: Synchronize with NTP server after successful WiFi connection
4. **MQTT connection**: Connect to broker and start publishing logs
5. **Main loop**: Periodic connection checks, memory management, and logging