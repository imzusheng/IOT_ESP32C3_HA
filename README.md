# ESP32-C3 IoT 系统

一个基于 ESP32-C3 微控制器的高性能 IoT 系统，采用事件驱动架构和温度自适应优化技术。

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
│   ├── main.py               # 主程序入口
│   ├── config.py             # 配置管理模块
│   ├── config.json           # 系统配置文件
│   ├── core.py               # 核心功能模块（事件总线、日志）
│   ├── utils.py              # 工具模块（WiFi、NTP、LED）
│   └── daemon.py             # 系统守护进程
├── deploy.py                 # 部署脚本
├── dist/                     # 编译后的 .mpy 文件
└── README.md                 # 项目文档
```

## 🏗️ 系统架构

### 模块关系图
```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   main.py   │    │  daemon.py  │    │  utils.py   │
│  主控制器   │    │  系统守护   │    │  工具模块   │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                   ┌──────▼──────┐
                   │   core.py   │
                   │  事件总线   │
                   └──────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  config.py  │
                   │  配置管理   │
                   └─────────────┘
```

### 事件驱动架构
- **事件总线**：模块间通信的核心，支持异步事件发布/订阅
- **配置驱动**：所有模块通过配置模块获取参数，支持运行时更新
- **温度优化**：根据 MCU 温度自动调整系统性能参数

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

### LED效果控制
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