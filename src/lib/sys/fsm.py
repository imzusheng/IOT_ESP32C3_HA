# -*- coding: utf-8 -*-
"""
高可用系统状态机模块 (v2.4 - 注释优化版)

为资源受限的 MicroPython 设备提供一个健壮、内存优化的有限状态机 (FSM)。
它通过将复杂的系统逻辑分解为明确的状态和转换，来管理设备的整个生命周期。

主要特性:
- 内存友好: 深度集成 mem_optimizer 模块，通过字符串缓存和对象池减少内存碎片。
- 高可用性: 内部捕获异常并转换为错误状态，避免程序崩溃。
- 事件驱动: 逻辑由外部事件和内部定时器驱动，结构清晰。
- 易于调试: 保留状态转换历史，便于追踪问题。

用法示例 (在 main.py 中):
--------------------------------------------------------------------------------
import time
import state_machine as sm

def run_main_loop():
    # 应用程序初始化代码...
    # ...
    # 初始化完成后，触发第一个事件
    state_machine.handle_event(state_machine.StateEvent.INIT_COMPLETE)

    # 主循环
    while True:
        # 1. 必须周期性调用 update，以驱动内部定时器和状态处理
        state_machine.update_state_machine()

        # 2. 获取当前状态，并执行该状态下的业务逻辑
        current_state = state_machine.get_current_state()

        if current_state == state_machine.SystemState.RUNNING:
            # do_my_iot_work() # 执行正常的业务逻辑
            print(".", end="")
        elif current_state == state_machine.SystemState.ERROR:
            # 3. 监控错误状态，并执行处理
            print("System error detected, preparing to restart...")
            # machine.reset() # 重启设备
            break
        
        # 4. 在其他地方，可以根据需要触发事件
        # if not is_network_ok():
        #     state_machine.handle_event(state_machine.StateEvent.NETWORK_FAILED)

        time.sleep(1)

if __name__ == "__main__":
    run_main_loop()
--------------------------------------------------------------------------------
"""

import time
import gc
from lib.sys import memo as mem_opt
import config

# =============================================================================
# Section: 系统状态常量
# =============================================================================

class SystemState:
    """定义了系统所有可能的核心状态。
    
    使用 mem_optimizer 的字符串缓存来确保每个状态名在内存中只有一份实例。
    """
    INIT = mem_opt.get_string("INIT")              # 系统初始化
    NETWORKING = mem_opt.get_string("NETWORKING")  # 网络连接中
    RUNNING = mem_opt.get_string("RUNNING")        # 正常运行
    WARNING = mem_opt.get_string("WARNING")        # 警告状态 (可恢复的非致命错误)
    ERROR = mem_opt.get_string("ERROR")            # 错误状态 (严重错误，可能需要重启)
    SAFE_MODE = mem_opt.get_string("SAFE_MODE")    # 安全模式 (通常因内存严重不足进入)
    RECOVERY = mem_opt.get_string("RECOVERY")      # 恢复模式 (正在尝试从错误中恢复)
    SHUTDOWN = mem_opt.get_string("SHUTDOWN")      # 关机状态

# =============================================================================
# Section: 状态转换事件
# =============================================================================

class StateEvent:
    """定义了所有可能触发状态转换的事件。"""
    INIT_COMPLETE = mem_opt.get_string("INIT_COMPLETE")         # 初始化完成
    NETWORK_SUCCESS = mem_opt.get_string("NETWORK_SUCCESS")     # 网络连接成功
    NETWORK_FAILED = mem_opt.get_string("NETWORK_FAILED")       # 网络连接失败
    SYSTEM_WARNING = mem_opt.get_string("SYSTEM_WARNING")       # 触发系统警告
    SYSTEM_ERROR = mem_opt.get_string("SYSTEM_ERROR")           # 触发系统错误
    MEMORY_CRITICAL = mem_opt.get_string("MEMORY_CRITICAL")     # 内存严重不足事件
    RECOVERY_SUCCESS = mem_opt.get_string("RECOVERY_SUCCESS")   # 从错误或警告中恢复成功
    RECOVERY_FAILED = mem_opt.get_string("RECOVERY_FAILED")     # 恢复失败
    SYSTEM_SHUTDOWN = mem_opt.get_string("SYSTEM_SHUTDOWN")     # 触发系统关机
    WATCHDOG_TIMEOUT = mem_opt.get_string("WATCHDOG_TIMEOUT")   # 看门狗超时

