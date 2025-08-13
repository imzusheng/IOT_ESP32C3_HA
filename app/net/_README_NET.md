# 网络模块说明文档 (_README_NET.md)

## 概述

网络模块 (`app/net/`) 提供了统一的网络连接管理功能，包括WiFi连接、NTP时间同步和MQTT通信。模块采用简化的架构设计，提供可靠的连接管理和错误恢复机制。

## 模块结构

```
app/net/
├── __init__.py          # 模块初始化和导出
├── index.py             # 网络统一控制器
├── fsm.py               # 网络状态机
├── wifi.py              # WiFi管理器
├── ntp.py               # NTP时间同步管理器
└── mqtt.py              # MQTT控制器
```

## 核心特性

### 1. 统一连接流程
- **连接顺序**: WiFi → NTP → MQTT
- **依赖关系**: MQTT依赖于WiFi，NTP依赖于WiFi
- **优雅降级**: NTP失败不影响MQTT连接

### 2. 指数退避重连机制
- **退避算法**: `delay = base * (multiplier ^ (failures - 1))`
- **最大延迟**: 可配置的最大退避时间
- **重试限制**: 可配置的最大重试次数

### 3. 事件驱动架构
- **状态变化**: 通过EventBus发布连接状态变化
- **错误处理**: 统一的错误事件发布
- **系统响应**: 响应系统状态变化事件

## 组件说明

### NetworkManager (网络统一控制器)

**功能**: 管理所有网络连接的统一控制器

**主要方法**:
- `start_connection_flow()`: 启动连接流程
- `check_connections()`: 检查并维护连接状态
- `disconnect_all()`: 断开所有连接
- `loop()`: 主循环处理
- `get_status()`: 获取连接状态
- `reset_failures()`: 重置失败计数器

**配置示例**:
```python
network_config = {
    'network': {                 # 状态机配置
        'backoff_delay': 2,      # 首次重连延迟(秒)
        'max_retries': 5,        # 最大重试次数
        'connection_timeout': 120  # 单次连接超时(秒)
    },
    'wifi': {
        'networks': [
            {'ssid': 'network1', 'password': 'password1'},
            {'ssid': 'network2', 'password': 'password2'}
        ]
    },
    'ntp': {
        'ntp_server': 'ntp1.aliyun.com',
        'ntp_max_attempts': 3,
        'ntp_retry_interval': 2
    },
    'mqtt': {
        'broker': 'broker.hivemq.com',
        'port': 1883,
        'keepalive': 60,
        'user': 'username',
        'password': 'password',
        'subscribe_topics': ['device/+/command']
    }
}
```

### WifiManager (WiFi管理器)

**功能**: 管理WiFi网络连接

**主要方法**:
- `scan_networks()`: 扫描可用网络
- `connect(ssid, password)`: 连接指定网络
- `disconnect()`: 断开连接
- `get_is_connected()`: 检查连接状态

**特性**:
- 按信号强度排序网络
- 支持多网络配置
- 自动网络选择

### NtpManager (NTP时间同步管理器)

**功能**: 管理NTP时间同步

**主要方法**:
- `sync_time()`: 执行时间同步
- `is_synced()`: 检查同步状态

**特性**:
- 支持自定义NTP服务器
- 重试机制
- 错误处理

### MqttController (MQTT控制器)

**功能**: 管理MQTT通信

**主要方法**:
- `connect()`: 连接MQTT服务器
- `disconnect()`: 断开连接
- `publish(topic, msg)`: 发布消息
- `subscribe(topic)`: 订阅主题
- `loop()`: 主循环处理

**特性**:
- 心跳保持
- 消息回调
- 自动重连

## 使用示例

### 基本使用

```python
from app.net import NetworkManager
from lib.lock.event_bus import EventBus

# 创建事件总线
event_bus = EventBus()

# 创建网络管理器
network_config = {
    'backoff_base': 2,
    'backoff_multiplier': 2,
    'max_backoff_time': 300,
    'max_retries': 5,
    'wifi': {
        'networks': [
            {'ssid': 'my_wifi', 'password': 'my_password'}
        ]
    },
    'mqtt': {
        'broker': 'broker.hivemq.com',
        'port': 1883,
        'subscribe_topics': ['device/+/command']
    }
}

network_manager = NetworkManager(event_bus, network_config)

# 启动连接流程
network_manager.connect()
# 可以根据需要检查 status


# 主循环中调用
while True:
    network_manager.loop()
    # 其他处理...
```

### 状态监控

```python
# 获取网络状态
status = network_manager.get_status()
print(f"WiFi连接: {status['wifi_connected']}")
print(f"MQTT连接: {status['mqtt_connected']}")
print(f"NTP同步: {status['ntp_synced']}")

# 检查连接状态
if network_manager.check_connections():
    print("所有连接正常")
else:
    print("存在连接问题")
```

### 消息发布

```python
# 发布MQTT消息
if network_manager.mqtt_connected:
    network_manager.mqtt.publish(
        topic="device/status",
        msg='{"temperature": 25.5, "humidity": 60}'
    )
```

## 事件处理

网络模块发布以下事件：

### WiFi事件
- `EVENTS.WIFI_STATE_CHANGE`: WiFi状态变化
  - `state="connecting"`: 正在连接
  - `state="connected"`: 连接成功
  - `state="disconnected"`: 连接断开

### NTP事件
- `EVENTS.NTP_STATE_CHANGE`: NTP状态变化
  - `state="started"`: 开始同步
  - `state="success"`: 同步成功
  - `state="failed"`: 同步失败

### MQTT事件
- `EVENTS.MQTT_STATE_CHANGE`: MQTT状态变化
  - `state="connected"`: 连接成功
  - `state="disconnected"`: 连接断开
- `EVENTS.MQTT_MESSAGE`: 收到MQTT消息

## 错误处理

### 重连策略
1. **指数退避**: 失败次数越多，重连间隔越长
2. **最大重试**: 超过最大重试次数停止尝试
3. **状态重置**: 可手动重置失败计数器

### 错误恢复
- **WiFi重连**: 自动扫描并连接可用网络
- **MQTT重连**: WiFi恢复后自动重连
- **NTP重试**: 网络恢复后自动重试

## 注意事项

1. **内存使用**: ESP32-C3内存有限，注意控制连接数
2. **网络稳定性**: 在网络不稳定环境下，调整退避参数
3. **事件风暴**: 避免频繁发布相同事件
4. **超时设置**: 根据网络环境调整连接超时时间

## 配置建议

### 稳定网络环境
```python
{
    'backoff_base': 2,
    'backoff_multiplier': 2,
    'max_backoff_time': 60,
    'max_retries': 3
}
```

### 不稳定网络环境
```python
{
    'backoff_base': 5,
    'backoff_multiplier': 1.5,
    'max_backoff_time': 300,
    'max_retries': 10
}
```

## 调试信息

网络模块提供详细的日志信息：
- 连接过程日志
- 错误信息日志
- 状态变化日志
- 性能统计日志

可通过配置日志级别来控制日志输出量。