# ESP32C3 IoT 设备项目

## 项目概述

这是一个基于ESP32C3的MicroPython物联网设备项目，专为Home Assistant智能家居系统设计。项目采用模块化架构，提供WiFi连接、MQTT通信、系统监控和错误恢复等功能，确保设备在资源受限的嵌入式环境中稳定运行。

## 项目特性

- **多网络WiFi支持**: 自动扫描并连接信号最强的配置网络
- **MQTT通信**: 高效的MQTT客户端，支持自动重连和内存优化
- **系统监控**: 实时监控温度、内存使用和系统健康状态
- **错误恢复**: 智能错误处理和自动恢复机制
- **内存管理**: 优化的垃圾回收策略，适合ESP32C3的264KB内存限制
- **看门狗保护**: 防止系统死锁，确保设备稳定运行
- **LED状态指示**: 通过LED显示设备运行状态
- **NTP时间同步**: 自动同步网络时间，支持时区设置

## 项目结构

```
src/
├── boot.py              # 系统启动脚本，初始化垃圾回收
├── config.py            # 统一配置管理模块
├── main.py              # 主程序入口
├── net_mqtt.py          # MQTT通信模块
├── net_wifi.py          # WiFi管理模块
├── sys_daemon.py        # 系统守护进程
├── sys_error.py         # 错误处理和日志模块
└── lib/
    └── umqtt/
        └── simple.py    # MQTT客户端库
```

## 核心模块详解

### 1. main.py - 主程序入口

**作用**: 系统的主控制中心，协调各模块运行。

**主要功能**:
- 系统初始化和配置验证
- WiFi连接管理
- MQTT客户端创建和连接
- 守护进程启动和管理
- 主循环控制和内存监控
- 看门狗喂狗操作
- 系统状态报告

**关键代码**:
```python
# 初始化看门狗
_wdt = machine.WDT(timeout=config.DaemonConfig.WDT_TIMEOUT)

# WiFi连接
connection_successful = net_wifi.connect_wifi()

# 创建MQTT客户端
mqtt_server = net_mqtt.MqttServer(CLIENT_ID, MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC)
mqtt_server.connect()

# 启动守护进程
daemon_started = sys_daemon.start_daemon()

# 主循环
while True:
    _wdt.feed()  # 喂狗
    # 内存管理和状态监控
    # MQTT连接检查
    # 系统状态报告
```

### 2. config.py - 统一配置管理

**作用**: 集中管理所有系统配置参数，提供配置验证功能。

**配置分类**:
- `MQTTConfig`: MQTT服务器连接参数
- `WiFiConfig`: WiFi网络配置
- `DaemonConfig`: 守护进程参数
- `SystemConfig`: 系统级参数

**关键配置**:
```python
class MQTTConfig:
    BROKER = "192.168.3.15"
    PORT = 1883
    TOPIC = "lzs/esp32c3"
    KEEPALIVE = 60

class WiFiConfig:
    NETWORKS = [
        {"ssid": "zsm60p", "password": "25845600"},
        {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
        {"ssid": "leju_software", "password": "leju123456"}
    ]
    TIMEOUT_S = 15

class DaemonConfig:
    LED_PINS = [12, 13]
    TEMP_THRESHOLD = 60.0
    MEMORY_THRESHOLD = 90
    WDT_TIMEOUT = 10000

class SystemConfig:
    DEBUG_MODE = False
    MAIN_LOOP_DELAY = 300
    AUTO_RESTART_ENABLED = False
```

### 3. net_wifi.py - WiFi管理模块

**作用**: 提供健壮的WiFi连接管理和NTP时间同步功能。

**主要功能**:
- 多WiFi网络支持，按信号强度自动选择
- 网络扫描和RSSI排序
- 自动重连和错误恢复
- NTP时间同步和时区设置
- 连接状态监控

**关键代码**:
```python
def connect_wifi():
    """连接WiFi并同步时间"""
    wlan = network.WLAN(network.STA_IF)
    
    # 扫描网络
    scanned_networks = _scan_for_ssids(wlan)
    
    # 按信号强度排序并连接最优网络
    for network_config in connectable_configs:
        wlan.connect(ssid, password)
        # 等待连接成功
        if wlan.isconnected():
            sync_and_set_time()  # 同步时间
            return True
    return False
```

