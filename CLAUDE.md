# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 全程使用中文

## Project Overview

这是一个基于ESP32-C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用模块化架构，提供WiFi连接、MQTT通信、系统监控、LED状态指示和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## Architecture

### Core Components

1. **Main Application** (`src/main.py`)
   - 系统主控制中心，协调各模块运行
   - 实现主循环、内存管理和看门狗喂狗
   - 集成配置管理器、WiFi连接、MQTT通信和守护进程
   - LED状态指示和系统监控功能

2. **Configuration Manager** (`src/config.py`)
   - 集中式配置管理，使用Python字典定义所有参数
   - 详细的配置说明和推荐值
   - 分模块配置：MQTT、WiFi、守护进程、系统、设备配置
   - 内存优化：避免JSON文件，减少I/O操作

3. **WiFi Manager** (`src/lib/net_wifi.py`)
   - 健壮的WiFi连接管理，支持多网络选择
   - 自动网络扫描和RSSI-based排序
   - NTP时间同步和时区设置
   - 连接超时处理和错误恢复

4. **MQTT Client** (`src/lib/net_mqtt.py`)
   - 基于umqtt.simple的自定义MQTT包装器
   - 智能连接管理和指数退避重连机制
   - 内存优化的日志发送（使用bytearray）
   - 心跳监控和连接状态跟踪
   - 重连冷却时间和重置机制

5. **System Daemon** (`src/sys_daemon.py`)
   - 系统监控和安全保护功能
   - LED状态指示控制
   - 温度监控和安全模式
   - 内存监控和垃圾回收
   - 系统健康检查和错误恢复

6. **Error Handler** (`src/lib/sys/logger.py`)
   - 统一错误处理和日志管理
   - 智能错误分类和恢复机制
   - 内存友好的日志缓冲
   - 自动错误恢复和系统重启

7. **LED Preset Manager** (`src/lib/sys/led.py`)
   - 统一的LED状态指示管理
   - 多种预设闪烁模式（快闪三下、SOS、心跳等）
   - 系统状态可视化（正常、警告、错误、安全模式）
   - 单例模式设计，避免重复初始化

8. **Boot Sequence** (`src/boot.py`)
   - 垃圾回收初始化
   - 最小化的MicroPython启动脚本

### Advanced Features

9. **State Machine** (`src/lib/sys/fsm.py`)
   - 清晰的系统状态管理
   - 事件驱动的状态转换
   - 支持INIT、NETWORKING、RUNNING、WARNING、ERROR、SAFE_MODE、RECOVERY、SHUTDOWN状态
   - 状态历史记录和监控

10. **Object Pool** (`src/lib/sys/memo.py`)
    - 高效的对象池和缓存管理
    - 字典对象池、字符串缓存、缓冲区管理
    - 减少内存分配和垃圾回收开销
    - 内存优化器提供智能内存管理

11. **Recovery Manager** (`src/lib/sys/erm.py`)
    - 集中化的错误恢复策略管理
    - 分级恢复动作：网络、内存、服务、系统、硬件恢复
    - 恢复成功率统计和冷却时间管理
    - 智能恢复调度和错误处理

## Key Features

- **多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **MQTT通信**: 高效的MQTT客户端，支持指数退避重连策略和内存优化
- **系统监控**: 实时监控温度、内存使用和系统健康状态
- **错误恢复**: 智能错误处理和自动恢复机制
- **内存管理**: 优化的垃圾回收策略，适合ESP32C3的264KB内存限制
- **看门狗保护**: 防止系统死锁，确保设备稳定运行
- **LED状态指示**: 通过LED显示设备运行状态，支持多种预设模式
- **配置管理**: 灵活的配置系统，支持运行时验证

## Configuration

### 配置文件结构
项目使用纯Python配置系统：
- `src/config.py`: Python字典配置（主要配置和验证规则）

### 配置管理原则
- **统一配置源**: 所有配置参数都从`src/config.py`中获取
- **避免硬编码**: 任何模块中不应有硬编码的配置值
- **配置一致性**: 确保所有模块使用相同的配置参数
- **运行时验证**: 配置加载时进行参数验证和类型检查

