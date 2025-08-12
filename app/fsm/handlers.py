# app/fsm/handlers.py
"""
状态处理函数模块
每个状态对应一个处理函数，负责处理状态进入、退出和定时事件
"""

import utime as time
import gc
from lib.logger import info, warning, error
from lib.event_bus.events_const import EVENTS
from .state_const import STATE_NAMES, get_state_name

def boot_state_handler(event, context):
    """启动状态处理函数"""
    if event == 'enter':
        info("进入启动状态，系统开始初始化", module="FSM")
        context['boot_start_time'] = time.ticks_ms()
        return None
    
    elif event == 'update':
        # 检查是否超过1秒
        if time.ticks_diff(time.ticks_ms(), context.get('boot_start_time', 0)) >= 1000:
            info("启动阶段完成，发布boot_complete事件", module="FSM")
            return 'boot_complete'
    
    elif event == 'exit':
        info("退出启动状态", module="FSM")
    
    return None

def init_state_handler(event, context):
    """初始化状态处理函数"""
    if event == 'enter':
        info("进入初始化状态，开始模块初始化", module="FSM")
        context['init_start_time'] = time.ticks_ms()
        _perform_initialization(context)
        return None
    
    elif event == 'update':
        # 检查是否超过2秒
        if time.ticks_diff(time.ticks_ms(), context.get('init_start_time', 0)) >= 2000:
            info("初始化阶段完成，发布init_complete事件", module="FSM")
            return 'init_complete'
    
    elif event == 'exit':
        info("退出初始化状态", module="FSM")
    
    return None

def networking_state_handler(event, context):
    """网络连接状态处理函数"""
    if event == 'enter':
        info("进入NETWORKING状态，开始WiFi连接", module="FSM")
        context['networking_start_time'] = time.ticks_ms()
        _start_wifi_connection(context)
        return None
    
    elif event == 'update':
        # 定期调用WiFi管理器的update方法来处理连接状态机
        wifi_manager = context.get('wifi_manager')
        if wifi_manager and hasattr(wifi_manager, 'update'):
            try:
                wifi_manager.update()
            except Exception as e:
                error("WiFi状态更新失败: {}", e, module="FSM")
        
        # 检查连接超时 - 使用与WiFi管理器一致的超时时间
        elapsed = time.ticks_diff(time.ticks_ms(), context.get('networking_start_time', 0))
        timeout = context['config'].get('wifi', {}).get('timeout', 15) * 1000
        
        if elapsed > timeout:
            warning("WiFi连接超时（{}ms），发布超时事件", elapsed, module="FSM")
            return 'error'
    
    elif event == 'wifi_connected':
        # WiFi连接成功，转换到RUNNING状态
        info("WiFi连接成功，转换到RUNNING状态", module="FSM")
        return 'running'
    
    elif event == 'exit':
        info("退出NETWORKING状态", module="FSM")
    
    return None

def running_state_handler(event, context):
    """运行状态处理函数"""
    if event == 'enter':
        info("进入RUNNING状态，系统正常运行中", module="FSM")
        info("NTP同步已完成，系统时间已同步", module="FSM")
        info("将在1秒后异步启动MQTT连接", module="FSM")
        
        context['running_start_time'] = time.ticks_ms()
        context['last_status_log_time'] = 0
        context['last_health_check_time'] = 0
        context['mqtt_connect_scheduled'] = False
        
        _schedule_mqtt_connection(context)
        return None
    
    elif event == 'update':
        current_time = time.ticks_ms()
        _periodic_maintenance(context, current_time)
    
    elif event == 'exit':
        info("退出RUNNING状态", module="FSM")
    
    return None

def warning_state_handler(event, context):
    """警告状态处理函数"""
    if event == 'enter':
        warning("进入WARNING状态，系统出现警告", module="FSM")
        context['warning_start_time'] = time.ticks_ms()
        return None
    
    elif event == 'update':
        # 30秒后尝试恢复
        elapsed = time.ticks_diff(time.ticks_ms(), context.get('warning_start_time', 0))
        if elapsed >= 30000:  # 30秒
            if not context.get('recovery_triggered', False):
                context['recovery_triggered'] = True
                info("警告状态超时，尝试恢复", module="FSM")
                return 'recovery_success'
    
    elif event == 'exit':
        info("退出WARNING状态", module="FSM")
        context.pop('recovery_triggered', None)
    
    return None

