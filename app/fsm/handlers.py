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
        info("进入NETWORKING状态，启动网络连接", module="FSM")
        context['networking_start_time'] = time.ticks_ms()
        _start_network_connection(context)
        return None
    
    elif event == 'update':
        # 定期调用网络管理器的update方法来处理连接状态机
        network_manager = context.get('network_manager')
        if network_manager and hasattr(network_manager, 'update'):
            try:
                network_manager.update()
            except Exception as e:
                error("网络状态更新失败: {}", e, module="FSM")
        
        # 检查连接超时 - 使用网络管理器统一配置的超时时间
        elapsed = time.ticks_diff(time.ticks_ms(), context.get('networking_start_time', 0))
        timeout = context['config'].get('network', {}).get('max_backoff_time', 300) * 1000
        
        if elapsed > timeout:
            warning("网络连接超时（{}ms），发布超时事件", elapsed, module="FSM")
            return 'error'
    
    elif event == 'wifi_connected':
        # WiFi连接成功，转换到RUNNING状态
        info("网络连接成功，转换到RUNNING状态", module="FSM")
        return 'running'
    
    elif event == 'exit':
        info("退出NETWORKING状态", module="FSM")
    
    return None

def running_state_handler(event, context):
    """运行状态处理函数"""
    if event == 'enter':
        info("进入RUNNING状态，系统正常运行中", module="FSM")
        info("网络连接已完成，启动网络服务", module="FSM")
        
        context['running_start_time'] = time.ticks_ms()
        context['last_status_log_time'] = 0
        context['last_health_check_time'] = 0
        context['mqtt_connect_scheduled'] = False
        
        _start_network_services(context)
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

def _start_network_connection(context):
    """启动网络连接过程"""
    network_manager = context.get('network_manager')
    if not network_manager:
        error("网络管理器不可用", module="FSM")
        context['event_bus'].publish(EVENTS.SYSTEM_ERROR, "缺少网络管理器")
        return
    
    # 启动网络连接过程 - 由网络管理器统一处理WiFi、NTP、MQTT
    try:
        info("启动网络连接过程", module="FSM")
        network_manager.connect()
    except Exception as e:
        error("启动网络连接失败: {}", e, module="FSM")
        context['event_bus'].publish(EVENTS.SYSTEM_ERROR, f"网络连接启动失败: {str(e)}")

def _start_network_services(context):
    """启动网络服务"""
    network_manager = context.get('network_manager')
    if not network_manager:
        info("网络管理器不可用，跳过网络服务", module="FSM")
        return
    
    try:
        info("启动网络服务（NTP、MQTT等）", module="FSM")
        network_manager.start_services()
        info("网络服务启动请求已发送", module="FSM")
    except Exception as e:
        error("启动网络服务失败: {}", e, module="FSM")

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
    
    # 如果网络服务还没有启动，且超过1秒，尝试启动
    if (not context.get('mqtt_connect_scheduled', False) and 
        time.ticks_diff(current_time, context.get('running_start_time', 0)) >= 1000):
        _start_network_services(context)
        context['mqtt_connect_scheduled'] = True

def _log_system_status(context):
    """记录系统状态"""
    try:
        running_duration = time.ticks_diff(time.ticks_ms(), context.get('running_start_time', 0))
        info("系统正常运行中 - 运行时间: {}秒", running_duration // 1000, module="FSM")
        
        # 检查网络状态
        network_manager = context.get('network_manager')
        if network_manager and hasattr(network_manager, 'get_status'):
            network_status = network_manager.get_status()
            info("RUNNING - 网络状态: {}", network_status, module="FSM")
        
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
        
        # 检查网络状态一致性
        network_manager = context.get('network_manager')
        if network_manager and hasattr(network_manager, 'check_consistency'):
            consistency_ok = network_manager.check_consistency()
            if not consistency_ok:
                warning("网络状态不一致", module="FSM")
                context['event_bus'].publish(EVENTS.SYSTEM_STATE_CHANGE, 
                                           state='warning', 
                                           warning_msg="网络状态不一致")
        
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
        
        # 断开网络连接
        network_manager = context.get('network_manager')
        if network_manager and hasattr(network_manager, 'disconnect'):
            try:
                info("断开网络连接", module="FSM")
                network_manager.disconnect()
            except Exception as e:
                info("断开网络连接失败（忽略）: {}", e, module="FSM")
        
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
        
        # 断开网络连接
        network_manager = context.get('network_manager')
        if network_manager and hasattr(network_manager, 'disconnect'):
            try:
                info("断开网络连接", module="FSM")
                network_manager.disconnect()
            except Exception as e:
                info("断开网络连接失败（忽略）: {}", e, module="FSM")
        
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