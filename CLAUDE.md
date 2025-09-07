# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

- 始终使用中文回答
- app 内的所有代码都是在 ESP32C3 MicroPython 上运行的, 不需要在本地测试和运行
- app/tests 的代码也是在 ESP32C3 MicroPython 上运行的, 用来测试 app 内的代码, 也不需要在本地测试和运行
- 若有差异以 README.md 为准
- 所有代码文件使用 UTF-8 编码,中文注释和文档
- 硬件限制：ESP32-C3 只有 264KB SRAM,2 个硬件定时器,必须时刻注意资源使用

## 常用开发命令

### 构建和部署

```bash
# 默认构建: 编译、上传、启动REPL
python build.py

# 仅编译不部署
python build.py --compile

# 仅上传到设备(智能同步)
python build.py --upload

# 强制全量上传(忽略缓存)
python build.py --full-upload

# 启动REPL交互模式
python build.py --repl

# 监控设备输出
python build.py --monitor

# 诊断设备状态
python build.py --diagnose

# 包含测试文件编译
python build.py --test

# 清理本地缓存
python build.py --clean-cache

# 指定端口上传
python build.py --upload --port COM3
```

### 开发环境准备

```bash
# 安装构建工具依赖
pip install pyserial mpremote mpy-cross

# 代码格式化(可选)
pip install black

# 代码检查(可选)
pip install flake8
```

### 代码质量检查

```bash
# 代码格式化
black app/

# 代码检查
flake8 app/

# 运行 MicroPython 语法检查
python -m py_compile app/main.py
```

## 项目架构概述

这是一个基于 ESP32-C3 的 MicroPython 物联网设备项目, 专为 Home Assistant 智能家居系统设计。项目采用**事件驱动架构**和**函数式状态机**, 在资源受限的嵌入式环境中提供高可靠性的 WiFi 连接、MQTT 通信、系统监控和错误恢复功能。

### 核心架构特点

1. **事件驱动架构**: 基于 EventBus 的松耦合设计, 支持模块间异步通信
2. **函数式状态机**: 使用函数和字典替代类继承, 简化架构提高稳定性
3. **内存优化**: 针对 ESP32C3 的 264KB 内存限制, 采用对象池、静态缓存等技术
4. **依赖注入**: 统一的组件管理和生命周期控制
5. **错误恢复**: 分级错误处理和自动恢复机制
6. **软件定时系统**: 基于 diff 时间的主循环, 节省硬件定时器资源

## 核心架构组件

### 1. 事件总线 (EventBus) - `app/lib/event_bus_lock.py`

- **功能**: 模块间异步通信的核心枢纽
- **特性**:
  - 基于 diff 时间的软件定时系统, 节省硬件定时器资源
  - 错误断路器机制, 防止系统级联故障
  - 系统状态监控(正常/警告/严重错误)
  - 批量事件处理和内存优化
  - 自动垃圾回收和性能统计
- **接口**: `subscribe(event_name, callback)`, `publish(event_name, *args, **kwargs)`, `process_events()`
- **配置**: 队列大小 64, 处理间隔 25ms, 批处理数量 5, 错误阈值 10

### 2. 函数式状态机 (FSM) - `app/state_machine.py`

- **功能**: 清晰的系统状态管理和转换
- **支持状态**: INIT → CONNECTING → RUNNING → ERROR (简化为 4 个核心状态)
- **特性**:
  - 事件驱动的状态转换
  - 错误计数和自动恢复
  - LED 状态同步
  - 网络连接状态监控
- **状态处理**: 每个状态有独立的进入逻辑和更新处理

### 3. 网络管理器 (NetworkManager) - `app/net/network_manager.py`

- **功能**: 极简网络连接管理, 封装 WiFi、MQTT、NTP
- **特性**:
  - 极简架构, 单一文件管理
  - 异步非阻塞调用
  - MQTT 失败不影响 WiFi 连接
  - 智能重连机制
  - 事件驱动状态通知
