# app/fsm/core.py
"""
状态机核心实现
简化状态模型为 5 个核心状态(BOOT/INIT/CONNECTING/RUNNING/ERROR), 移除独立的 NetworkFSM 冗余

职责：
- 订阅网络/系统关键事件(WIFI_STATE_CHANGE、MQTT_STATE_CHANGE、SYSTEM_STATE_CHANGE)
- 驱动系统从启动到运行的状态演进, 并在异常时进入 ERROR 并执行重试/重启策略
- 统一控制 LED 指示与看门狗喂狗

状态与转换：
- BOOT -> INIT -> CONNECTING -> RUNNING
- 运行中发生断链则回到 CONNECTING；长时间连接失败进入 ERROR；超过最大错误次数重启

设计边界：
- 具体网络连接流程委托给 NetworkManager
- 退避/重试策略可后续在 FSM 或 NetworkManager 层统一引入
"""

import utime as time
import machine
import gc
from lib.logger import info, warning, error, debug
from lib.lock.event_bus import EVENTS

# 状态常量定义
STATE_INIT = 0  # 系统启动、初始化
STATE_CONNECTING = 1  # 网络连接中
STATE_RUNNING = 2  # 正常运行
STATE_ERROR = 3  # 错误状态

STATE_NAMES = {
    STATE_INIT: "INIT",
    STATE_CONNECTING: "CONNECTING",
    STATE_RUNNING: "RUNNING", 
    STATE_ERROR: "ERROR"
}

# 状态转换表
STATE_TRANSITIONS = {
    STATE_INIT: {"connecting": STATE_CONNECTING, "timeout": STATE_ERROR, "error": STATE_ERROR},
    STATE_CONNECTING: {"connected": STATE_RUNNING, "timeout": STATE_ERROR, "error": STATE_ERROR},
    STATE_RUNNING: {"disconnected": STATE_CONNECTING, "error": STATE_ERROR},
    STATE_ERROR: {"retry": STATE_INIT}
}


