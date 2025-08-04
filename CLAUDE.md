# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 始终使用中文
- 代码是在嵌入式设备运行， 需要时刻注意代码的RAM使用情况以及内存泄漏问题
- 只允许编辑 ./src 下一级目录的文件
- 完成时移除所有测试代码和文件
- 不要擅自添加说明文档
- 不需要测试代码

## Project Overview

这是一个基于ESP32C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用模块化架构，提供WiFi连接、MQTT通信、系统监控、蓝牙扫描和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## Architecture

### Core Components

1. **Main Application** (`src/main.py`)
   - 系统主控制中心，协调各模块运行
   - 实现主循环、内存管理和看门狗喂狗
   - 集成配置管理器、WiFi连接、MQTT通信和守护进程
   - 蓝牙扫描集成和设备发现功能

2. **Configuration Manager** (`src/config.py`)
   - 集中式配置管理，使用类常量定义所有参数
   - 配置验证器，启动时自动验证配置有效性
   - 分模块配置：MQTTConfig、WiFiConfig、DaemonConfig、SystemConfig
   - 内存优化：避免JSON文件，减少I/O操作

3. **WiFi Manager** (`src/net_wifi.py`)
   - 健壮的WiFi连接管理，支持多网络选择
   - 自动网络扫描和RSSI-based排序
   - NTP时间同步和时区设置
   - 连接超时处理和错误恢复

4. **MQTT Client** (`src/net_mqtt.py`)
   - 基于umqtt.simple的自定义MQTT包装器
   - 连接管理和自动重连机制
   - 内存优化的日志发送（使用bytearray）
   - 心跳监控和连接状态跟踪

5. **System Daemon** (`src/sys_daemon.py`)
   - 系统监控和安全保护功能
   - LED状态指示控制
   - 温度监控和安全模式
   - 内存监控和垃圾回收
   - 系统健康检查和错误恢复

6. **Error Handler** (`src/sys_error.py`)
   - 统一错误处理和日志管理
   - 智能错误分类和恢复机制
   - 内存友好的日志缓冲
   - 自动错误恢复和系统重启

7. **Bluetooth Scanner** (`src/ble_scanner.py`)
   - 内存优化的BLE设备扫描器
   - 增强的设备信息显示和名称解析
   - 标准BLE广告数据解析
   - 多种扫描模式和调试功能
   - MQTT集成用于Home Assistant兼容性

8. **Boot Sequence** (`src/boot.py`)
   - 垃圾回收初始化
   - 最小化的MicroPython启动脚本

### Key Features

- **多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **MQTT通信**: 高效的MQTT客户端，支持自动重连和内存优化
- **系统监控**: 实时监控温度、内存使用和系统健康状态
- **错误恢复**: 智能错误处理和自动恢复机制
- **内存管理**: 优化的垃圾回收策略，适合ESP32C3的264KB内存限制
- **看门狗保护**: 防止系统死锁，确保设备稳定运行
- **LED状态指示**: 通过LED显示设备运行状态
- **蓝牙扫描**: 内存优化的BLE设备扫描与MQTT集成
- **配置管理**: 灵活的配置系统，支持运行时验证

## Configuration

### 配置文件结构
项目使用双重配置系统：
- `src/config.py`: Python类常量配置（主要配置）
- `src/config.json`: JSON运行时配置（蓝牙和动态参数）

### 主要配置类

#### MQTT配置 (`src/config.py:21-44`)
```python
class MQTTConfig:
    BROKER = "192.168.3.15"         # MQTT服务器地址
    PORT = 1883                     # MQTT端口
    TOPIC = "lzs/esp32c3"          # 设备主题
    KEEPALIVE = 60                 # 心跳间隔
    CONNECT_TIMEOUT = 10           # 连接超时
    RECONNECT_DELAY = 5            # 重连延迟
    MAX_RETRIES = 3                # 最大重试次数
```

#### WiFi配置 (`src/config.py:49-72`)
```python
class WiFiConfig:
    TIMEOUT_S = 15                 # 连接超时
    SCAN_INTERVAL = 30             # 扫描间隔
    NETWORKS = [
        {"ssid": "zsm60p", "password": "25845600"},
        {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
        {"ssid": "leju_software", "password": "leju123456"}
    ]
```

#### 守护进程配置 (`src/config.py:78-122`)
```python
class DaemonConfig:
    LED_PINS = [12, 13]           # LED引脚
    TEMP_THRESHOLD = 60.0          # 温度阈值
    MEMORY_THRESHOLD = 90         # 内存阈值
    WDT_TIMEOUT = 10000           # 看门狗超时
    MONITOR_INTERVAL = 30000      # 监控间隔
```

#### 蓝牙配置 (`src/config.json:51-57`)
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

- **umqtt.simple**: 轻量级MQTT客户端库 (`src/lib/umqtt/simple.py`)
- **MicroPython标准库**: network, time, machine, ntptime, bluetooth, gc
- **第三方库**: 无，全部使用标准库确保兼容性

