# -*- coding: utf-8 -*-
"""
系统状态机管理模块

为ESP32C3设备提供状态机管理，实现清晰的状态转换和事件处理：
- 系统状态定义和管理
- 状态转换逻辑
- 事件处理机制
- 状态监控和恢复

状态说明：
- INIT: 系统初始化状态
- NETWORKING: 网络连接状态
- RUNNING: 正常运行状态
- WARNING: 警告状态
- ERROR: 错误状态
- SAFE_MODE: 安全模式
- RECOVERY: 恢复模式
- SHUTDOWN: 关机状态
"""

import time
import gc
import object_pool

# =============================================================================
# 系统状态常量
# =============================================================================

class SystemState:
    """系统状态常量"""
    INIT = "INIT"           # 系统初始化
    NETWORKING = "NETWORKING"  # 网络连接
    RUNNING = "RUNNING"     # 正常运行
    WARNING = "WARNING"     # 警告状态
    ERROR = "ERROR"         # 错误状态
    SAFE_MODE = "SAFE_MODE" # 安全模式
    RECOVERY = "RECOVERY"   # 恢复模式
    SHUTDOWN = "SHUTDOWN"   # 关机状态

# =============================================================================
# 状态转换事件
# =============================================================================

class StateEvent:
    """状态转换事件"""
    INIT_COMPLETE = "INIT_COMPLETE"         # 初始化完成
    NETWORK_SUCCESS = "NETWORK_SUCCESS"     # 网络连接成功
    NETWORK_FAILED = "NETWORK_FAILED"       # 网络连接失败
    SYSTEM_WARNING = "SYSTEM_WARNING"       # 系统警告
    SYSTEM_ERROR = "SYSTEM_ERROR"           # 系统错误
    MEMORY_CRITICAL = "MEMORY_CRITICAL"     # 内存严重不足
    SAFE_MODE_TRIGGER = "SAFE_MODE_TRIGGER" # 安全模式触发
    RECOVERY_SUCCESS = "RECOVERY_SUCCESS"   # 恢复成功
    RECOVERY_FAILED = "RECOVERY_FAILED"     # 恢复失败
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"     # 系统关机
    WATCHDOG_TIMEOUT = "WATCHDOG_TIMEOUT"   # 看门狗超时

# =============================================================================
# 状态机类
# =============================================================================

