# ESP32-C3 IoT 系统 - 重构版本

一个基于 ESP32-C3 微控制器的高性能 IoT 系统，采用模块化架构、事件驱动设计和温度自适应优化技术。

## 🔄 重构更新 (v2.0.0)

本项目已完成重大重构，主要改进包括：
- **模块化架构**：将原有的大型模块拆分为专门的功能模块
- **清理冗余代码**：移除重复和过时的代码注释
- **优化导入结构**：使用新的lib包结构组织代码
- **增强LED功能**：合并并增强LED控制功能
- **温度优化独立**：将温度优化功能独立为专门模块

## 🚀 项目特性

### 核心功能
- **WiFi 连接管理**：自动连接、智能重连、状态监控
- **NTP 时间同步**：定期同步、时区处理
- **LED 硬件控制**：PWM 控制、多种灯效、呼吸灯效果
- **系统守护进程**：看门狗管理、温度监控、安全模式
- **事件驱动架构**：模块间解耦、异步处理

### 技术亮点
- **温度自适应优化**：根据 MCU 温度动态调整系统参数
- **配置驱动设计**：支持 JSON 配置文件，运行时可调
- **模块化架构**：高内聚低耦合，易于维护和扩展
- **错误隔离机制**：单模块故障不影响系统稳定性
- **内存优化**：代码体积优化，适合资源受限环境

## 📁 项目结构

```
IOT_ESP32C3/
├── micropython_src/          # MicroPython 源代码
│   ├── boot.py               # 系统启动脚本
│   ├── main.py               # 主程序入口（重构）
│   ├── config.py             # 配置管理模块
│   ├── config.json           # 系统配置文件
│   ├── core.py               # 核心事件总线模块（精简）
│   ├── daemon.py             # 系统守护进程（更新导入）
│   ├── logger.py             # 日志系统模块
│   └── lib/                  # 功能模块包（新增）
│       ├── __init__.py       # 包初始化文件
│       ├── wifi.py           # WiFi管理模块（从utils分离）
│       ├── ntp.py            # NTP时间同步模块（从utils分离）
│       ├── led.py            # LED控制模块（增强版）
│       └── temp_optimizer.py # 温度优化模块（从main分离）
├── deploy.py                 # 部署脚本
├── PLAN.md                   # 重构计划文档
└── README.md                 # 项目文档（更新）
```

## 🏗️ 系统架构

### 重构后模块关系图
```
┌─────────────┐    ┌─────────────┐    ┌─────────────────┐
│   main.py   │    │  daemon.py  │    │   lib/ 包       │
│  主控制器   │    │  系统守护   │    │ ┌─────────────┐ │
│  (精简)     │    │  (更新)     │    │ │   wifi.py   │ │
└──────┬──────┘    └──────┬──────┘    │ │   ntp.py    │ │
       │                  │           │ │   led.py    │ │
       │                  │           │ │temp_opt.py  │ │
       └──────────────────┼───────────┤ └─────────────┘ │
                          │           └─────────┬───────┘
                   ┌──────▼──────┐              │
                   │   core.py   │◄─────────────┘
                   │ 事件总线核心 │
                   │  (精简)     │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  config.py  │
                   │  配置管理   │
                   └─────────────┘
```

### 重构后架构特点
- **模块化设计**：功能模块独立，职责单一，易于维护
- **事件总线核心**：精简的事件系统，专注于模块间通信
- **包结构组织**：使用lib包组织功能模块，结构清晰
- **温度优化独立**：专门的温度优化模块，支持动态系统调整
- **LED功能增强**：合并并增强LED控制，支持更多灯效模式

## ⚙️ 配置说明

### WiFi 配置
```json
"wifi": {
  "configs": [
    {"ssid": "你的WiFi名称", "password": "你的WiFi密码"}
  ],
  "connect_timeout_s": 15,
  "retry_interval_s": 60
}
```

### LED 配置
```json
"led": {
  "pin_1": 12,           // LED1 引脚
  "pin_2": 13,           // LED2 引脚
  "pwm_freq": 60,        // PWM 频率
  "max_brightness": 20000, // 最大亮度
  "fade_step": 256       // 渐变步长
}
```

### 守护进程配置
```json
"daemon": {
  "main_interval_ms": 5000,      // 主循环间隔
  "watchdog_interval_ms": 3000,  // 看门狗间隔
  "monitor_interval_ms": 30000,  // 监控间隔
  "scheduler_interval_ms": 200   // 调度器间隔
}
```

