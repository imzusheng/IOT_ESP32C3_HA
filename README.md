# ESP32-C3 MicroPython IoT 项目

## 📋 项目概述

这是一个基于ESP32-C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用模块化架构，提供WiFi连接、MQTT通信、系统监控、LED状态指示和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## ✨ 主要特性

- **多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **MQTT通信**: 高效的MQTT客户端，支持指数退避重连策略和内存优化
- **系统监控**: 实时监控温度、内存使用和系统健康状态
- **错误恢复**: 智能错误处理和自动恢复机制
- **内存管理**: 优化的垃圾回收策略，适合ESP32C3的264KB内存限制
- **看门狗保护**: 防止系统死锁，确保设备稳定运行
- **LED状态指示**: 通过LED显示设备运行状态，支持多种预设模式
- **配置管理**: 灵活的配置系统，支持运行时验证
- **Web配置界面**: 基于Web Bluetooth的配置工具，支持Apple设计风格

## 🏗️ 项目架构

### 核心组件

1. **主应用程序** ([`src/main.py`](src/main.py))
   - 系统主控制中心，协调各模块运行
   - 实现主循环、内存管理和看门狗喂狗
   - 集成配置管理器、WiFi连接、MQTT通信和守护进程
   - LED状态指示和系统监控功能

2. **配置管理** ([`src/config.py`](src/config.py))
   - 集中式配置管理，使用Python字典定义所有参数
   - 详细的配置说明和推荐值
   - 分模块配置：MQTT、WiFi、守护进程、系统、设备配置
   - 内存优化：避免JSON文件，减少I/O操作

3. **WiFi管理器** ([`src/lib/net_wifi.py`](src/lib/net_wifi.py))
   - 健壮的WiFi连接管理，支持多网络选择
   - 自动网络扫描和RSSI-based排序
   - NTP时间同步和时区设置
   - 连接超时处理和错误恢复

4. **MQTT客户端** ([`src/lib/net_mqtt.py`](src/lib/net_mqtt.py))
   - 基于umqtt.simple的自定义MQTT包装器
   - 智能连接管理和指数退避重连机制
   - 内存优化的日志发送（使用bytearray）
   - 心跳监控和连接状态跟踪
   - 重连冷却时间和重置机制

5. **系统守护进程** ([`src/sys_daemon.py`](src/sys_daemon.py))
   - 系统监控和安全保护功能
   - LED状态指示控制
   - 温度监控和安全模式
   - 内存监控和垃圾回收
   - 系统健康检查和错误恢复

6. **错误恢复管理器** ([`src/lib/sys/erm.py`](src/lib/sys/erm.py))
   - 统一错误处理和恢复策略管理
   - 分级恢复动作：网络、内存、服务、系统、硬件恢复
   - 恢复成功率统计和冷却时间管理
   - 智能恢复调度和错误处理

7. **状态机系统** ([`src/lib/sys/fsm.py`](src/lib/sys/fsm.py))
   - 清晰的系统状态管理
   - 事件驱动的状态转换
   - 支持INIT、NETWORKING、RUNNING、WARNING、ERROR、SAFE_MODE、RECOVERY、SHUTDOWN状态
   - 状态历史记录和监控

8. **内存优化器** ([`src/lib/sys/memo.py`](src/lib/sys/memo.py))
   - 高效的对象池和缓存管理
   - 字典对象池、字符串缓存、缓冲区管理
   - 减少内存分配和垃圾回收开销
   - 智能内存管理功能

9. **日志系统** ([`src/lib/sys/logger.py`](src/lib/sys/logger.py))
   - 统一的日志管理
   - 错误分类和统计
   - MQTT日志发送
   - 内存友好的日志缓冲

10. **LED控制** ([`src/lib/sys/led.py`](src/lib/sys/led.py))
    - 统一的LED状态指示管理
    - 多种预设闪烁模式
    - 系统状态可视化
    - 单例模式设计，避免重复初始化

11. **工具函数** ([`src/lib/utils.py`](src/lib/utils.py))
    - 通用工具函数库
    - 内存检查和格式化
    - 字符串处理
    - 系统信息获取

12. **启动序列** ([`src/boot.py`](src/boot.py))
    - 垃圾回收初始化
    - 最小化的MicroPython启动脚本

## ⚙️ 配置说明

### 配置文件结构

项目使用纯Python配置系统：
- [`src/config.py`](src/config.py): Python字典配置（主要配置和验证规则）

### 主要配置项

