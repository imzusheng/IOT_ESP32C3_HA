# 安全模式LED闪烁问题分析

## 问题描述

进入安全模式后，LED不能正常闪烁，虽然LED测试模块工作正常，确认硬件和引脚没有问题。

## 根本原因分析

### 1. **双重LED控制冲突** ⚠️ **主要问题**

**位置：** `sys_daemon.py:434-436` 和 `main.py:258-260`

**问题描述：**
- 守护进程的定时器回调函数（`_monitor_callback`）每5秒执行一次
- 在安全模式下，定时器会调用 `_led_controller.update_safe_mode_led()`
- 同时，主循环的安全模式循环也在每100ms调用 `sys_daemon._led_controller.update_safe_mode_led()`
- 两个不同的调用源在同时控制同一个LED控制器，导致状态冲突

**具体代码：**
```python
# 守护进程定时器回调 (sys_daemon.py:434-436)
if _safe_mode_active:
    # 安全模式：持续更新LED闪烁状态
    _led_controller.update_safe_mode_led()
    _check_safe_mode_recovery()

# 主循环安全模式 (main.py:258-260)
if hasattr(sys_daemon, '_led_controller') and sys_daemon._led_controller:
    sys_daemon._led_controller.update_safe_mode_led()
```

### 2. **LED状态重置问题** ⚠️ **次要问题**

**位置：** `sys_daemon.py:441`

**问题描述：**
- 在守护进程的监控回调中，如果不是安全模式，会调用 `_led_controller.reset_blink_state()`
- 这个重置操作会清除 `_blink_start_time` 和 `_last_blink_state` 属性
- 如果在安全模式期间，守护进程的某个检查导致暂时退出安全模式，然后重新进入，闪烁状态会被重置

**具体代码：**
```python
# sys_daemon.py:438-441
else:
    # 正常模式：根据健康状态设置LED
    # 重置闪烁状态，确保下次进入安全模式时重新开始闪烁
    _led_controller.reset_blink_state()
```

### 3. **时序控制不精确**

**位置：** `sys_daemon.py:111-142`

**问题描述：**
- LED闪烁使用 `time.ticks_diff()` 计算时间差，依赖于 `_blink_start_time`
- 由于双重控制冲突，`_blink_start_time` 可能被意外重置或修改
- 500ms的闪烁周期与100ms的主循环调用频率不匹配

### 4. **守护进程定时器配置**

**位置：** `config.json:25` 和 `sys_daemon.py:521-527`

**问题描述：**
- 守护进程定时器间隔配置为5000ms（5秒）
- 这意味着每5秒就会有一次额外的LED状态更新干扰

## 具体执行流程

### 正常情况下的LED闪烁逻辑：
1. 调用 `update_safe_mode_led()`
2. 检查是否有 `_blink_start_time` 属性，如果没有则初始化
3. 计算从开始到当前时间的时间差
4. 基于时间差计算闪烁状态 (0或1)
5. 只有当状态改变时才更新LED

### 实际发生的问题：
1. 主循环每100ms调用一次LED更新
2. 守护进程定时器每5秒调用一次LED更新
3. 两次调用可能同时发生，导致时间计算混乱
4. 守护进程的其他检查可能导致闪烁状态被重置

## 解决方案建议

### 方案1：禁用守护进程的LED控制（推荐）
在安全模式下，只允许主循环控制LED，禁用守护进程的LED控制。

### 方案2：统一LED控制逻辑
将所有LED控制逻辑集中到一个地方，避免双重控制。

### 方案3：改进状态管理
使用更健壮的状态管理机制，避免状态冲突。

## 影响评估

**严重程度：** 高
**影响范围：** 安全模式LED指示功能
**修复优先级：** 高

## 验证方法

1. 注释掉 `sys_daemon.py:434-436` 的LED控制代码
2. 重新测试安全模式LED闪烁
3. 观察是否能正常闪烁

## 结论

问题的根本原因是**守护进程定时器和主循环同时在控制LED**，导致状态冲突。这是一个典型的并发控制问题，需要通过统一控制源来解决。