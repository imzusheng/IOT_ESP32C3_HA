# 事件系统分析报告

## 问题概述
项目经历了事件总线重构，但整个项目仍在使用旧的事件常量系统，导致系统不一致。

## 事件系统现状

### 1. 旧的事件系统 (app/event_const.py)
- 使用 `EVENT` 类
- 包含 18 个具体事件常量
- 被以下模块使用：
  - fsm.py (状态机)
  - hw/sensor.py (传感器)
  - lib/logger.py (日志)
  - net/wifi.py (WiFi)
  - main.py (主程序)
  - net/mqtt.py (MQTT)

### 2. 新的事件系统 (app/lib/event_bus/events_const.py)
- 使用 `EVENTS` 类
- 简化为 7 个通用事件
- 被事件总线核心使用：
  - core.py (事件总线核心)

## 事件映射关系

### 新事件系统架构：
1. **WIFI_STATE_CHANGE** - 统一的WiFi状态变化
   - 替代: WIFI_CONNECTING, WIFI_CONNECTED, WIFI_DISCONNECTED, WIFI_SCAN_DONE
   - 参数: state='connecting'/'connected'/'disconnected'/'scan_done'

2. **MQTT_STATE_CHANGE** - 统一的MQTT状态变化
   - 替代: MQTT_CONNECTED, MQTT_DISCONNECTED
   - 参数: state='connected'/'disconnected'

3. **SYSTEM_STATE_CHANGE** - 统一的系统状态变化
   - 替代: SYSTEM_BOOT, SYSTEM_INIT, SYSTEM_HEARTBEAT, SYSTEM_WARNING, SYSTEM_SHUTDOWN
   - 参数: state='boot'/'init'/'running'/'warning'/'error'/'critical'/'shutdown'

4. **SYSTEM_ERROR** - 统一的系统错误
   - 替代: SYSTEM_ERROR, RECOVERY_SUCCESS, RECOVERY_FAILED, MEMORY_CRITICAL
   - 参数: error_type='system_error'/'memory_critical'/'hardware_error'等

5. **NTP_STATE_CHANGE** - 统一的NTP状态变化
   - 替代: NTP_SYNC_STARTED, NTP_SYNC_SUCCESS, NTP_SYNC_FAILED
   - 参数: state='started'/'success'/'failed'

6. **MQTT_MESSAGE** - 保持不变
7. **SENSOR_DATA** - 保持不变

## 需要同步修改的文件

### 高优先级：
1. **app/main.py** - 主控制器
2. **app/fsm.py** - 状态机
3. **app/net/wifi.py** - WiFi管理器
4. **app/net/mqtt.py** - MQTT控制器

### 中优先级：
5. **app/hw/sensor.py** - 传感器管理器
6. **app/lib/logger.py** - 日志系统

### 修改策略：
- 保持事件数量不变 (18个)
- 将新事件系统的简化架构映射到旧的具体事件
- 确保向后兼容性

## 建议的解决方案

### 方案1：统一使用旧事件系统
- 修改事件总线核心，使其支持旧的事件常量
- 保持现有代码不变

### 方案2：统一使用新事件系统
- 修改所有使用旧事件系统的模块
- 采用新的简化事件架构

### 方案3：混合方案 (推荐)
- 保持 app/event_const.py 不变
- 在事件总线核心中建立新旧事件映射
- 逐步迁移到新事件系统