### 安全配置
```json
"safety": {
  "temperature_threshold": 45.0,  // 温度阈值
  "wdt_timeout_ms": 30000,       // 看门狗超时
  "max_error_count": 10,         // 最大错误次数
  "max_recovery_attempts": 5     // 最大恢复尝试次数
}
```

## 📦 重构后的模块说明

### lib/wifi.py - WiFi管理模块
- 从原utils.py中分离的WiFi功能
- 支持多网络配置和自动重连
- 事件驱动的状态通知
- 网络扫描和连接管理

### lib/ntp.py - NTP时间同步模块  
- 从原utils.py中分离的NTP功能
- 定期时间同步和时区处理
- 网络时间获取和本地时间设置
- 事件驱动的同步状态通知

### lib/led.py - LED控制模块（增强版）
- 合并原led.py和utils.py中的LED功能
- 支持更多灯效模式（心跳、双闪等）
- 异步灯效任务和PWM控制
- 温度优化支持和动态配置

### lib/temp_optimizer.py - 温度优化模块
- 从原main.py中分离的温度优化功能
- 温度级别判断和配置优化
- 系统性能动态调整
- 温度建议和优化策略

### core.py - 事件总线核心（精简版）
- 移除LED和日志功能，专注事件总线
- 轻量级事件发布/订阅机制
- 异步和同步事件处理
- 系统初始化和清理功能

## 🔧 部署指南

### 环境要求
- **硬件**：ESP32-C3 开发板
- **软件**：MicroPython 固件
- **工具**：mpy-cross（用于代码编译）

### 部署步骤

1. **安装 MicroPython 固件**
   ```bash
   esptool.py --chip esp32c3 --port COM6 erase_flash
   esptool.py --chip esp32c3 --port COM6 write_flash -z 0x0 esp32c3-usb-20240602-v1.23.0.bin
   ```

2. **配置串口**
   - 修改 `deploy.py` 中的 `SERIAL_PORT` 为你的串口号
   - Windows: `COM3`, `COM4` 等
   - Linux: `/dev/ttyUSB0`, `/dev/ttyACM0` 等
   - macOS: `/dev/cu.usbserial-xxxx` 等

3. **修改配置**
   - 编辑 `micropython_src/config.json`
   - 配置你的 WiFi 信息
   - 根据硬件调整 LED 引脚

4. **编译和部署**
   ```bash
   python deploy.py
   ```

### 部署脚本功能
- **自动编译**：使用 mpy-cross 将 .py 文件编译为 .mpy
- **文件上传**：通过串口上传编译后的文件到设备
- **设备重启**：自动重启设备加载新代码
- **大小报告**：显示编译后文件大小统计

## 🌡️ 温度优化系统

### 温度级别
- **正常**（< 40°C）：标准性能模式
- **温暖**（40-45°C）：轻度优化模式
- **过热**（45-50°C）：中度优化模式
- **危险**（> 50°C）：激进优化模式

### 优化策略
- **动态调频**：根据温度调整 PWM 频率
- **亮度限制**：高温时降低 LED 最大亮度
- **间隔调整**：延长循环间隔减少 CPU 负载
- **功能降级**：必要时禁用非关键功能

## 🔍 系统监控

### 状态指示
- **LED1**：WiFi 连接状态指示
- **LED2**：系统运行状态指示
- **慢闪**：等待WiFi连接
- **快闪**：快速闪烁模式
- **交替闪烁**：两个LED交替闪烁
- **双闪**：快速闪烁两次后暂停
- **心跳闪烁**：模拟心跳节奏的闪烁

### 日志系统
- **分级日志**：CRITICAL、WARNING、INFO
- **队列缓存**：内存中保存最近日志
- **事件驱动**：通过事件总线记录日志

## 🛠️ 开发指南

### 添加新功能
1. **创建模块**：在 `micropython_src/` 下创建新的 .py 文件
2. **注册事件**：在 `config.py` 中定义新的事件类型
3. **订阅事件**：使用 `core.subscribe()` 订阅相关事件
4. **发布事件**：使用 `core.publish()` 发布状态变化

### 事件系统使用
```python
import core
from config import get_event_id

# 订阅事件
def on_custom_event(**kwargs):
    print(f"收到自定义事件: {kwargs}")

core.subscribe('custom_event', on_custom_event)

# 发布事件
core.publish('custom_event', data='hello world')
```

### 重构后的模块使用示例