# =============================================================================
# Section: 状态机核心类
# =============================================================================

class SystemStateMachine:
    """系统状态机的核心控制器。
    
    它管理当前状态、处理事件、执行状态转换，并维护一个状态历史记录。
    采用单例模式，通过模块级的便捷函数进行全局访问。
    """
    
    def __init__(self):
        """初始化状态机实例，设置初始状态和内部数据结构。"""
        self._current_state = SystemState.INIT
        self._previous_state = None
        self._state_start_time = time.ticks_ms()
        self._state_duration = 0
        self._transition_history = []
        self._max_history = 10  # 最多保留最近10条历史记录
        
        # 状态转换表定义了所有合法的状态路径
        self._transition_table = self._build_transition_table()
        
        # 状态处理器将每个状态映射到一个处理函数
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
    
    def _build_transition_table(self):
        """构建状态转换表。
        
        结构为: {当前状态: {触发事件: 目标状态, ...}, ...}
        这是状态机行为规则的核心。
        """
        return {
            SystemState.INIT: { StateEvent.INIT_COMPLETE: SystemState.NETWORKING, StateEvent.SYSTEM_ERROR: SystemState.ERROR, StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE },
            SystemState.NETWORKING: { StateEvent.NETWORK_SUCCESS: SystemState.RUNNING, StateEvent.NETWORK_FAILED: SystemState.WARNING, StateEvent.SYSTEM_ERROR: SystemState.ERROR, StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE },
            SystemState.RUNNING: { StateEvent.SYSTEM_WARNING: SystemState.WARNING, StateEvent.SYSTEM_ERROR: SystemState.ERROR, StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE, StateEvent.NETWORK_FAILED: SystemState.NETWORKING, StateEvent.RECOVERY_SUCCESS: SystemState.RUNNING, StateEvent.WATCHDOG_TIMEOUT: SystemState.RECOVERY },
            SystemState.WARNING: { StateEvent.SYSTEM_ERROR: SystemState.ERROR, StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE, StateEvent.RECOVERY_SUCCESS: SystemState.RUNNING, StateEvent.NETWORK_SUCCESS: SystemState.RUNNING },
            SystemState.ERROR: { StateEvent.RECOVERY_SUCCESS: SystemState.WARNING, StateEvent.RECOVERY_FAILED: SystemState.SAFE_MODE, StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE, StateEvent.SYSTEM_SHUTDOWN: SystemState.SHUTDOWN },
            SystemState.SAFE_MODE: { StateEvent.RECOVERY_SUCCESS: SystemState.WARNING, StateEvent.SYSTEM_SHUTDOWN: SystemState.SHUTDOWN },
            SystemState.RECOVERY: { StateEvent.RECOVERY_SUCCESS: SystemState.RUNNING, StateEvent.RECOVERY_FAILED: SystemState.SAFE_MODE, StateEvent.SYSTEM_ERROR: SystemState.ERROR, StateEvent.MEMORY_CRITICAL: SystemState.SAFE_MODE },
            SystemState.SHUTDOWN: {}  # 终止状态，没有出口
        }
    
    def transition_to(self, new_state, reason=""):
        """执行状态转换的核心函数。
        
        Args:
            new_state (str): 要转换到的目标状态。
            reason (str): 本次转换的原因，用于记录历史。
        Returns:
            bool: 如果状态成功转换则返回 True，否则返回 False。
        """
        if new_state == self._current_state:
            return False
        
        self._record_transition(self._current_state, new_state, reason)
        
        self._previous_state = self._current_state
        self._current_state = new_state
        self._state_start_time = time.ticks_ms()
        
        self._on_state_exit(self._previous_state)
        self._on_state_enter(self._current_state)
        
        return True
    
    def handle_event(self, event, data=None):
        """处理外部事件，这是状态机的主要入口之一。
        
        它会根据当前状态和传入事件，在转换表中查找下一个状态。
        """
        if event in self._transition_table.get(self._current_state, {}):
            new_state = self._transition_table[self._current_state][event]
            if new_state:
                reason = mem_opt.get_string(f"事件: {event}")
                return self.transition_to(new_state, reason)
        return False
    
    def update(self):
        """更新状态机，此方法必须在主循环中被周期性调用。
        
        它负责计算当前状态的持续时间，并执行当前状态的处理器函数，
        从而实现基于时间的逻辑（如超时）。
        它还包含一个顶层异常捕获，防止状态处理器中的错误导致程序崩溃。
        """
        self._state_duration = time.ticks_diff(time.ticks_ms(), self._state_start_time)
        
        handler = self._state_handlers.get(self._current_state)
        if handler:
            try:
                handler()
            except Exception as e:
                # 捕获处理器中的所有异常，打印错误并转换到 ERROR 状态
                print(f"[StateMachine] ERROR: State '{self._current_state}' handler exception: {e}")
                self.handle_event(StateEvent.SYSTEM_ERROR)
    
    def _record_transition(self, from_state, to_state, reason):
        """使用对象池记录一次状态转换历史，用于调试。"""
        transition = mem_opt.get_dict()
        if transition is None:
            # 当对象池耗尽时，打印警告，保证程序继续运行
            print("[StateMachine] WARN: Failed to get dictionary from pool, this history record will be lost.")
            return
            
        transition[mem_opt.get_string('from')] = from_state
        transition[mem_opt.get_string('to')] = to_state
        transition[mem_opt.get_string('reason')] = reason
        transition[mem_opt.get_string('timestamp')] = time.ticks_ms()
        
        self._transition_history.append(transition)
        
        # 如果历史记录超过最大值，则移除最旧的记录并将其归还到对象池
        if len(self._transition_history) > self._max_history:
            old_transition = self._transition_history.pop(0)
            mem_opt.return_dict(old_transition)
    
    def _on_state_enter(self, state):
        """状态进入时的钩子函数，用于执行特定状态的初始化操作。"""
        # 根据状态设置LED显示
        try:
            from lib.sys import led as led_preset
            
            # 获取全局LED控制器实例
            led_controller = None
            if 'led_controller' in globals():
                led_controller = globals()['led_controller']
            
            # 如果全局实例不存在或不可用，创建一个临时实例
            if led_controller is None:
                led_pins = config.get_config('daemon', 'led_pins', [12, 13])
                led_controller = led_preset.LEDPatternController(led_pins)
            
            # 根据状态映射到LED模式
            if state == SystemState.INIT:
                led_controller.play('off')
            elif state == SystemState.NETWORKING:
                led_controller.play('blink')  # 使用闪烁模式表示网络连接中
            elif state == SystemState.RUNNING:
                led_controller.play('cruise')  # 使用巡航模式表示正常运行
            elif state == SystemState.WARNING:
                led_controller.play('blink')  # 使用闪烁模式表示警告状态
            elif state == SystemState.ERROR:
                led_controller.play('blink')  # 使用闪烁模式表示错误状态
            elif state == SystemState.SAFE_MODE:
                led_controller.play('sos')    # 使用SOS模式表示安全模式
                # 进入安全模式是严重事件，执行最高级别的内存清理
                print("[StateMachine] INFO: Entering safe mode, executing emergency memory cleanup...")
                mem_opt.clear_all_pools()
                gc.collect()
            elif state == SystemState.RECOVERY:
                led_controller.play('blink')  # 使用闪烁模式表示恢复模式
            elif state == SystemState.SHUTDOWN:
                led_controller.play('off')    # 关闭LED
        except Exception as e:
            print(f"[StateMachine] ERROR: Failed to set LED status for state {state}: {e}")
    
    def _on_state_exit(self, state):
        """状态退出时的钩子函数，用于执行清理操作。"""
        pass
    
    # --- 状态处理器 ---
    # 以下 `_handle_*` 方法定义了每个状态下需要周期性执行的逻辑。
    
    def _handle_init_state(self): pass
    
    def _handle_networking_state(self):
        """处理网络连接状态，包含一个30秒的超时逻辑。"""
        # 检查状态持续时间，超时则触发网络失败事件
        if self._state_duration > config.get_config('daemon', 'safe_mode_cooldown', 30000): # 从config.py中获取
            self.handle_event(StateEvent.NETWORK_FAILED)
        
        # 检查WiFi连接状态
        try:
            import net_wifi
            wifi_status = net_wifi.get_wifi_status()
            if not wifi_status.get('connected', False):
                self.handle_event(StateEvent.NETWORK_FAILED)
            else:
                # 网络连接成功，尝试MQTT连接
                try:
                    import net_mqtt
                    mqtt_client = net_mqtt.get_client()
                    if mqtt_client and not mqtt_client.is_connected:
                        if mqtt_client.connect():
                            self.handle_event(StateEvent.NETWORK_SUCCESS)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _handle_running_state(self):
        """处理运行状态"""
        # 检查MQTT连接状态
        try:
            import net_mqtt
            mqtt_client = net_mqtt.get_client()
            if mqtt_client and not mqtt_client.is_connected:
                print("[StateMachine] MQTT disconnected in running state, attempting reconnect...")
                if mqtt_client.connect():
                    print("[StateMachine] MQTT reconnection successful")
                else:
                    self.handle_event(StateEvent.NETWORK_FAILED)
        except Exception:
            pass
        
        # 检查系统内存状态
        try:
            from lib import utils
            memory_status = utils.check_memory()
            if memory_status and memory_status['percent'] > 90:
                self.handle_event(StateEvent.MEMORY_CRITICAL)
        except Exception:
            pass
    
    def _handle_warning_state(self):
        """处理警告状态，如果1分钟内没有解决，则尝试自动恢复。"""
        if self._state_duration > config.get_config('daemon', 'safe_mode_cooldown', 60000): # 从config.py中获取
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_error_state(self):
        """处理错误状态，如果30秒内没有解决，则尝试自动恢复。"""
        # 检查状态持续时间，超时则尝试恢复
        if self._state_duration > config.get_config('daemon', 'safe_mode_cooldown', 30000): # 从config.py中获取
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
        
        # 尝试MQTT重连
        try:
            import net_mqtt
            mqtt_client = net_mqtt.get_client()
            if mqtt_client and not mqtt_client.is_connected:
                print("[StateMachine] Attempting MQTT reconnection in error state...")
                if mqtt_client.connect():
                    print("[StateMachine] MQTT reconnection successful in error state")
                    # 如果MQTT重连成功，尝试转换到警告状态
                    self.handle_event(StateEvent.SYSTEM_WARNING)
        except Exception:
            pass
    
    def _handle_safe_mode_state(self):
        """处理安全模式，如果5分钟没有解决，则尝试自动恢复。"""
        if self._state_duration > config.get_config('daemon', 'safe_mode_cooldown', 300000): # 从config.py中获取
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_recovery_state(self):
        """处理恢复模式，1分钟后默认恢复成功（实际应用中应有更复杂的逻辑）。"""
        if self._state_duration > config.get_config('daemon', 'safe_mode_cooldown', 60000): # 从config.py中获取
            self.handle_event(StateEvent.RECOVERY_SUCCESS)
    
    def _handle_shutdown_state(self): pass
    
    # --- Getter 方法 ---
    
    def get_current_state(self):
        """获取当前状态。"""
        return self._current_state
    
    def get_state_info(self):
        """获取当前状态的详细信息字典。"""
        return {
            'current_state': self._current_state,
            'previous_state': self._previous_state,
            'duration_seconds': self._state_duration // 1000
        }
        
    def get_transition_history(self):
        """获取状态转换历史记录列表的副本。"""
        return self._transition_history.copy()

# =============================================================================
# Section: 全局实例与便捷函数
# =============================================================================

# 创建全局唯一的状态机实例 (单例模式)
_state_machine = SystemStateMachine()

# 提供一系列便捷函数，方便应用其他部分调用，无需直接操作实例
def get_state_machine():
    """获取全局状态机实例。"""
    return _state_machine

def get_current_state():
    """便捷函数：获取当前状态。"""
    return _state_machine.get_current_state()

def handle_event(event, data=None):
    """便捷函数：处理状态事件。"""
    return _state_machine.handle_event(event, data)

def update_state_machine():
    """便捷函数：更新状态机。"""
    _state_machine.update()

# =============================================================================
# Section: 模块初始化
# =============================================================================

# 在模块加载结束时执行一次垃圾回收，清理加载过程中产生的临时对象
gc.collect()