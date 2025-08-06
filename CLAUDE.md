# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

这是一个基于ESP32-C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用模块化架构，提供WiFi连接、MQTT通信、系统监控、LED状态指示和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## Architecture

### Core Components

1. **Main Application** (`src/main.py`)
   - 系统主控制中心，协调各模块运行
   - 实现主循环、内存管理和看门狗喂狗
   - 集成配置管理器、WiFi连接、MQTT通信和守护进程
   - LED状态指示和系统监控功能

2. **Configuration Manager** (`src/config_manager.py`)
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

7. **LED Preset Manager** (`src/led_preset.py`)
   - 统一的LED状态指示管理
   - 多种预设闪烁模式（快闪三下、SOS、心跳等）
   - 系统状态可视化（正常、警告、错误、安全模式）
   - 单例模式设计，避免重复初始化

8. **Boot Sequence** (`src/boot.py`)
   - 垃圾回收初始化
   - 最小化的MicroPython启动脚本

### Advanced Features

9. **State Machine** (`src/state_machine.py`)
   - 清晰的系统状态管理
   - 事件驱动的状态转换
   - 支持INIT、NETWORKING、RUNNING、WARNING、ERROR、SAFE_MODE、RECOVERY、SHUTDOWN状态
   - 状态历史记录和监控

10. **Object Pool** (`src/object_pool.py`)
    - 高效的对象池和缓存管理
    - 字典对象池、字符串缓存、缓冲区管理
    - 减少内存分配和垃圾回收开销
    - 内存优化器提供智能内存管理

11. **Recovery Manager** (`src/recovery_manager.py`)
    - 集中化的错误恢复策略管理
    - 分级恢复动作：网络、内存、服务、系统、硬件恢复
    - 恢复成功率统计和冷却时间管理
    - 智能恢复调度和错误处理

## Key Features

- **多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **MQTT通信**: 高效的MQTT客户端，支持自动重连和内存优化
- **系统监控**: 实时监控温度、内存使用和系统健康状态
- **错误恢复**: 智能错误处理和自动恢复机制
- **内存管理**: 优化的垃圾回收策略，适合ESP32C3的264KB内存限制
- **看门狗保护**: 防止系统死锁，确保设备稳定运行
- **LED状态指示**: 通过LED显示设备运行状态，支持多种预设模式
- **配置管理**: 灵活的配置系统，支持运行时验证

## Configuration

### 配置文件结构
项目使用双重配置系统：
- `src/config.json`: JSON运行时配置（动态参数和设备设置）
- `src/config_manager.py`: Python类常量配置（主要配置和验证规则）

### 主要配置类

#### MQTT配置 (`src/config.json:2-11`)
```json
"mqtt": {
  "broker": "192.168.3.15",
  "port": 1883,
  "topic": "lzs/esp32c3",
  "keepalive": 60,
  "config": {
    "reconnect_delay": 5,
    "max_retries": 3
  }
}
```

#### WiFi配置 (`src/config.json:12-23`)
```json
"wifi": {
  "networks": [
    {"ssid": "zsm60p", "password": "25845600"},
    {"ssid": "leju_software", "password": "leju123456"}
  ],
  "config": {
    "timeout": 15,
    "scan_interval": 30,
    "retry_delay": 2,
    "max_attempts": 3
  }
}
```

#### 守护进程配置 (`src/config.json:24-38`)
```json
"daemon": {
  "config": {
    "led_pins": [12, 13],
    "timer_id": 0,
    "monitor_interval": 5000,
    "temp_threshold": 65,
    "temp_hysteresis": 5,
    "memory_threshold": 80,
    "memory_hysteresis": 10,
    "max_error_count": 10,
    "safe_mode_cooldown": 60000
  },
  "wdt_timeout": 120000,
  "wdt_enabled": false,
  "gc_force_threshold": 95
}
```

#### 系统配置 (`src/config.json:40-46`)
```json
"system": {
  "debug_mode": false,
  "log_level": "INFO",
  "main_loop_delay": 300,
  "status_report_interval": 30,
  "auto_restart_enabled": false
}
```

#### 设备配置 (`src/config.json:47-51`)
```json
"device": {
  "name": "ESP32C3-IOT",
  "location": "未知位置",
  "firmware_version": "1.0.0"
}
```

## Dependencies

- **umqtt.simple**: 轻量级MQTT客户端库 (`src/lib/umqtt/simple.py`)
- **MicroPython标准库**: network, time, machine, ntptime, gc
- **第三方库**: 无，全部使用标准库确保兼容性

## Development Workflow

### 文件上传到设备
使用MicroPython工具上传文件到ESP32C3：
```bash
# 使用rshell或类似工具
rshell cp src/boot.py /pyboard/boot.py
rshell cp src/config_manager.py /pyboard/config_manager.py
rshell cp src/main.py /pyboard/main.py
rshell cp src/config.json /pyboard/config.json
rshell cp src/net_mqtt.py /pyboard/net_mqtt.py
rshell cp src/net_wifi.py /pyboard/net_wifi.py
rshell cp src/sys_daemon.py /pyboard/sys_daemon.py
rshell cp src/sys_error.py /pyboard/sys_error.py
rshell cp src/led_preset.py /pyboard/led_preset.py
rshell cp src/state_machine.py /pyboard/state_machine.py
rshell cp src/object_pool.py /pyboard/object_pool.py
rshell cp src/recovery_manager.py /pyboard/recovery_manager.py
rshell cp src/lib/umqtt/simple.py /pyboard/umqtt/simple.py
```

### 设备测试
主应用程序包含内存监控，每30次循环记录日志。通过串口查看：
- WiFi连接状态
- MQTT连接状态
- 内存使用报告
- 系统日志
- LED状态指示

