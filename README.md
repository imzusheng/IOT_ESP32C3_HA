# ESP32-C3 MicroPython IoT 项目 (重构版)

- 蓝牙和风扇功能暂时搁置

- ESP32C3 设备基础限制
  - 最多支持 2 个定时器(编号 0 至 1)
  - 总 RAM: 264KB SRAM
  - 总 Flash: 4MB Flash
  - CPU 频率: 160000000 Hz (160.00 MHz)
- machine 模块
  - 支持: ADC, I2C, I2S, PWM, Pin, RTC, SPI, UART, WDT 等
  - machine.ADC: 支持 12 位精度, 多种衰减模式
  - 支持:['__class__', '__name__', 'ADC', 'ADCBlock', 'DEEPSLEEP', 'DEEPSLEEP_RESET', 'EXT0_WAKE', 'EXT1_WAKE', 'HARD_RESET', 'I2C', 'I2S', 'PIN_WAKE', 'PWM', 'PWRON_RESET', 'Pin', 'RTC', 'SDCard', 'SLEEP', 'SOFT_RESET', 'SPI', 'Signal', 'SoftI2C', 'SoftSPI', 'TIMER_WAKE', 'TOUCHPAD_WAKE', 'Timer', 'UART', 'ULP_WAKE', 'WDT', 'WDT_RESET', '__dict__', 'bitstream', 'bootloader', 'deepsleep', 'dht_readinto', 'disable_irq', 'enable_irq', 'freq', 'idle', 'lightsleep', 'mem16', 'mem32', 'mem8', 'reset', 'reset_cause', 'sleep', 'soft_reset', 'time_pulse_us', 'unique_id', 'wake_reason']
  - machine.ADC:['__class__', '__name__', 'read', 'ATTN_0DB', 'ATTN_11DB', 'ATTN_2_5DB', 'ATTN_6DB', 'WIDTH_12BIT', '__bases__', '__dict__', 'atten', 'block', 'init', 'read_u16', 'read_uv', 'width']
- 蓝牙模块
  - bluetooth/ubluetooth: ['__class__', '__name__', 'BLE', 'FLAG_INDICATE', 'FLAG_NOTIFY', 'FLAG_READ', 'FLAG_WRITE', 'FLAG_WRITE_NO_RESPONSE', 'UUID', '__dict__']
- **重要**: 在开发过程中 MQTT 服务器失败为正常现象, 代码中已做好异常处理

## 📋 项目概述

这是一个基于 ESP32-C3 的 MicroPython 物联网设备项目, 专为 Home Assistant 智能家居系统设计。采用**事件驱动架构**和**模块化设计**, 提供 WiFi 连接, MQTT 通信, 系统监控, LED 状态指示和错误恢复等功能, 确保设备在资源受限的嵌入式环境中稳定运行。

## 📁 项目结构

