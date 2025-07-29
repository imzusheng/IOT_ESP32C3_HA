# ESP32-C3 IoT系统 (重构版本 v2.0)

基于MicroPython的ESP32-C3物联网系统，采用事件驱动架构，具备WiFi连接、LED控制、系统监控和日志记录功能。

## 🎯 重构亮点

- ✅ **事件总线系统** - 实现发布/订阅模式，模块间完全解耦
- ✅ **配置管理中心** - 集中管理所有系统配置，告别硬编码
- ✅ **守护进程优化** - 独立稳定的系统监控，错误隔离机制
- ✅ **模块化设计** - 高内聚低耦合，易于维护和扩展
- ✅ **异步事件驱动** - 提高系统响应性和稳定性

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

这是一个基于ESP32-C3微控制器的IoT系统，采用事件驱动架构重构，具有以下核心特性：

- 🌐 **WiFi连接管理** - 自动连接WiFi网络，事件驱动状态通知
- 💡 **智能LED控制** - 支持多种灯效模式，事件驱动控制
- 🛡️ **系统守护进程** - 完全独立的守护进程，通过事件总线通信
- 🌡️ **温度监控** - 实时监控芯片温度，事件驱动安全保护
- 📝 **日志系统** - 事件驱动的日志记录和文件管理
- ⏰ **NTP时间同步** - 网络时间同步，事件通知机制
- 🚌 **事件总线** - 核心通信机制，实现模块间解耦
- ⚙️ **配置管理** - 集中化配置管理，提高可维护性

## 系统架构

### 🏗️ 模块设计 (重构版本)

- **main.py** - 主程序入口，事件驱动的系统协调器
- **event_bus.py** - 事件总线核心，实现发布/订阅模式
- **config.py** - 配置管理中心，集中管理所有系统配置
- **daemon.py** - 独立守护进程，通过事件总线通信
- **utils.py** - 工具模块，事件驱动的WiFi、NTP和LED控制
- **logger.py** - 日志系统，事件驱动的日志记录
- **boot.py** - 启动配置，启用垃圾回收机制

### 🔄 工作流程 (事件驱动)

1. **系统启动** - 初始化事件总线和配置管理
2. **守护进程启动** - 独立启动，通过事件发布系统状态
3. **异步任务启动** - 启动WiFi、NTP、LED效果异步任务
4. **事件驱动通信** - 所有模块通过事件总线通信
   - WiFi连接成功 → 发布 `wifi_connected` 事件
   - NTP同步完成 → 发布 `ntp_synced` 事件
   - 温度超限 → 发布 `temperature_overheat` 事件
5. **LED状态指示** - 订阅网络事件，自动更新LED状态
6. **业务循环** - 事件驱动的系统维护和监控
7. **后台监控** - 守护进程独立监控，错误隔离

## 文件结构 (重构版本)

```
micropython_src/
├── main.py            # 主程序入口 (事件驱动)
├── event_bus.py       # 事件总线核心模块
├── config.py          # 配置管理中心
├── daemon.py          # 独立守护进程模块
├── utils.py           # 工具函数模块 (事件驱动)
├── logger.py          # 日志系统模块 (事件驱动)
├── boot.py            # 启动配置文件
├── temp_optimization.py   # 温度优化模块 (动态温度管理)
├── test_refactor.py   # 重构测试脚本
└── REFACTOR_SUMMARY.md # 重构总结文档
```

## 快速开始

### 1. 配置WiFi

在 `config.py` 中修改WiFi凭据：

```python
WIFI_CONFIGS = [
    {"ssid": "你的WiFi名称", "password": "你的WiFi密码"},
    {"ssid": "备用WiFi", "password": "备用密码"},
    # 可以添加更多网络配置
]
```

### 2. 上传代码

将 `micropython_src/` 目录下的所有文件上传到ESP32-C3设备。

### 3. 运行系统

```python
# 在ESP32-C3上运行
import main
```

### 4. 事件驱动示例

```python
import event_bus
import utils

# 订阅WiFi连接事件
def on_wifi_connected(**kwargs):
    print(f"WiFi已连接: {kwargs.get('ip_address')}")
    utils.set_effect('single_on', led_num=1)  # 设置LED常亮

event_bus.subscribe('wifi_connected', on_wifi_connected)

# 订阅温度过热事件
def on_temperature_overheat(**kwargs):
    temp = kwargs.get('temperature')
    print(f"警告：温度过热 {temp}°C")

event_bus.subscribe('temperature_overheat', on_temperature_overheat)

# LED控制示例
utils.set_effect('single_on', led_num=1)  # LED1常亮
utils.set_effect('breathing')             # 呼吸灯效果
utils.set_effect('off')                   # 关闭所有LED
```

## API 参考

### 事件总线模块 (event_bus.py)

#### `subscribe(event_type, callback)`
订阅指定类型的事件。

**参数：**
- `event_type` (str): 事件类型名称
- `callback` (callable): 事件回调函数

#### `publish(event_type, **kwargs)`
发布事件，通知所有订阅者。

**参数：**
- `event_type` (str): 事件类型名称
- `**kwargs`: 事件参数