- **子模块**:
  - WiFi 管理器 (`app/net/wifi.py`)
  - MQTT 控制器 (`app/net/mqtt.py`)
  - NTP 同步 (`app/net/ntp.py`)

### 4. LED 模式控制器 - `app/hw/led.py`

- **功能**: 丰富的 LED 状态指示和模式控制, 开箱即用
- **特性**:
  - 开箱即用: 无需初始化, 直接调用全局函数
  - 延迟初始化: 首次调用时自动初始化
  - 单例模式: 防止重复实例化
  - 手动更新模式: 由主循环调用,节省硬件定时器
  - 多种预设模式: blink, pulse, cruise, sos, off
  - 状态可视化: 通过不同 LED 模式指示系统状态
- **使用方式**:
  ```python
  from hw.led import play, cleanup, process_led_updates
  play('blink')  # 播放闪烁模式
  process_led_updates()  # 手动处理LED更新(主循环中调用)
  cleanup()      # 清理资源
  ```

### 5. 事件常量 (EVENTS) - `app/lib/event_bus_lock.py`

- **功能**: 统一事件名称定义, 避免字符串散落
- **包含**: WIFI_STATE_CHANGE, MQTT_STATE_CHANGE, SYSTEM_STATE_CHANGE, SYSTEM_ERROR, NTP_STATE_CHANGE, SENSOR_DATA
- **特性**: 集中在 EventBus 模块中, 避免额外的导入依赖

## 硬件抽象层

### 6. WiFi 管理器 (WifiManager) - `app/net/wifi.py`

- **功能**: 健壮的 WiFi 连接管理
- **特性**: 扫描与 RSSI 排序、连接/断开、状态检查(多网络选择由上层实现)
- **事件**: 发布 WIFI_STATE_CHANGE 事件

### 7. MQTT 控制器 (MqttController) - `app/net/mqtt.py`

- **功能**: 高效的 MQTT 通信管理
- **特性**: 轻量连接管理、内存优化(指数退避/心跳可在上层统一策略后引入)
- **事件**: 发布 MQTT_STATE_CHANGE 事件

## 系统服务层

### 9. 配置管理 (Config) - `app/config.py`

- **功能**: 集中式配置管理
- **特性**: 类型验证、默认值、运行时检查
- **接口**: `get_config(section, key, default)`
- **当前配置**: 包含 daemon(看门狗、错误计数)和 system(主循环延迟)配置段

### 10. 日志系统 (Logger) - `app/lib/logger.py`

- **功能**: 极简日志系统, 专为 ESP32-C3 嵌入式环境设计
- **特性**: 零配置、拿来即用、固定格式、颜色支持、内存优化
- **级别**: DEBUG, INFO, WARNING, ERROR
- **使用**: 直接导入 `debug`, `info`, `warning`, `error` 函数即可使用
- **颜色支持**: ERROR 级别显示为红色, WARNING 级别显示为橙黄色, FSM 模块显示为翠绿色, NET 模块显示为靛蓝色

### 11. 主控制器 (MainController) - `app/main.py`

- **功能**: 依赖注入容器和系统启动
- **特性**: 模块化管理、优雅启动、资源清理、基于 diff 时间的主循环
- **流程**: 加载配置 → 初始化核心服务 → 创建模块控制器 → 启动基于 diff 时间的主循环
- **主循环特点**:
  - 使用 `time.ticks_ms()` 和 `time.ticks_diff()` 实现精确时间控制
  - 集成 EventBus 手动事件处理, 节省硬件定时器
  - 默认循环延迟 50ms, 可通过配置调整
  - 支持看门狗喂狗和状态监控
  - 集成 LED 手动更新处理

### 12. 守护服务 (Daemon) - `app/daemon.py`

- **功能**: 独立硬件定时器驱动的系统守护服务
- **特性**:
  - 错误计数达到阈值后触发重启
  - MCU 温度超过阈值时立即触发重启
  - 完全自包含,无外部配置依赖
  - 支持安全模式标记文件创建

### 13. Home Assistant 集成 (HomeAssistantHelper) - `app/ha.py`

