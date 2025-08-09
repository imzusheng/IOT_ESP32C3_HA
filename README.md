# ESP32-C3 MicroPython IoT 项目 (重构版)

- 所有AI始终使用中文回答
- AI 完成后若有额外建议则记录在SUG.md中
- app 内的所有代码都是在 ESP32C3 MicroPython 上运行的, 不需要在本地测试和运行
- app/tests 的代码也是在 ESP32C3 MicroPython 上运行的， 用来测试 app 内的代码，也不需要在本地测试和运行

## 📋 项目概述

这是一个基于ESP32-C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用**事件驱动架构**和**模块化设计**，提供WiFi连接、MQTT通信、系统监控、LED状态指示和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## ✨ 主要特性

- **🔄 事件驱动架构**: 基于EventBus的松耦合设计，支持模块间通信
- **📡 多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **📡 MQTT通信**: 高效的MQTT客户端，支持指数退避重连策略和内存优化
- **📊 系统监控**: 实时监控温度、内存使用和系统健康状态
- **🛠️ 智能错误恢复**: 分级错误处理和自动恢复机制
- **💾 内存优化**: 对象池模式和智能垃圾回收，适合ESP32C3的264KB内存限制
- **🐕 看门狗保护**: 防止系统死锁，确保设备稳定运行
- **💡 LED状态指示**: 通过LED显示设备运行状态，支持多种预设模式
- **⚙️ 配置管理**: 集中式配置系统，支持运行时验证
- **🌐 Web配置界面**: 基于Web Bluetooth的配置工具，支持Apple设计风格

## 📁 项目结构

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

## 🏗️ 重构架构设计

### 核心架构组件

#### 1. 事件总线 (EventBus)
- **位置**: [`app/lib/event_bus.py`](app/lib/event_bus.py)
- **功能**: 模块间通信的核心枢纽，支持发布-订阅模式
- **特性**: 异步非阻塞事件处理、错误隔离、内存优化

#### 2. 对象池管理器 (ObjectPoolManager)
- **位置**: [`app/lib/object_pool.py`](app/lib/object_pool.py)
- **功能**: 高效的对象复用和内存管理
- **特性**: 减少GC压力、内存预分配、智能回收

#### 3. 状态机系统 (FSM)
- **位置**: [`app/fsm.py`](app/fsm.py)
- **功能**: 清晰的系统状态管理和转换
- **支持状态**: BOOT → INIT → NETWORKING → RUNNING → WARNING → ERROR → SAFE_MODE → RECOVERY → SHUTDOWN

#### 4. 静态缓存系统 (StaticCache)
- **位置**: [`app/lib/static_cache.py`](app/lib/static_cache.py)
- **功能**: 防抖写入的持久化缓存
- **特性**: 自动保存、内存优化、错误恢复

### 硬件抽象层

#### 5. 传感器管理器 (SensorManager)
- **位置**: [`app/hw/sensor.py`](app/hw/sensor.py)
- **功能**: 统一的传感器数据采集和管理
- **支持**: 内部温度传感器、外部传感器(DHT11/DHT22/BMP280)

#### 6. LED模式控制器 (LEDPatternController)
- **位置**: [`app/hw/led.py`](app/hw/led.py)
- **功能**: 丰富的LED状态指示和模式控制
- **特性**: 多种预设模式、状态可视化、低功耗设计

### 网络通信层

#### 7. WiFi管理器 (WifiManager)
- **位置**: [`app/net/wifi.py`](app/net/wifi.py)
- **功能**: 健壮的WiFi连接管理
- **特性**: 多网络选择、RSSI排序、自动重连

#### 8. MQTT控制器 (MqttController)
- **位置**: [`app/net/mqtt.py`](app/net/mqtt.py)
- **功能**: 高效的MQTT通信管理
- **特性**: 指数退避重连、内存优化、心跳监控

### 工具和辅助模块

#### 9. 定时器工具 (Timers)
- **位置**: [`app/utils/timers.py`](app/utils/timers.py)
- **功能**: 丰富的定时器工具集
- **包含**: 防抖定时器、周期定时器、超时定时器、硬件定时器管理器、性能分析器