#### 支持的事件类型
- `wifi_connected`: WiFi连接成功
- `wifi_disconnected`: WiFi断开连接
- `ntp_synced`: NTP时间同步成功
- `temperature_overheat`: 温度过热
- `enter_safe_mode`: 进入安全模式
- `log_critical`: 关键错误日志
- `log_info`: 信息日志
- `log_warning`: 警告日志

### 配置管理模块 (config.py)

#### `validate_config()`
验证配置的有效性。

**返回：** `True` 配置有效，`False` 配置无效

#### `get_wifi_configs()`
获取WiFi配置列表。

#### `get_led_config()`
获取LED硬件配置。

#### `get_daemon_config()`
获取守护进程配置。

#### `get_safety_config()`
获取安全保护配置。

### 守护进程模块 (daemon.py)

#### `start_critical_daemon()`
启动系统守护进程。

**返回：**
- `True`: 启动成功
- `False`: 启动失败

**特点：**
- 完全独立运行，不依赖其他业务模块
- 通过事件总线发布系统状态
- 配置驱动的参数管理

### 工具模块 (utils.py) - 事件驱动版本

#### 异步任务系统

##### `start_all_tasks()`
启动所有异步任务（WiFi、NTP、LED）。

##### `wifi_task()`
WiFi连接和重连管理异步任务。
- 智能扫描可用网络
- 按配置优先级连接
- 自动重连机制
- **事件发布**: 连接成功时发布 `wifi_connected` 事件
- **配置驱动**: 从config模块获取WiFi配置

##### `ntp_task()`
NTP时间同步异步任务。
- **事件驱动**: 订阅 `wifi_connected` 事件自动触发同步
- **事件发布**: 同步成功时发布 `ntp_synced` 事件
- 定期重新同步（24小时）
- 时区自动转换

##### `led_effect_task()`
LED效果异步任务。
- **事件驱动**: 订阅网络状态事件自动更新LED
- 呼吸灯动画
- 状态指示
- 非阻塞更新

#### LED控制功能

##### `init_leds()`
初始化LED PWM硬件。

**返回：** `True` 初始化成功，`False` 初始化失败

##### `set_effect(mode, led_num=1, brightness_u16=MAX_BRIGHTNESS)`
设置LED效果模式。

**参数：**
- `mode` (str): 效果模式
  - `'off'`: 关闭
  - `'single_on'`: 单灯常亮
  - `'both_on'`: 双灯常亮
  - `'breathing'`: 呼吸灯效果
- `led_num` (int): LED编号 (1 或 2)
- `brightness_u16` (int): 亮度值 (0-65535)

##### `deinit_leds()`
关闭并释放LED PWM硬件资源。

### 日志模块 (logger.py) - 事件驱动版本

#### `init_logger()`
初始化日志系统，订阅日志事件。

#### `process_log_queue()`
处理日志队列，将日志写入文件。

#### `log_info(message)`
记录信息级别日志。

#### `log_warning(message)`
记录警告级别日志。

#### `log_critical(message)`
记录关键错误日志。

#### 事件驱动特性
- 自动订阅 `log_info`、`log_warning`、`log_critical` 事件
- 通过事件总线接收日志消息
- 独立的日志队列管理
- 自动日志轮转

## 配置参数 (重构版本)

### 配置管理中心 (config.py)

重构后所有配置都集中在 `config.py` 文件中管理：

#### WiFi网络配置
```python
WIFI_CONFIGS = [
    {"ssid": "Lejurobot", "password": "Leju2022"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
    # 可以继续添加更多网络配置
]

WIFI_CONNECT_TIMEOUT_S = 15     # WiFi连接超时时间（秒）
WIFI_RETRY_INTERVAL_S = 60      # WiFi重连间隔时间（秒）
```

#### LED硬件配置
```python
LED_PIN_1 = 12                  # LED 1 引脚
LED_PIN_2 = 13                  # LED 2 引脚
PWM_FREQ = 60                   # PWM频率 (Hz)
MAX_BRIGHTNESS = 20000          # 最大亮度
FADE_STEP = 256                 # 呼吸灯步长
```

#### 守护进程配置
```python
DAEMON_CONFIG = {
    'main_interval_ms': 5000,         # 主循环间隔 (毫秒)
    'watchdog_interval_ms': 5000,     # 看门狗间隔 (毫秒)
    'monitor_interval_ms': 30000,     # 监控间隔 (毫秒)
    'perf_report_interval_s': 30,     # 性能报告间隔 (秒)
}
```

#### 安全保护配置
```python
SAFETY_CONFIG = {
    'temperature_threshold': 45.0,    # 温度阈值 (°C) - 已优化
    'wdt_timeout_ms': 10000,          # 看门狗超时 (毫秒)
    'blink_interval_ms': 200,         # 安全模式闪烁间隔 (毫秒)
    'safe_mode_cooldown_ms': 5000,    # 安全模式冷却时间 (毫秒)
    'max_error_count': 10,            # 最大错误计数
    'error_reset_interval_ms': 60000, # 错误重置间隔 (毫秒)
    'max_recovery_attempts': 5        # 最大恢复尝试次数
}
```