```
IOT_ESP32C3/
├── app/                    # 开发源代码目录 (编译后直接上传到设备根目录)
│   ├── lib/                # 核心库模块
│   │   ├── event_bus_lock.py  # 事件总线 (含事件常量)
│   │   ├── logger.py          # 极简日志系统
│   │   ├── async_runtime.py   # 异步运行时
│   │   ├── ulogging_lock.py   # ulogging 兼容封装
│   │   └── umqtt_lock.py      # umqtt 兼容封装
│   ├── hw/                # 硬件抽象层
│   │   ├── led.py            # LED 控制器
│   │   └── sht40.py          # SHT40 温湿度传感器
│   ├── net/               # 网络通信层
│   │   ├── network_manager.py # 网络管理器
│   │   ├── wifi.py           # WiFi 管理器
│   │   ├── mqtt.py           # MQTT 控制器
│   │   └── ntp.py            # NTP 时间同步
│   ├── utils/             # 工具函数
│   ├── ha.py              # Home Assistant 助手
│   ├── daemon.py          # 守护与系统监管
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
  - 基于 diff 时间的软件定时系统
  - 错误断路器机制, 防止系统级联故障
  - 批量事件处理和内存优化
  - 支持发布-订阅模式

### 状态机 (FSM)

- **位置**: `app/state_machine.py`
- **功能**: 系统状态管理和转换
- **支持状态**: INIT → CONNECTING → RUNNING → ERROR
- **特性**: 事件驱动的状态转换、错误计数和自动恢复

### 网络管理器 (NetworkManager)

- **位置**: `app/net/network_manager.py`
- **功能**: 统一管理 WiFi、MQTT、NTP 连接
- **特性**:
  - 支持多 WiFi 网络自动选择
  - 指数退避重连机制
  - 异步非阻塞调用

### LED 控制器

- **位置**: `app/hw/led.py`
- **功能**: 丰富的 LED 状态指示和模式控制
- **特性**: 开箱即用、延迟初始化、多种预设模式

### 日志系统

- **位置**: `app/lib/logger.py`
- **功能**: 极简日志系统, 专为 ESP32-C3 设计
- **特性**: 零配置、颜色支持、模块标识

### Home Assistant 集成

- **位置**: `app/ha.py`
- **功能**: 发布 Home Assistant discovery 配置、设备可用性 availability、温湿度状态
- **特性**: 可配置 discovery_prefix、设备信息、唯一 ID、支持 retain 发布

## ⚙️ 常用配置

### MQTT 配置 (Home Assistant)

```python
# app/config.py
"mqtt": {
    "broker": "your-home-assistant-ip",  # Home Assistant 服务器地址
    "port": 1883,                         # MQTT 端口
    "user": "your-mqtt-username",       # MQTT 用户名
    "password": "your-mqtt-password",   # MQTT 密码
    "keepalive": 60,                      # 心跳间隔 (秒)
    "base_delay_ms": 3000,                # 重连基础延迟
    "max_delay_ms": 60000,                # 最大重连延迟
    "max_retries": 3,                     # 最大重试次数 (-1 为无限)
    "enable_log_forward": False           # 是否将日志转发到 MQTT
}
```

### WiFi 配置

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
    "max_retries": 3,                     # 最大重试次数 (-1 为无限)
}
```

### HA 配置

```python
# app/config.py
"ha": {
    "discovery_prefix": "homeassistant",
    "device_name": "Zusheng's ESP32C3",
    "manufacturer": "Zusheng STU",
    "model": "C3",
    "sw_version": "2.3.0",
    "temp_name": "Temperature",
    "hum_name": "Humidity",
}
```

### BLE 配置 (可选)

```python
# app/config.py
"ble": {
    "enabled": True,
    "use_hid": False,
    "device_name": "ESP32-C3",
    "adv": {"interval_ms": 150},
    "services": {"battery": True, "device_info": True, "env_sensing": False, "uart": False, "ota": False},
    "security": {"auth": "none", "token": "changeme", "allowlist": []},
    "simulation": {"battery": {"enabled": True, "start": 100, "step": -1, "min": 0, "period_ms": 10000, "strategy": "hardware", "timer_id": 0}},
    "config_service": {"enabled": True, "persistence_path": "/config.json", "allow_reboot": True}
}
```

> 注意: 生产环境建议关闭 `enable_log_forward`, 并将 `security.auth` 设置为 `token`。

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install pyserial mpremote mpy-cross

