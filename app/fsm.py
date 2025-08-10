# app/fsm.py
"""
系统状态机模块 (重构版本)
基于事件驱动的状态机，负责协调所有系统模块

采用事件驱动架构，通过状态转换管理系统的生命周期。
支持错误恢复、资源清理和LED状态同步。
"""

import utime as time
import gc
import machine  # 导入 machine 模块
from event_const import EVENT
from lib.object_pool import ObjectPoolManager
from lib.static_cache import StaticCache
from lib.logger import info, error, warning

class SystemState:
    """系统状态定义"""
    BOOT = "BOOT"
    INIT = "INIT"
    NETWORKING = "NETWORKING"
    RUNNING = "RUNNING"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SAFE_MODE = "SAFE_MODE"
    RECOVERY = "RECOVERY"
    SHUTDOWN = "SHUTDOWN"

class SystemFSM:
    """
    系统状态机
    使用事件驱动架构，协调所有系统模块
    """
    
    def __init__(self, event_bus, object_pool, static_cache, config, 
                 wifi_manager=None, mqtt_controller=None, led_controller=None):
        """
        初始化状态机
        Args:
            event_bus: 事件总线实例
            object_pool: 对象池管理器实例
            static_cache: 静态缓存实例
            config: 配置字典
            wifi_manager: WiFi管理器实例
            mqtt_controller: MQTT控制器实例
            led_controller: LED控制器实例
        """
        self.event_bus = event_bus
        self.object_pool = object_pool
        self.static_cache = static_cache
        self.config = config
        self.wifi_manager = wifi_manager
        self.mqtt_controller = mqtt_controller
        self.led_controller = led_controller
        
        # 状态机变量
        self.current_state = SystemState.BOOT
        self.previous_state = None
        self.state_start_time = time.ticks_ms()
        self.state_duration = 0
        
        # 状态转换表
        self.transition_table = self._build_transition_table()
        
        # 状态处理器
        self.state_handlers = {
            SystemState.BOOT: self._handle_boot_state,
            SystemState.INIT: self._handle_init_state,
            SystemState.NETWORKING: self._handle_networking_state,
            SystemState.RUNNING: self._handle_running_state,
            SystemState.WARNING: self._handle_warning_state,
            SystemState.ERROR: self._handle_error_state,
            SystemState.SAFE_MODE: self._handle_safe_mode_state,
            SystemState.RECOVERY: self._handle_recovery_state,
            SystemState.SHUTDOWN: self._handle_shutdown_state
        }
        
        # 订阅事件
        self._subscribe_events()
        
        # 错误计数
        self.error_count = 0
        self.max_errors = config.get('daemon', {}).get('max_error_count', 10)
        
        # 初始化看门狗
        self.wdt = None
        if self.config.get('daemon', {}).get('wdt_enabled', False):
            wdt_timeout = self.config.get('daemon', {}).get('wdt_timeout', 120000)
            try:
                self.wdt = machine.WDT(timeout=wdt_timeout)
                info("Watchdog enabled with timeout: {} ms", wdt_timeout, module="FSM")
            except Exception as e:
                error("Failed to enable watchdog: {}", e, module="FSM")

        info("System state machine initialized", module="FSM")
    
    def _build_transition_table(self):
        """构建状态转换表"""
        return {
            SystemState.BOOT: {
                EVENT.SYSTEM_BOOT: SystemState.INIT
            },
            SystemState.INIT: {
                EVENT.SYSTEM_INIT: SystemState.NETWORKING,
                EVENT.SYSTEM_ERROR: SystemState.ERROR
            },
            SystemState.NETWORKING: {
                EVENT.WIFI_CONNECTED: SystemState.RUNNING,
                EVENT.WIFI_DISCONNECTED: SystemState.WARNING,
                EVENT.SYSTEM_ERROR: SystemState.ERROR
            },
            SystemState.RUNNING: {
                EVENT.WIFI_DISCONNECTED: SystemState.NETWORKING,
                EVENT.MQTT_DISCONNECTED: SystemState.WARNING,
                EVENT.SYSTEM_WARNING: SystemState.WARNING,
                EVENT.SYSTEM_ERROR: SystemState.ERROR,
                EVENT.MEMORY_CRITICAL: SystemState.SAFE_MODE
            },
            SystemState.WARNING: {
                EVENT.WIFI_CONNECTED: SystemState.RUNNING,
                EVENT.MQTT_CONNECTED: SystemState.RUNNING,
                EVENT.SYSTEM_ERROR: SystemState.ERROR,
                EVENT.MEMORY_CRITICAL: SystemState.SAFE_MODE,
                EVENT.RECOVERY_SUCCESS: SystemState.RUNNING
            },
            SystemState.ERROR: {
                EVENT.RECOVERY_SUCCESS: SystemState.WARNING,
                EVENT.RECOVERY_FAILED: SystemState.SAFE_MODE,
                EVENT.MEMORY_CRITICAL: SystemState.SAFE_MODE,
                EVENT.SYSTEM_SHUTDOWN: SystemState.SHUTDOWN
            },
            SystemState.SAFE_MODE: {
                EVENT.RECOVERY_SUCCESS: SystemState.WARNING,
                EVENT.SYSTEM_SHUTDOWN: SystemState.SHUTDOWN
            },
            SystemState.RECOVERY: {
                EVENT.RECOVERY_SUCCESS: SystemState.RUNNING,
                EVENT.RECOVERY_FAILED: SystemState.SAFE_MODE,
                EVENT.SYSTEM_ERROR: SystemState.ERROR,
                EVENT.MEMORY_CRITICAL: SystemState.SAFE_MODE
            },
            SystemState.SHUTDOWN: {}  # 终止状态
        }
    
    def _subscribe_events(self):
        """订阅事件"""
        events_to_subscribe = [
            EVENT.SYSTEM_BOOT,
            EVENT.SYSTEM_INIT,
            EVENT.SYSTEM_ERROR,
            EVENT.SYSTEM_WARNING,
            EVENT.MEMORY_CRITICAL,
            EVENT.WIFI_CONNECTED,
            EVENT.WIFI_DISCONNECTED,
            EVENT.MQTT_CONNECTED,
            EVENT.MQTT_DISCONNECTED,
            EVENT.RECOVERY_SUCCESS,
            EVENT.RECOVERY_FAILED,
            EVENT.SYSTEM_SHUTDOWN
        ]
        
        for event in events_to_subscribe:
            self.event_bus.subscribe(event, self._handle_event)
    
    def _handle_event(self, event_name, *args, **kwargs):
        """处理事件"""
        if event_name in self.transition_table.get(self.current_state, {}):
            new_state = self.transition_table[self.current_state][event_name]
            if new_state:
                self.transition_to(new_state, f"Event: {event_name}")
    
    def transition_to(self, new_state, reason=""):
        """转换到新状态"""
        if new_state == self.current_state:
            return False
        
        info("State transition: {} -> {} ({})", self.current_state, new_state, reason, module="FSM")
        
        # 退出当前状态
        self._on_state_exit(self.current_state)
        
        # 更新状态
        self.previous_state = self.current_state
        self.current_state = new_state
        self.state_start_time = time.ticks_ms()
        
        # 进入新状态
        self._on_state_enter(new_state)
        
        # 保存状态到缓存
        self.static_cache.set('current_state', new_state)
        self.static_cache.set('last_state_change', time.ticks_ms())
        
        return True
    
    def _on_state_enter(self, state):
        """状态进入处理"""
        # 状态进入日志已在transition_to中记录，避免重复
        
        # 更新LED状态
        if self.led_controller:
            self._update_led_for_state(state)
        
        # 状态特定的进入处理
        if state == SystemState.SAFE_MODE:
            self._on_safe_mode_enter()
        elif state == SystemState.ERROR:
            self._on_error_enter()
        elif state == SystemState.RUNNING:
            # 尝试连接MQTT
            if self.mqtt_controller:
                self.mqtt_controller.connect()
            else:
                info("MQTT controller not available, skipping connection", module="FSM")
        elif state == SystemState.NETWORKING:
            # 如果进入 NETWORKING 时 WiFi 已经处于已连接状态（例如事件先于状态切换触发），
            # 为避免卡在 NETWORKING 状态，这里补发 WIFI_CONNECTED 事件以驱动状态转换。
            try:
                if self.wifi_manager and hasattr(self.wifi_manager, 'is_connected') and self.wifi_manager.is_connected():
                    ip = None
                    ssid = None
                    try:
                        # 尝试从 wlan 和配置中获取基本信息
                        if hasattr(self.wifi_manager, 'wlan') and self.wifi_manager.wlan:
                            cfg = self.wifi_manager.wlan.ifconfig()
                            if cfg and len(cfg) > 0:
                                ip = cfg[0]
                        if getattr(self.wifi_manager, 'target_network', None):
                            ssid = self.wifi_manager.target_network.get('ssid')
                    except Exception:
                        pass
                    info("WiFi already connected when entering NETWORKING, fast-forwarding to RUNNING", module="FSM")
                    # 通过事件驱动转换，保持架构一致性
                    self.event_bus.publish(EVENT.WIFI_CONNECTED, ip=ip, ssid=ssid, module="FSM")
            except Exception as e:
                error("NETWORKING fast-path check failed: {}", e, module="FSM")
    
    def _on_state_exit(self, state):
        """状态退出处理"""
        # 状态退出日志已在transition_to中记录，避免重复
        
        # 状态特定的退出处理
        if state == SystemState.SAFE_MODE:
            self._on_safe_mode_exit()
    
    def _on_safe_mode_enter(self):
        """安全模式进入处理"""
        info("Entering safe mode - performing emergency cleanup", module="FSM")
        
        # 深度垃圾回收
        for _ in range(3):
            gc.collect()
            time.sleep_ms(50)
        
        # 清理对象池
        if hasattr(self.object_pool, 'clear_all_pools'):
            self.object_pool.clear_all_pools()
    
    def _on_safe_mode_exit(self):
        """安全模式退出处理"""
        info("Exiting safe mode", module="FSM")
        self.error_count = 0  # 重置错误计数
    
    def _on_error_enter(self):
        """错误状态进入处理"""
        self.error_count += 1
        info("Error count: {}/{}", self.error_count, self.max_errors, module="FSM")
        
        if self.error_count >= self.max_errors:
            info("Maximum error count reached, entering safe mode", module="FSM")
            self.transition_to(SystemState.SAFE_MODE, "Max errors reached")
    
    def _update_led_for_state(self, state):
        """根据状态更新LED"""
        if not self.led_controller:
            return
        
        led_patterns = {
            SystemState.BOOT: 'off',
            SystemState.INIT: 'blink',
            SystemState.NETWORKING: 'pulse',
            SystemState.RUNNING: 'cruise',
            SystemState.WARNING: 'blink',
            SystemState.ERROR: 'blink',
            SystemState.SAFE_MODE: 'sos',
            SystemState.RECOVERY: 'blink',
            SystemState.SHUTDOWN: 'off'
        }
        
        pattern = led_patterns.get(state, 'off')
        try:
            self.led_controller.play(pattern)
        except Exception as e:
            error("Failed to update LED for state {}: {}", state, e, module="FSM")
    
    def update(self):
        """更新状态机"""
        self.state_duration = time.ticks_diff(time.ticks_ms(), self.state_start_time)
        
        # 驱动依赖模块的循环
        if self.wifi_manager:
            self.wifi_manager.update()
        if self.mqtt_controller:
            self.mqtt_controller.loop()
        if self.led_controller:
            # LED控制器是自驱动的，无需调用update
            pass

        # 执行当前状态处理器
        handler = self.state_handlers.get(self.current_state)
        if handler:
            try:
                handler()
            except Exception as e:
                error("Error in state handler for {}: {}", self.current_state, e, module="FSM")
                self.event_bus.publish(EVENT.SYSTEM_ERROR, str(e))
    
    # 状态处理器
    def _handle_boot_state(self):
        """启动状态处理"""
        # 等待系统启动完成
        if self.state_duration > 1000:  # 1秒后进入初始化
            self.event_bus.publish(EVENT.SYSTEM_BOOT)
    
    def _handle_init_state(self):
        """初始化状态处理"""
        # 初始化各模块
        if self.state_duration > 2000:  # 2秒后开始网络连接
            self.event_bus.publish(EVENT.SYSTEM_INIT)
    
    def _handle_networking_state(self):
        """网络连接状态处理"""
        if not self.wifi_manager:
            error("WiFi manager not available", module="FSM")
            self.transition_to(SystemState.ERROR, "WiFi manager missing")
            return
        
        # 仅驱动WiFi管理器更新，实际的连接/断开事件由 WifiManager 统一发布
        # 避免在此处根据瞬时状态再次发布 WIFI_CONNECTED/WIFI_DISCONNECTED，防止重复事件
        self.wifi_manager.update()
        
        # 周期性打印WiFi状态用于调试
        try:
            wifi_status = getattr(self.wifi_manager, 'status', None)
            now = time.ticks_ms()
            if not hasattr(self, '_last_wifi_status_log'):
                self._last_wifi_status_log = 0
            if time.ticks_diff(now, self._last_wifi_status_log) > 10000:  # 10秒间隔
                if callable(wifi_status):
                    ws = wifi_status()
                else:
                    ws = wifi_status
                # 映射常见状态码
                status_names = {
                    0: "DISCONNECTED",
                    1: "CONNECTING",
                    2: "CONNECTED",
                    3: "ERROR"
                }
                current_status = status_names.get(ws, str(ws))
                info("NETWORKING - WiFi status: {}", current_status, module="FSM")
                # 如果有连接计时，显示连接/尝试时长
                if hasattr(self.wifi_manager, 'connection_start_time'):
                    duration = time.ticks_diff(now, getattr(self.wifi_manager, 'connection_start_time')) // 1000
                    info("NETWORKING - WiFi connecting for {}s", duration, module="FSM")
                self._last_wifi_status_log = now
        except Exception as e:
                error("NETWORKING - WiFi status log error: {}", e, module="FSM")
    
    def _handle_running_state(self):
        """运行状态处理"""
        # 检查系统健康状态
        if self.state_duration % 10000 == 0:  # 每10秒检查一次
            self._check_system_health()
    
    def _handle_warning_state(self):
        """警告状态处理"""
        # 尝试自动恢复
        if self.state_duration > 30000:  # 30秒后尝试恢复
            info("Attempting recovery from warning state", module="FSM")
            self.event_bus.publish(EVENT.RECOVERY_SUCCESS)
    
    def _handle_error_state(self):
        """错误状态处理"""
        # 尝试恢复
        if self.state_duration > 15000:  # 15秒后尝试恢复
            info("Attempting recovery from error state", module="FSM")
            self.event_bus.publish(EVENT.RECOVERY_SUCCESS)
    
    def _handle_safe_mode_state(self):
        """安全模式处理"""
        # 安全模式下的最小化操作
        if self.state_duration % 30000 == 0:  # 每30秒执行一次垃圾回收
            gc.collect()
            info("Safe mode garbage collection", module="FSM")
    
    def _handle_recovery_state(self):
        """恢复状态处理"""
        # 恢复处理
        if self.state_duration > 10000:  # 10秒后恢复完成
            info("Recovery completed", module="FSM")
            self.event_bus.publish(EVENT.RECOVERY_SUCCESS)
    
    def _handle_shutdown_state(self):
        """关机状态处理"""
        pass
    
    def _check_system_health(self):
        """检查系统健康状态"""
        try:
            # 检查内存使用
            import gc
            mem_free = gc.mem_free()
            mem_total = gc.mem_free() + gc.mem_alloc()
            mem_percent = (mem_total - mem_free) / mem_total * 100
            
            memory_threshold = self.config.get('daemon', {}).get('memory_threshold', 80)
            if mem_percent > memory_threshold:
                warning("High memory usage: {:.1f}%", mem_percent, module="FSM")
                self.event_bus.publish(EVENT.SYSTEM_WARNING, f"High memory: {mem_percent:.1f}%")
            
            # 检查温度
            try:
                from utils.helpers import get_temperature
                temp = get_temperature()
                if temp:
                    temp_threshold = self.config.get('daemon', {}).get('temp_threshold', 65)
                    if temp > temp_threshold:
                        warning("High temperature: {}°C", temp, module="FSM")
                        self.event_bus.publish(EVENT.SYSTEM_WARNING, f"High temp: {temp}°C")
            except Exception as e:
                error("Temperature check failed: {}", e, module="FSM")
            
        except Exception as e:
            error("Health check failed: {}", e, module="FSM")
    
    def get_current_state(self):
        """获取当前状态"""
        return self.current_state
    
    def get_state_info(self):
        """获取状态信息"""
        return {
            'current_state': self.current_state,
            'previous_state': self.previous_state,
            'duration_seconds': self.state_duration // 1000,
            'error_count': self.error_count
        }
    
    def force_state(self, state):
        """强制设置状态"""
        info("Forcing state to: {}", state, module="FSM")
        return self.transition_to(state, "Forced by external request")
    
    def run(self):
        """运行状态机主循环"""
        info("Starting state machine main loop", module="FSM")
        try:
            while self.current_state != SystemState.SHUTDOWN:
                # 喂狗
                if self.wdt:
                    self.wdt.feed()

                self.update()
                
                # 获取主循环延迟配置
                main_loop_delay = self.config.get('system', {}).get('main_loop_delay', 300)
                time.sleep_ms(main_loop_delay)
                
                # 更新静态缓存
                if hasattr(self, 'static_cache') and self.static_cache:
                    self.static_cache.loop()
                    
        except KeyboardInterrupt:
            info("State machine stopped by user", module="FSM")
        except Exception as e:
            error("State machine error: {}", e, module="FSM")
            self.event_bus.publish(EVENT.SYSTEM_ERROR, str(e))
        finally:
            info("State machine stopped", module="FSM")

# 全局状态机实例
_fsm_instance = None

def get_fsm():
    """获取全局状态机实例"""
    return _fsm_instance

def create_fsm(event_bus, object_pool, static_cache, config, 
              wifi_manager=None, mqtt_controller=None, led_controller=None):
    """创建全局状态机实例"""
    global _fsm_instance
    _fsm_instance = SystemFSM(event_bus, object_pool, static_cache, config,
                             wifi_manager, mqtt_controller, led_controller)
    return _fsm_instance