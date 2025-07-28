# ESP32-C3 IoT系统

基于MicroPython的ESP32-C3物联网系统，具备WiFi连接、LED控制、系统监控和日志记录功能。

## 设备信息

```bash
Chip is ESP32-C3 (QFN32) (revision v0.4)
Features: Wi-Fi, BT 5 (LE), Single Core, 160MHz
Crystal is 40MHz
MAC: 50787df23340
Manufacturer: 68
Device: 4016
Status value: 0x400000
Detected flash size: 4MB
```

## 概述

这是一个基于ESP32-C3微控制器的IoT系统，具有以下核心特性：

- 🌐 **WiFi连接管理** - 自动连接WiFi网络，支持连接状态监控
- 💡 **智能LED控制** - 支持多种灯效模式（常亮、呼吸灯、关闭等）
- 🛡️ **系统守护进程** - 硬件定时器驱动的守护进程，提供系统保护
- 🌡️ **温度监控** - 实时监控芯片温度，超温保护
- 📝 **日志系统** - 错误日志记录和文件滚动管理
- ⏰ **NTP时间同步** - 网络时间同步功能

## 系统架构

### 🏗️ 模块设计

- **main.py** - 主程序入口，负责系统初始化和业务逻辑循环
- **daemon.py** - 守护进程模块，提供系统监控和保护功能
- **utils.py** - 工具函数模块，包含WiFi、NTP和LED控制功能
- **logger.py** - 日志系统，负责错误日志的记录和管理
- **boot.py** - 启动配置，启用垃圾回收机制

### 🔄 工作流程

1. **系统启动** - 启动守护进程，初始化硬件
2. **网络连接** - 连接WiFi网络
3. **时间同步** - 通过NTP同步系统时间
4. **业务循环** - 执行主要业务逻辑，处理日志队列
5. **后台监控** - 守护进程持续监控系统状态

## 文件结构

```
micropython_src/
├── main.py            # 主程序入口
├── daemon.py          # 系统守护进程模块
├── utils.py           # 工具函数模块（WiFi、NTP、LED控制）
├── logger.py          # 日志系统模块
└── boot.py            # 启动配置文件
```

## 快速开始

### 1. 配置WiFi

在 `main.py` 中修改WiFi凭据：

```python
WIFI_SSID = "你的WiFi名称"
WIFI_PASSWORD = "你的WiFi密码"
```

### 2. 上传代码

将 `micropython_src/` 目录下的所有文件上传到ESP32-C3设备。

### 3. 运行系统

```python
# 在ESP32-C3上运行
import main
```

### 4. LED控制示例

```python
import utils

# 设置LED1常亮
utils.set_effect('single_on', led_num=1)

# 设置呼吸灯效果
utils.set_effect('breathing')

# 关闭所有LED
utils.set_effect('off')
```

## API 参考

### 守护进程模块 (daemon.py)

#### `start_critical_daemon()`
启动系统守护进程。

**返回：**
- `True`: 启动成功
- `False`: 启动失败

#### `get_log_queue()`
获取守护进程的日志队列。

**返回：** 日志条目列表

### 工具模块 (utils.py)

#### WiFi功能

##### `connect_wifi(ssid, password)`
连接到指定的WiFi网络。

**参数：**
- `ssid` (str): WiFi网络名称
- `password` (str): WiFi密码

**返回：** `True` 连接成功，`False` 连接失败

##### `sync_ntp_time()`
通过NTP同步系统时间。

**返回：** `True` 同步成功，`False` 同步失败

#### LED控制功能

##### `init_leds()`
初始化LED PWM硬件。

**返回：** `True` 初始化成功，`False` 初始化失败

##### `set_effect(mode, led_num=1, brightness_u16=MAX_BRIGHTNESS)`
设置LED灯效。

**参数：**
- `mode` (str): 灯效模式 ('off', 'single_on', 'both_on', 'breathing')
- `led_num` (int): LED编号 (1 或 2)，仅在 'single_on' 模式下有效
- `brightness_u16` (int): 亮度值 (0-65535)

##### `update_led_effect()`
更新LED状态（由守护进程调用）。

##### `deinit_leds()`
关闭LED PWM硬件。

### 日志模块 (logger.py)

#### `process_log_queue()`
处理日志队列，将日志写入文件。

## 配置参数

### 守护进程配置 (daemon.py)