- **功能**: Home Assistant 设备发现和状态上报
- **特性**:
  - 自动设备发现配置
  - 温湿度传感器状态上报
  - 设备可用性管理
  - 标准 HA 主题格式

### 14. 启动引导 (boot.py) - `app/boot.py`

- **功能**: 系统启动控制和安全模式检测
- **特性**:
  - 支持按键安全模式检测
  - 双击复位进入安全模式
  - 标记文件安全模式触发
  - 系统路径初始化

### 15. 工具函数模块 - `app/utils/`

- **功能**: 提供各种工具函数和辅助功能
- **包含模块**:
  - `json_utils.py`: JSON 文件读写工具,支持原子写入
  - `time_utils.py`: 时间处理工具函数
  - `timers.py`: 定时器管理工具集

## 事件驱动工作流程

### 事件类型和处理

```python
# 系统事件
EVENTS.SYSTEM_STATE_CHANGE    # 状态变化
EVENTS.SYSTEM_ERROR          # 系统错误

# 网络事件
EVENTS['WIFI_STATE_CHANGE']     # WiFi状态
EVENTS['MQTT_STATE_CHANGE']     # MQTT状态
EVENTS['MQTT_MESSAGE']          # MQTT消息

# 时间事件
EVENTS['NTP_STATE_CHANGE']      # NTP同步状态
```

### 事件处理流程

```
事件发生 → EventBus.publish → 事件队列 → 主循环diff时间处理 → 订阅者回调 → 状态更新 → LED指示 → 日志记录
```

### 状态机事件转换

```
外部事件 → 内部事件转换 → 状态查询 → 状态转换 → 新状态处理 → LED同步 → 状态持久化
```

### 主循环工作流程

```
喂看门狗 → 状态机更新 → EventBus事件处理 → LED更新 → 状态监控 → 固定延迟循环
```

## 硬件定时器管理

### ESP32-C3 硬件定时器限制

- **可用定时器**: 2 个硬件定时器
- **优化策略**: 使用软件定时替代硬件定时器, 节省宝贵资源
- **当前使用**: 无硬件定时器占用(全部释放给用户应用)

### 软件定时实现

- **EventBus**: 使用 `time.ticks_ms()` 和 `time.ticks_diff()` 实现 25ms 间隔处理
- **LED 控制器**: 使用 `time.ticks_ms()` 和 `time.ticks_diff()` 实现 100ms 间隔更新
- **主循环**: 基于 diff 时间的精确延迟控制, 默认 50ms 循环间隔
- **优势**: 避免硬件定时器冲突, 提高系统稳定性, 支持动态调整

### 时间管理函数

```python
# 获取当前时间戳(毫秒)
current_time = time.ticks_ms()

# 计算时间差
elapsed = time.ticks_diff(current_time, start_time)

# 精确延迟
while time.ticks_diff(time.ticks_ms(), start_time) < delay_ms:
    time.sleep_ms(1)  # 短暂休眠避免CPU占用过高
```

## 内存管理策略

### ESP32-C3 内存限制

- **总内存**: 264KB SRAM
- **优化策略**: 对象池、静态缓存、智能垃圾回收
- **监控指标**: 实时内存使用、GC 触发、内存预警

### 对象池配置

```python
# MQTT消息对象池
object_pool.add_pool("mqtt_messages", lambda: {"topic": "", "payload": ""}, 8)

# 传感器数据对象池

# 系统事件对象池
object_pool.add_pool("system_events", lambda: {"event": "", "state": ""}, 5)
```

## 配置管理

### 核心配置段

- **mqtt**: MQTT 服务器连接配置(broker、port、user、password、keepalive 等)
- **wifi**: WiFi 网络配置(支持多网络列表,按 RSSI 强度排序连接)
- **ntp**: NTP 时间同步配置
- **daemon**: 系统守护进程配置(看门狗、错误计数等)
- **system**: 系统行为配置(主循环延迟等)
- **ha**: Home Assistant 集成配置(发现前缀、设备信息、按钮配置等)
- **ble**: 蓝牙功能配置(设备名称、服务开关、安全设置、配置服务等)
- **buttons**: Home Assistant 按钮实体配置(支持 LED 控制等功能按钮)

