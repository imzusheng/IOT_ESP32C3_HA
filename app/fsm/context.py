# app/fsm/context.py
"""
状态机上下文管理器
集中管理状态机数据和依赖
"""

import utime as time
import machine
from lib.logger import info, error
from .state_const import STATE_BOOT

def create_fsm_context(event_bus, config, 
                      network_manager=None, led_controller=None):
    """创建状态机上下文"""
    context = {
        # 核心依赖
        'event_bus': event_bus,
        'config': config,
        
        # 外部组件
        'network_manager': network_manager,
        'led_controller': led_controller,
        
        # 状态机数据
        'current_state': STATE_BOOT,
        'previous_state': None,
        'state_start_time': time.ticks_ms(),
        
        # 错误处理
        'error_count': 0,
        'max_errors': config.get('daemon', {}).get('max_error_count', 10),
        
        # 看门狗
        'wdt': None,
        
        # 状态特定的临时数据
        'boot_start_time': 0,
        'init_start_time': 0,
        'networking_start_time': 0,
        'running_start_time': 0,
        'warning_start_time': 0,
        'error_start_time': 0,
        'recovery_start_time': 0,
        'safe_mode_start_time': 0,
        
        # 运行时标志
        'mqtt_connect_scheduled': False,
        'recovery_triggered': False,
        'completion_triggered': False,
        
        # 定时器
        'last_status_log_time': 0,
        'last_health_check_time': 0,
        'last_gc_time': 0
    }
    
    # 初始化看门狗
    _init_watchdog(context, config)
    
    return context

def _init_watchdog(context, config):
    """初始化看门狗"""
    if config.get('daemon', {}).get('wdt_enabled', False):
        wdt_timeout = config.get('daemon', {}).get('wdt_timeout', 120000)
        try:
            context['wdt'] = machine.WDT(timeout=wdt_timeout)
            info("看门狗已启用，超时时间: {} ms", wdt_timeout, module="FSM")
        except Exception as e:
            error("启用看门狗失败: {}", e, module="FSM")

def get_context_value(context, key, default=None):
    """安全获取上下文值"""
    return context.get(key, default)

def set_context_value(context, key, value):
    """设置上下文值"""
    context[key] = value

def clear_context_flags(context):
    """清理上下文中的临时标志"""
    flags_to_clear = [
        'mqtt_connect_scheduled',
        'recovery_triggered',
        'completion_triggered'
    ]
    
    for flag in flags_to_clear:
        context.pop(flag, None)

def reset_state_timers(context):
    """重置状态定时器"""
    timer_keys = [
        'boot_start_time',
        'init_start_time',
        'networking_start_time',
        'running_start_time',
        'warning_start_time',
        'error_start_time',
        'recovery_start_time',
        'safe_mode_start_time',
        'last_status_log_time',
        'last_health_check_time',
        'last_gc_time'
    ]
    
    for key in timer_keys:
        context[key] = 0

def feed_watchdog(context):
    """喂看门狗"""
    wdt = context.get('wdt')
    if wdt:
        try:
            wdt.feed()
        except Exception as e:
            error("喂看门狗失败: {}", e, module="FSM")

def increase_error_count(context):
    """增加错误计数"""
    context['error_count'] += 1
    info("错误计数: {}/{}", context['error_count'], context['max_errors'], module="FSM")
    
    # 检查是否达到最大错误数
    if context['error_count'] >= context['max_errors']:
        info("达到最大错误计数，进入安全模式", module="FSM")
        return True
    return False

def reset_error_count(context):
    """重置错误计数"""
    context['error_count'] = 0
    info("错误计数已重置", module="FSM")

def update_led_for_state(context):
    """根据当前状态更新LED"""
    led_controller = context.get('led_controller')
    if not led_controller:
        return
    
    from .state_const import get_led_pattern, get_state_name
    
    current_state = context['current_state']
    pattern = get_led_pattern(current_state)
    
    try:
        led_controller.play(pattern)
        info("LED状态更新为: {} (状态: {})", pattern, get_state_name(current_state), module="FSM")
    except Exception as e:
        error("更新LED状态失败: {}", e, module="FSM")

def save_state_to_cache(context):
    """保存状态到缓存"""
    pass

def get_state_duration(context):
    """获取当前状态持续时间（毫秒）"""
    return time.ticks_diff(time.ticks_ms(), context['state_start_time'])

def get_state_info(context):
    """获取状态信息"""
    from .state_const import get_state_name
    
    return {
        'current_state': get_state_name(context['current_state']),
        'previous_state': get_state_name(context['previous_state']) if context['previous_state'] is not None else None,
        'duration_seconds': get_state_duration(context) // 1000,
        'error_count': context['error_count']
    }

def cleanup_context(context):
    """清理上下文资源"""
    # 关闭看门狗（如果有的话）
    wdt = context.get('wdt')
    if wdt:
        try:
            # MicroPython 的 WDT 通常不需要显式关闭
            pass
        except:
            pass
    
    # 清理所有临时数据
    clear_context_flags(context)
    reset_state_timers(context)
    
    info("状态机上下文已清理", module="FSM")