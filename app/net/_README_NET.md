# 网络模块说明文档 (_README_NET.md)

## 概述

网络模块 (`app/net/`) 提供了统一的网络连接管理功能, 包括WiFi连接、NTP时间同步和MQTT通信。模块采用简化的架构设计, 提供可靠的连接管理和错误恢复机制。

## 模块结构

```
app/net/
├── __init__.py          # 模块初始化和导出
├── index.py             # 网络统一控制器(含状态机功能)
├── wifi.py              # WiFi管理器
├── ntp.py               # NTP时间同步管理器
└── mqtt.py              # MQTT控制器
```

## 核心特性

### 1. 统一连接流程
- **连接顺序**: WiFi → NTP → MQTT
- **依赖关系**: MQTT依赖于WiFi, NTP依赖于WiFi
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

### NetworkManager (网络统一控制器) - index.py

**功能**: 管理所有网络连接的统一控制器, 包含完整的状态机功能, 是外部主要交互点。

**初始化**:
```python
from app.net import NetworkManager
network_manager = NetworkManager(event_bus, config)
```
- `event_bus`: 事件总线实例 (lib.lock.event_bus.EventBus)
- `config`: 配置字典 (详见配置示例)

**暴露方法**:
- `connect()`: 启动网络连接流程
  - 无参数
  - 返回: 无

- `disconnect()`: 断开所有网络连接
  - 无参数
  - 返回: 无

- `loop()`: 主循环处理 (需在主循环中定期调用)
  - 无参数
  - 返回: 无

- `get_status()`: 获取当前网络状态
  - 无参数
  - 返回: dict - {'wifi': bool, 'mqtt': bool, 'ntp': bool}

- `publish_mqtt_message(topic, message, retain=False, qos=0)`: 发送MQTT消息
  - `topic`: str - 主题
  - `message`: str - 消息内容
  - `retain`: bool - 是否保留 (默认False)
  - `qos`: int - 服务质量 (默认0)
  - 返回: bool - 发送成功

- `subscribe_mqtt_topic(topic, qos=0)`: 订阅MQTT主题
  - `topic`: str - 主题
  - `qos`: int - 服务质量 (默认0)
  - 返回: bool - 订阅成功

- `get_mqtt_status()`: 获取MQTT连接状态
  - 无参数
  - 返回: bool - 是否连接

**配置示例**:
```python
config = {
    'network': {
        'backoff_delay': 2,
        'max_retries': 5,
        'connection_timeout': 120
    },
    'wifi': {
        'networks': [{'ssid': 'net1', 'password': 'pass1'}]
    },
    'ntp': {
        'ntp_server': 'ntp.aliyun.com',
        'ntp_max_attempts': 3,
        'ntp_retry_interval': 2
    },
    'mqtt': {
        'broker': 'broker.hivemq.com',
        'port': 1883,
        'keepalive': 60,
        'user': 'user',
        'password': 'pass',
        'subscribe_topics': ['topic1']
    }
}
```

### WifiManager (WiFi管理器) - wifi.py

**注意**: 通常不直接使用, 通过NetworkManager间接操作。

**主要方法** (如果需要直接使用):
- `connect(ssid, password)`: 连接WiFi
- `disconnect()`: 断开
- `is_connected()`: 检查状态

### NtpManager (NTP时间同步管理器) - ntp.py

**注意**: 通常不直接使用, 通过NetworkManager间接操作。

**主要方法** (如果需要直接使用):
- `sync_time()`: 同步时间
- `is_synced()`: 检查同步状态

### MqttController (MQTT控制器) - mqtt.py

**注意**: 通常不直接使用, 通过NetworkManager间接操作。

**主要方法** (如果需要直接使用):
- `connect()`: 连接MQTT
- `disconnect()`: 断开
- `publish(topic, msg, retain=False, qos=0)`: 发布
- `subscribe(topic, qos=0)`: 订阅
- `loop()`: 处理循环
- `is_connected()`: 检查状态

## 使用示例

### 基本初始化和连接
```python
from lib.lock.event_bus import EventBus
from app.net import NetworkManager

event_bus = EventBus()
network_manager = NetworkManager(event_bus, config)
network_manager.connect()

while True:
    network_manager.loop()
    time.sleep(0.1)
```

### 发送和接收MQTT消息
```python
# 发送
network_manager.publish_mqtt_message('topic', 'message')

# 接收 (通过事件)
def handle_mqtt(data):
    print(data['topic'], data['message'])

event_bus.subscribe(EVENTS.MQTT_MESSAGE, handle_mqtt)
```

### 状态监控
```python
status = network_manager.get_status()
print(status)
```

## 事件管理

所有事件通过 NetworkManager 统一发布：
- EVENTS.WIFI_STATE_CHANGE
- EVENTS.NTP_STATE_CHANGE
- EVENTS.MQTT_STATE_CHANGE
- EVENTS.MQTT_MESSAGE

**订阅示例**:
```python
event_bus.subscribe(EVENTS.MQTT_STATE_CHANGE, handler)
```

## 注意事项

- 事件发布集中在 NetworkManager 中
- 外部交互主要通过 index.py 的 NetworkManager
- 配置参数需完整提供
- 在主循环中定期调用 loop()

## 调试

- 使用 logger 查看 'NET' 模块日志
- 监控事件总线输出