### 4. net_mqtt.py - MQTT通信模块

**作用**: 提供高效的MQTT通信功能，支持自动重连和内存优化。

**主要功能**:
- MQTT客户端创建和连接管理
- 自动重连机制
- 内存优化的日志发送
- 连接状态监控
- 错误恢复机制

**关键代码**:
```python
class MqttServer:
    def connect(self):
        """连接到MQTT代理"""
        try:
            self.client.connect()
            self.is_connected = True
            self.log("INFO", f"设备在线，ID: {self.client_id}")
            return True
        except Exception as e:
            self.connection_attempts += 1
            return False
    
    def log(self, level, message):
        """格式化并发送日志消息"""
        # 使用bytearray进行内存优化的字符串拼接
        log_ba = bytearray()
        log_ba.extend(f"[{level}] [".encode())
        log_ba.extend(f"{timestamp}".encode())
        log_ba.extend(f"] {message}".encode())
        self.client.publish(self.topic, log_ba)
```

### 5. sys_daemon.py - 系统守护进程

**作用**: 提供系统监控和安全保护功能，确保设备稳定运行。

**主要功能**:
- LED状态指示控制
- 温度监控和安全模式
- 内存监控和垃圾回收
- 系统健康检查
- 错误处理和恢复
- 定时器监控

**关键代码**:
```python
def _monitor_callback(timer):
    """监控定时器回调函数"""
    # 系统健康检查
    health = _perform_health_check()
    
    # 根据健康状态决定是否进入安全模式
    if not health['overall']:
        _enter_safe_mode(f"系统异常: {reason}")
    
    # LED状态控制
    if _safe_mode_active:
        _led_controller.set_status('safe_mode')
    else:
        _led_controller.set_status('normal' if health['overall'] else 'warning')
```

### 6. sys_error.py - 错误处理模块

**作用**: 提供集中式错误处理和日志管理功能。

**主要功能**:
- 统一错误分类和处理
- 智能日志系统
- 自动错误恢复机制
- 内存友好的日志缓冲
- 错误严重程度分类

**错误类型**:
```python
class ErrorType(Enum):
    NETWORK = "NETWORK_ERROR"
    HARDWARE = "HARDWARE_ERROR"
    MEMORY = "MEMORY_ERROR"
    CONFIG = "CONFIG_ERROR"
    SYSTEM = "SYSTEM_ERROR"
    MQTT = "MQTT_ERROR"
    WIFI = "WIFI_ERROR"
    DAEMON = "DAEMON_ERROR"
    FATAL = "FATAL_ERROR"
```

### 7. boot.py - 启动脚本

**作用**: 系统启动时首先执行的脚本，负责初始化垃圾回收。

```python
import gc
gc.collect()
```

## 系统工作流程

### 1. 启动流程

```
boot.py → main.py → config.py → WiFi连接 → MQTT连接 → 守护进程启动 → 主循环
```

### 2. 主循环流程

```
喂狗 → 内存监控 → 守护进程状态检查 → 安全模式判断 → MQTT连接检查 → 状态报告 → 延迟
```

### 3. 错误处理流程

```
错误发生 → 错误分类 → 严重程度判断 → 执行恢复动作 → 记录日志 → 继续运行/进入安全模式/重启
```

## 内存管理策略

### 1. 内存优化技术

- **全局变量使用**: 减少实例化开销
- **智能垃圾回收**: 根据内存使用情况动态调整
- **轻量级数据结构**: 使用简单数据类型和bytearray
- **限制缓冲区大小**: 限制日志和错误历史记录
- **避免复杂对象**: 减少对象创建和销毁

### 2. 垃圾回收策略

```python
# 定期垃圾回收
if memory_usage_percent > config.DaemonConfig.GC_FORCE_THRESHOLD:
    print("[Main] 内存使用过高，执行强制垃圾回收")
    gc.collect()

# 深度垃圾回收
for _ in range(2):
    gc.collect()
    time.sleep_ms(50)
```

## 配置管理

### 1. 配置验证

系统启动时自动验证所有配置参数：
- 类型检查：确保参数类型正确
- 范围检查：验证数值在合理范围内
- 依赖检查：检查配置间的依赖关系

### 2. 配置修改

