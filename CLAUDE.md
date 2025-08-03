# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 始终使用中文
<!-- - 只允许编辑 ./src 一级目录的代码, 因为这是 micropython 项目的代码， 也是 ESP32C3 的代码根目录 -->
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

5. **Bluetooth Scanner** (`src/ble_scanner.py`)
   - Memory-optimized BLE device scanner for ESP32C3
   - Enhanced device information display with MAC addresses and device names
   - Comprehensive BLE advertising data parsing (names, services, manufacturer data)
   - Interactive device selection with detailed information viewing
   - Debug mode for analyzing raw advertising data
   - Multiple scan modes: interactive, simple, and parse-only
   - UTF-8 encoding support for Chinese device names
   - Integration with MQTT for Home Assistant compatibility
   - Configurable scan parameters and memory management
   - Standard MAC address formatting (XX:XX:XX:XX:XX:XX)
   - Standard BLE advertising data parsing based on BLE_ADV.md specification
   - Efficient name parsing using only standard types 0x08 (Short Name) and 0x09 (Complete Name)

### Key Features

- **Multi-network WiFi support**: Automatically connects to the strongest available configured network
- **MQTT logging**: Publishes structured logs with timestamps to MQTT topics
- **Memory management**: Implements garbage collection and memory monitoring
- **Connection resilience**: Automatic reconnection for both WiFi and MQTT
- **Time synchronization**: NTP-based time sync with timezone offset support
- **Bluetooth scanning**: Memory-optimized BLE device scanning with MQTT integration
- **Chinese device name support**: UTF-8 encoding for Chinese and special characters
- **Configuration-based**: All parameters configurable via JSON configuration file
- **Standard device name parsing**: Efficient parsing using BLE standard types 0x08 and 0x09 based on BLE_ADV.md specification
- **Standard MAC address display**: Formatted MAC addresses with colon separators (XX:XX:XX:XX:XX:XX)

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

### Bluetooth Configuration
Located in `src/config.json:51-57`:
```json
"bluetooth": {
  "scan_enabled": true,
  "scan_interval": 300,
  "max_devices": 10,
  "scan_duration": 8000,
  "memory_threshold": 90
}
```

## Dependencies

- **umqtt.simple**: Lightweight MQTT client library for MicroPython
- **MicroPython standard libraries**: network, time, machine, ntptime, socket, struct, binascii
- **bluetooth**: MicroPython Bluetooth library for BLE scanning

## Development Workflow

### File Upload to Device
Use MicroPython tools to upload files to ESP32C3:
```bash
# Using rshell or similar tools
rshell cp src/main.py /pyboard/main.py
rshell cp src/mqtt.py /pyboard/mqtt.py
rshell cp src/wifi_manager.py /pyboard/wifi_manager.py
rshell cp src/boot.py /pyboard/boot.py
rshell cp src/ble_scanner.py /pyboard/ble_scanner.py
rshell cp src/config.json /pyboard/config.json
```

### Device Testing
The main application includes memory monitoring and logs loop count every 30 iterations. Check device serial output for:
- WiFi connection status
- MQTT connection state
- Memory usage reports
- System logs
- Bluetooth scanning results
- Device discovery notifications

## Memory Management

The project implements careful memory management:
- Periodic garbage collection (`gc.collect()`)
- Memory monitoring with `gc.mem_free()`
- Efficient string concatenation using `bytearray` for MQTT messages
- Minimal memory footprint design for constrained ESP32C3 environment
- Bluetooth scanner memory optimization:
  - Pre-allocated buffers to reduce memory allocation
  - Device count limits to prevent memory overflow
  - Memory threshold monitoring (configurable)
  - Smart garbage collection before and after scans

## Error Handling

- WiFi connection timeouts with automatic retry
- MQTT connection loss detection and reconnection
- Network scanning failures with graceful degradation
- Memory allocation monitoring and recovery
- Color-coded console output for different log levels
- Bluetooth scanning error handling:
  - Scan timeout protection with automatic recovery
  - Memory threshold monitoring to prevent crashes
  - Scanner auto-reset on critical errors
  - UTF-8 decoding error handling for device names

## Network Behavior