```python
CONFIG = {
    # 定时器间隔配置
    'main_interval_ms': 1000,         # 主循环间隔 (毫秒)
    'watchdog_interval_ms': 3000,     # 看门狗间隔 (毫秒)
    'monitor_interval_ms': 10000,     # 监控间隔 (毫秒)
    'perf_report_interval_s': 10,     # 性能报告间隔 (秒)
    
    # 安全保护配置
    'temperature_threshold': 60.0,    # 温度阈值 (°C)
    'wdt_timeout_ms': 10000,          # 看门狗超时 (毫秒)
    'blink_interval_ms': 200,         # 安全模式闪烁间隔 (毫秒)
    'safe_mode_cooldown_ms': 5000,    # 安全模式冷却时间 (毫秒)
    
    # 错误处理配置
    'max_error_count': 10,            # 最大错误计数
    'error_reset_interval_ms': 60000, # 错误重置间隔 (毫秒)
    'max_recovery_attempts': 5        # 最大恢复尝试次数
}
```

### LED控制配置 (utils.py)

```python
LED_PIN_1 = 12                  # LED 1 引脚
LED_PIN_2 = 13                  # LED 2 引脚
PWM_FREQ = 60                   # PWM频率 (Hz)
MAX_BRIGHTNESS = 20000          # 最大亮度
FADE_STEP = 256                 # 呼吸灯步长
```

### WiFi和NTP配置 (utils.py)

```python
WIFI_CONNECT_TIMEOUT_S = 15     # WiFi连接超时 (秒)
NTP_RETRY_COUNT = 3             # NTP重试次数
NTP_RETRY_DELAY_S = 2           # NTP重试延迟 (秒)
```

## 系统特性

### 🛡️ 安全保护机制

1. **看门狗保护**
   - 硬件看门狗定时器，防止系统死锁
   - 定期喂狗，超时自动重启

2. **温度监控**
   - 实时监控ESP32-C3内部温度
   - 超温自动进入安全模式
   - 温度恢复后自动退出安全模式

3. **错误处理**
   - 自动错误计数和定期重置
   - 多重硬件恢复尝试
   - 关键错误触发紧急重启

4. **安全模式**
   - 紧急情况下LED交替闪烁指示
   - 关闭PWM硬件，降低系统负载
   - 保护硬件免受损坏

### 📝 日志系统

- 错误日志自动记录到文件
- 日志文件大小限制和自动滚动
- 队列化日志处理，避免阻塞

### 💡 LED控制

- 支持多种灯效模式
- PWM硬件控制，亮度可调
- 低功耗设计，静态模式不消耗CPU

## 硬件要求

- **微控制器**: ESP32-C3
- **LED**: 连接到GPIO 12和13引脚
- **内存**: 建议至少64KB RAM
- **定时器**: 需要2个硬件定时器
- **WiFi**: 2.4GHz WiFi网络

## 使用场景

### ✅ 适用场景

- IoT设备状态指示
- 环境监控系统
- 智能家居设备
- 远程监控节点
- 需要WiFi连接的嵌入式设备

### 🔧 扩展可能

- 添加传感器数据采集
- 集成MQTT通信
- 连接Home Assistant
- 添加Web服务器
- 实现OTA更新

## 故障排除

### 常见问题

**Q: WiFi连接失败？**
A: 检查SSID和密码是否正确，确保设备在WiFi信号范围内。

**Q: LED不亮？**
A: 检查GPIO 12和13引脚连接，确保LED正确连接。

**Q: 守护进程启动失败？**
A: 检查硬件连接，确保有足够的内存空间。

**Q: 时间同步失败？**
A: 确保WiFi连接正常，检查网络是否允许NTP访问。

**Q: 系统进入安全模式？**
A: 检查设备温度，确保散热良好，等待温度降低后自动恢复。

### 调试方法

1. 检查串口输出的状态信息
2. 观察LED指示灯状态
3. 检查error.log文件内容
4. 监控系统性能报告

## 开发说明

### 代码结构

- **模块化设计**: 功能分离，便于维护和扩展
- **错误处理**: 完善的异常捕获和错误恢复机制
- **资源管理**: 自动垃圾回收和内存优化
- **硬件抽象**: 统一的硬件接口，便于移植

### 性能优化

- 静态LED模式下CPU使用率极低
- 队列化日志处理，避免I/O阻塞
- 定时器中断驱动，确保实时响应
- 内存使用监控和自动回收

## 许可证

本项目采用 MIT 许可证。

## 贡献

欢迎提交问题报告和功能请求。请确保代码符合项目规范并经过充分测试。

## 注意事项

⚠️ **重要提醒**：

1. 确保WiFi凭据正确配置
2. 检查LED硬件连接
3. 监控设备温度，确保散热良好
4. 定期检查日志文件
5. 在生产环境中使用前请充分测试

---

**ESP32-C3 IoT系统**  
*基于MicroPython的物联网解决方案*