#### 10. 系统助手 (Helpers)
- **位置**: [`app/utils/helpers.py`](app/utils/helpers.py)
- **功能**: 系统监控和辅助函数
- **包含**: 内存检查、温度监控、时间格式化、设备信息

#### 11. 日志系统 (Logger)
- **位置**: [`app/lib/logger.py`](app/lib/logger.py)
- **功能**: 统一的日志管理和错误处理
- **特性**: 事件驱动、内存优化、MQTT集成

#### 12. 配置管理 (Config)
- **位置**: [`app/config.py`](app/config.py)
- **功能**: 集中式配置管理
- **特性**: 类型验证、默认值、运行时检查

### 主应用程序

#### 13. 主控制器 (Main)
- **位置**: [`app/main.py`](app/main.py)
- **功能**: 系统初始化和主循环控制
- **特性**: 依赖注入、模块化管理、优雅启动

#### 14. 启动引导 (Boot)
- **位置**: [`app/boot.py`](app/boot.py)
- **功能**: 系统启动引导
- **特性**: 最小化启动、GC初始化

## 🔄 事件驱动系统

### 事件类型定义
- **位置**: [`app/event_const.py`](app/event_const.py)
- **包含**: 系统事件、网络事件、传感器事件、错误事件

### 事件流程示例
```
传感器数据变化 → EventBus发布事件 → 相关模块订阅处理 → 状态更新 → LED指示变化
WiFi连接成功 → NTP时间同步 → TIME_UPDATED事件 → 时间相关模块开始工作
```

### 事件载荷与回调签名约定
- 回调优先采用新签名：callback(event_name, *args, **kwargs)，事件名作为第一个参数，便于统一处理与日志追踪。
- 兼容旧签名：若回调不接受 event_name，将自动降级为 callback(*args, **kwargs)；仍不兼容则尝试 callback()，确保向后兼容。
- TIME_UPDATED 事件载荷：从"完成B"起，事件将附带关键字参数 timestamp（秒级Unix时间戳）。示例：
  - 发布方：event_bus.publish(EVENT.TIME_UPDATED, timestamp=timestamp)
  - 订阅方回调示例：def _on_time_updated(self, event_name, timestamp=None, **kwargs): ...

## ⚙️ 配置说明

### 配置文件结构
项目使用纯Python配置系统：
- [`app/config.py`](app/config.py): Python字典配置（主要配置和验证规则）

### 主要配置项

#### MQTT配置
```python
"mqtt": {
    "broker": "192.168.3.15",        # MQTT服务器地址
    "port": 1883,                   # MQTT端口
    "topic": "lzs/esp32c3",         # MQTT主题
    "keepalive": 60,                # 心跳间隔(秒)
    "reconnect_delay": 5,           # 重连延迟(秒)
    "max_retries": 3,               # 最大重试次数
    "exponential_backoff": True,    # 启用指数退避策略
    "max_backoff_time": 300,        # 最大退避时间(秒)
    "backoff_multiplier": 2         # 退避倍数因子
}
```

#### WiFi配置
```python
"wifi": {
    "networks": [                   # WiFi网络列表
        {"ssid": "zsm60p", "password": "25845600"},
        {"ssid": "leju_software", "password": "leju123456"}
    ],
    "config": {
        "timeout": 15,              # 连接超时(秒)
        "scan_interval": 30,        # 扫描间隔(秒)
        "retry_delay": 2,           # 重试延迟(秒)
        "max_attempts": 3           # 最大尝试次数
    }
}
```

#### 守护进程配置
```python
"daemon": {
    "config": {
        "led_pins": [12, 13],       # LED引脚
        "timer_id": 0,              # 定时器ID
        "monitor_interval": 5000,   # 监控间隔(毫秒)
        "temp_threshold": 65,       # 温度阈值(°C)
        "temp_hysteresis": 5,       # 温度迟滞(°C)
        "memory_threshold": 50000,  # 内存阈值(字节)
        "memory_gc_trigger": 30000, # GC触发阈值(字节)
        "status_report_interval": 30000, # 状态报告间隔(毫秒)
        "error_recovery_timeout": 120000 # 错误恢复超时(毫秒)
    }
}
```