1. **Boot sequence**: Initialize garbage collection, attempt WiFi connection
2. **WiFi selection**: Scan for available networks, connect to strongest configured network
3. **Time sync**: Synchronize with NTP server after successful WiFi connection
4. **MQTT connection**: Connect to broker and start publishing logs
5. **Main loop**: Periodic connection checks, memory management, and logging
6. **Bluetooth scanning**: Periodic BLE device scanning with configurable intervals
7. **Device reporting**: Send discovered devices to MQTT topic for Home Assistant integration

## Bluetooth Features

### Scanning Capabilities
- **BLE device discovery**: Scans for nearby Bluetooth Low Energy devices
- **Enhanced device information display**: Shows MAC addresses, device names, signal strength, address type, and service count
- **Comprehensive advertising data parsing**: Extracts device names, service UUIDs, manufacturer data, appearance, TX power, and flags
- **Signal strength monitoring**: Records RSSI values for each discovered device
- **Memory-optimized parsing**: Efficient packet parsing to minimize memory usage

### BLE Scanner Usage Modes

#### Interactive Mode
```bash
python ble_scanner.py                    # Standard interactive mode
python ble_scanner.py debug              # Debug mode with raw advertising data
python ble_scanner.py 10                 # 10-second scan
python ble_scanner.py debug 15            # Debug mode with 15-second scan
```

#### Simple Mode
```bash
python ble_scanner.py simple             # Simple scan with debug output
```

#### Parse Mode
```bash
python ble_scanner.py parse <hex_data>   # Parse hex advertising data
python ble_scanner.py parse 0319C1001409434F524F532050414345203220414232453037
```

#### Test Mode
```bash
python ble_scanner.py test               # Test parsing functionality
```

### Device Information Display
The scanner displays devices in a formatted table with columns:
- **序号**: Device index number
- **信号**: Signal strength (RSSI) in dBm
- **地址**: MAC address in standard format (XX:XX:XX:XX:XX:XX)
- **名称**: Device name (truncated if too long)
- **类型**: Address type (Public/Random)
- **服务**: Number of service UUIDs discovered

### Interactive Features
- **Device selection**: Choose devices by index number
- **Detailed view**: View complete device information including advertising data
- **Advertising data analysis**: Raw hex data parsing with field-by-field breakdown
- **Confirmation prompts**: Confirm device selection before proceeding

### Debug Capabilities
- **Raw advertising data display**: Shows hex data for each discovered device
- **Field-by-field parsing**: Detailed breakdown of advertising packet structure
- **Memory monitoring**: Real-time memory usage reports
- **Error handling**: Comprehensive error reporting and recovery
- **Enhanced name parsing debug**: Shows detailed parsing process for device names
- **Alternative parsing methods**: Attempts multiple approaches to extract device names from non-standard advertising data formats
- **Real-time field analysis**: Displays all field types and attempts to extract names from any printable character sequences

### MQTT Integration
- **Automatic reporting**: Sends scan results to configured MQTT topic
- **Structured data**: JSON format with device information and timestamps
- **Configurable reporting**: Adjustable scan intervals and device limits
- **Home Assistant ready**: Direct integration with Home Assistant device tracking

### Configuration Options
- `scan_enabled`: Enable/disable Bluetooth scanning
- `scan_interval`: Time between scans in seconds (default: 300)
- `max_devices`: Maximum number of devices to track (default: 10)
- `scan_duration`: Scan duration in milliseconds (default: 8000)
- `memory_threshold`: Memory usage threshold percentage (default: 90)

### BLE Advertising Data Parsing
The scanner supports comprehensive parsing of BLE advertising data fields:
- **Flags**: Device discoverability and connection modes
- **Service UUIDs**: 16-bit, 32-bit, and 128-bit service identifiers
- **Local Name**: Complete and short device names with UTF-8 support
- **TX Power Level**: Transmit power level information
- **Appearance**: Device appearance identifier
- **Manufacturer Data**: Manufacturer-specific data
- **Device Class**: Bluetooth device class information
- **Standard Name Parsing**: Efficient parsing based on BLE_ADV.md specification:
  - Length field: 1 byte indicating data length
  - Type field: 1 byte (0x08 for short name, 0x09 for complete name)
  - Data content: Variable length name data in UTF-8 encoding