# 重构设计方案：性能显示修复与LED初始化优化

## 修复方案总览

### 目标
1. 修复性能显示0.0Hz错误
2. 优化LED初始化顺序和状态指示
3. 确保主循环中LED正确更新

## 详细设计方案

### 1. 性能计算逻辑修复

#### 问题分析
```python
# 当前问题代码 (main.py:168-170)
loops = self.loop_count
freq_hz = (loops / 30.0) if loops else 0.0
```

**根因**: 首次统计时，循环计数可能为0，导致频率显示0.0Hz

#### 解决方案
```python
# 修复后的逻辑
if self.last_stats_time == 0:
    # 首次统计，使用当前时间作为基准
    self.last_stats_time = current_time
    freq_hz = 0.0  # 首次显示为0是正常的
else:
    # 计算实际时间窗口
    time_window_ms = time.ticks_diff(current_time, self.last_stats_time)
    time_window_s = time_window_ms / 1000.0
    freq_hz = (self.loop_count / time_window_s) if time_window_s > 0 else 0.0
```

**关键改进**:
- 正确处理首次统计的边界情况
- 使用实际时间窗口而非固定30秒
- 避免除零错误

### 2. LED初始化顺序调整

#### 当前顺序（有问题）
```
1. 配置加载
2. 日志系统
3. 事件总线
4. 网络管理器  ← 可能失败，延迟用户反馈
5. 状态机
6. LED初始化    ← 太晚了
```

#### 优化后顺序
```
1. 配置加载
2. 日志系统  
3. LED初始化    ← 提前到第3位
4. LED启动慢速闪烁 ← 立即提供运行状态指示
5. 事件总线
6. 网络管理器
7. 状态机
```

**优势**:
- 用户能立即看到系统启动反馈
- LED故障能早期发现
- 不依赖网络状态即可提供状态指示

### 3. LED状态指示优化

#### 添加慢速闪烁模式调用
```python
def _init_led(self):
    """初始化LED并启动运行状态指示"""
    try:
        from hw.led import init_led, play
        init_led()
        play('blink')  # 立即启动慢速闪烁表示运行中
        info("LED初始化完成，已启动运行状态指示", module="MAIN")
    except Exception as e:
        error("LED初始化失败: {}", e, module="MAIN")
```

### 4. 主循环LED更新确保

#### 检查当前主循环是否调用LED更新
```python
# 在 _main_loop 中添加LED更新调用
def _main_loop(self):
    # ... 现有逻辑 ...
    
    # 5. 更新LED显示
    self._update_led()
    
    # 6. 定期垃圾回收和统计
    # ... 现有逻辑 ...

def _update_led(self):
    """更新LED显示"""
    try:
        from hw.led import process_led_updates
        process_led_updates()
    except Exception as e:
        # 静默失败，避免影响主循环
        pass
```

## 实施计划

### 阶段1: 性能计算修复（关键）
1. 修复 `_periodic_maintenance` 中的频率计算逻辑
2. 正确处理首次统计的边界情况
3. 使用实际时间窗口进行计算

### 阶段2: LED初始化顺序调整（重要）
1. 将 `_init_led()` 调用移动到 `initialize()` 方法的第3位
2. 在LED初始化后立即调用 `play('blink')`
3. 更新相关日志输出

### 阶段3: LED更新确保（优化）
1. 在主循环中添加LED更新调用
2. 确保LED更新不会影响主循环稳定性

## 代码变更摘要

### 主要修改文件
- `app/main.py` (约15行修改+新增)

### 具体变更点
1. `initialize()` 方法：调整LED初始化位置
2. `_init_led()` 方法：添加慢速闪烁启动
3. `_periodic_maintenance()` 方法：修复频率计算逻辑
4. `_main_loop()` 方法：添加LED更新调用

### 预期效果
1. 性能显示：从 `0.0Hz` → 显示真实频率值（如 `10.0Hz`）
2. LED反馈：系统启动后立即可见闪烁状态
3. 用户体验：更快的视觉反馈，更准确的性能监控

## 风险评估

### 低风险变更
- 性能计算逻辑：纯数学计算，无副作用
- LED初始化顺序：LED模块独立性强

### 零风险
- 添加LED更新调用：静默失败机制，不影响主循环

### 兼容性
- 完全向后兼容，无API变更
- 现有功能不受影响