class SystemStateMachine:
    """系统状态机"""
    
    def __init__(self):
        """初始化状态机"""
        self._current_state = SystemState.INIT
        self._previous_state = None
        self._state_start_time = time.ticks_ms()
        self._state_duration = 0
        self._transition_history = []
        self._max_history = 10
        
        # 状态转换表
        self._transition_table = self._build_transition_table()
        
        # 状态处理器映射
        self._state_handlers = {
            SystemState.INIT: self._handle_init_state,
            SystemState.NETWORKING: self._handle_networking_state,
            SystemState.RUNNING: self._handle_running_state,
            SystemState.WARNING: self._handle_warning_state,
            SystemState.ERROR: self._handle_error_state,
            SystemState.SAFE_MODE: self._handle_safe_mode_state,
            SystemState.RECOVERY: self._handle_recovery_state,
            SystemState.SHUTDOWN: self._handle_shutdown_state
        }
        
        print(f"[StateMachine] 状态机初始化完成，初始状态: {self._current_state}")
    
    def _build_transition_table(self):
        """构建状态转换表"""
        return {
            SystemState.INIT: {
                StateEvent.INIT_COMPLETE: SystemState.NETWORKING,
                StateEvent.SYSTEM_ERROR: SystemState.ERROR,
                StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE
            },
            SystemState.NETWORKING: {
                StateEvent.NETWORK_SUCCESS: SystemState.RUNNING,
                StateEvent.NETWORK_FAILED: SystemState.WARNING,
                StateEvent.SYSTEM_ERROR: SystemState.ERROR,
                StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE
            },
            SystemState.RUNNING: {
                StateEvent.SYSTEM_WARNING: SystemState.WARNING,
                StateEvent.SYSTEM_ERROR: SystemState.ERROR,
                StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE,
                StateEvent.NETWORK_FAILED: SystemState.NETWORKING,
                StateEvent.RECOVERY_SUCCESS: SystemState.RUNNING,
                StateEvent.WATCHDOG_TIMEOUT: SystemState.RECOVERY
            },
            SystemState.WARNING: {
                StateEvent.SYSTEM_ERROR: SystemState.ERROR,
                StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE,
                StateEvent.RECOVERY_SUCCESS: SystemState.RUNNING,
                StateEvent.NETWORK_SUCCESS: SystemState.RUNNING
            },
            SystemState.ERROR: {
                StateEvent.RECOVERY_SUCCESS: SystemState.WARNING,
                StateEvent.RECOVERY_FAILED: SystemState.SAFE_MODE,
                StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE,
                StateEvent.SYSTEM_SHUTDOWN: SystemState.SHUTDOWN
            },
            SystemState.SAFE_MODE: {
                StateEvent.RECOVERY_SUCCESS: SystemState.WARNING,
                StateEvent.SYSTEM_SHUTDOWN: SystemState.SHUTDOWN
            },
            SystemState.RECOVERY: {
                StateEvent.RECOVERY_SUCCESS: SystemState.RUNNING,
                StateEvent.RECOVERY_FAILED: SystemState.SAFE_MODE,
                StateEvent.SYSTEM_ERROR: SystemState.ERROR,
                StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE
            },
            SystemState.SHUTDOWN: {}  # 终止状态
        }
    
    def transition_to(self, new_state, reason=""):
        """状态转换"""
        if new_state == self._current_state:
            return False
        
        # 记录转换历史
        self._record_transition(self._current_state, new_state, reason)
        
        # 更新状态信息
        self._previous_state = self._current_state
        self._current_state = new_state
        self._state_start_time = time.ticks_ms()
        self._state_duration = 0
        
        print(f"[StateMachine] 状态转换: {self._previous_state} -> {self._current_state} ({reason})")
        
        # 执行状态退出和进入处理
        self._on_state_exit(self._previous_state)
        self._on_state_enter(self._current_state)
        
        return True
    
    def handle_event(self, event, data=None):
        """处理状态转换事件"""
        if event in self._transition_table.get(self._current_state, {}):
            new_state = self._transition_table[self._current_state][event]
            if new_state:
                return self.transition_to(new_state, f"事件: {event}")
        return False
    
    def handle_state_event(self, event, data=None):
        """处理状态转换事件（handle_event的别名）"""
        return self.handle_event(event, data)
    
    def update(self):
        """更新状态机"""
        self._state_duration = time.ticks_diff(time.ticks_ms(), self._state_start_time)
        
        # 调用当前状态处理器
        handler = self._state_handlers.get(self._current_state)
        if handler:
            try:
                handler()
            except Exception as e:
                print(f"[StateMachine] 状态处理器异常: {e}")
                self.handle_event(StateEvent.SYSTEM_ERROR)
    
    def _record_transition(self, from_state, to_state, reason):
        """记录状态转换历史"""
        transition = {
            'from': from_state,
            'to': to_state,
            'reason': reason,
            'timestamp': time.ticks_ms()
        }
        
        self._transition_history.append(transition)
        
        # 保持历史记录大小
        if len(self._transition_history) > self._max_history:
            self._transition_history.pop(0)
    
    def _on_state_enter(self, state):
        """状态进入处理"""
        print(f"[StateMachine] 进入状态: {state}")
        
        # 执行状态特定的进入处理
        if state == SystemState.SAFE_MODE:
            # 进入安全模式时的特殊处理
            gc.collect()  # 立即执行垃圾回收
        elif state == SystemState.RECOVERY:
            # 进入恢复模式时的特殊处理
            pass
    
    def _on_state_exit(self, state):
        """状态退出处理"""
        print(f"[StateMachine] 退出状态: {state}")
        
        # 执行状态特定的退出处理
        if state == SystemState.SAFE_MODE:
            # 退出安全模式时的清理
            pass
    
    def _handle_init_state(self):
        """处理初始化状态"""
        # 初始化状态主要是等待外部触发
        pass
    
    def _handle_networking_state(self):
        """处理网络连接状态"""
        # 网络连接状态监控
        if self._state_duration > 30000:  # 30秒超时
            self.handle_event(StateEvent.NETWORK_FAILED)
    
    def _handle_running_state(self):
        """处理正常运行状态"""
        # 正常运行状态的监控
        if self._state_duration > 300000:  # 5分钟执行一次内存检查
            memory_info = object_pool.check_memory()
            if memory_info and memory_info['percent'] > 90:
                self.handle_event(StateEvent.MEMORY_CRITICAL)
    
    def _handle_warning_state(self):
        """处理警告状态"""
        # 警告状态的监控和恢复
        if self._state_duration > 60000:  # 1分钟后尝试恢复
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_error_state(self):
        """处理错误状态"""
        # 错误状态的恢复处理
        if self._state_duration > 30000:  # 30秒后尝试恢复
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_safe_mode_state(self):
        """处理安全模式状态"""
        # 安全模式状态监控
        if self._state_duration > 300000:  # 5分钟后尝试恢复
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_recovery_state(self):
        """处理恢复模式状态"""
        # 恢复模式处理
        if self._state_duration > 60000:  # 1分钟后判断恢复结果
            # 这里应该根据实际的恢复情况决定成功还是失败
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_shutdown_state(self):
        """处理关机状态"""
        # 关机状态处理
        pass
    
    def get_current_state(self):
        """获取当前状态"""
        return self._current_state
    
    def get_previous_state(self):
        """获取上一个状态"""
        return self._previous_state
    
    def get_state_duration(self):
        """获取当前状态持续时间"""
        return self._state_duration
    
    def get_state_info(self):
        """获取状态信息"""
        return {
            'current_state': self._current_state,
            'previous_state': self._previous_state,
            'duration': self._state_duration,
            'duration_seconds': self._state_duration // 1000
        }
    
    def get_transition_history(self):
        """获取状态转换历史"""
        return self._transition_history.copy()
    
    def is_in_state(self, state):
        """检查是否处于指定状态"""
        return self._current_state == state
    
    def can_transition_to(self, target_state):
        """检查是否可以转换到目标状态"""
        # 检查是否存在从当前状态到目标状态的转换
        for event, next_state in self._transition_table.get(self._current_state, {}).items():
            if next_state == target_state:
                return True
        return False