#### 系统配置
```python
"system": {
    "debug_mode": False,            # 调试模式
    "log_level": "INFO",            # 日志级别
    "main_loop_delay": 300,         # 主循环延迟(毫秒)
    "status_report_interval": 30,  # 状态报告间隔(秒)
    "auto_restart_enabled": False   # 自动重启开关
}
```

#### 设备配置
```python
"device": {
    "name": "ESP32C3-IOT",          # 设备名称
    "location": "未知位置",         # 设备位置
    "firmware_version": "2.0.0"     # 固件版本
}
```

## 🚀 快速开始

### 硬件要求
- ESP32-C3开发板
- LED指示灯（连接到GPIO 12和13）
- USB数据线

### 软件依赖
- **MicroPython固件**: ESP32-C3支持的MicroPython版本
- **umqtt.simple**: 轻量级MQTT客户端库 ([`app/lib/lock/umqtt.py`](app/lib/lock/umqtt.py))
- **ulogging**: 轻量级日志库 ([`app/lib/lock/ulogging.py`](app/lib/lock/ulogging.py))
- **MicroPython标准库**: network, time, machine, ntptime, gc

### 安装步骤

1. **刷写MicroPython固件**
   ```bash
   # 使用esptool刷写固件
   esptool.py --chip esp32c3 --port COMx erase_flash
   esptool.py --chip esp32c3 --port COMx write_flash -z 0x0 firmware.bin
   ```

2. **上传项目文件**
   ```bash
   # 使用构建脚本
   python build.py --upload
   
   # 或手动上传
   mpremote connect COMx fs cp -r app/ /
   ```

3. **配置设备**
   - 修改 [`app/config.py`](app/config.py) 中的配置项
   - 或使用Web配置界面进行配置

4. **重启设备**
   ```bash
   # 重启设备
   mpremote connect COMx reset
   ```

### 构建和部署

使用 [`build.py`](build.py) 脚本构建和部署项目：

```bash
# 构建项目（排除测试文件）
python build.py

# 构建项目（包含测试文件）
python build.py --test

# 仅编译不部署
python build.py --compile

# 上传并监听设备输出
python build.py --upload

# 指定端口上传
python build.py --upload --port COM3

# 启用完整REPL交互模式
python build.py --upload --repl

# 使用原始REPL模式（调试用）
python build.py --upload --raw-repl

# 诊断设备安全模式状态
python build.py --diagnose

# 清理本地缓存
python build.py --clean-cache
```

## 📊 系统状态和监控

### 状态机系统
系统支持以下状态：
- **INIT**: 系统初始化
- **NETWORKING**: 网络连接
- **RUNNING**: 正常运行
- **WARNING**: 警告状态
- **ERROR**: 错误状态
- **SAFE_MODE**: 安全模式
- **RECOVERY**: 恢复模式
- **SHUTDOWN**: 关机状态

### LED状态指示
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

## 🛠️ 开发和调试

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

## 💾 内存管理优化

### 对象池系统
- **字典对象池**: 避免频繁创建销毁字典对象
- **字符串缓存**: 缓存常用字符串减少内存分配
- **缓冲区管理**: 预分配缓冲区管理器
- **内存优化器**: 提供内存监控和优化功能

### 关键内存优化技术
- 全局变量减少实例化开销
- 智能垃圾回收（根据内存使用动态调整）
- 轻量级数据结构
- 避免复杂对象创建
- 定期内存清理和监控

### 静态缓存系统
- **防抖写入**: 避免频繁的Flash写入
- **自动保存**: 定期保存缓存数据
- **内存优化**: 高效的内存使用
- **错误恢复**: 系统重启后自动恢复

## 🌐 网络行为

