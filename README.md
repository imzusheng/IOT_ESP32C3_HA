# ESP32-C3 MicroPython IoT 项目 (重构版)

- ESP32C3 设备基础限制
  - 最多支持 2 个定时器(编号 0 至 1)
  - 总RAM: 264KB SRAM
  - 总Flash: 4MB Flash
  - CPU频率: 160000000 Hz (160.00 MHz)
- machine 模块
  - 支持: ADC, I2C, I2S, PWM, Pin, RTC, SPI, UART, WDT 等
  - machine.ADC: 支持 12位精度，多种衰减模式
  - 支持:['__class__', '__name__', 'ADC', 'ADCBlock', 'DEEPSLEEP', 'DEEPSLEEP_RESET', 'EXT0_WAKE', 'EXT1_WAKE', 'HARD_RESET', 'I2C', 'I2S', 'PIN_WAKE', 'PWM', 'PWRON_RESET', 'Pin', 'RTC', 'SDCard', 'SLEEP', 'SOFT_RESET', 'SPI', 'Signal', 'SoftI2C', 'SoftSPI', 'TIMER_WAKE', 'TOUCHPAD_WAKE', 'Timer', 'UART', 'ULP_WAKE', 'WDT', 'WDT_RESET', '__dict__', 'bitstream', 'bootloader', 'deepsleep', 'dht_readinto', 'disable_irq', 'enable_irq', 'freq', 'idle', 'lightsleep', 'mem16', 'mem32', 'mem8', 'reset', 'reset_cause', 'sleep', 'soft_reset', 'time_pulse_us', 'unique_id', 'wake_reason']
  - machine.ADC:['__class__', '__name__', 'read', 'ATTN_0DB', 'ATTN_11DB', 'ATTN_2_5DB', 'ATTN_6DB', 'WIDTH_12BIT', '__bases__', '__dict__', 'atten', 'block', 'init', 'read_u16', 'read_uv', 'width']
- **重要**: 在开发过程中 MQTT 服务器失败为正常现象，代码中已做好异常处理

## 📋 项目概述

这是一个基于ESP32-C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。采用**事件驱动架构**和**模块化设计**，提供WiFi连接、MQTT通信、系统监控、LED状态指示和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## 📁 项目结构

```
IOT_ESP32C3/
├── app/                    # 开发源代码目录(编译后直接上传到设备根目录)
│   ├── lib/               # 核心库模块
│   │   ├── event_bus_lock.py  # 事件总线(含事件常量)
│   │   ├── logger.py          # 极简日志系统
│   │   ├── async_runtime.py   # 异步运行时
│   │   └── lock/              # 不可编辑的外部库
│   ├── hw/                # 硬件抽象层
│   │   ├── led.py            # LED控制器
│   │   └── sht40.py          # SHT40温湿度传感器
│   ├── net/               # 网络通信层
│   │   ├── network_manager.py # 网络管理器
│   │   ├── wifi.py           # WiFi管理器
│   │   ├── mqtt.py           # MQTT控制器
│   │   └── ntp.py            # NTP时间同步
│   ├── utils/             # 工具函数
│   ├── state_machine.py   # 状态机实现
│   ├── config.py          # 配置管理
│   ├── main.py            # 主程序入口
│   └── boot.py            # 启动引导
├── build.py               # 构建脚本
└── README.md              # 项目说明
```

## 🏗️ 核心模块

### 事件总线 (EventBus)
- **位置**: `app/lib/event_bus_lock.py`
- **功能**: 模块间异步通信的核心枢纽
- **特性**: 
  - 基于diff时间的软件定时系统
  - 错误断路器机制，防止系统级联故障
  - 批量事件处理和内存优化
  - 支持发布-订阅模式

### 状态机 (FSM)
- **位置**: `app/state_machine.py`
- **功能**: 系统状态管理和转换
- **支持状态**: INIT → CONNECTING → RUNNING → ERROR
- **特性**: 事件驱动的状态转换、错误计数和自动恢复

### 网络管理器 (NetworkManager)
- **位置**: `app/net/network_manager.py`
- **功能**: 统一管理WiFi、MQTT、NTP连接
- **特性**: 
  - 支持多WiFi网络自动选择
  - 指数退避重连机制
  - 异步非阻塞调用

### LED控制器
- **位置**: `app/hw/led.py`
- **功能**: 丰富的LED状态指示和模式控制
- **特性**: 开箱即用、延迟初始化、多种预设模式

### 日志系统
- **位置**: `app/lib/logger.py`
- **功能**: 极简日志系统，专为ESP32-C3设计
- **特性**: 零配置、颜色支持、模块标识

## ⚙️ 常用配置

### MQTT配置 (Home Assistant)
```python
# app/config.py
"mqtt": {
    "broker": "your-home-assistant-ip",  # Home Assistant服务器地址
    "port": 1883,                         # MQTT端口
    "user": "your-mqtt-username",         # MQTT用户名
    "password": "your-mqtt-password",     # MQTT密码
    "keepalive": 60,                      # 心跳间隔(秒)
    "base_delay_ms": 3000,                # 重连基础延迟
    "max_delay_ms": 60000,                # 最大重连延迟
}
```

