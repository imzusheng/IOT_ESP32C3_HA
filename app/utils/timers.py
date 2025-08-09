# app/utils/timers.py
"""
定时器工具模块 (重构版本)
提供防抖定时器、周期定时器、超时定时器等功能

为事件驱动架构提供定时器支持，包括防抖、周期执行、
超时检测和性能分析等功能。

特性:
- 防抖定时器防止重复触发
- 周期定时器支持定时任务
- 超时定时器检测操作超时
- 硬件定时器管理
- 性能分析工具
- 上下文管理器支持
"""

import time
import machine
import micropython

class DebounceTimer:
    """
    防抖定时器
    防止短时间内重复触发
    """
    def __init__(self, debounce_ms=1000):
        self.debounce_ms = debounce_ms
        self.last_trigger = 0
    
    def should_trigger(self):
        """
        检查是否应该触发
        返回True表示可以触发，False表示在防抖期内
        """
        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, self.last_trigger) >= self.debounce_ms:
            self.last_trigger = current_time
            return True
        return False
    
    def reset(self):
        """重置定时器"""
        self.last_trigger = 0
    
    def set_debounce_time(self, debounce_ms):
        """设置防抖时间"""
        self.debounce_ms = debounce_ms

class PeriodicTimer:
    """
    周期定时器
    定期执行回调函数
    """
    def __init__(self, period_ms, callback=None):
        self.period_ms = period_ms
        self.callback = callback
        self.last_run = 0
        self.enabled = True
    
    def check_and_run(self, *args, **kwargs):
        """
        检查并执行周期任务
        返回True表示执行了回调，False表示未执行
        """
        if not self.enabled or not self.callback:
            return False
        
        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, self.last_run) >= self.period_ms:
            try:
                # 使用micropython.schedule避免递归问题
                micropython.schedule(self.callback, (args, kwargs))
                self.last_run = current_time
                return True
            except Exception as e:
                print(f"[Timer] Callback execution failed: {e}")
                return False
        return False
    
    def reset(self):
        """重置定时器"""
        self.last_run = 0
    
    def set_period(self, period_ms):
        """设置周期"""
        self.period_ms = period_ms
    
    def set_callback(self, callback):
        """设置回调函数"""
        self.callback = callback
    
    def enable(self):
        """启用定时器"""
        self.enabled = True
    
    def disable(self):
        """禁用定时器"""
        self.enabled = False

class TimeoutTimer:
    """
    超时定时器
    用于检测操作是否超时
    """
    def __init__(self, timeout_ms):
        self.timeout_ms = timeout_ms
        self.start_time = None
        self.is_running = False
    
    def start(self):
        """启动定时器"""
        self.start_time = time.ticks_ms()
        self.is_running = True
    
    def stop(self):
        """停止定时器"""
        self.is_running = False
        self.start_time = None
    
    def is_timeout(self):
        """检查是否超时"""
        if not self.is_running or not self.start_time:
            return False
        
        current_time = time.ticks_ms()
        return time.ticks_diff(current_time, self.start_time) >= self.timeout_ms
    
    def elapsed_ms(self):
        """获取已运行时间"""
        if not self.is_running or not self.start_time:
            return 0
        
        current_time = time.ticks_ms()
        return time.ticks_diff(current_time, self.start_time)
    
    def remaining_ms(self):
        """获取剩余时间"""
        if not self.is_running or not self.start_time:
            return 0
        
        remaining = self.timeout_ms - self.elapsed_ms()
        return max(0, remaining)
    
    def reset(self):
        """重置定时器"""
        if self.is_running:
            self.start_time = time.ticks_ms()