### 配置访问接口

```python
# 获取整个配置段
wifi_config = get_config('wifi')

# 获取特定配置项
broker = get_config('mqtt', 'broker', 'default_broker')

# 获取默认值
timeout = get_config('wifi', 'timeout', 15)
```

## 开发指南

### 代码结构

````
app/                        # 开发源代码目录(编译后上传到设备根目录)
├── lib/                    # 核心库模块
│   ├── lock/              # 不可编辑的外部库
│   │   ├── event_bus.py   # 事件总线核心实现
│   │   ├── umqtt.py       # MQTT客户端库
│   │   └── ulogging.py    # 轻量级日志库
│   ├── event_bus_lock.py  # 事件总线(含事件常量)
│   ├── logger.py          # 极简日志系统
│   ├── async_runtime.py   # 异步运行时
│   └── ulogging_lock.py   # 日志库包装
├── hw/                     # 硬件抽象层
│   ├── led.py            # LED控制器(开箱即用)
│   └── sht40.py          # SHT40温湿度传感器
├── net/                    # 网络通信层
│   ├── __init__.py       # 网络模块导入
│   ├── network_manager.py # 网络管理器
│   ├── wifi.py           # WiFi管理器
│   ├── mqtt.py           # MQTT控制器
│   └── ntp.py            # NTP时间同步
├── utils/                  # 工具函数
│   ├── __init__.py       # 工具模块导入
│   ├── json_utils.py     # JSON工具函数
│   ├── time_utils.py     # 时间工具函数
│   └── timers.py         # 定时器工具集
├── main.py                # 主程序入口
├── state_machine.py       # 状态机实现
├── config.py              # 配置管理
├── daemon.py              # 守护服务
├── ha.py                  # Home Assistant集成
└── boot.py                # 启动引导
└── tests/                 # 单元测试目录

## 测试脚本

### 硬件测试脚本
- **test_tb6612fng.py**: TB6612FNG电机驱动器测试脚本,支持PWM和TACH信号诊断
- **test_bluetoot_working.py**: 蓝牙功能测试脚本,支持BLE设备连接和通信测试

### 测试脚本使用
```bash
# 运行风扇诊断测试
python test_tb6612fng.py

# 运行蓝牙功能测试
python test_bluetoot_working.py
````

## 开发原则

1. **事件驱动**: 所有模块间通信通过 EventBus 进行
2. **内存优化**: 注意 ESP32C3 的 264KB 内存限制
3. **错误处理**: 统一的错误处理和恢复机制
4. **状态管理**: 使用函数式状态机管理设备状态
5. **配置中心**: 所有配置在 config.py 中统一管理
6. **日志记录**: 统一的日志系统和错误追踪
7. **资源优化**: 使用软件定时替代硬件定时器, 节省系统资源

### 模块开发模式

```python
# 1. 依赖注入
class MyModule:
    def __init__(self, event_bus, config):
        self.event_bus = event_bus
        self.config = config

    # 2. 事件订阅
    def setup(self):
        from lib.event_bus_lock import EVENTS
        self.event_bus.subscribe(EVENTS.SYSTEM_STATE_CHANGE, self.on_system_state_change)

    # 3. 事件发布
    def do_something(self):
        from lib.event_bus_lock import EVENTS
        self.event_bus.publish(EVENTS.SYSTEM_ERROR, error_type="my_error", error_info="details")

    # 4. 使用LED(开箱即用)
    def indicate_status(self):
        from hw.led import play
        play('blink')  # 无需初始化, 直接使用

    # 5. 使用日志系统
    def log_status(self):
        from lib.logger import info, error
        info("操作成功", module="MyModule")
        error("操作失败", module="MyModule")