### WiFi配置
```python
# app/config.py
"wifi": {
    "networks": [
        {"ssid": "your-home-wifi", "password": "your-password"},
        {"ssid": "backup-wifi", "password": "backup-password"},
    ],
    "scan_timeout_ms": 10000,             # 扫描超时时间
    "base_delay_ms": 3000,                # 重连基础延迟
    "max_delay_ms": 60000,                # 最大重连延迟
    "max_retries": 3,                     # 最大重试次数
}
```

### 设备配置
```python
# app/config.py
"device": {
    "name": "ESP32C3-IOT",                 # 设备名称
    "location": "客厅",                   # 设备位置
    "firmware_version": "2.3.0"           # 固件版本
}
```

## 🚀 快速开始

### 1. 环境准备
```bash
# 安装依赖
pip install pyserial mpremote mpy-cross

# 连接设备并查看端口
python build.py --diagnose
```

### 2. 配置设备
编辑 `app/config.py` 文件，修改MQTT和WiFi配置。

### 3. 构建和部署
```bash
# 编译并上传
python build.py

# 监控设备输出
python build.py --monitor

# 启动REPL调试
python build.py --repl
```

## 📖 常见问题 (FAQ)

### 目录
- [连接问题](#连接问题)
- [配置问题](#配置问题)
- [性能问题](#性能问题)
- [开发问题](#开发问题)

### 连接问题

**Q: 设备无法连接WiFi？**
A: 检查WiFi配置是否正确，确保：
- SSID和密码正确
- 路由器在工作范围内
- 尝试重启设备

**Q: MQTT连接失败？**
A: 检查MQTT配置：
- 服务器地址和端口正确
- 用户名和密码正确
- Home Assistant的MQTT集成已启用

**Q: 设备频繁断线重连？**
A: 可能原因：
- WiFi信号弱
- MQTT服务器不稳定
- 配置的重连参数过于激进

### 配置问题

**Q: 如何修改LED引脚？**
A: 在 `app/hw/led.py` 中修改LED引脚定义。

**Q: 如何添加新的传感器？**
A: 在 `app/hw/` 目录下创建新的传感器模块，并在主程序中集成。

**Q: 如何调整日志级别？**
A: 在 `app/lib/logger.py` 中修改日志级别设置。

### 性能问题

**Q: 内存不足怎么办？**
A: 优化建议：
- 减少不必要的变量和对象
- 使用生成器替代列表
- 及时释放大对象
- 调整垃圾回收频率

**Q: 设备运行缓慢？**
A: 检查：
- 主循环延迟是否过长
- 是否有阻塞操作
- 内存使用情况

### 开发问题

**Q: 如何调试设备？**
A: 调试方法：
- 使用 `python build.py --monitor` 查看日志
- 使用 `python build.py --repl` 进行交互式调试
- 检查LED状态指示

**Q: 如何添加新功能？**
A: 开发流程：
1. 创建新模块
2. 在EventBus中注册事件
3. 在状态机中添加处理逻辑
4. 测试和部署

## 🔄 系统工作流程

### 启动流程
```
boot.py → main.py → 配置加载 → 网络连接 → 主循环
```

### 主循环流程
```
喂看门狗 → 状态机更新 → 事件处理 → LED更新 → 状态监控 → 循环
```

### 事件处理流程
```
事件发生 → EventBus.publish → 事件队列 → 主循环处理 → 订阅者回调
```

## 📊 系统状态

### LED状态指示
- **INIT**: 快速闪烁 (系统初始化)
- **CONNECTING**: 脉冲模式 (连接中)
- **RUNNING**: 常亮 (正常运行)
- **ERROR**: SOS模式 (错误状态)

### MQTT主题结构
```
device/{device_id}/state/metrics     # 系统指标
device/{device_id}/state/temperature # 温度数据
device/{device_id}/state/humidity    # 湿度数据
```

## 🛠️ 开发命令

```bash
# 构建和部署
python build.py                    # 编译并上传
python build.py --compile          # 仅编译
python build.py --upload           # 仅上传
python build.py --full-upload      # 强制全量上传

# 调试和监控
python build.py --monitor          # 监控设备输出
python build.py --repl             # 启动REPL
python build.py --diagnose         # 诊断设备状态

# 其他功能
python build.py --test             # 包含测试文件编译
python build.py --clean-cache      # 清理本地缓存
```

## ⚠️ 重要说明

- **内存限制**: ESP32C3只有264KB内存，必须时刻注意内存使用
- **文件位置**: 所有代码位于 `app/` 目录，编译后上传到设备根目录
- **导入机制**: 设备上从根目录导入，不存在 `app` 包
- **配置管理**: 所有配置在 `config.py` 中统一管理
- **语言**: 代码注释和文档使用中文

## 📝 版本信息

- **当前版本**: 2.3.0 (架构重构版)
- **架构版本**: 事件驱动架构 v3.0 (软件定时驱动)
- **最后更新**: 2025-08-24
- **维护者**: ESP32C3 开发团队

---

**最后更新**: 2025-08-24  
**版本**: 2.3.0 (架构重构版)  
**架构**: 事件驱动架构 v3.0  
**维护者**: ESP32C3 开发团队