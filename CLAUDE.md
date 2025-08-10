# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 始终使用中文回答
- 完成后若有额外建议则记录在SUG.md中
- app 内的所有代码都是在 ESP32C3 MicroPython 上运行的, 不需要在本地测试和运行
- app/tests 的代码也是在 ESP32C3 MicroPython 上运行的， 用来测试 app 内的代码，也不需要在本地测试和运行
- 若有差异以 README.md 为准


## Project Overview

这是一个基于ESP32-C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用**事件驱动架构**和**模块化设计**，提供WiFi连接、MQTT通信、系统监控、LED状态指示和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## Architecture

### 事件驱动架构 (Event-Driven Architecture)

项目已重构为松耦合的事件驱动架构，核心组件包括：

#### 1. 事件总线 (EventBus) - `app/lib/event_bus.py`
- **功能**: 模块间通信的核心枢纽，支持发布-订阅模式
- **特性**: 异步非阻塞事件处理、错误隔离、内存优化、事件优先级、计时器队列驱动
- **接口**: `subscribe(event_name, callback)`, `publish(event_name, *args, **kwargs)`
- **实现**: 基于硬件计时器的循环队列系统，避免 micropython.schedule 的 queue full 问题，提升系统稳定性

#### 2. 对象池管理器 (ObjectPoolManager) - `app/lib/object_pool.py`
- **功能**: 高效的对象复用和内存管理
- **特性**: 减少GC压力、内存预分配、智能回收
- **接口**: `add_pool(name, factory, size)`, `acquire(pool_name)`, `release(obj)`

#### 3. 静态缓存系统 (StaticCache) - `app/lib/static_cache.py`
- **功能**: 防抖写入的持久化缓存
- **特性**: 自动保存、内存优化、错误恢复
- **接口**: `get(key, default)`, `set(key, value)`, `load()`, `save()`

#### 4. 系统状态机 (SystemFSM) - `app/fsm.py`
- **功能**: 清晰的系统状态管理和转换
- **支持状态**: BOOT → INIT → NETWORKING → RUNNING → WARNING → ERROR → SAFE_MODE → RECOVERY → SHUTDOWN
- **特性**: 事件驱动的状态转换、错误恢复、LED状态同步

#### 5. 事件常量 (EVENT) - `app/event_const.py`
- **功能**: 统一事件名称定义，避免字符串散落
- **包含**: 系统事件、网络事件、传感器事件、错误事件

### 硬件抽象层

#### 6. WiFi管理器 (WifiManager) - `app/net/wifi.py`
- **功能**: 健壮的WiFi连接管理
- **特性**: 多网络选择、RSSI排序、自动重连、非阻塞连接
- **事件**: 发布 WIFI_CONNECTED, WIFI_DISCONNECTED 等事件

#### 7. MQTT控制器 (MqttController) - `app/net/mqtt.py`
- **功能**: 高效的MQTT通信管理
- **特性**: 指数退避重连、内存优化、心跳监控
- **事件**: 发布 MQTT_CONNECTED, MQTT_DISCONNECTED, MQTT_MESSAGE 等事件

#### 8. LED模式控制器 (LEDPatternController) - `app/hw/led.py`
- **功能**: 丰富的LED状态指示和模式控制
- **特性**: 多种预设模式、状态可视化、低功耗设计
- **模式**: 快闪三下、SOS、心跳、警灯、霹雳游侠、呼吸灯等

#### 9. 传感器管理器 (SensorManager) - `app/hw/sensor.py`
- **功能**: 统一的传感器数据采集和管理
- **支持**: 内部温度传感器、外部传感器(DHT11/DHT22/BMP280)

### 系统服务层

#### 10. 配置管理 (Config) - `app/config.py`
- **功能**: 集中式配置管理
- **特性**: 类型验证、默认值、运行时检查
- **接口**: `get_config(section, key, default)`