# =============================================================================
# 全局状态机实例
# =============================================================================

# 创建全局状态机实例
_state_machine = SystemStateMachine()

def get_state_machine():
    """获取全局状态机实例"""
    return _state_machine

def get_current_state():
    """获取当前状态的便捷函数"""
    return _state_machine.get_current_state()

def handle_state_event(event, data=None):
    """处理状态事件的便捷函数"""
    return _state_machine.handle_event(event, data)

def transition_to_state(state, reason=""):
    """转换到指定状态的便捷函数"""
    return _state_machine.transition_to(state, reason)

def update_state_machine():
    """更新状态机的便捷函数"""
    _state_machine.update()

def get_state_info():
    """获取状态信息的便捷函数"""
    return _state_machine.get_state_info()

def is_in_state(state):
    """检查是否处于指定状态的便捷函数"""
    return _state_machine.is_in_state(state)

# =============================================================================
# 状态相关工具函数
# =============================================================================

def is_system_running():
    """检查系统是否正在运行"""
    return _state_machine.is_in_state(SystemState.RUNNING)

def is_system_safe():
    """检查系统是否处于安全状态"""
    return _state_machine.is_in_state(SystemState.SAFE_MODE)

def is_system_error():
    """检查系统是否处于错误状态"""
    return _state_machine.is_in_state(SystemState.ERROR)

def get_system_uptime():
    """获取系统运行时间"""
    return _state_machine.get_state_duration()

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()

print("[StateMachine] 系统状态机模块加载完成")