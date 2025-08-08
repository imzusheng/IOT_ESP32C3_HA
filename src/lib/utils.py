# -*- coding: utf-8 -*-
"""
ESP32-C3 通用工具函数库

为ESP32C3设备提供常用的工具函数，包括：
- 内存检查和管理
- 字符串格式化
- 时间处理
- 其他通用功能

这些函数被设计为可重用的、高效的，并且适合在资源受限的
MicroPython环境中使用。
"""

import gc
import time

# =============================================================================
# 内存管理工具函数
# =============================================================================

def check_memory():
    """
    检查内存使用情况
    
    返回包含内存使用信息的字典，包括：
    - free: 空闲内存字节数
    - used: 已使用内存字节数
    - total: 总内存字节数
    - percent: 内存使用百分比
    
    如果无法获取内存信息，则返回None
    """
    try:
        total_memory = gc.mem_alloc() + gc.mem_free()
        if total_memory == 0:
            return None
        
        used_percent = (gc.mem_alloc() / total_memory) * 100
        return {
            'free': gc.mem_free(),
            'used': gc.mem_alloc(),
            'total': total_memory,
            'percent': used_percent
        }
    except Exception as e:
        # 在工具函数中避免使用print，以减少生产环境中的输出
        return None

def format_memory_info(memory_info):
    """
    格式化内存信息为可读字符串
    
    参数:
        memory_info: 由check_memory()返回的内存信息字典
        
    返回:
        格式化后的内存信息字符串
    """
    if not memory_info:
        return "内存信息不可用"
    
    return f"内存: {memory_info['free']}B可用, {memory_info['percent']:.1f}%已使用"

# =============================================================================
# 字符串格式化工具函数
# =============================================================================

def format_string(template, *args):
    """
    安全的字符串格式化函数
    
    参数:
        template: 格式化模板字符串
        *args: 格式化参数
        
    返回:
        格式化后的字符串，如果格式化失败则返回原始模板
    """
    try:
        if args:
            return template.format(*args)
        return template
    except Exception:
        return template

# =============================================================================
# 时间处理工具函数
# =============================================================================

def get_timestamp():
    """
    获取当前时间戳（毫秒）
    
    返回:
        当前时间的毫秒时间戳
    """
    return time.ticks_ms()

def get_formatted_time():
    """
    获取格式化的当前时间字符串（完整格式，不包含中文）
    
    返回:
        格式化后的时间字符串，格式为 "YYYY-MM-DD HH:MM:SS"
        如果无法获取时间，则返回 "1970-01-01 00:00:00"
    """
    try:
        # 获取当前时间
        current_time = time.localtime()
        
        # 格式化为完整时间字符串
        formatted_time = f"{current_time[0]:04d}-{current_time[1]:02d}-{current_time[2]:02d} {current_time[3]:02d}:{current_time[4]:02d}:{current_time[5]:02d}"
        
        return formatted_time
    except Exception:
        # 如果获取时间失败，返回默认时间
        return "1970-01-01 00:00:00"

def get_elapsed_time(start_time):
    """
    计算从开始时间到当前时间的经过时间（毫秒）
    
    参数:
        start_time: 开始时间的时间戳
        
    返回:
        经过的时间（毫秒）
    """
    return time.ticks_diff(time.ticks_ms(), start_time)

def format_elapsed_time(milliseconds):
    """
    格式化经过时间为可读字符串
    
    参数:
        milliseconds: 毫秒数
        
    返回:
        格式化后的时间字符串（例如："1m 30s"）
    """
    try:
        seconds = milliseconds // 1000
        minutes = seconds // 60
        hours = minutes // 60
        
        if hours > 0:
            remaining_minutes = minutes % 60
            return f"{hours}h {remaining_minutes}m"
        elif minutes > 0:
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        else:
            return f"{seconds}s"
    except Exception:
        return f"{milliseconds}ms"

# =============================================================================
# 系统工具函数
# =============================================================================

def is_memory_critical(threshold=90):
    """
    检查内存是否处于临界状态
    
    参数:
        threshold: 内存使用百分比阈值，默认为90%
        
    返回:
        如果内存使用超过阈值则返回True，否则返回False
    """
    memory_info = check_memory()
    if not memory_info:
        return False
    
    return memory_info['percent'] > threshold

def is_memory_warning(threshold=None):
    """
    检查内存是否处于警告状态
    
    参数:
        threshold: 内存使用百分比阈值，从config.py中的daemon.memory_threshold获取
        
    返回:
        如果内存使用超过阈值则返回True，否则返回False
        
    注意:
        如果threshold为None，则使用配置文件中的默认阈值
    """
    memory_info = check_memory()
    if not memory_info:
        return False
    
    return memory_info['percent'] > threshold

def safe_garbage_collect():
    """
    安全的垃圾回收
    
    执行垃圾回收并捕获可能的异常，避免因垃圾回收
    导致的系统崩溃。
    """
    try:
        gc.collect()
    except Exception:
        pass

# =============================================================================
# 系统监控工具函数
# =============================================================================