#### 11. 日志系统 (Logger) - `app/lib/logger.py`
- **功能**: 统一的日志管理和错误处理
- **特性**: 事件驱动、内存优化、MQTT集成
- **接口**: `setup(event_bus)` 订阅日志事件

#### 12. 主控制器 (Main) - `app/main.py`
- **功能**: 依赖注入容器和系统启动
- **特性**: 模块化管理、优雅启动、资源清理
- **流程**: 加载配置 → 初始化核心服务 → 创建模块控制器 → 启动状态机

### 工具和辅助模块

#### 13. 系统助手 (Helpers) - `app/utils/helpers.py`
- **功能**: 系统监控和辅助函数
- **包含**: 内存检查、温度监控、时间格式化、设备信息

#### 14. 定时器工具 (Timers) - `app/utils/timers.py`
- **功能**: 丰富的定时器工具集
- **包含**: 防抖定时器、周期定时器、超时定时器、硬件定时器管理器

#### 15. MQTT客户端库 - `app/lib/lock/umqtt.py`
- **功能**: 轻量级MQTT客户端库
- **特性**: 内存优化、断线重连、心跳保持

#### 16. 轻量级日志库 - `app/lib/lock/ulogging.py`
- **功能**: 基础日志记录功能
- **特性**: 轻量级、低内存占用

## Key Features

- **🔄 事件驱动架构**: 基于EventBus的松耦合设计，支持模块间通信
- **📡 多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **📡 MQTT通信**: 高效的MQTT客户端，支持指数退避重连策略和内存优化
- **📊 系统监控**: 实时监控温度、内存使用和系统健康状态
- **🛠️ 智能错误恢复**: 分级错误处理和自动恢复机制
- **💾 内存优化**: 对象池模式和智能垃圾回收，适合ESP32C3的264KB内存限制
- **🐕 看门狗保护**: 防止系统死锁，确保设备稳定运行
- **💡 LED状态指示**: 通过LED显示设备运行状态，支持多种预设模式
- **⚙️ 配置管理**: 集中式配置系统，支持运行时验证

## Build and Deployment

### 构建和部署工具

使用 [`build.py`](build.py) 脚本编译和部署项目：

```bash
# 默认行为：编译、上传、启动REPL
python build.py

# 仅编译不部署
python build.py --compile

# 仅上传到设备根目录
python build.py --upload

# 仅启动REPL监听
python build.py --repl

# 指定端口上传
python build.py --upload --port COM3

# 包含测试文件编译
python build.py --test

# 清理本地缓存
python build.py --clean-cache
```

### 构建脚本功能 (build.py v5.1 重构增强版)
- **编译**: 使用 mpy-cross 编译 Python 文件为 .mpy 格式（排除 boot.py 和 main.py）
- **上传**: 使用 mpremote 自动检测 ESP32 设备并上传文件到设备根目录 `/`
- **设备检测**: 自动识别 ESP32-C3 设备端口（支持多种USB转串口芯片）
- **文件验证**: 上传完成后自动验证设备上的文件列表
- **缓存管理**: 智能文件上传缓存，避免重复上传未修改文件
- **安全模式**: 特殊的安全模式检测和恢复机制
- **多设备支持**: 自动检测和选择多个ESP32设备
- **错误恢复**: 完善的重试和错误处理机制
- **增量上传**: 基于MD5哈希的智能文件变更检测

### 项目结构
```
IOT_ESP32C3/
├── app/                    # 开发源代码目录（编译后直接上传到设备根目录）
│   ├── lib/               # 通用库和工具模块
│   │   ├── event_bus.py   # 事件总线
│   │   ├── object_pool.py # 对象池管理器
│   │   ├── static_cache.py # 静态缓存系统
│   │   ├── logger.py      # 日志系统
│   │   └── lock/          # 不可编辑的外部库
│   │       ├── umqtt.py   # MQTT客户端库
│   │       └── ulogging.py # 轻量级日志库
│   ├── hw/                # 硬件相关模块
│   ├── net/               # 网络通信模块
│   ├── utils/             # 工具函数模块
│   ├── boot.py           # 启动引导
│   ├── config.py         # 配置管理
│   ├── event_const.py    # 事件常量定义
│   ├── fsm.py            # 系统状态机
│   ├── main.py           # 主程序入口
│   └── logger.py         # 日志系统
├── app/tests/             # 单元测试
├── docs/                  # 文档
├── build.py              # 构建脚本
└── requirements.txt      # Python依赖
```