### 启动流程
1. **boot.py** → 系统启动引导
2. **main.py** → 主程序初始化
3. **配置验证** → 加载系统配置
4. **WiFi连接** → 连接最优网络
5. **时间同步** → NTP服务器同步
6. **MQTT连接** → 连接MQTT代理
7. **守护进程启动** → 系统监控开始
8. **主循环** → 系统稳定运行

### MQTT 重连机制
当MQTT连接断开时，系统采用智能的指数退避重连策略：
- **第1轮**: 立即重试3次
- **第2轮**: 等待5秒后重试3次
- **第3轮**: 等待10秒后重试3次
- **第4轮**: 等待20秒后重试3次
- **第5轮**: 等待40秒后重试3次
- **第6轮**: 等待80秒后重试3次
- **第7轮**: 等待160秒后重试3次
- **第8轮及以后**: 等待300秒（最大值）后重试3次

## 🛡️ 错误处理和恢复

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

### 恢复管理器
- **网络恢复**: WiFi重连 + MQTT重连
- **内存恢复**: 深度清理 + 对象池重建
- **服务恢复**: 守护进程重启
- **系统恢复**: 状态机管理 + 安全模式
- **硬件恢复**: 系统重启

### 安全模式特性
- **触发条件**: 温度过高、内存不足、错误过多
- **行为模式**: LED显示SOS、禁用自动恢复、深度清理
- **恢复方式**: 必须手动重启设备

## 📖 硬件资源

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
- **温度传感器**: GPIO 4 (ADC4)
- **看门狗**: 软件实现

## 🌐 Web配置界面

项目包含基于Web Bluetooth的配置界面：
- **位置**: [`web/index.html`](web/index.html)
- **功能**: 蓝牙连接、WiFi配置、MQTT配置、设备配置
- **设计**: Apple设计风格，响应式布局
- **浏览器要求**: 支持Web Bluetooth API的现代浏览器

## ⚠️ 重要说明

- **内存限制**: ESP32C3只有264KB内存，必须时刻注意内存使用
- **文件位置**: 主要代码位于 `./app` 目录，但上传到设备时直接位于根目录
- **路径引用**: 设备上使用 `from lib.event_bus import EventBus` 等相对导入，MicroPython自动识别 `lib/` 目录
- **配置管理**: 所有配置项都在 `config.py` 中定义
- **语言**: 代码注释和文档使用中文
- **架构重构**: 已完成事件驱动架构重构，提升了系统的可维护性和扩展性

## 🔄 系统工作流程

### 主循环流程
```
喂狗 → 状态机更新 → WiFi管理 → MQTT控制 → 传感器更新 → 
缓存更新 → 健康检查 → 状态报告 → 垃圾回收 → 延迟
```

### 事件处理流程
```
事件发生 → EventBus发布 → 订阅者处理 → 状态更新 → 
LED指示 → 日志记录 → MQTT发送
```

### 错误处理流程
```
错误发生 → 错误分类 → 严重程度判断 → 执行恢复动作 → 
记录日志 → 发布事件 → 状态转换 → 继续运行/安全模式
```

## 📝 版本信息

- **当前版本**: 2.0.0 (重构版)
- **架构版本**: 事件驱动架构 v1.0
- **最后更新**: 2025-08-09
- **维护者**: ESP32C3 开发团队

## 🤝 贡献

欢迎贡献代码、报告问题或提出改进建议！

### 贡献方式
1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建Pull Request

## 📄 许可证

本项目采用 MIT 许可证。

## 📞 支持

如果您在使用过程中遇到任何问题，请通过以下方式获取支持：

- 📧 **邮件支持**: [your-email@example.com](mailto:your-email@example.com)
- 🐛 **问题报告**: [GitHub Issues](https://github.com/your-username/IOT_ESP32C3_HA/issues)
- 📖 **文档**: [项目 Wiki](https://github.com/your-username/IOT_ESP32C3_HA/wiki)

---

**最后更新**: 2025-08-09  
**版本**: 2.0.0 (重构版)  
**架构**: 事件驱动架构  
**维护者**: ESP32C3 开发团队