#### WiFi模块使用
```python
from lib import wifi

# 启动WiFi任务
await wifi.wifi_task()

# 获取WiFi状态
status = wifi.get_wifi_status()
```

#### LED模块使用
```python
from lib.led import init_led, set_led_effect, start_led_task

# 初始化LED
init_led()

# 设置LED效果
set_led_effect('heartbeat_blink', led_num=1, brightness=800)

# 启动LED异步任务
start_led_task()
```

#### 温度优化模块使用
```python
from lib import temp_optimizer

# 根据温度优化系统
await temp_optimizer.optimize_system_by_temperature()

# 获取温度级别
temp_level = temp_optimizer.get_temperature_level(45.0)
```

#### 事件系统使用
```python
import core
from config import get_event_id

# 订阅事件
def on_custom_event(**kwargs):
    print(f"收到自定义事件: {kwargs}")

core.subscribe('custom_event', on_custom_event)

# 发布事件
core.publish('custom_event', data='hello world')
```

## 🔄 重构带来的改进

### 代码质量提升
- **模块职责单一**：每个模块专注特定功能
- **减少代码重复**：消除冗余代码和注释
- **导入结构优化**：清晰的包结构和导入关系
- **错误隔离增强**：模块间依赖减少，故障影响范围缩小

### 维护性改善
- **功能定位容易**：相关功能集中在对应模块
- **测试更加简单**：模块独立，便于单元测试
- **扩展更加方便**：新功能可独立开发和集成
- **调试更加高效**：问题定位更精确

### 性能优化
- **内存使用优化**：按需导入，减少内存占用
- **启动速度提升**：模块化加载，启动更快
- **运行效率改善**：减少不必要的函数调用
- **资源管理优化**：更好的资源分配和释放

## 📋 重构检查清单

- ✅ 创建lib包结构
- ✅ 分离WiFi功能到lib/wifi.py
- ✅ 分离NTP功能到lib/ntp.py  
- ✅ 增强LED功能到lib/led.py
- ✅ 分离温度优化到lib/temp_optimizer.py
- ✅ 精简core.py为事件总线核心
- ✅ 更新main.py导入和逻辑
- ✅ 更新daemon.py导入引用
- ✅ 删除旧的utils.py和led.py文件
- ✅ 清理冗余代码和注释
- ✅ 更新README文档

### 原有LED效果控制（兼容性保持）
```python
import utils

# 设置不同的闪烁效果
utils.set_effect('fast_blink')      # 快闪
utils.set_effect('slow_blink')      # 慢闪
utils.set_effect('alternate_blink') # 交替闪烁
utils.set_effect('double_blink')    # 双闪
utils.set_effect('heartbeat_blink') # 心跳闪烁
utils.set_effect('single_on', led_num=1)  # 单个LED常亮
utils.set_effect('both_on')         # 两个LED常亮
utils.set_effect('off')             # 关闭所有LED
```

### 配置管理
```python
import config

# 获取配置值
wifi_timeout = config.WIFI_CONNECT_TIMEOUT_S
led_pin = config.LED_PIN_1

# 动态配置属性会自动从 config.json 加载
```

## 🚨 故障排除

### 常见问题

1. **WiFi 连接失败**
   - 检查 `config.json` 中的 WiFi 配置
   - 确认信号强度和密码正确
   - 查看串口输出的错误信息

2. **LED 不亮**
   - 检查引脚配置是否正确
   - 确认 LED 硬件连接
   - 检查 PWM 频率设置

3. **系统重启**
   - 检查看门狗配置
   - 查看温度是否过高
   - 检查内存使用情况

4. **部署失败**
   - 确认串口号正确
   - 检查 mpy-cross 是否安装
   - 确认设备连接正常

### 调试模式
在 `config.py` 中设置 `DEBUG = True` 启用详细日志输出。

## 📊 性能指标

### 内存使用
- **代码大小**：约 15KB（编译后）
- **运行内存**：约 50KB
- **配置文件**：约 1KB

### 响应时间
- **WiFi 连接**：5-15 秒
- **NTP 同步**：1-3 秒
- **LED 响应**：< 100ms
- **事件处理**：< 10ms

## 🤝 贡献指南

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [MicroPython](https://micropython.org/) - 优秀的 Python 微控制器实现
- [ESP32-C3](https://www.espressif.com/en/products/socs/esp32-c3) - 强大的 RISC-V 微控制器
- 所有贡献者和测试者

---

**注意**：本项目仍在积极开发中，API 可能会发生变化。建议在生产环境使用前进行充分测试。