# 连接设备并查看端口
python build.py --diagnose
```

### 2. 配置设备

编辑 `app/config.py` 文件, 修改 MQTT 和 WiFi 配置。

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

**Q: 设备无法连接 WiFi?**
A: 检查 WiFi 配置是否正确, 确保:

- SSID 和密码正确
- 路由器在工作范围内
- 尝试重启设备

**Q: MQTT 连接失败?**
A: 检查 MQTT 配置:

- 服务器地址和端口正确
- 用户名和密码正确
- Home Assistant 的 MQTT 集成已启用

**Q: 设备频繁断线重连?**
A: 可能原因:

- WiFi 信号弱
- MQTT 服务器不稳定
- 配置的重连参数过于激进

### 配置问题

**Q: 如何修改 LED 引脚?**
A: 在 `app/hw/led.py` 中修改 LED 引脚定义。

**Q: 如何添加新的传感器?**
A: 在 `app/hw/` 目录下创建新的传感器模块, 并在主程序中集成。

**Q: 如何调整日志级别?**
A: 在 `app/lib/logger.py` 中修改日志级别设置。

### 性能问题

**Q: 内存不足怎么办?**
A: 优化建议:

- 减少不必要的变量和对象
- 使用生成器替代列表
- 及时释放大对象
- 调整垃圾回收频率

**Q: 设备运行缓慢?**
A: 检查:

- 主循环延迟是否过长
- 是否有阻塞操作
- 内存使用情况

### 开发问题

**Q: 如何调试设备?**
A: 调试方法:

- 使用 `python build.py --monitor` 查看日志
- 使用 `python build.py --repl` 进行交互式调试
- Windows 独立终端原始 REPL: `python build.py -R`
- 原始 REPL: `python build.py --raw-repl`
- 检查 LED 状态指示

**Q: 如何添加新功能?**
A: 开发流程:

1. 创建新模块
2. 在 EventBus 中注册事件
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

### LED 状态指示

- **INIT**: 快速闪烁 (系统初始化)
- **CONNECTING**: 脉冲模式 (连接中)
- **RUNNING**: 常亮 (正常运行)
- **ERROR**: SOS 模式 (错误状态)

### MQTT 主题结构

```
device/{device_id}/availability         # 设备可用性 (online/offline)
device/{device_id}/state/metrics        # 系统指标
device/{device_id}/state/temperature    # 温度数据
device/{device_id}/state/humidity       # 湿度数据
```

### Home Assistant Discovery 主题

```
{discovery_prefix}/sensor/{device_id}/temperature/config
{discovery_prefix}/sensor/{device_id}/humidity/config
```

> 默认 discovery_prefix 为 `homeassistant`。

## 🛠️ 开发命令

```bash
# 构建和部署
python build.py                    # 编译并上传
python build.py --compile          # 仅编译
python build.py --upload           # 仅上传
python build.py --full-upload      # 强制全量上传

# 调试和监控
python build.py --monitor          # 监控设备输出
python build.py --repl             # 启动 REPL
python build.py -R                 # Windows 独立终端原始 REPL
python build.py --raw-repl         # 原始 REPL
python build.py --diagnose         # 诊断设备状态

# 其他功能
python build.py --clean            # 仅清空设备, 不上传
python build.py --clean-cache      # 清理本地缓存
```

## ⚠️ 重要说明

- **内存限制**: ESP32C3 只有 264KB 内存, 必须时刻注意内存使用
- **文件位置**: 所有代码位于 `app/` 目录, 编译后上传到设备根目录
- **导入机制**: 设备上从根目录导入, 不存在 `app` 包
- **配置管理**: 所有配置在 `config.py` 中统一管理
- **语言**: 代码注释和文档使用中文

## 🔌 硬件连接重要规则

### 风扇控制连接 (利民 TL-S12W 等 PWM 风扇)

**⚠️ 关键要求: 必须连接共地线!**

正确的连接方式:

```
ESP32-C3         风扇
GPIO2    ←→      PWM控制线
GPIO6    ←→      TACH信号线
GND      ←→      GND (共地线) ⚠️ 必须连接!
VIN/3.3V ←→      风扇电源正极 (12V/5V)
```

**常见问题:**

- ❌ 只连接 PWM 和 TACH 线, 不接 GND → 转速读数异常, 信号不稳定
- ❌ 共地线接触不良 → 转速计算错误, 可能出现异常高转速
- ✅ 正确连接共地线 → 转速读数准确, 符合物理实际值(500-1700 RPM)

**诊断工具使用:**

- 使用 `test_tb6612fng.py` 进行引脚配置诊断
- 正确配置应显示: GPIO2=PWM 输出, GPIO6=TACH 输入
- 转速应随 PWM 增加而正常增加, 数值在合理范围内

## 📝 版本信息

- **当前版本**: 2.3.0 (架构重构版)
- **架构版本**: 事件驱动架构 v3.0 (软件定时驱动)
- **最后更新**: 2025-08-29
- **维护者**: ESP32C3 开发团队

---

**最后更新**: 2025-08-29  
**版本**: 2.3.0 (架构重构版)  
**架构**: 事件驱动架构 v3.0  
**维护者**: ESP32C3 开发团队