```

## 重要注意事项

- **内存限制**: ESP32C3 只有 264KB 内存, 必须时刻注意内存使用
- **文件位置**: 只允许编辑 `./app` 下一级目录的文件, `app/lib/*_lock.py` 外部库文件不可编辑
- **测试代码**: 不要添加测试代码和文件, 所有测试都在 `app/tests/` 目录下
- **文档**: 不要擅自添加说明文档, 项目文档位于 `docs/` 目录
- **语言**: 始终使用中文进行代码注释和文档
- **架构**: 项目已完成事件驱动架构重构, 使用松耦合设计
- **构建系统**: 使用 `build.py` 进行编译和部署, 支持智能增量上传
- **事件驱动**: 所有模块间通信都通过 EventBus 进行, 避免直接耦合
- **依赖注入**: 使用依赖注入模式, 在 `main.py` 中统一管理组件生命周期
- **状态管理**: 使用函数式状态机管理系统状态, 支持自动错误恢复
- **内存优化**: 使用对象池、静态缓存等技术优化内存使用
- **事件总线**: EventBus 已简化为单队列模式, 集成错误断路器机制, 使用手动处理节省硬件定时器
- **网络管理**: 使用统一的 NetworkManager 管理所有网络连接,支持 WiFi 多网络选择和指数退避重连
- **配置系统**: 配置集中在 `config.py` 中, 支持运行时验证和默认值
- **日志系统**: 已重构为极简日志系统, 直接导入全局函数使用, 支持颜色输出和模块标识
- **LED 系统**: 已重构为开箱即用模式, 无需实例化, 直接调用全局函数使用, 支持延迟初始化和手动更新
- **软件定时**: 主循环、EventBus 和 LED 控制器都使用 diff 时间实现, 节省硬件定时器资源
- **错误处理**: 集成错误断路器和分级错误恢复机制, 提高系统稳定性
- **异步运行时**: 使用 `lib.async_runtime` 管理异步任务,支持任务生命周期管理
- **温湿度监控**: 集成 SHT40 传感器,支持环境温湿度数据采集和 MQTT 上报
- **WiFi 多网络**: 支持配置多个 WiFi 网络,按信号强度自动选择最优网络连接
- **蓝牙支持**: 支持 BLE 功能,包括设备信息、电池服务等标准服务
- **安全模式**: 支持按键和双击复位进入安全模式,便于故障恢复
- **配置覆盖**: 支持 MQTT 动态配置和配置文件覆盖
- **HA 按钮**: 支持 Home Assistant 可配置按钮实体,用于设备控制

## 项目实际特性

### 网络连接特性

- **WiFi 多网络支持**: 配置文件中可设置多个 WiFi 网络,系统会扫描并按 RSSI 强度排序连接
- **指数退避重连**: WiFi 和 MQTT 都支持指数退避重连机制,避免频繁重连
- **连接状态监控**: 实时监控 WiFi 和 MQTT 连接状态,自动处理断线重连
- **LWT 支持**: MQTT 支持 Last Will and Testament 功能

### 系统监控特性

- **内存监控**: 实时监控内存使用情况,支持垃圾回收触发
- **温度监控**: 监控 MCU 内部温度和环境温湿度(SHT40)
- **状态报告**: 定期通过 MQTT 上报系统状态和传感器数据
- **看门狗保护**: 支持硬件看门狗,防止系统死锁

### 开发调试特性

- **详细日志**: 支持分级日志输出,包含模块标识和时间戳
- **LED 状态指示**: 通过 LED 模式显示系统运行状态
- **REPL 支持**: 支持通过串口进行交互式调试
- **构建系统**: 支持智能增量上传,提高开发效率
- **安全模式**: 支持多种方式进入安全模式,便于系统故障恢复

### 硬件资源使用

- **硬件定时器**: 无占用(全部使用软件定时实现)
- **内存**: 264KB SRAM,通过对象池、缓存等技术优化使用
- **存储**: 4MB Flash,支持文件系统和配置持久化
- **传感器**: 支持 SHT40 温湿度传感器,MCU 内部温度监控
- **通信**: WiFi、MQTT、BLE 多种通信方式