### 重要说明
- **设备目录结构**: 编译后的 `app/` 目录内容直接上传到 ESP32-C3 设备的根目录 `/`，因此设备根目录下的文件结构就是 `app/` 目录的镜像
- **文件位置**: 代码开发在 `./app` 目录下，但运行时直接位于设备根目录
- **路径引用**: 设备代码中的导入语句使用 `from lib.xxx import xxx`、`from hw.xxx import xxx` 等，因为文件直接位于根目录，MicroPython会自动识别 `lib/` 目录

## Configuration Management

### 配置系统
- **配置文件**: `app/config.py` - Python字典配置系统
- **访问接口**: `get_config(section, key, default)` 函数
- **配置验证**: 类型检查、范围验证、格式验证
- **运行时监控**: 配置变更和有效性监控

### 主要配置段

#### MQTT配置 (`app/config.py:18-62`)
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

#### WiFi配置 (`app/config.py:64-92`)
```python
"wifi": {
    "networks": [
        {"ssid": "zsm60p", "password": "25845600"},
        {"ssid": "leju_software", "password": "leju123456"}
    ],
    "timeout": 15,
    "scan_interval": 30,
    "retry_delay": 2,
    "max_attempts": 3
}
```

#### 系统配置 (`app/config.py:154-181`)
```python
"system": {
    "debug_mode": False,
    "log_level": "INFO",
    "main_loop_delay": 300,
    "status_report_interval": 30,
    "auto_restart_enabled": False
}
```

## Testing

### 测试框架
- **测试工具**: pytest + unittest.mock
- **测试覆盖**: 事件总线、对象池、日志系统等核心组件
- **测试文件**: `app/tests/test_event_bus.py`, `app/tests/test_logger.py`
- **测试环境**: 测试代码也在 ESP32-C3 MicroPython 上运行，不需要本地测试

### 运行测试
```bash
# 安装测试依赖
pip install -r requirements.txt

# 运行所有测试
pytest app/tests/

# 运行特定测试
pytest app/tests/test_event_bus.py

# 带覆盖率报告
pytest app/tests/ --cov=app
```

## Event-Driven Architecture

### 事件流程
```
事件发生 → EventBus发布 → 计时器队列调度 → 订阅者处理 → 状态更新 → LED指示 → 日志记录
```

### 核心事件类型
- **系统事件**: SYSTEM_BOOT, SYSTEM_INIT, SYSTEM_READY, SYSTEM_ERROR
- **网络事件**: WIFI_CONNECTED, WIFI_DISCONNECTED, MQTT_CONNECTED, MQTT_DISCONNECTED
- **时间事件**: NTP_SYNC_STARTED, NTP_SYNC_SUCCESS, TIME_UPDATED
- **传感器事件**: SENSOR_DATA
- **日志事件**: LOG_INFO, LOG_WARN, LOG_ERROR, LOG_DEBUG

### 事件优先级系统
EventBus实现了事件优先级机制，确保关键事件优先处理：
- **最高优先级 (0)**: system.error, system.critical, memory.critical
- **高优先级 (1)**: log.error
- **中优先级 (2-3)**: log.warn, system.warning, log.info, wifi.connected, mqtt.connected
- **低优先级 (4)**: log.debug, system.heartbeat

### 状态机系统
- **状态**: BOOT → INIT → NETWORKING → RUNNING → WARNING → ERROR → SAFE_MODE → RECOVERY → SHUTDOWN
- **状态转换**: 事件驱动的自动状态转换
- **错误恢复**: 智能错误处理和自动恢复机制