### 主要配置类

#### MQTT配置 (`src/config.py:18-62`)
```python
"mqtt": {
  "broker": "192.168.3.15",
  "port": 1883,
  "topic": "lzs/esp32c3",
  "keepalive": 60,
  "reconnect_delay": 5,
  "max_retries": 3,
  "exponential_backoff": True,
  "max_backoff_time": 300,
  "backoff_multiplier": 2
}
```

#### WiFi配置 (`src/config.py:51-80`)
```python
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

#### 守护进程配置 (`src/config.py:81-142`)
```python
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
  "wdt_enabled": False,
  "gc_force_threshold": 95
}
```

#### 系统配置 (`src/config.py:143-168`)
```python
"system": {
  "debug_mode": False,
  "log_level": "INFO",
  "main_loop_delay": 300,
  "status_report_interval": 30,
  "auto_restart_enabled": False
}
```

#### 设备配置 (`src/config.py:169-184`)
```python
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

### 构建和部署

使用 [`build_m.py`](build_m.py) 脚本编译和部署项目：

```bash
# 构建项目（排除测试文件）
python build_m.py

# 构建项目（包含测试文件）
python build_m.py --test

# 仅编译不部署
python build_m.py --compile

# 上传并监听设备输出
python build_m.py --upload

# 指定端口上传
python build_m.py --upload --port COM3

# 启用完整REPL交互模式
python build_m.py --upload --repl

# 使用原始REPL模式（调试用）
python build_m.py --upload --raw-repl

# 诊断设备安全模式状态
python build_m.py --diagnose

# 清理本地缓存
python build_m.py --clean-cache
```

构建脚本功能：
- **编译**: 使用 mpy-cross 编译 Python 文件为 .mpy 格式（排除 boot.py 和 main.py）
- **上传**: 使用 mpremote 自动检测 ESP32 设备并上传文件
- **监控**: 实时监控设备串口输出，支持中文编码处理
- **设备检测**: 自动识别 ESP32-C3 设备端口（支持多种USB转串口芯片）
- **安全模式处理**: 智能检测和处理设备安全模式状态
- **缓存管理**: 智能文件上传缓存，避免重复上传未修改文件

### 文件上传到设备
构建脚本会自动处理文件上传，也可手动使用 MicroPython 工具：
```bash
# 使用 mpremote（推荐）
mpremote connect <port> fs cp -r dist/ /

# 使用 rshell
rshell cp dist/* /pyboard/ -r
```

### 设备监控和调试

#### 实时监控
构建脚本支持多种监控模式：
- **安全监控模式**: 智能处理中文编码，避免特殊字符导致的崩溃
- **原始REPL模式**: 查看所有原始输出（可能遇到编码问题）
- **交互REPL模式**: 完整的Python交互环境，可执行代码和查看状态

#### 监控指标
通过串口查看：
- WiFi连接状态和网络扫描结果
- MQTT连接状态和消息发布
- 内存使用报告和垃圾回收统计
- 系统运行时间和错误计数
- LED状态指示和系统状态转换
- CPU温度监控和看门狗状态

#### 调试技巧
- 使用 `--verbose` 参数查看详细构建信息
- 使用 `--repl` 参数进入完整交互模式进行远程调试
- 监控模式下按 Ctrl+C 停止监听
- 使用 `--diagnose` 参数诊断设备安全模式问题

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
from lib.sys import led as led_preset

# 获取LED管理器实例
led_manager = led_preset.get_led_manager()

# 设置系统状态
led_manager.set_system_status(led_preset.SYSTEM_NORMAL)  # 正常运行
led_manager.set_system_status(led_preset.SYSTEM_ERROR)   # 错误状态
led_manager.set_system_status(led_preset.SYSTEM_SAFE_MODE)  # 安全模式

# 使用预设模式
led_preset.sos_pattern(0)  # LED1 SOS模式
led_preset.heartbeat(1)    # LED2 心跳模式
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
- **配置驱动的内存管理**: 内存阈值和垃圾回收策略从配置文件获取