def error_state_handler(event, context):
    """错误状态处理函数"""
    if event == 'enter':
        error("进入ERROR状态，系统出现错误", module="FSM")
        
        # 增加错误计数
        context['error_count'] += 1
        info("错误计数: {}/{}", context['error_count'], context['max_errors'], module="FSM")
        
        context['error_start_time'] = time.ticks_ms()
        
        # 检查是否达到最大错误数
        if context['error_count'] >= context['max_errors']:
            info("达到最大错误计数，进入安全模式", module="FSM")
            return 'safe_mode'
        
        return None
    
    elif event == 'update':
        # 15秒后尝试恢复
        elapsed = time.ticks_diff(time.ticks_ms(), context.get('error_start_time', 0))
        if elapsed >= 15000:  # 15秒
            if not context.get('recovery_triggered', False):
                context['recovery_triggered'] = True
                info("错误状态超时，尝试恢复", module="FSM")
                return 'recovery_success'
    
    elif event == 'exit':
        info("退出ERROR状态", module="FSM")
        context.pop('recovery_triggered', None)
    
    return None

def safe_mode_state_handler(event, context):
    """安全模式状态处理函数"""
    if event == 'enter':
        info("进入安全模式 - 执行紧急清理", module="FSM")
        context['safe_mode_start_time'] = time.ticks_ms()
        context['last_gc_time'] = time.ticks_ms()
        _emergency_cleanup(context)
        return None
    
    elif event == 'update':
        current_time = time.ticks_ms()
        
        # 定期垃圾回收（每30秒）
        if time.ticks_diff(current_time, context.get('last_gc_time', 0)) >= 30000:
            context['last_gc_time'] = current_time
            try:
                gc.collect()
                info("安全模式垃圾回收", module="FSM")
            except Exception as e:
                info("安全模式垃圾回收失败: {}", e, module="FSM")
    
    elif event == 'exit':
        info("退出安全模式", module="FSM")
        
        # 重置错误计数
        context['error_count'] = 0
        info("错误计数已重置", module="FSM")
        
        # 最后一次垃圾回收
        try:
            gc.collect()
        except:
            pass
    
    return None

def recovery_state_handler(event, context):
    """恢复状态处理函数"""
    if event == 'enter':
        info("进入RECOVERY状态，开始系统恢复", module="FSM")
        context['recovery_start_time'] = time.ticks_ms()
        return None
    
    elif event == 'update':
        # 10秒后完成恢复
        elapsed = time.ticks_diff(time.ticks_ms(), context.get('recovery_start_time', 0))
        if elapsed >= 10000:  # 10秒
            if not context.get('completion_triggered', False):
                context['completion_triggered'] = True
                info("恢复超时，自动完成恢复", module="FSM")
                return 'recovery_success'
    
    elif event == 'exit':
        info("退出RECOVERY状态", module="FSM")
        context.pop('completion_triggered', None)
    
    return None

def shutdown_state_handler(event, context):
    """关机状态处理函数"""
    if event == 'enter':
        info("进入SHUTDOWN状态，系统准备关机", module="FSM")
        _perform_shutdown_cleanup(context)
        return None
    
    elif event == 'update':
        # 关机状态通常不处理更新
        pass
    
    elif event == 'exit':
        info("退出SHUTDOWN状态（这通常不应该发生）", module="FSM")
    
    return None

# 状态处理函数映射表
STATE_HANDLERS = {
    0: boot_state_handler,      # STATE_BOOT
    1: init_state_handler,      # STATE_INIT
    2: networking_state_handler, # STATE_NETWORKING
    3: running_state_handler,   # STATE_RUNNING
    4: warning_state_handler,   # STATE_WARNING
    5: error_state_handler,     # STATE_ERROR
    6: safe_mode_state_handler, # STATE_SAFE_MODE
    7: recovery_state_handler,  # STATE_RECOVERY
    8: shutdown_state_handler   # STATE_SHUTDOWN
}

# ========== 辅助函数 ==========

def _perform_initialization(context):
    """执行初始化任务"""
    try:
        info("执行系统初始化任务", module="FSM")
        
        # 初始化对象池（如果需要）
        if context.get('object_pool'):
            pass
        
        # 初始化静态缓存（如果需要）
        if context.get('static_cache'):
            pass
    
    except Exception as e:
        error("初始化任务执行失败: {}", e, module="FSM")
        context['event_bus'].publish(EVENTS.SYSTEM_ERROR, str(e))