#### MQTT配置
```python
"mqtt": {
    "broker": "192.168.3.15",        # MQTT服务器地址
    "port": 1883,                   # MQTT端口
    "topic": "lzs/esp32c3",         # MQTT主题
    "keepalive": 60,                # 心跳间隔(秒)
    "reconnect_delay": 5,            # 重连延迟(秒)
    "max_retries": 3,                # 最大重试次数
    "exponential_backoff": True,     # 启用指数退避策略
    "max_backoff_time": 300,         # 最大退避时间(秒)
    "backoff_multiplier": 2          # 退避倍数因子
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
        "monitor_interval": 5000,    # 监控间隔(毫秒)
        "temp_threshold": 65,       # 温度阈值(°C)
        "temp_hysteresis": 5,       # 温度迟滞(°C)
        "memory_threshold": 80,     # 内存阈值(%)
        "memory_hysteresis": 10,    # 内存迟滞(%)
        "max_error_count": 10,      # 最大错误数
        "safe_mode_cooldown": 60000 # 安全模式冷却(毫秒)
    },
    "wdt_timeout": 120000,          # 看门狗超时(毫秒)
    "wdt_enabled": False,           # 看门狗开关
    "gc_force_threshold": 95        # 强制GC阈值(%)
}
```

#### 系统配置
```python
"system": {
    "debug_mode": False,            # 调试模式
    "log_level": "INFO",            # 日志级别
    "main_loop_delay": 300,         # 主循环延迟(毫秒)
    "status_report_interval": 50,   # 状态报告间隔(循环次数)
    "auto_restart_enabled": False   # 自动重启开关
}
```

#### 设备配置
```python
"device": {
    "name": "ESP32C3-IOT",          # 设备名称
    "location": "未知位置",         # 设备位置
    "firmware_version": "1.0.0"     # 固件版本
}
```

## 🚀 快速开始

### 硬件要求

- ESP32-C3开发板
- LED指示灯（连接到GPIO 12和13）
- USB数据线

### 软件依赖

- **MicroPython固件**: ESP32-C3支持的MicroPython版本
- **umqtt.simple**: 轻量级MQTT客户端库 ([`src/lib/umqtt/simple.py`](src/lib/umqtt/simple.py))
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
   # 使用rshell或类似工具
   rshell cp src/boot.py /pyboard/boot.py
   rshell cp src/config.py /pyboard/config.py
   rshell cp src/main.py /pyboard/main.py
   rshell cp src/lib/ /pyboard/lib/ -r
   ```

3. **配置设备**
   - 修改 [`src/config.py`](src/config.py) 中的配置项
   - 或使用Web配置界面进行配置

4. **重启设备**
   ```bash
   # 重启设备
   rshell repl ~ import machine ~ machine.reset()
   ```

### Web配置界面

项目包含基于Web Bluetooth的配置界面：

- **位置**: [`web/index.html`](web/index.html)
- **功能**: 蓝牙连接、WiFi配置、MQTT配置、设备配置
- **设计**: Apple设计风格，响应式布局
- **浏览器要求**: 支持Web Bluetooth API的现代浏览器

#### 使用Web配置界面

1. **打开页面**
   ```bash
   # 在支持Web Bluetooth API的浏览器中打开
   # file:///path/to/your/project/web/index.html
   ```

2. **连接设备**
   - 点击"连接设备"按钮
   - 选择ESP32C3设备
   - 等待连接完成

3. **配置参数**
   - **WiFi配置**: 扫描并添加WiFi网络
   - **MQTT配置**: 设置MQTT服务器参数
   - **设备配置**: 设置设备基本信息

4. **应用配置**
   - 保存配置后重启设备
   - 设备将使用新配置运行

## 📊 系统状态

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

## 🔧 开发和构建

### 构建脚本

使用 [`build.py`](build.py) 脚本构建项目：

```bash
# 构建项目（排除测试文件）
python build.py