### 对象池系统
- **字典对象池**: 避免频繁创建销毁字典对象
- **字符串缓存**: 缓存常用字符串减少内存分配
- **缓冲区管理**: 预分配缓冲区管理器
- **内存优化器**: 提供内存监控和优化功能
- **配置化参数**: 对象池大小和缓存策略从配置文件获取

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
- **配置驱动的恢复策略**: 所有恢复参数和超时时间从配置文件获取

## Network Behavior

1. **启动流程**: boot.py → main.py → 配置验证 → WiFi连接
2. **WiFi选择**: 扫描网络 → RSSI排序 → 连接最优网络
3. **时间同步**: NTP服务器同步 + 时区设置
4. **MQTT连接**: 连接代理 → 开始发布日志
5. **守护进程启动**: 开始系统监控 → LED控制 → 系统健康检查
6. **主循环**: 看门狗喂狗 → 内存管理 → 状态监控 → LED状态指示

## MQTT 重连机制

### 指数退避策略
当MQTT连接断开时，系统采用智能的指数退避重连策略，避免频繁重试消耗资源：

#### 重连流程
1. **第1轮**: 立即重试3次
2. **第2轮**: 等待5秒后重试3次
3. **第3轮**: 等待10秒后重试3次
4. **第4轮**: 等待20秒后重试3次
5. **第5轮**: 等待40秒后重试3次
6. **第6轮**: 等待80秒后重试3次
7. **第7轮**: 等待160秒后重试3次
8. **第8轮及以后**: 等待300秒（最大值）后重试3次

#### 配置参数
- `exponential_backoff`: 是否启用指数退避策略（默认：True）
- `max_backoff_time`: 最大退避时间，单位秒（默认：300）
- `backoff_multiplier`: 退避倍数因子（默认：2）
- `reconnect_delay`: 初始重连延迟，单位秒（默认：5）
- `max_retries`: 每轮最大重试次数（默认：3）

#### 重连特性
- **渐进式等待**: 重连间隔按指数增长，避免服务器压力
- **最大限制**: 退避时间不会超过配置的最大值
- **自动重置**: 连接成功后重置所有计数器
- **内存优化**: 每轮重试后执行垃圾回收
- **状态监控**: 提供详细的连接状态和重连统计

#### 日志示例
```
[MQTT] Connection failed (attempt 1/3): ECONNRESET
[MQTT] Connection failed (attempt 2/3): ECONNRESET
[MQTT] Connection failed (attempt 3/3): ECONNRESET
[MQTT] Starting exponential backoff: waiting 5s (cycle 1)
[MQTT] Starting exponential backoff: waiting 10s (cycle 2)
[MQTT] Starting exponential backoff: waiting 20s (cycle 3)
[MQTT] MQTT connection successful
```

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
内存监控 → 配置阈值检查 → 垃圾回收 → 深度清理 → 
状态报告 → 继续监控
```

## Configuration Usage Guidelines

### 配置参数访问方式
所有模块应使用统一的配置访问方式：

```python
from config import get_config_value