def _start_wifi_connection(context):
    """启动WiFi连接过程"""
    wifi_manager = context.get('wifi_manager')
    if not wifi_manager:
        error("WiFi管理器不可用", module="FSM")
        context['event_bus'].publish(EVENTS.SYSTEM_ERROR, "缺少WiFi管理器")
        return
    
    # 快速路径检查：如果WiFi已经连接，直接返回成功
    try:
        if hasattr(wifi_manager, 'is_connected') and wifi_manager.is_connected():
            info("进入NETWORKING状态时WiFi已连接，快速切换到RUNNING状态", module="FSM")
            context['event_bus'].publish(EVENTS.WIFI_STATE_CHANGE, state='connected')
            return
    except Exception as e:
        error("NETWORKING快速路径检查失败: {}", e, module="FSM")
    
    # 启动WiFi连接过程
    try:
        if hasattr(wifi_manager, 'connect'):
            info("启动WiFi连接过程", module="FSM")
            wifi_manager.connect()
        elif hasattr(wifi_manager, 'update'):
            wifi_manager.update()
    except Exception as e:
        error("启动WiFi连接失败: {}", e, module="FSM")
        context['event_bus'].publish(EVENTS.SYSTEM_ERROR, f"WiFi连接启动失败: {str(e)}")

def _schedule_mqtt_connection(context):
    """调度MQTT连接"""
    mqtt_controller = context.get('mqtt_controller')
    if not mqtt_controller:
        info("MQTT控制器不可用，跳过连接", module="FSM")
        return
    
    try:
        info("开始异步MQTT连接", module="FSM")
        mqtt_controller.connect()
        info("MQTT连接请求已发送，等待异步结果", module="FSM")
    except Exception as e:
        error("MQTT连接失败: {}", e, module="FSM")

def _periodic_maintenance(context, current_time):
    """定期维护任务"""
    # 每30秒输出一次运行状态日志
    if current_time - context.get('last_status_log_time', 0) >= 30000:  # 30秒
        context['last_status_log_time'] = current_time
        _log_system_status(context)
    
    # 每10秒检查一次系统健康状态
    if current_time - context.get('last_health_check_time', 0) >= 10000:  # 10秒
        context['last_health_check_time'] = current_time
        _check_system_health(context)
    
    # 如果MQTT还没有连接，且超过1秒，尝试连接
    if (not context.get('mqtt_connect_scheduled', False) and 
        time.ticks_diff(current_time, context.get('running_start_time', 0)) >= 1000):
        _schedule_mqtt_connection(context)
        context['mqtt_connect_scheduled'] = True

