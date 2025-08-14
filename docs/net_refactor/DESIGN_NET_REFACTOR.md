# DESIGN_NET_REFACTOR

## 架构对比

### 重构前架构
```
NetworkManager (359行)
├── 状态管理 (复杂状态机)
├── WiFi管理 (重复实现)
├── MQTT管理 (重复实现)  
├── NTP管理 (重复实现)
├── 重试逻辑 (分散在各处)
├── 事件发布 (重复代码)
└── 配置管理 (硬编码)
```

### 重构后架构
```
NetworkManager (目标<150行)
├── ConnectionManager (统一连接状态)
├── RetryManager (统一重试逻辑)
├── NetworkConfig (统一配置)
├── WifiManager (简化版)
├── MqttController (简化版)
└── NtpManager (简化版)
```

## 阶段1：提取公共组件

### 1.1 ConnectionManager
**职责**：统一管理连接状态和事件发布

**功能**：
- 统一的状态管理 (WiFi/MQTT)
- 事件发布标准化
- 状态变化检测
- 连接状态聚合

**接口**：
```python
class ConnectionManager:
    def __init__(self, event_bus)
    def update_wifi_status(self, connected)
    def update_mqtt_status(self, connected) 
    def get_network_status(self)
    def is_network_available(self)
    def is_fully_connected(self)
```

### 1.2 RetryManager
**职责**：统一重试逻辑和退避策略

**功能**：
- 指数退避算法
- 重试计数管理
- 超时控制
- 重试状态跟踪

**接口**：
```python
class RetryManager:
    def __init__(self, max_retries=3, base_delay=1000)
    def should_retry(self, retry_count)
    def get_retry_delay(self, retry_count)
    def reset(self)
    def record_attempt(self)
```

### 1.3 NetworkConfig
**职责**：统一配置管理

**功能**：
- 配置验证
- 默认值处理
- 配置合并
- 类型检查

**接口**：
```python
class NetworkConfig:
    def __init__(self, config=None)
    def get_wifi_config(self)
    def get_mqtt_config(self)
    def get_ntp_config(self)
    def validate_config(self)
```

## 阶段2：简化NetworkManager

### 重构策略
1. **移除重复逻辑**：
   - 状态检查 → ConnectionManager
   - 重试逻辑 → RetryManager
   - 配置管理 → NetworkConfig

2. **简化方法**：
   - `_update_connection_status()` → 删除
   - `_handle_connection_failed()` → 简化
   - `_check_timeouts()` → 简化

3. **流程优化**：
   - 连接流程标准化
   - 错误处理统一化
   - 事件发布集中化

### 新NetworkManager结构
```python
class NetworkManager:
    def __init__(self, event_bus)
    def connect(self)  # 简化连接逻辑
    def disconnect(self)  # 简化断开逻辑
    def loop(self)  # 简化主循环
    def get_status(self)  # 委托给ConnectionManager
    def is_connected(self)  # 委托给ConnectionManager
```

## 阶段3：优化子模块

### 3.1 WifiManager优化
**移除功能**：
- 复杂的错误处理
- 冗余的状态检查

**保留功能**：
- 基本WiFi操作
- 网络扫描
- 连接/断开

### 3.2 MqttController优化  
**移除功能**：
- 重复的连接验证
- 复杂的异常处理

**保留功能**：
- 基本MQTT操作
- 消息收发
- 连接管理

### 3.3 NtpManager优化
**移除功能**：
- 冗余的配置处理
- 复杂的重试逻辑

**保留功能**：
- 基本NTP同步
- 状态检查

## 实施计划

### Phase 1.1: 创建ConnectionManager
1. 创建 `app/net/connection_manager.py`
2. 实现统一状态管理
3. 提取事件发布逻辑
4. 验证功能

### Phase 1.2: 创建RetryManager
1. 创建 `app/net/retry_manager.py`
2. 实现统一重试逻辑
3. 提取退避算法
4. 验证功能

### Phase 1.3: 创建NetworkConfig
1. 创建 `app/net/network_config.py`
2. 实现统一配置管理
3. 提取配置验证逻辑
4. 验证功能

### Phase 2: 重构NetworkManager
1. 使用新的公共组件
2. 移除重复代码
3. 简化连接流程
4. 验证功能

### Phase 3: 优化子模块
1. 简化WifiManager
2. 简化MqttController
3. 简化NtpManager
4. 最终验证

## 回退机制

### 每个阶段的回退策略
1. **代码备份**：每个阶段开始前备份当前代码
2. **功能验证**：每个阶段完成后验证功能
3. **快速回退**：使用git回退到上一个阶段

### 验证检查点
- 每次修改后运行 `python build.py --compile`
- 检查WiFi连接功能
- 检查MQTT连接功能
- 检查NTP同步功能
- 检查状态事件发布

## 成功标准

### 代码质量指标
- NetworkManager代码行数 < 150行
- 总代码量减少40-50%
- 圈复杂度降低30%
- 方法数量减少25%

### 功能验证指标
- 所有现有功能正常工作
- 接口保持兼容
- 性能无明显下降
- 内存使用优化