class HardwareTimerManager:
    """
    硬件定时器管理器
    管理ESP32的硬件定时器资源
    """
    def __init__(self):
        self.timers = {}  # timer_id: timer_instance
        self.used_ids = set()
    
    def get_available_timer(self):
        """获取可用的定时器ID"""
        for timer_id in range(4):  # ESP32有4个硬件定时器
            if timer_id not in self.used_ids:
                return timer_id
        return None
    
    def create_timer(self, period_ms, callback, mode=machine.Timer.PERIODIC):
        """
        创建硬件定时器
        返回定时器实例，失败返回None
        """
        timer_id = self.get_available_timer()
        if timer_id is None:
            print("[Timer] No available hardware timers")
            return None
        
        try:
            timer = machine.Timer(timer_id)
            timer.init(period=period_ms, mode=mode, callback=callback)
            
            self.timers[timer_id] = timer
            self.used_ids.add(timer_id)
            
            return timer
        except Exception as e:
            print(f"[Timer] Failed to create hardware timer {timer_id}: {e}")
            return None
    
    def release_timer(self, timer):
        """释放硬件定时器"""
        if timer in self.timers.values():
            timer_id = None
            for tid, t in self.timers.items():
                if t == timer:
                    timer_id = tid
                    break
            
            if timer_id is not None:
                try:
                    timer.deinit()
                    del self.timers[timer_id]
                    self.used_ids.remove(timer_id)
                except Exception as e:
                    print(f"[Timer] Failed to release timer {timer_id}: {e}")
    
    def cleanup(self):
        """清理所有定时器"""
        for timer in self.timers.values():
            try:
                timer.deinit()
            except Exception:
                pass
        self.timers.clear()
        self.used_ids.clear()

# 全局硬件定时器管理器
_hardware_timer_manager = HardwareTimerManager()

def get_hardware_timer_manager():
    """获取硬件定时器管理器实例"""
    return _hardware_timer_manager

# 性能分析工具
class TimeProfiler:
    """
    性能分析器
    用于测量代码执行时间
    """
    def __init__(self, name="Unnamed"):
        self.name = name
        self.start_time = None
        self.measurements = []
        self.max_measurements = 100
    
    def start(self):
        """开始计时"""
        self.start_time = time.ticks_ms()
    
    def stop(self):
        """停止计时并记录结果"""
        if self.start_time is not None:
            elapsed = time.ticks_diff(time.ticks_ms(), self.start_time)
            self.measurements.append(elapsed)
            
            # 限制测量数据数量
            if len(self.measurements) > self.max_measurements:
                self.measurements.pop(0)
            
            self.start_time = None
            return elapsed
        return 0
    
    def get_average(self):
        """获取平均执行时间"""
        if not self.measurements:
            return 0
        return sum(self.measurements) / len(self.measurements)
    
    def get_max(self):
        """获取最大执行时间"""
        return max(self.measurements) if self.measurements else 0
    
    def get_min(self):
        """获取最小执行时间"""
        return min(self.measurements) if self.measurements else 0
    
    def get_stats(self):
        """获取统计信息"""
        if not self.measurements:
            return {
                'count': 0,
                'average': 0,
                'min': 0,
                'max': 0
            }
        
        return {
            'count': len(self.measurements),
            'average': self.get_average(),
            'min': self.get_min(),
            'max': self.get_max()
        }
    
    def clear(self):
        """清除测量数据"""
        self.measurements.clear()

# 上下文管理器
class TimeProfilerContext:
    """性能分析器上下文管理器"""
    def __init__(self, profiler):
        self.profiler = profiler
    
    def __enter__(self):
        self.profiler.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.profiler.stop()

def profile_time(name="Unnamed"):
    """性能分析装饰器"""
    def decorator(func):
        profiler = TimeProfiler(name)
        
        def wrapper(*args, **kwargs):
            with TimeProfilerContext(profiler):
                result = func(*args, **kwargs)
            
            # 每10次测量输出一次统计信息
            if len(profiler.measurements) % 10 == 0:
                stats = profiler.get_stats()
                print(f"[Profiler] {name}: avg={stats['average']:.1f}ms, "
                      f"min={stats['min']:.1f}ms, max={stats['max']:.1f}ms, "
                      f"count={stats['count']}")
            
            return result
        
        return wrapper
    return decorator

print("[Timers] Timer utilities module loaded")