#### 系统配置
```python
SYSTEM_CONFIG = {
    'main_loop_interval_s': 5,        # 主业务循环间隔（秒）
    'gc_interval_loops': 20,          # 垃圾回收间隔（循环次数）
    'status_report_interval_loops': 12, # 状态报告间隔（循环次数）
}
```

### NTP时间同步配置

```python
NTP_SERVER = "pool.ntp.org"      # NTP服务器
NTP_TIMEOUT_S = 10               # NTP超时时间 (秒)
NTP_RETRY_DELAY_S = 60           # NTP重试延迟 (秒)
TIMEZONE_OFFSET_H = 8            # 时区偏移 (小时)
WIFI_CONNECT_TIMEOUT_S = 15     # WiFi连接超时 (秒)
NTP_RETRY_COUNT = 3             # NTP重试次数
```

## 温度优化分析

### 当前温度问题

系统运行时温度达到39°C，可能的原因和优化措施：

#### 1. 定时器频率优化
- **原因**: 原始配置中主循环间隔为1000ms，频繁的任务调度增加CPU负载
- **优化**: 已将主循环间隔调整为5000ms，减少50%的CPU使用率
- **效果**: 预计降低温度2-3°C

#### 2. PWM频率调整
- **当前配置**: PWM频率60Hz，可能导致持续的电流消耗
- **建议**: 考虑降低到30Hz或使用更节能的LED控制方式
- **代码位置**: `config.py` 中的 `PWM_FREQ` 参数

#### 3. 监控间隔优化
- **原因**: 原始监控间隔10秒过于频繁，增加传感器读取负载
- **优化**: 已调整为30秒间隔，减少温度传感器访问频率
- **效果**: 减少硬件I/O操作，降低功耗

#### 4. 安全阈值调整
- **优化**: 将温度阈值从60°C降低到45°C，提前触发保护机制
- **好处**: 更早进入安全模式，防止过热损坏

#### 5. 系统负载分析
- **WiFi连接**: 频繁的网络活动可能增加功耗
- **异步任务**: 多个并发任务可能导致CPU过载
- **建议**: 监控 `daemon.py` 中的性能报告，识别高负载任务

### 进一步优化建议

1. **动态频率调整**: 根据温度动态调整任务频率
2. **睡眠模式**: 在空闲时使用深度睡眠模式
3. **LED亮度控制**: 降低LED最大亮度减少功耗
4. **网络优化**: 减少不必要的网络请求频率

### 温度优化模块 (temp_optimization.py)

为了解决39°C的温度问题，新增了专门的温度优化模块：

#### 功能特性
- **动态温度监控**: 实时监控系统温度并自动调整配置
- **分级优化策略**: 根据温度级别(normal/warning/critical/emergency)应用不同优化
- **自动功耗管理**: 动态调整PWM频率、LED亮度和任务间隔
- **优化历史记录**: 记录温度变化和优化策略的历史

#### 温度分级阈值
```python
TEMP_THRESHOLDS = {
    'normal': 35.0,      # 正常温度阈值
    'warning': 40.0,     # 警告温度阈值 (当前39°C属于此级别)
    'critical': 45.0,    # 危险温度阈值
    'emergency': 50.0,   # 紧急温度阈值
}
```

#### 使用示例
```python
from temp_optimization import temp_optimizer

# 检查当前温度并应用优化
current_temp = 39.0  # 当前温度
optimization_info = temp_optimizer.check_and_optimize(current_temp)

# 获取优化后的配置
optimized_config = optimization_info['optimized_config']
print(f"建议主循环间隔: {optimized_config['main_interval_ms']}ms")
print(f"建议PWM频率: {optimized_config['pwm_freq']}Hz")
print(f"建议LED亮度: {optimized_config['max_brightness']}")
```

#### 针对39°C的具体优化
当温度达到39°C时，系统会自动：
1. 将主循环间隔从5秒延长到8秒
2. 将监控间隔从30秒延长到45秒
3. 将PWM频率从60Hz降低到40Hz
4. 将LED最大亮度降低到75% (15000)
5. 预计温度降低3-5°C

## 系统特性

### 🚀 异步架构

- **事件驱动**：WiFi连接成功自动触发NTP同步
- **非阻塞操作**：所有网络和I/O操作均为异步
- **任务管理**：统一的异步任务生命周期管理
- **回调机制**：支持注册和触发事件回调函数

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

### 🌐 智能连接

- **多网络支持**：支持配置多个WiFi网络作为备选
- **智能扫描**：自动扫描可用网络并按优先级连接
- **自动重连**：网络断开时自动重连机制
- **温度保护**：高温时暂停连接尝试

### 📝 日志系统

- 错误日志自动记录到文件
- 日志文件大小限制和自动滚动
- 队列化日志处理，避免阻塞

### 💡 LED状态指示

- **PWM控制**：精确的亮度控制
- **动态效果**：呼吸灯、闪烁等动画效果
- **状态映射**：
  - 呼吸灯：等待WiFi连接
  - 常亮：WiFi连接成功
  - 闪烁：连接过程中

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