根据实际环境修改 `config.py` 中的配置：
- WiFi网络配置：修改 `WiFiConfig.NETWORKS`
- MQTT服务器配置：修改 `MQTTConfig.BROKER`
- 监控参数：调整 `DaemonConfig` 中的阈值
- LED引脚：配置 `DaemonConfig.LED_PINS`

## 部署和使用

### 1. 文件上传

使用MicroPython工具将文件上传到ESP32C3：

```bash
# 上传所有源文件
rshell cp src/boot.py /pyboard/boot.py
rshell cp src/config.py /pyboard/config.py
rshell cp src/main.py /pyboard/main.py
rshell cp src/net_mqtt.py /pyboard/net_mqtt.py
rshell cp src/net_wifi.py /pyboard/net_wifi.py
rshell cp src/sys_daemon.py /pyboard/sys_daemon.py
rshell cp src/sys_error.py /pyboard/sys_error.py
rshell cp src/lib/umqtt/simple.py /pyboard/umqtt/simple.py
```

### 2. 设备测试

设备启动后，通过串口查看输出：
- WiFi连接状态
- MQTT连接状态
- 系统监控信息
- 内存使用情况
- 错误和警告信息

### 3. MQTT主题

设备发布状态到以下MQTT主题：
- 主主题：`lzs/esp32c3`
- 日志主题：`esp32c3/logs/{level}`

## 开发指南

### 1. 添加新功能

1. **确定模块位置**: 根据功能性质选择合适的模块
2. **创建函数/类**: 在相应模块中添加新功能
3. **更新配置**: 在 `config.py` 中添加相关配置
4. **集成错误处理**: 使用 `sys_error.py` 的错误处理机制
5. **添加日志**: 使用统一的日志系统

### 2. 调试技巧

1. **启用调试模式**:
   ```python
   # 在config.py中设置
   DEBUG_MODE = True
   ```

2. **查看内存使用**:
   ```python
   free_memory = gc.mem_free()
   memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100
   ```

3. **监控系统状态**:
   ```python
   daemon_status = sys_daemon.get_daemon_status()
   health = sys_daemon.get_system_health()
   ```

## 注意事项

### 1. 内存限制

- ESP32C3总内存约264KB
- 避免创建大对象和复杂数据结构
- 定期监控内存使用情况
- 使用内存优化的数据结构（如bytearray）

### 2. 实时性要求

- 主循环延迟不宜过长（建议100-500ms）
- 避免阻塞操作
- 确保看门狗正常喂狗
- 合理设置定时器间隔

### 3. 网络稳定性

- WiFi连接可能不稳定，需要重连机制
- MQTT连接需要心跳保持
- 网络操作要有超时处理
- 考虑网络中断时的降级运行

### 4. 硬件限制

- LED引脚必须是ESP32C3有效GPIO（0-19, 21-23, 26-33）
- 温度监控：ESP32C3正常工作温度<85°C
- 看门狗超时：建议1000-32000毫秒

## 故障排除

### 1. WiFi连接问题

- 检查WiFi配置是否正确
- 确保路由器信号强度足够
- 验证密码是否正确
- 查看串口输出的错误信息

### 2. MQTT连接问题

- 检查MQTT服务器地址和端口
- 确保网络连接正常
- 验证MQTT服务器运行状态
- 检查防火墙设置

### 3. 内存问题

- 监控内存使用情况
- 检查是否有内存泄漏
- 调整垃圾回收策略
- 优化数据结构使用

### 4. 系统不稳定

- 检查看门狗配置
- 验证主循环延迟设置
- 查看错误日志
- 检查硬件连接

## 总结

本项目提供了一个完整的ESP32C3 IoT设备解决方案，具有以下特点：

- **模块化设计**: 清晰的模块划分，便于维护和扩展
- **内存优化**: 针对ESP32C3内存限制的优化策略
- **错误恢复**: 完善的错误处理和自动恢复机制
- **系统监控**: 全面的系统状态监控和健康检查
- **配置管理**: 灵活的配置系统，支持运行时验证
- **易于部署**: 简单的文件上传和配置过程

通过这些特性，项目能够在资源受限的嵌入式环境中稳定运行，为Home Assistant等智能家居系统提供可靠的设备支持。