def _log_system_status(context):
    """记录系统状态"""
    try:
        running_duration = time.ticks_diff(time.ticks_ms(), context.get('running_start_time', 0))
        info("系统正常运行中 - 运行时间: {}秒", running_duration // 1000, module="FSM")
        
        # 检查WiFi连接状态
        wifi_manager = context.get('wifi_manager')
        if wifi_manager:
            if hasattr(wifi_manager, 'is_connected'):
                # 正确调用方法
                wifi_status = "已连接" if wifi_manager.is_connected() else "未连接"
            else:
                # 备用检查方法
                wifi_status = "已连接" if wifi_manager.wlan.isconnected() else "未连接"
            info("RUNNING - WiFi状态: {}", wifi_status, module="FSM")
        
        # 检查MQTT连接状态
        mqtt_controller = context.get('mqtt_controller')
        if mqtt_controller and hasattr(mqtt_controller, 'is_connected'):
            mqtt_status = "已连接" if mqtt_controller.is_connected() else "未连接"
            info("RUNNING - MQTT状态: {}", mqtt_status, module="FSM")
        
        # 检查内存使用情况
        gc.collect()
        mem_free = gc.mem_free()
        mem_alloc = gc.mem_alloc()
        mem_total = mem_free + mem_alloc
        mem_percent = (mem_alloc / mem_total * 100) if mem_total > 0 else 0
        info("RUNNING - 内存使用: {:.1f}% (空闲: {}KB)", mem_percent, mem_free // 1024, module="FSM")
        
    except Exception as e:
        # 增加更详细的错误信息
        import sys
        error_type = type(e).__name__
        error_msg = str(e)
        error("RUNNING - 状态检查失败: 类型={}, 错误={}", error_type, error_msg, module="FSM")

def _check_system_health(context):
    """检查系统健康状态"""
    try:
        # 检查内存使用
        gc.collect()
        mem_free = gc.mem_free()
        mem_total = gc.mem_free() + gc.mem_alloc()
        mem_percent = (mem_total - mem_free) / mem_total * 100
        
        memory_threshold = context['config'].get('daemon', {}).get('memory_threshold', 80)
        if mem_percent > memory_threshold:
            warning("高内存使用率: {:.1f}%", mem_percent, module="FSM")
            context['event_bus'].publish(EVENTS.SYSTEM_STATE_CHANGE, 
                                       state='warning', 
                                       warning_msg=f"高内存使用: {mem_percent:.1f}%")
        
        # 检查温度
        try:
            from utils.helpers import get_temperature
            temp = get_temperature()
            if temp:
                temp_threshold = context['config'].get('daemon', {}).get('temp_threshold', 65)
                if temp > temp_threshold:
                    warning("高温: {}°C", temp, module="FSM")
                    context['event_bus'].publish(EVENTS.SYSTEM_STATE_CHANGE, 
                                               state='warning', 
                                               warning_msg=f"高温: {temp}°C")
        except Exception:
            # 温度检查失败不是致命错误，只记录日志
            pass
        
        # 检查WiFi状态一致性
        mqtt_controller = context.get('mqtt_controller')
        wifi_manager = context.get('wifi_manager')
        
        if mqtt_controller and hasattr(mqtt_controller, 'is_connected') and mqtt_controller.is_connected():
            # 如果MQTT已连接，WiFi也应该连接
            wifi_connected = False
            if wifi_manager:
                if hasattr(wifi_manager, 'is_connected'):
                    wifi_connected = wifi_manager.is_connected()
                else:
                    wifi_connected = wifi_manager.wlan.isconnected()
            
            if not wifi_connected:
                warning("MQTT已连接但WiFi状态异常，可能存在状态不一致", module="FSM")
                context['event_bus'].publish(EVENTS.SYSTEM_STATE_CHANGE, 
                                           state='warning', 
                                           warning_msg="WiFi状态不一致")
        
    except Exception as e:
        error("健康检查失败: {}", e, module="FSM")

def _emergency_cleanup(context):
    """执行紧急清理"""
    try:
        # 深度垃圾回收
        info("执行深度垃圾回收", module="FSM")
        for _ in range(3):
            gc.collect()
            time.sleep_ms(50)
        
        # 清理对象池
        object_pool = context.get('object_pool')
        if object_pool and hasattr(object_pool, 'clear_all_pools'):
            info("清理对象池", module="FSM")
            object_pool.clear_all_pools()
        
        # 断开非关键连接
        mqtt_controller = context.get('mqtt_controller')
        if mqtt_controller and hasattr(mqtt_controller, 'disconnect'):
            try:
                info("断开MQTT连接", module="FSM")
                mqtt_controller.disconnect()
            except Exception as e:
                info("断开MQTT连接失败（忽略）: {}", e, module="FSM")
        
        # 保存关键状态到缓存
        static_cache = context.get('static_cache')
        if static_cache:
            try:
                info("保存系统状态", module="FSM")
                static_cache.set('safe_mode_entry_time', time.ticks_ms())
                static_cache.save(force=True)
            except Exception as e:
                info("保存系统状态失败（忽略）: {}", e, module="FSM")
    
    except Exception as e:
        # 即使在安全模式下，清理失败也不应该导致系统崩溃
        info("安全模式紧急清理部分失败（继续运行）: {}", e, module="FSM")

def _perform_shutdown_cleanup(context):
    """执行关机清理"""
    try:
        info("执行关机清理工作", module="FSM")
        
        # 断开MQTT连接
        mqtt_controller = context.get('mqtt_controller')
        if mqtt_controller:
            try:
                info("断开MQTT连接", module="FSM")
                mqtt_controller.disconnect()
            except Exception as e:
                info("断开MQTT连接失败（忽略）: {}", e, module="FSM")
        
        # 断开WiFi连接
        wifi_manager = context.get('wifi_manager')
        if wifi_manager:
            try:
                info("断开WiFi连接", module="FSM")
                wifi_manager.disconnect()
            except Exception as e:
                info("断开WiFi连接失败（忽略）: {}", e, module="FSM")
        
        # 关闭LED
        led_controller = context.get('led_controller')
        if led_controller:
            try:
                info("关闭LED", module="FSM")
                led_controller.cleanup()
            except Exception as e:
                info("关闭LED失败（忽略）: {}", e, module="FSM")
        
        # 保存关键数据到缓存
        static_cache = context.get('static_cache')
        if static_cache:
            try:
                info("保存系统状态", module="FSM")
                static_cache.set('shutdown_time', time.ticks_ms())
                static_cache.save(force=True)
            except Exception as e:
                info("保存系统状态失败（忽略）: {}", e, module="FSM")
        
        info("关机清理完成", module="FSM")
        
    except Exception as e:
        info("关机清理过程中出现错误（忽略）: {}", e, module="FSM")