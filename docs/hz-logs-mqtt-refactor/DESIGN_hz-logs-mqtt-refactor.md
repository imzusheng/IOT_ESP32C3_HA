# 重构设计方案：Hz性能移除 & 日志优化 & MQTT重连增强

## 修复方案总览

### 目标
1. 完全移除Hz性能显示逻辑
2. 优化INFO日志密度，将非关键操作降级为DEBUG
3. 增强MQTT重连机制的健壮性

## 详细设计方案

### 1. Hz性能显示移除

#### 问题分析
```python
# 当前需要移除的代码 (main.py:165-172)
if self.last_stats_time == 0:
    self.last_stats_time = current_time
    loops = self.loop_count
    freq_hz = (loops / 30.0) if loops else 0.0
else:
    time_window_ms = time.ticks_diff(current_time, self.last_stats_time)
    time_window_s = time_window_ms / 1000.0 if time_window_ms > 0 else 1.0
    loops = self.loop_count
    freq_hz = loops / time_window_s if time_window_s > 0 else 0.0

# 当前日志输出 (main.py:183-184)
info("系统状态 - 状态:{}, 内存:{}KB({:.0f}%), 性能:{:.1f}Hz, WiFi:{}, MQTT:{}", 
     state, free_kb, percent_used, freq_hz, net_status['wifi'], net_status['mqtt'])
```

#### 解决方案
```python
# 移除后的简化逻辑
def _periodic_maintenance(self, current_time):
    """定期维护任务"""
    # 每30秒执行一次
    if time.ticks_diff(current_time, self.last_stats_time) >= 30000:
        self.last_stats_time = current_time
        
        # 垃圾回收
        gc.collect()
        
        # 输出系统状态（移除性能显示）
        from utils.helpers import check_memory
        mem = check_memory()
        free_kb = mem.get("free_kb", gc.mem_free() // 1024)
        percent_used = mem.get("percent", 0)
        state = self.state_machine.get_current_state()
        net_status = self.network_manager.get_status()
        
        info("系统状态 - 状态:{}, 内存:{}KB({:.0f}%), WiFi:{}, MQTT:{}", 
             state, free_kb, percent_used, net_status['wifi'], net_status['mqtt'], 
             module="MAIN")
```

**需要移除的属性和变量**:
- `self.loop_count` (类属性)
- `freq_hz` (局部变量)
- 循环计数相关逻辑

### 2. 日志级别优化策略

#### 分类标准
**保留为INFO级别的日志**:
- 系统启动/关闭关键节点
- 网络连接状态变更（连接成功/失败/断开）
- 状态机重要状态转换（INIT→NETWORKING→RUNNING→ERROR）
- 严重错误和异常情况

**降级为DEBUG级别的日志**:
- LED操作确认
- 事件总线消息处理详情
- 网络连接过程中的中间步骤
- 状态机内部处理逻辑
- 定期检查和维护操作

#### 具体调整方案

**app/main.py调整**:
```python
# 保留INFO
info("=== ESP32C3系统启动 ===", module="MAIN")
info("=== 系统初始化完成 ===", module="MAIN")

# 改为DEBUG
debug("LED初始化完成", module="MAIN")
debug("事件总线初始化完成", module="MAIN")
debug("网络管理器初始化完成", module="MAIN")
```

**app/fsm/core.py调整**:
```python
# 保留INFO - 重要状态转换
info("进入{}状态", state_name, module="FSM")

# 改为DEBUG - 内部处理
debug("状态机更新", module="FSM")
debug("处理WiFi事件", module="FSM")
```

**app/net/network_manager.py调整**:
```python
# 保留INFO - 连接结果
info("网络连接流程启动成功", module="NET")
info("WiFi连接成功", module="NET")
info("MQTT连接成功", module="NET")

# 改为DEBUG - 过程步骤
debug("开始网络连接流程", module="NET")
debug("正在连接WiFi...", module="NET")
debug("正在连接MQTT...", module="NET")
```

### 3. MQTT重连机制增强

#### 现状分析
当前重连机制：
1. `_check_mqtt_status()` 检测连接丢失
2. 发布 `MQTT_STATE_CHANGE` 事件
3. FSM响应事件并重新进入NETWORKING状态
4. 通过NetworkManager重新连接