# 获取配置参数
mqtt_broker = get_config_value(config, 'mqtt', 'broker')
wifi_timeout = get_config_value(config, 'wifi', 'config', 'timeout')
led_pins = get_config_value(config, 'daemon', 'config', 'led_pins')
```

### 配置参数命名规范
- 使用小写字母和下划线分隔单词
- 配置键名应具有描述性和一致性
- 布尔值配置使用`enabled`/`disabled`而不是`true`/`false`
- 时间配置统一使用毫秒为单位

### 配置验证规则
- **必需参数**: MQTT broker、WiFi网络列表、LED引脚
- **类型验证**: 数字、字符串、布尔值、列表类型检查
- **范围验证**: 端口号、超时时间、阈值参数的范围检查
- **格式验证**: IP地址、SSID、主题名称的格式验证

### 配置错误处理
- **缺失配置**: 使用默认值并记录警告日志
- **无效配置**: 抛出ConfigurationError异常
- **类型错误**: 自动类型转换或记录错误
- **范围错误**: 限制在有效范围内并记录警告

### 配置加载流程
1. **配置解析**: 读取config.py文件并解析配置字典
2. **参数验证**: 验证必需参数和参数类型
3. **默认值填充**: 为可选参数设置默认值
4. **范围检查**: 确保数值参数在有效范围内
5. **格式验证**: 验证IP地址、SSID等格式
6. **配置分发**: 将配置传递给各个模块
7. **运行时监控**: 监控配置变更和有效性

## Configuration Best Practices

### 配置文件维护
- **版本控制**: 配置文件变更应纳入版本控制
- **变更测试**: 配置变更后应在测试环境中验证
- **文档同步**: 配置变更后及时更新相关文档
- **回滚机制**: 保留配置备份以便快速回滚

### 配置使用最佳实践
- **延迟加载**: 只在需要时加载配置，减少启动时间
- **缓存机制**: 缓存频繁使用的配置参数
- **配置验证**: 在使用配置前进行有效性验证
- **错误处理**: 优雅处理配置缺失或无效的情况
- **日志记录**: 记录配置加载和使用情况

### 配置优化建议
- **内存优化**: 避免在配置中存储大量数据
- **访问优化**: 减少配置参数的频繁访问
- **初始化优化**: 简化配置加载和验证流程
- **维护优化**: 保持配置结构清晰和一致

### 配置调试技巧
- **配置检查**: 使用`get_config_value`函数检查配置是否正确加载
- **配置验证**: 使用配置验证函数确保参数有效性
- **配置测试**: 在不同场景下测试配置变更的影响
- **配置监控**: 监控配置使用情况和性能影响

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

## 常见问题和解决方案

### WiFi连接问题
- **问题**: WiFi扫描显示空字符串SSID的相似网络
- **解决**: 这是正常现象，系统会自动过滤无效网络并尝试连接配置的网络列表

### LED状态指示问题
- **问题**: 进入错误状态时LED未按预期闪烁
- **解决**: 检查守护进程是否正确启动，确认LED引脚配置与硬件连接一致

### 编码问题
- **问题**: mpremote 监控时出现中文编码错误
- **解决**: 使用构建脚本的 `--raw-repl` 参数或 `--repl` 参数进行调试

### 网络超时问题
- **问题**: MQTT连接失败显示 EHOSTUNREACH 错误
- **解决**: 检查网络连接和MQTT服务器配置，确认IP地址和端口正确

### MQTT重连问题
- **问题**: MQTT断开后频繁重试，日志显示大量连接失败
- **解决**: 系统已实现指数退避策略，会自动调整重连间隔：5s → 10s → 20s → 40s → 80s → 160s → 300s(max)
- **配置**: 可通过 `config.py` 中的 `exponential_backoff`、`max_backoff_time`、`backoff_multiplier` 参数调整
- **监控**: 通过 `get_connection_status()` 方法查看当前重连状态和退避时间

### 构建脚本问题
- **问题**: mpremote 因特殊字符崩溃
- **解决**: 构建脚本已实现智能编码处理，使用安全监控模式避免崩溃

### 安全模式问题
- **问题**: 设备进入安全模式后无法自动恢复
- **解决**: 这是设计特性，安全模式需要手动重启设备才能退出，确保问题得到人工干预

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

### 串口日志
设备通过串口输出详细日志：
- WiFi连接状态
- MQTT连接状态
- 内存使用报告
- 系统日志
- LED状态指示

### 安全模式特性

#### 安全模式触发条件
- CPU温度超过阈值（默认65°C）
- 内存使用率超过阈值（默认80%）
- 错误计数超过限制（默认10次）
- 看门狗超时
- 系统严重错误

#### 安全模式行为
- LED显示SOS闪烁模式
- 禁用自动恢复功能
- 执行深度垃圾回收
- 记录关键错误日志
- 等待手动重启

#### 安全模式恢复
- **必须手动重启设备**: 这是设计特性，确保问题得到人工干预
- **断电重启**: 完全断开电源，等待10秒后重新上电
- **检查硬件**: 确认设备没有过热或其他硬件问题
- **检查配置**: 确认配置参数是否合理