class FSM:
    """
    状态机类
    合并原有的FunctionalStateMachine功能, 消除冗余
    """
    
    def __init__(self, event_bus, config, network_manager=None):
        """初始化状态机"""
        self.event_bus = event_bus
        self.config = config
        self.network_manager = network_manager
        
        # 状态数据
        self.current_state = STATE_INIT
        self.state_start_time = time.ticks_ms()
        self.error_count = 0
        self.max_errors = config.get("daemon", {}).get("max_error_count", 5)
        
        # 看门狗
        self.wdt = None
        self._init_watchdog()
        
        # 订阅事件
        self._subscribe_events()
        
        # 进入初始状态
        self._enter_state(STATE_INIT)
        
    def _init_watchdog(self):
        """初始化看门狗"""
        try:
            wdt_config = self.config.get("daemon", {}).get("watchdog", {})
            if wdt_config.get("enabled", True):
                timeout = wdt_config.get("timeout", 120000)
                self.wdt = machine.WDT(timeout=timeout)
                debug("看门狗已启用, 超时时间: {} ms", timeout, module="FSM")
        except Exception as e:
            error("启用看门狗失败: {}", e, module="FSM")
            
    def _subscribe_events(self):
        """订阅必要的事件"""
        events_to_subscribe = [
            EVENTS["WIFI_STATE_CHANGE"],
            EVENTS["MQTT_STATE_CHANGE"], 
            EVENTS["SYSTEM_STATE_CHANGE"]
        ]
        
        for event in events_to_subscribe:
            self.event_bus.subscribe(event, self._handle_event)
            debug("状态机订阅事件: {}", event, module="FSM")
            
    def _enter_state(self, new_state):
        """进入新状态"""
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = time.ticks_ms()
        
        debug("状态转换: {} -> {}", 
             STATE_NAMES.get(old_state, "UNKNOWN"),
             STATE_NAMES.get(new_state, "UNKNOWN"), 
             module="FSM")
             
        # 执行状态进入逻辑
        self._handle_state_enter(new_state)
        
        # 更新LED状态
        self._update_led()
        
    def _handle_state_enter(self, state):
        """处理状态进入逻辑"""
        if state == STATE_INIT:
            debug("系统启动、初始化并连接网络中...", module="FSM")
            self._init_and_connect_system()
            
        elif state == STATE_RUNNING:
            info("进入 RUNNING 状态", module="FSM")
            self.error_count = 0  # 重置错误计数
            
        elif state == STATE_ERROR:
            info("系统错误状态", module="FSM")
            self.error_count += 1
            
        elif state == STATE_CONNECTING:
            # 进入重连流程
            info("开始网络连接流程", module="FSM")
            try:
                if self.network_manager:
                    self.network_manager.connect()
                else:
                    error("网络管理器不可用", module="FSM")
                    self._transition_to_error()
            except Exception as e:
                error("启动网络连接流程失败: {}", e, module="FSM")
                self._transition_to_error()
            
    def _init_and_connect_system(self):
        """初始化系统并启动网络连接"""
        try:
            # 执行基本的系统初始化
            debug("执行系统初始化任务", module="FSM")
            
            # 启动网络连接
            if not self.network_manager:
                error("网络管理器不可用", module="FSM")
                self._transition_to_error()
                return
                
            # 直接调用网络管理器的连接方法
            success = self.network_manager.connect()
            if not success:
                warning("网络连接启动失败", module="FSM")
                
        except Exception as e:
            error("系统初始化和网络连接失败: {}", e, module="FSM")
            self._transition_to_error()
            
    def _transition_to_error(self):
        """转换到错误状态"""
        if self.error_count >= self.max_errors:
            error("达到最大错误次数, 系统将重启", module="FSM")
            machine.reset()
        else:
            self._enter_state(STATE_ERROR)
            
    def _update_led(self):
        """更新LED状态"""
        try:
            from hw.led import play
            
            # 与当前简化状态模型对齐：INIT/CONNECTING/RUNNING/ERROR
            led_modes = {
                # STATE_BOOT removed as it's no longer part of the model
                STATE_INIT: "blink",
                STATE_CONNECTING: "pulse",
                STATE_RUNNING: "cruise",
                STATE_ERROR: "blink",
            }
            
            mode = led_modes.get(self.current_state, "off")
            play(mode)
            
        except Exception as e:
            error("更新LED状态失败: {}", e, module="FSM")
            
    def _handle_event(self, event_name, *args, **kwargs):
        """处理事件"""
        try:
            # 处理网络相关事件
            if event_name == EVENTS["WIFI_STATE_CHANGE"]:
                self._handle_wifi_event(*args, **kwargs)
            elif event_name == EVENTS["MQTT_STATE_CHANGE"]:
                self._handle_mqtt_event(*args, **kwargs)
            elif event_name == EVENTS["SYSTEM_STATE_CHANGE"]:
                self._handle_system_event(*args, **kwargs)
                
        except Exception as e:
            error("处理事件 {} 时发生错误: {}", event_name, e, module="FSM")
            
    def _handle_wifi_event(self, *args, **kwargs):
        """处理WiFi事件"""
        state = kwargs.get('state', 'unknown')
        
        if state == 'connected' and self.current_state == STATE_INIT:
            # WiFi连接成功, 检查是否完全连接
            info("WiFi连接成功", module="FSM")
            if self.network_manager and self.network_manager.is_connected():
                self._enter_state(STATE_RUNNING)
            
        elif state == 'disconnected' and self.current_state == STATE_RUNNING:
            # WiFi断开, 需要重新连接
            warning("WiFi连接断开, 重新连接", module="FSM")
            self._enter_state(STATE_INIT)
        
        # 连接阶段发生断开/失败: 不改变状态机策略, 但让LED进入SOS提示
        elif state == 'disconnected' and self.current_state in (STATE_INIT, STATE_CONNECTING):
            try:
                from hw.led import play
                play('sos')
                debug("WiFi断开于连接阶段: LED进入SOS模式", module="FSM")
            except Exception:
                pass
            
    def _handle_mqtt_event(self, *args, **kwargs):
        """处理MQTT事件"""
        state = kwargs.get('state', 'unknown')
        
        if state == 'connected' and self.current_state == STATE_INIT:
            # MQTT连接成功, 检查是否完全连接
            info("MQTT连接成功", module="FSM")
            if self.network_manager and self.network_manager.is_connected():
                self._enter_state(STATE_RUNNING)
            
        elif state == 'disconnected' and self.current_state == STATE_RUNNING:
            # MQTT断开, 重新连接
            warning("MQTT连接断开, 重新连接", module="FSM")
            self._enter_state(STATE_INIT)
        
        # 连接阶段发生断开/失败: 不改变状态机策略, 但让LED进入SOS提示
        elif state == 'disconnected' and self.current_state in (STATE_INIT, STATE_CONNECTING):
            try:
                from hw.led import play
                play('sos')
                debug("MQTT断开于连接阶段: LED进入SOS模式", module="FSM")
            except Exception:
                pass
            
    def _handle_system_event(self, *args, **kwargs):
        """处理系统事件"""
        state = kwargs.get('state', 'unknown')
        
        if state == 'running' and self.current_state == STATE_INIT:
            # 系统报告运行状态
            self._enter_state(STATE_RUNNING)
            
    def update(self):
        """状态机主循环更新"""
        try:
            current_time = time.ticks_ms()
            elapsed = time.ticks_diff(current_time, self.state_start_time)
            
            # 根据当前状态执行相应逻辑
            if self.current_state == STATE_INIT:
                # INIT状态：检查网络连接状态
                if self.network_manager and self.network_manager.is_connected():
                    self._enter_state(STATE_RUNNING)
                else:
                    # 取消全局60秒超时切换到ERROR, 以避免与NET内部退避/重试策略冲突
                    # 保持在 INIT, 等待 NetworkManager 自行管理重连与退避
                    pass
                
            elif self.current_state == STATE_RUNNING:
                # 运行状态的定期检查
                self._check_system_health()
                
            elif self.current_state == STATE_ERROR:
                if elapsed >= 10000:  # 10秒后重试
                    info("错误状态超时({} ms), 尝试重新连接", elapsed, module="FSM")
                    self._enter_state(STATE_CONNECTING)
                    
            elif self.current_state == STATE_CONNECTING:
                # 取消全局60秒超时切换到ERROR, 以避免与NET内部退避/重试策略冲突
                # 保持在 CONNECTING, 由 NetworkManager 的 WiFi/MQTT 模块(各自10s超时)配合退避驱动连接流程
                pass
                    
        except Exception as e:
            error("状态机更新失败: {}", e, module="FSM")
            
    def _check_system_health(self):
        """检查系统健康状态"""
        try:
            # 检查网络连接状态
            if self.network_manager and hasattr(self.network_manager, 'is_connected'):
                if not self.network_manager.is_connected():
                    warning("网络连接丢失", module="FSM")
                    self._enter_state(STATE_CONNECTING)
                    return
                    
            # 温度监控
            self._check_temperature()
                    
            # 定期垃圾回收
            current_time = time.ticks_ms()
            if not hasattr(self, '_last_gc_time'):
                self._last_gc_time = current_time
                
            if time.ticks_diff(current_time, self._last_gc_time) >= 30000:  # 30秒
                gc.collect()
                self._last_gc_time = current_time
                
        except Exception as e:
            error("系统健康检查失败: {}", e, module="FSM")
            
    def _check_temperature(self):
        """检查温度状态"""
        try:
            # 检查是否启用温度监控
            if not self.config.get("system", {}).get("temperature_monitoring_enabled", True):
                return
                
            current_time = time.ticks_ms()
            
            # 初始化温度检查时间
            if not hasattr(self, '_last_temp_check_time'):
                self._last_temp_check_time = current_time
                
            # 获取温度检查间隔
            temp_check_interval = self.config.get("system", {}).get("temperature_check_interval", 30000)
            
            # 检查是否到了温度检查时间
            if time.ticks_diff(current_time, self._last_temp_check_time) >= temp_check_interval:
                self._last_temp_check_time = current_time
                
                # 读取SHT40温度
                temp_data = self._read_sht40_temperature()
                
                if temp_data and temp_data.get("temperature") is not None:
                    temp = temp_data["temperature"]
                    
                    # 获取温度阈值配置
                    temp_threshold = self.config.get("system", {}).get("temperature_threshold", 50.0)
                    
                    # 温度状态检查
                    if temp >= temp_threshold:
                        # 超过阈值, 进入安全模式
                        error("温度超过阈值: {}°C >= {}°C, 进入安全模式", temp, temp_threshold, module="FSM")
                        self._handle_temperature_critical(temp)
                    elif hasattr(self, '_temperature_state') and self._temperature_state == 'critical':
                        # 从高温状态恢复
                        if temp < temp_threshold:
                            info("温度已恢复正常: {}°C < {}°C", temp, temp_threshold, module="FSM")
                            self._handle_temperature_recovery(temp)
                    
                    # 发布温度数据事件
                    self._publish_temperature_event(temp, temp_data.get("humidity"))
                    
        except Exception as e:
            error("温度检查失败: {}", e, module="FSM")
            
    def _read_sht40_temperature(self):
        """读取SHT40温度传感器数据"""
        try:
            from hw.sht40 import read
            
            # 读取温度数据（使用中等精度以平衡速度和准确性）
            temp_data = read("med")
            
            if temp_data and temp_data.get("temperature") is not None:
                debug("SHT40温度读取成功: {}°C, 湿度:{}%", 
                      temp_data["temperature"], temp_data["humidity"], module="FSM")
                return temp_data
            else:
                warning("SHT40温度读取失败", module="FSM")
                return None
                
        except Exception as e:
            error("SHT40温度读取异常: {}", e, module="FSM")
            return None
            
    def _handle_temperature_critical(self, temperature):
        """处理危险温度情况"""
        try:
            # 设置温度状态
            self._temperature_state = 'critical'
            
            # 进入错误状态
            if self.current_state != STATE_ERROR:
                self._enter_state(STATE_ERROR)
                
            # LED显示警告模式
            try:
                from hw.led import play
                play('sos')  # SOS模式表示紧急情况
            except Exception:
                pass
                
            # 发布温度危险事件
            self.event_bus.publish(
                EVENTS["SYSTEM_ERROR"],
                error_type="temperature_critical",
                error_info=f"温度超过危险阈值: {temperature}°C"
            )
            
        except Exception as e:
            error("处理危险温度失败: {}", e, module="FSM")
            
    def _handle_temperature_recovery(self, temperature):
        """处理温度恢复情况"""
        try:
            # 恢复温度状态
            self._temperature_state = 'normal'
            
            # 如果当前在错误状态, 尝试恢复
            if self.current_state == STATE_ERROR:
                info("温度恢复正常, 尝试恢复系统状态", module="FSM")
                self._enter_state(STATE_INIT)  # 重新初始化系统
                
        except Exception as e:
            error("处理温度恢复失败: {}", e, module="FSM")
            
    def _publish_temperature_event(self, temperature, humidity):
        """发布温度数据事件"""
        try:
            # 发布传感器数据事件
            self.event_bus.publish(
                EVENTS["SENSOR_DATA"],
                sensor_id="sht40",
                temperature=temperature,
                humidity=humidity
            )
            
        except Exception as e:
            error("发布温度事件失败: {}", e, module="FSM")
            
    def get_current_state(self):
        """获取当前状态名称"""
        return STATE_NAMES.get(self.current_state, "UNKNOWN")
        
    def feed_watchdog(self):
        """喂看门狗"""
        try:
            if self.wdt:
                self.wdt.feed()
        except Exception as e:
            error("喂看门狗失败: {}", e, module="FSM")
            
    def force_state(self, state_name):
        """强制设置状态"""
        state_map = {v: k for k, v in STATE_NAMES.items()}
        if state_name in state_map:
            debug("强制设置状态为: {}", state_name, module="FSM")
            self._enter_state(state_map[state_name])
        else:
            error("未知的状态名称: {}", state_name, module="FSM")