# 构建项目（包含测试文件）
python build.py --test
```

构建脚本会：
1. 编译Python文件为.mpy格式（除boot.py和main.py）
2. 复制所有文件到dist目录
3. 保持目录结构

### 测试

测试文件位于 [`src/tests/`](src/tests/) 目录：

```bash
# 运行内存优化测试
python -m src.tests.test_mem_optimizer
```

## 📱 监控和调试

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

## 🛡️ 错误处理

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
- **看门狗**: 软件实现

## 💡 内存管理

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

### 对象池系统

- **字典对象池**: 避免频繁创建销毁字典对象
- **字符串缓存**: 缓存常用字符串减少内存分配
- **缓冲区管理**: 预分配缓冲区管理器
- **内存优化器**: 提供内存监控和优化功能

## ⏰ 定时器架构

项目采用双定时器架构，实现时间敏感任务和一般管理任务的分离：

### 定时器类型

#### 1. 硬件定时器（machine.Timer）
- **位置**: [`src/sys_daemon.py:418`](src/sys_daemon.py#L418)
- **配置**: `timer_id: 0`, `monitor_interval: 5000ms`
- **初始化**: 在守护进程启动时创建
- **驱动**: `machine.Timer.PERIODIC` 模式
- **回调**: [`_monitor_callback(timer)`](src/sys_daemon.py#L240)
- **功能**: 系统监控、健康检查、LED控制、安全模式管理

#### 2. 软件循环定时器
- **位置**: [`src/main.py:405`](src/main.py#L405)
- **配置**: `main_loop_delay: 300ms`（来自配置文件）
- **驱动**: `time.sleep_ms(loop_delay)`
- **功能**: 主循环调度、看门狗喂狗、状态报告、内存管理

### 驱动机制

#### 硬件定时器
- 由MicroPython的`machine.Timer`硬件定时器驱动
- 每5ms触发一次回调函数
- 用于高频监控任务
- 硬件中断驱动，响应时间精确

#### 软件定时器
- 由主循环中的`time.sleep_ms()`驱动
- 每300ms循环一次
- 用于低频管理任务
- 软件延时驱动，灵活性高

### 执行位置

#### 硬件定时器回调
- **文件**: [`src/sys_daemon.py`](src/sys_daemon.py)
- **函数**: `_monitor_callback(timer)` (第240行)
- **执行频率**: 每5ms执行一次

#### 主循环
- **文件**: [`src/main.py`](src/main.py)
- **函数**: `main_loop()` (第356行)
- **执行频率**: 每300ms循环一次

### 分工协作

#### 硬件定时器职责
- 系统健康检查
- 温度和内存监控
- LED状态控制
- 安全模式管理
- 错误计数管理
- 系统状态记录

#### 软件定时器职责
- 看门狗喂狗
- 状态机管理
- 定期状态报告
- 内存优化
- 错误恢复调度
- 网络连接检查

### 优势

1. **性能优化**: 高频任务和低频任务分离，避免主循环阻塞
2. **响应性**: 硬件定时器确保监控任务的及时响应
3. **稳定性**: 软件定时器处理管理任务，保证系统稳定性
4. **灵活性**: 可独立调整两个定时器的频率和优先级
5. **资源管理**: 合理分配CPU资源，避免不必要的轮询

### 配置参数

```python
# 硬件定时器配置
"daemon": {
    "config": {
        "timer_id": 0,              # 定时器ID
        "monitor_interval": 5000,    # 监控间隔(毫秒)
    }
}

# 软件定时器配置
"system": {
    "main_loop_delay": 300,         # 主循环延迟(毫秒)
    "status_report_interval": 50,   # 状态报告间隔(循环次数)
}
```

## 🌐 网络行为

1. **启动流程**: boot.py → main.py → 配置验证 → WiFi连接
2. **WiFi选择**: 扫描网络 → RSSI排序 → 连接最优网络
3. **时间同步**: NTP服务器同步 + 时区设置
4. **MQTT连接**: 连接代理 → 开始发布日志
5. **守护进程启动**: 开始系统监控 → LED控制 → 系统健康检查
6. **主循环**: 看门狗喂狗 → 内存管理 → 状态监控 → LED状态指示

## 🔄 MQTT 重连机制

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

## 🔄 系统工作流程

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
内存监控 → 阈值检查 → 垃圾回收 → 深度清理 → 
状态报告 → 继续监控
```

## ⚠️ 重要说明

- **内存限制**: ESP32C3只有264KB内存，必须时刻注意内存使用
- **文件位置**: 主要代码位于 `./src` 目录
- **配置管理**: 所有配置项都在 `src/config.py` 中定义
- **语言**: 代码注释和文档使用中文

## 📝 文档更新规范

### 更新要求

**重要**: 以后每次更新功能后，必须同步更新相关文档和注释，确保文档与代码保持一致。

### 更新清单

在完成功能开发后，请检查并更新以下内容：

#### 1. 代码文档
- [ ] 更新函数和类的文档字符串
- [ ] 更新参数说明和返回值描述
- [ ] 添加新增功能的详细注释
- [ ] 更新配置参数说明

#### 2. 项目文档
- [ ] 更新 `README.md` 中的功能描述
- [ ] 更新 `CLAUDE.md` 中的技术细节
- [ ] 更新配置示例和参数说明
- [ ] 添加新功能的使用说明

#### 3. 用户文档
- [ ] 更新常见问题解答
- [ ] 添加新功能的配置指导
- [ ] 更新调试和监控说明
- [ ] 添加故障排除指南

### 更新流程

1. **功能开发** → 完成代码实现
2. **代码注释** → 添加详细的中文注释
3. **文档更新** → 同步更新README.md和CLAUDE.md
4. **验证检查** → 确保文档与代码一致
5. **提交审核** → 提交前再次检查文档完整性

### 文档标准

- **准确性**: 文档必须与实际代码行为一致
- **完整性**: 包含配置、使用、调试等完整信息
- **时效性**: 及时更新，避免过时信息
- **可读性**: 使用清晰的结构和示例

### 责任分工

- **开发者**: 负责更新所开发功能的文档
- **审核者**: 检查文档完整性和准确性
- **维护者**: 定期检查文档更新情况

> **提示**: 良好的文档是项目成功的关键，请务必重视文档更新工作！

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

**最后更新**: 2025-08-08  
**版本**: 1.1.0  
**维护者**: ESP32C3 开发团队