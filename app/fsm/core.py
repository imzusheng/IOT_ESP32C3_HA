# app/fsm/core.py
"""
函数式状态机核心实现
使用函数和字典替代类继承，简化状态机架构，提高稳定性
"""

import utime as time
from lib.lock.event_bus import EVENTS
from lib.logger import info, error, warning
from .state_const import (
    STATE_BOOT, STATE_NAMES, STATE_TRANSITIONS,
    get_state_name, get_next_state
)
from .handlers import STATE_HANDLERS
from .context import (
    create_fsm_context, feed_watchdog, update_led_for_state,
    save_state_to_cache, get_state_info as context_get_state_info,
    increase_error_count, reset_error_count
)


class FunctionalStateMachine:
    """
    函数式状态机类
    采用函数和字典查找替代类继承，彻底简化架构
    """
    
    def __init__(self, event_bus, config, 
                 network_manager=None, static_cache=None):
        """
        初始化函数式状态机
        Args:
            event_bus: 事件总线实例
            static_cache: 静态缓存实例 (暂时禁用)
            config: 配置字典
            network_manager: 网络管理器实例
        """
        # 创建状态机上下文
        self.context = create_fsm_context(
            event_bus, config,
            network_manager=network_manager
        )
        
        # 订阅事件
        self._subscribe_events()
        
        # 进入初始状态
        self._enter_state(STATE_BOOT)
        
        info("函数式状态机已初始化", module="FSM")
    
    def _subscribe_events(self):
        """订阅事件"""
        events_to_subscribe = [
            EVENTS['SYSTEM_STATE_CHANGE'],
            EVENTS['SYSTEM_ERROR'],
            EVENTS['WIFI_STATE_CHANGE'],
            EVENTS['MQTT_STATE_CHANGE'],
            EVENTS['NTP_STATE_CHANGE']
        ]
        
        for event in events_to_subscribe:
            self.context['event_bus'].subscribe(event, self._handle_event)
            info("状态机订阅事件: {}", event, module="FSM")
        
        # 订阅网络状态变化事件
        self.context['event_bus'].subscribe("network_state_change", self._handle_network_state_change)
        info("状态机订阅网络状态事件: network_state_change", module="FSM")
    
    def _enter_state(self, new_state):
        """进入指定状态"""
        if new_state == self.context['current_state']:
            return False
        
        # 退出当前状态
        current_state = self.context['current_state']
        if current_state is not None:
            current_handler = STATE_HANDLERS.get(current_state)
            if current_handler:
                try:
                    current_handler('exit', self.context)
                except Exception as e:
                    error("退出状态 {} 时发生错误: {}", get_state_name(current_state), e, module="FSM")
        
        # 更新状态
        self.context['previous_state'] = self.context['current_state']
        self.context['current_state'] = new_state
        self.context['state_start_time'] = time.ticks_ms()
        
        # 进入新状态
        new_handler = STATE_HANDLERS.get(new_state)
        if new_handler:
            try:
                result = new_handler('enter', self.context)
                # 处理状态处理函数返回的事件
                if result:
                    self._handle_internal_event(result)
            except Exception as e:
                error("进入状态 {} 时发生错误: {}", get_state_name(new_state), e, module="FSM")
        else:
            error("未找到状态处理函数: {}", get_state_name(new_state), module="FSM")
        
        # 更新LED状态
        update_led_for_state(self.context)
        
        # 保存状态到缓存
        save_state_to_cache(self.context)
        
        return True
    
    def _handle_event(self, event_name, *args, **kwargs):
        """处理外部事件"""
        try:
            info("状态机收到事件: {} (参数: {}, {})", event_name, args, kwargs, module="FSM")
            
            # 将事件转换为内部事件
            internal_event = self._convert_external_event(event_name, *args, **kwargs)
            info("事件转换: {} -> {}", event_name, internal_event, module="FSM")
            
            if internal_event:
                # 处理状态转换
                self._handle_internal_event(internal_event)
            
            # 将事件传递给当前状态处理函数
            current_state = self.context['current_state']
            state_handler = STATE_HANDLERS.get(current_state)
            if state_handler:
                try:
                    info("状态 {} 处理事件 {}", get_state_name(current_state), event_name, module="FSM")
                    result = state_handler(event_name, self.context, *args, **kwargs)
                    if result:
                        info("状态 {} 返回内部事件: {}", get_state_name(current_state), result, module="FSM")
                        self._handle_internal_event(result)
                except Exception as e:
                    error("状态 {} 处理事件 {} 时发生错误: {}", 
                          get_state_name(current_state), event_name, e, module="FSM")
        
        except Exception as e:
            error("处理事件 {} 时发生错误: {}", event_name, e, module="FSM")
    
    def _convert_external_event(self, event_name, *args, **kwargs):
        """将外部事件转换为内部事件"""
        try:
            if event_name == EVENTS['WIFI_STATE_CHANGE']:
                state = kwargs.get('state', '')
                if state == 'connected':
                    return 'wifi_connected'
                elif state == 'disconnected':
                    return 'wifi_disconnected'
            
            elif event_name == EVENTS['MQTT_STATE_CHANGE']:
                state = kwargs.get('state', '')
                if state == 'connected':
                    return 'mqtt_connected'
                elif state == 'disconnected':
                    return 'mqtt_disconnected'
            
            elif event_name == EVENTS['SYSTEM_STATE_CHANGE']:
                state = kwargs.get('state', '')
                # 直接返回状态值作为内部事件
                return state
            
            elif event_name == EVENTS['SYSTEM_ERROR']:
                # 增加错误计数
                if increase_error_count(self.context):
                    return 'safe_mode'
                return 'error'
            
            elif event_name == EVENTS['NTP_STATE_CHANGE']:
                # NTP事件通常不直接触发状态转换
                state = kwargs.get('state', '')
                info("NTP状态变化: {}", state, module="FSM")
                return None
        
        except Exception as e:
            error("转换外部事件 {} 时发生错误: {}", event_name, e, module="FSM")
        
        return None
    
    def _handle_network_state_change(self, state, **kwargs):
        """处理网络状态变化事件"""
        info("网络状态变化: {} (参数: {})", state, kwargs, module="FSM")
        
        # 网络状态变化时，根据当前状态决定是否需要重新连接
        current_state = self.context['current_state']
        if state == 'disconnected' and current_state in [STATE_RUNNING, STATE_NETWORKING]:
            info("网络断开，重新连接", module="FSM")
            self._handle_internal_event('networking')
    
    def _handle_internal_event(self, event):
        """处理内部事件，执行状态转换"""
        current_state = self.context['current_state']
        next_state = get_next_state(current_state, event)
        
        if next_state is not None and next_state != current_state:
            self._enter_state(next_state)
        else:
            # 事件未触发状态转换，记录调试信息
            if next_state is None:
                info("事件 {} 在状态 {} 中未定义转换", event, get_state_name(current_state), module="FSM")
    
    def update(self):
        """更新状态机，处理定时任务等"""
        try:
            # 喂看门狗
            feed_watchdog(self.context)
            
            # 调用当前状态的更新处理
            current_state = self.context['current_state']
            state_handler = STATE_HANDLERS.get(current_state)
            if state_handler:
                result = state_handler('update', self.context)
                if result:
                    self._handle_internal_event(result)
        
        except Exception as e:
            error("更新状态机时发生错误: {}", e, module="FSM")
    
    # ========== 公共接口方法（保持兼容性） ==========
    
    def get_current_state(self):
        """获取当前状态名称"""
        return get_state_name(self.context['current_state'])
    
    def get_state_duration(self):
        """获取当前状态持续时间（毫秒）"""
        return time.ticks_diff(time.ticks_ms(), self.context['state_start_time'])
    
    def get_state_info(self):
        """获取状态信息"""
        return context_get_state_info(self.context)
    
    def force_state(self, state_name):
        """强制设置状态"""
        # 将状态名称转换为状态ID
        state_id = None
        for sid, name in STATE_NAMES.items():
            if name == state_name:
                state_id = sid
                break
        
        if state_id is not None:
            info("强制设置状态为: {}", state_name, module="FSM")
            return self._enter_state(state_id)
        else:
            error("未知的状态名称: {}", state_name, module="FSM")
            return False
    
    def transition_to(self, new_state_name, reason=""):
        """转换到新状态（兼容性接口）"""
        info("请求状态转换: {} (原因: {})", new_state_name, reason, module="FSM")
        return self.force_state(new_state_name)
    
    def increase_error_count(self):
        """增加错误计数"""
        if increase_error_count(self.context):
            # 达到最大错误数，进入安全模式
            self._handle_internal_event('safe_mode')
    
    def reset_error_count(self):
        """重置错误计数"""
        reset_error_count(self.context)
    
    def feed_watchdog(self):
        """喂看门狗"""
        feed_watchdog(self.context)


# 为了保持兼容性，创建别名
StateMachine = FunctionalStateMachine

# 全局状态机实例
_state_machine_instance = None

def get_state_machine():
    """获取全局状态机实例"""
    return _state_machine_instance

def create_state_machine(config, event_bus, 
                        network_manager=None, static_cache=None):
    """创建全局状态机实例"""
    global _state_machine_instance
    _state_machine_instance = FunctionalStateMachine(
        event_bus, config,
        network_manager=network_manager,
        static_cache=static_cache
    )
    return _state_machine_instance