## LED Preset Manager

### 系统状态模式
- **normal**: 正常运行（LED1亮，LED2灭）
- **warning**: 警告状态（LED1亮，LED2亮）
- **error**: 错误状态（LED1灭，LED2亮）
- **off**: 关闭状态（LED1灭，LED2灭）
- **safe_mode**: 安全模式（SOS闪烁模式）

### 预设闪烁模式
- **快闪三下**: 快速闪烁三次
- **一长两短**: 一个长闪加两个短闪
- **SOS求救信号**: 标准的SOS摩尔斯电码
- **心跳模式**: 模拟心跳节奏的闪烁
- **警灯模式**: 双LED交替闪烁
- **霹雳游侠**: 来回扫描效果
- **计数闪烁**: 数字计数闪烁
- **呼吸灯**: 渐变呼吸效果

### 使用方式
```python
from led_preset import get_led_manager, set_system_status

# 获取LED管理器实例
led_manager = get_led_manager()

# 设置系统状态
set_system_status("normal")  # 正常运行
set_system_status("error")   # 错误状态
set_system_status("safe_mode")  # 安全模式

# 使用预设模式
from led_preset import sos_pattern, heartbeat
sos_pattern(0)  # LED1 SOS模式
heartbeat(1)    # LED2 心跳模式
```

## State Machine System

### 系统状态
- **INIT**: 系统初始化
- **NETWORKING**: 网络连接
- **RUNNING**: 正常运行
- **WARNING**: 警告状态
- **ERROR**: 错误状态
- **SAFE_MODE**: 安全模式
- **RECOVERY**: 恢复模式
- **SHUTDOWN**: 关机状态

### 状态转换事件
- **INIT_COMPLETE**: 初始化完成
- **NETWORK_SUCCESS**: 网络连接成功
- **NETWORK_FAILED**: 网络连接失败
- **SYSTEM_WARNING**: 系统警告
- **SYSTEM_ERROR**: 系统错误
- **MEMORY_CRITICAL**: 内存严重不足
- **SAFE_MODE_TRIGGER**: 安全模式触发
- **RECOVERY_SUCCESS**: 恢复成功
- **RECOVERY_FAILED**: 恢复失败
- **SYSTEM_SHUTDOWN**: 系统关机
- **WATCHDOG_TIMEOUT**: 看门狗超时

## Memory Management

项目实现精细的内存管理：
- **垃圾回收策略**: 定期`gc.collect()`和深度清理
- **内存监控**: 实时监控`gc.mem_free()`和使用百分比
- **优化数据结构**: 使用bytearray进行MQTT消息拼接
- **缓冲区限制**: 限制日志和错误历史记录大小
- **LED状态管理**: 优化的LED控制模式，减少内存占用

### 关键内存优化技术
- 全局变量减少实例化开销
- 智能垃圾回收（根据内存使用动态调整）
- 轻量级数据结构
- 避免复杂对象创建
- 定期内存清理和监控

### 对象池系统
- **字典对象池**: 避免频繁创建销毁字典对象
- **字符串缓存**: 缓存常用字符串减少内存分配
- **缓冲区管理**: 预分配缓冲区管理器
- **内存优化器**: 提供内存监控和优化功能

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

### 恢复管理器
- **网络恢复**: WiFi重连 + MQTT重连
- **内存恢复**: 深度清理 + 对象池重建
- **服务恢复**: 守护进程重启
- **系统恢复**: 状态机管理 + 安全模式
- **硬件恢复**: 系统重启

## Network Behavior

1. **启动流程**: boot.py → main.py → 配置验证 → WiFi连接
2. **WiFi选择**: 扫描网络 → RSSI排序 → 连接最优网络
3. **时间同步**: NTP服务器同步 + 时区设置
4. **MQTT连接**: 连接代理 → 开始发布日志
5. **守护进程启动**: 开始系统监控 → LED控制 → 系统健康检查
6. **主循环**: 看门狗喂狗 → 内存管理 → 状态监控 → LED状态指示

## System Workflow

### 主循环流程
```
喂狗 → 内存监控 → 守护进程状态检查 → 安全模式判断 → 
MQTT连接检查 → LED状态检查 → 状态报告 → 延迟
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

## Hardware Resources

### ESP32-C3 规格
- **内存**: 264KB SRAM
- **存储**: 4MB Flash
- **处理器**: RISC-V 双核 32位
- **无线**: WiFi 802.11b/g/n
- **GPIO**: 22个数字IO引脚
- **接口**: SPI, I2C, UART, ADC

### 引脚分配
- **LED1**: GPIO 12
- **LED2**: GPIO 13
- **看门狗**: 软件实现

## Web Interface

项目包含基于Web Bluetooth的配置界面：
- **位置**: `web/index.html`
- **功能**: 蓝牙连接、WiFi配置、MQTT配置、设备配置
- **设计**: Apple设计风格，响应式布局
- **浏览器要求**: 支持Web Bluetooth API的现代浏览器

## Important Notes

- **内存限制**: ESP32C3只有264KB内存，必须时刻注意内存使用
- **文件位置**: 只允许编辑 `./src` 下一级目录的文件
- **测试代码**: 不要添加测试代码和文件
- **文档**: 不要擅自添加说明文档
- **语言**: 始终使用中文进行代码注释和文档

## Monitoring and Debugging

### 系统监控指标
- 内存使用率（实时监控）
- 温度监控（MCU内部温度）
- 错误计数和统计
- 网络连接状态
- MQTT连接状态
- 系统运行时间

### 调试技巧
- 通过串口查看详细日志
- 监控内存使用情况
- 检查LED状态指示
- 查看错误统计信息
- 使用状态机监控系统状态