def check_system_health():
    """
    检查系统健康状态
    
    返回包含系统健康信息的字典，包括：
    - overall: 整体健康状态
    - temperature: 温度状态
    - memory: 内存状态
    - errors: 错误状态
    - details: 详细信息
    
    如果无法获取系统信息，则返回None
    """
    try:
        import gc
        
        # 获取内存信息
        memory_info = check_memory()
        
        # 检查内存状态
        memory_status = True
        memory_details = ""
        if memory_info:
            if memory_info['percent'] > 85:
                memory_status = False
                memory_details = f'内存使用过高: {memory_info["percent"]:.1f}%'
        
        # 检查错误状态（简化版本）
        error_status = True
        error_details = ""
        
        # 整体健康状态
        overall_status = memory_status and error_status
        
        return {
            'overall': overall_status,
            'memory': memory_status,
            'errors': error_status,
            'details': {
                'memory': memory_details,
                'errors': error_details
            }
        }
    except Exception:
        return None

def deep_memory_cleanup():
    """
    执行深度内存清理
    
    执行多次垃圾回收和内存优化操作，
    适用于内存紧张或系统进入安全模式时。
    """
    try:
        import gc
        
        # 执行多次垃圾回收
        for _ in range(3):
            gc.collect()
            time.sleep_ms(100)
        
        # 尝试清理对象池（如果存在）
        try:
            import mem_optimizer
            mem_optimizer.clear_all_pools()
        except ImportError:
            pass
        
        return True
    except Exception:
        return False

def check_watchdog_status(last_feed_time, timeout_ms=120000):
    """
    检查看门狗状态
    
    参数:
        last_feed_time: 上次喂狗时间的时间戳
        timeout_ms: 超时时间（毫秒），从config.py中的daemon.wdt_timeout获取
        
    返回:
        如果看门狗状态正常则返回True，否则返回False
    """
    try:
        if last_feed_time == 0:
            return True
        
        elapsed = time.ticks_diff(time.ticks_ms(), last_feed_time)
        return elapsed <= timeout_ms
    except Exception:
        return False

# =============================================================================
# 状态管理工具函数
# =============================================================================

def calculate_state_duration(start_time):
    """
    计算状态持续时间（毫秒）
    
    参数:
        start_time: 状态开始时间的时间戳
        
    返回:
        状态持续时间（毫秒）
    """
    try:
        return time.ticks_diff(time.ticks_ms(), start_time)
    except Exception:
        return 0

def format_state_info(current_state, previous_state, duration_ms):
    """
    格式化状态信息为可读字典
    
    参数:
        current_state: 当前状态
        previous_state: 上一个状态
        duration_ms: 状态持续时间（毫秒）
        
    返回:
        格式化后的状态信息字典
    """
    return {
        'current_state': current_state,
        'previous_state': previous_state,
        'duration_seconds': duration_ms // 1000,
        'duration_ms': duration_ms
    }

# =============================================================================
# 错误处理工具函数
# =============================================================================

def safe_execute(func, *args, **kwargs):
    """
    安全执行函数，捕获并处理异常
    
    参数:
        func: 要执行的函数
        *args: 函数参数
        **kwargs: 函数关键字参数
        
    返回:
        元组 (success, result)
        success: 执行是否成功
        result: 执行结果或错误信息
    """
    try:
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        return False, str(e)

def retry_operation(func, max_retries=3, delay_ms=1000, *args, **kwargs):
    """
    重试执行操作
    
    参数:
        func: 要执行的函数
        max_retries: 最大重试次数
        delay_ms: 重试间隔（毫秒）
        *args: 函数参数
        **kwargs: 函数关键字参数
        
    返回:
        元组 (success, result)
        success: 执行是否成功
        result: 执行结果或错误信息
    """
    last_error = ""
    
    for attempt in range(max_retries):
        success, result = safe_execute(func, *args, **kwargs)
        if success:
            return True, result
        
        last_error = result
        if attempt < max_retries - 1:
            time.sleep_ms(delay_ms)
    
    return False, last_error

# =============================================================================
# 系统信息工具函数
# =============================================================================

def get_temperature():
    """
    获取MCU内部温度
    
    返回:
        MCU内部温度（摄氏度），如果无法获取则返回None
    """
    try:
        import esp32
        return esp32.mcu_temperature()
    except Exception:
        return None

def get_memory_usage():
    """
    获取内存使用情况 - 优化内存使用
    
    返回:
        包含内存使用信息的字典，包括：
        - percent: 内存使用百分比
        - free: 空闲内存字节数
        如果无法获取内存信息，则返回None
    """
    try:
        # 减少垃圾回收频率，每20次监控才执行
        # if _monitor_count % 20 == 0:
        #     gc.collect()
        
        alloc = gc.mem_alloc()
        free = gc.mem_free()
        total = alloc + free
        percent = (alloc / total) * 100 if total > 0 else 0
        
        # 返回更简洁的数据结构
        return {
            'percent': percent,
            'free': free
        }
    except Exception:
        return None

# =============================================================================
# 初始化
# =============================================================================

# 模块加载时执行一次垃圾回收
safe_garbage_collect()