#### 问题识别
- 没有重连延迟，可能导致频繁重试
- 缺乏重连次数限制
- 重连失败后没有退避策略

#### 增强方案

**添加重连控制逻辑**:
```python
class NetworkManager:
    def __init__(self, config, event_bus):
        # ... 现有代码 ...
        
        # MQTT重连控制
        self.mqtt_retry_count = 0
        self.mqtt_max_retries = 5
        self.mqtt_retry_delay = 5000  # 5秒基础延迟
        self.mqtt_last_retry_time = 0
        
    def _connect_mqtt(self):
        """连接MQTT（增强版）"""
        current_time = time.ticks_ms()
        
        # 检查重连间隔
        if self.mqtt_last_retry_time > 0:
            elapsed = time.ticks_diff(current_time, self.mqtt_last_retry_time)
            min_delay = self.mqtt_retry_delay * (2 ** min(self.mqtt_retry_count, 3))  # 指数退避
            if elapsed < min_delay:
                debug("MQTT重连延迟中，还需等待{}ms", min_delay - elapsed, module="NET")
                return False
        
        # 检查重试次数限制
        if self.mqtt_retry_count >= self.mqtt_max_retries:
            warning("MQTT重连次数超限({}次)，暂停重连", self.mqtt_max_retries, module="NET")
            return False
        
        try:
            if self.mqtt_connected and self.mqtt_controller and self.mqtt_controller.is_connected():
                # 连接成功，重置重试计数
                self.mqtt_retry_count = 0
                self.mqtt_last_retry_time = 0
                return True
                
            info("正在连接MQTT... (尝试{}/{})", self.mqtt_retry_count + 1, self.mqtt_max_retries, module="NET")
            success = self.mqtt_controller.connect()
            
            if success:
                self.mqtt_connected = True
                self.mqtt_retry_count = 0
                self.mqtt_last_retry_time = 0
                info("MQTT连接成功", module="NET")
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                return True
            else:
                self.mqtt_retry_count += 1
                self.mqtt_last_retry_time = current_time
                warning("MQTT连接失败 (尝试{}/{})", self.mqtt_retry_count, self.mqtt_max_retries, module="NET")
                return False
                
        except Exception as e:
            self.mqtt_retry_count += 1
            self.mqtt_last_retry_time = current_time
            error("MQTT连接异常 (尝试{}/{}): {}", self.mqtt_retry_count, self.mqtt_max_retries, e, module="NET")
            return False
```

**添加重连重置机制**:
```python
def reset_mqtt_retry_state(self):
    """重置MQTT重连状态（用于外部触发完全重置）"""
    self.mqtt_retry_count = 0
    self.mqtt_last_retry_time = 0
    info("MQTT重连状态已重置", module="NET")
```

## 实施计划

### 阶段1: Hz性能显示移除（关键）
1. 移除 `_periodic_maintenance` 中的频率计算逻辑
2. 简化系统状态日志输出格式
3. 移除不必要的循环计数累加

### 阶段2: 日志级别优化（重要）
1. 调整main.py中的初始化日志级别
2. 优化FSM状态转换日志
3. 简化网络管理器操作日志
4. 调整LED和其他组件的详细日志

### 阶段3: MQTT重连增强（优化）
1. 在NetworkManager中添加重连控制属性
2. 实现指数退避重连逻辑
3. 添加重连次数限制和状态重置机制

## 代码变更摘要

### 主要修改文件
- `app/main.py` (~10行修改)
- `app/fsm/core.py` (~5行修改)
- `app/net/network_manager.py` (~25行新增/修改)
- `app/net/mqtt.py` (~3行修改)

### 预期效果
1. **性能显示**: 完全移除Hz显示，日志更简洁
2. **日志密度**: INFO日志减少约60%，关键信息更突出
3. **MQTT重连**: 更稳定的重连机制，避免频繁重试

## 风险评估

### 低风险变更
- Hz性能移除：纯统计逻辑，无功能影响
- 日志级别调整：不改变程序行为

### 中等风险
- MQTT重连逻辑：需要仔细测试重连场景

### 兼容性
- 完全向后兼容，无API变更
- 现有功能不受影响