## Memory Management

### 内存优化策略 (针对ESP32-C3 264KB内存限制)
- **对象池**: 减少频繁的对象创建销毁，降低GC压力
- **静态缓存**: 避免频繁的Flash写入，使用防抖机制
- **智能垃圾回收**: 根据内存使用动态调整，紧急垃圾回收流程
- **轻量级数据结构**: 优化内存占用，使用全局变量减少实例化开销
- **事件频率限制**: 防止计时器队列溢出，限制高频率事件
- **内存监控**: 实时监控内存使用，触发内存预警和紧急处理
- **单例模式**: 核心组件使用单例模式，减少重复实例化

### 对象池系统
```python
# 创建对象池
object_pool.add_pool("mqtt_messages", lambda: {}, 10)
object_pool.add_pool("sensor_data", lambda: {}, 5)

# 使用对象池
msg_obj = object_pool.acquire("mqtt_messages")
# 使用对象...
object_pool.release(msg_obj)
```

## Dependencies

### 开发依赖
- **mpy-cross**: MicroPython编译器
- **mpremote**: MicroPython远程工具
- **pytest**: 单元测试框架
- **black**: 代码格式化
- **flake8**: 代码检查

### 运行依赖
- **MicroPython标准库**: network, time, machine, ntptime, gc
- **自定义库**: umqtt (轻量级MQTT客户端), ulogging (轻量级日志库)

## Development Guidelines

### 代码规范
- **语言**: 全程使用中文进行代码注释和文档
- **文件位置**: 主要代码位于 `./app` 目录
- **模块化**: 每个模块职责单一，避免硬编码配置
- **事件驱动**: 使用EventBus进行模块间通信
- **内存优化**: 注意ESP32C3的264KB内存限制

### 依赖注入
项目使用依赖注入模式，在 `main.py` 中创建和连接所有对象：

```python
# 初始化核心服务
from config import get_config
from lib.event_bus import EventBus
from lib.object_pool import ObjectPoolManager
from lib.static_cache import StaticCache
from lib.logger import Logger, set_global_logger
from event_const import EVENT
from fsm import SystemFSM
from net.wifi import WifiManager
from net.mqtt import MqttController
from hw.led import LEDPatternController
from hw.sensor import SensorManager

# 加载配置
config = get_config()

# 初始化核心服务
event_bus = EventBus()
object_pool = ObjectPoolManager()
static_cache = StaticCache()
logger = Logger()

# 初始化模块控制器
wifi = WifiManager(event_bus, config.get('wifi', {}))
mqtt = MqttController(event_bus, object_pool, config.get('mqtt', {}))

# 创建状态机并注入依赖
fsm = SystemFSM(event_bus, object_pool, static_cache, config, wifi, mqtt)
```

## Important Notes

- **内存限制**: ESP32C3只有264KB内存，必须时刻注意内存使用，所有组件都针对此限制进行了优化
- **文件位置**: 只允许编辑 `./app` 下一级目录的文件，`app/lib/lock/` 目录下的外部库文件不可编辑
- **测试代码**: 不要添加测试代码和文件，所有测试都在 `app/tests/` 目录下
- **文档**: 不要擅自添加说明文档，项目文档位于 `docs/` 目录
- **语言**: 始终使用中文进行代码注释和文档
- **架构**: 项目已完成事件驱动架构重构，使用松耦合设计
- **外部库**: `app/lib/lock/` 目录包含外部下载的库文件，这些文件不应被修改
- **构建系统**: 使用 `build.py` 进行编译和部署，支持智能增量上传
- **事件驱动**: 所有模块间通信都通过 EventBus 进行，避免直接耦合
- **依赖注入**: 使用依赖注入模式，在 `main.py` 中统一管理组件生命周期
- **状态管理**: 使用 SystemFSM 管理系统状态，支持自动错误恢复
- **内存优化**: 使用对象池、静态缓存等技术优化内存使用