## Development Workflow

### 文件上传到设备
使用MicroPython工具上传文件到ESP32C3：
```bash
# 使用rshell或类似工具
rshell cp src/boot.py /pyboard/boot.py
rshell cp src/config.py /pyboard/config.py
rshell cp src/main.py /pyboard/main.py
rshell cp src/net_mqtt.py /pyboard/net_mqtt.py
rshell cp src/net_wifi.py /pyboard/net_wifi.py
rshell cp src/sys_daemon.py /pyboard/sys_daemon.py
rshell cp src/sys_error.py /pyboard/sys_error.py
rshell cp src/ble_scanner.py /pyboard/ble_scanner.py
rshell cp src/config.json /pyboard/config.json
rshell cp src/lib/umqtt/simple.py /pyboard/umqtt/simple.py
```

### 设备测试
主应用程序包含内存监控，每30次循环记录日志。通过串口查看：
- WiFi连接状态
- MQTT连接状态
- 内存使用报告
- 系统日志
- 蓝牙扫描结果
- 设备发现通知

## Memory Management

项目实现精细的内存管理：
- **垃圾回收策略**: 定期`gc.collect()`和深度清理
- **内存监控**: 实时监控`gc.mem_free()`和使用百分比
- **优化数据结构**: 使用bytearray进行MQTT消息拼接
- **缓冲区限制**: 限制日志和错误历史记录大小
- **蓝牙扫描优化**: 预分配缓冲区、设备数量限制、内存阈值监控

### 关键内存优化技术
- 全局变量减少实例化开销
- 智能垃圾回收（根据内存使用动态调整）
- 轻量级数据结构
- 避免复杂对象创建
- 定期内存清理和监控

## Error Handling

### 错误类型分类
- **NETWORK**: 网络连接错误
- **HARDWARE**: 硬件故障
- **MEMORY**: 内存不足
- **CONFIG**: 配置错误
- **SYSTEM**: 系统错误
- **MQTT**: MQTT通信错误
- **WIFI**: WiFi连接错误
- **DAEMON**: 守护进程错误
- **FATAL**: 致命错误

### 错误恢复策略
- **重试机制**: 自动重试失败操作
- **内存清理**: 深度垃圾回收
- **连接重置**: 重置网络连接
- **安全模式**: 进入降级运行模式
- **系统重启**: 致命错误时自动重启

## Network Behavior

1. **启动流程**: boot.py → main.py → 配置验证 → WiFi连接
2. **WiFi选择**: 扫描网络 → RSSI排序 → 连接最优网络
3. **时间同步**: NTP服务器同步 + 时区设置
4. **MQTT连接**: 连接代理 → 开始发布日志
5. **守护进程**: 启动监控 → LED控制 → 系统健康检查
6. **主循环**: 看门狗喂狗 → 内存管理 → 状态监控 → 蓝牙扫描
7. **蓝牙扫描**: 定期扫描 → 设备发现 → MQTT报告

## Bluetooth Features

### 扫描能力
- **BLE设备发现**: 扫描附近的蓝牙低功耗设备
- **增强设备信息**: 显示MAC地址、设备名称、信号强度、地址类型、服务数量
- **广告数据解析**: 解析设备名称、服务UUID、制造商数据、外观、发射功率等
- **信号强度监控**: 记录每个发现设备的RSSI值
- **内存优化解析**: 高效数据包解析最小化内存使用

### 扫描模式
- **交互模式**: 标准交互式设备扫描和选择
- **调试模式**: 显示原始广告数据和详细解析过程
- **简单模式**: 带调试输出的简单扫描
- **解析模式**: 解析十六进制广告数据
- **测试模式**: 测试解析功能

### 设备信息显示
扫描器以格式化表格显示设备：
- **序号**: 设备索引号
- **信号**: 信号强度（RSSI，dBm）
- **地址**: 标准格式MAC地址（XX:XX:XX:XX:XX:XX）
- **名称**: 设备名称（过长时截断）
- **类型**: 地址类型（Public/Random）
- **服务**: 发现的服务UUID数量

### MQTT集成
- **自动报告**: 发送扫描结果到配置的MQTT主题
- **结构化数据**: JSON格式的设备信息和时间戳
- **可配置报告**: 可调整扫描间隔和设备限制
- **Home Assistant就绪**: 直接集成Home Assistant设备跟踪

## System Workflow

### 主循环流程
```
喂狗 → 内存监控 → 守护进程状态检查 → 安全模式判断 → 
MQTT连接检查 → 蓝牙扫描 → 状态报告 → 延迟
```

### 错误处理流程
```
错误发生 → 错误分类 → 严重程度判断 → 执行恢复动作 → 
记录日志 → 继续运行/进入安全模式/重启
```

### 内存管理流程
```
内存监控 → 阈值检查 → 垃圾回收 → 深度清理 → 
状态报告 → 继续监控
```