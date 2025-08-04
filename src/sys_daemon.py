# -*- coding: utf-8 -*-
"""
守护进程模块

为ESP32C3设备提供系统监控和安全保护功能，整合了高级监控功能：
- LED状态指示
- 温度监控和安全模式
- 看门狗保护
- 内存监控
- 系统状态报告
- 错误处理和恢复
- 智能资源管理

内存优化说明：
- 使用全局变量减少实例化开销
- 限制监控频率和日志大小
- 智能垃圾回收策略
- 简化数据结构
- 避免重复对象创建
"""

import time
import machine
import gc

try:
    import esp32
except ImportError:
    # 模拟esp32模块用于测试
    class MockESP32:
        @staticmethod
        def mcu_temperature():
            return 45.0
    esp32 = MockESP32()

# 全局配置变量
_daemon_config = {
    'led_pins': [12, 13],
    'timer_id': 0,
    'monitor_interval': 5000,
    'temp_threshold': 65,
    'temp_hysteresis': 5,
    'memory_threshold': 80,
    'memory_hysteresis': 10,
    'max_error_count': 10,
    'safe_mode_cooldown': 60000
}

def set_daemon_config(config_dict=None, **kwargs):
    """设置守护进程配置"""
    global _daemon_config
    if config_dict:
        _daemon_config.update(config_dict)
    _daemon_config.update(kwargs)
    print("[Daemon] 守护进程配置已更新")

# =============================================================================
# 全局状态变量（内存优化：使用全局变量而非类实例）
# =============================================================================

# 守护进程状态
_daemon_active = False
_safe_mode_active = False
_safe_mode_start_time = 0
_start_time = 0
_monitor_count = 0

# 错误处理状态
_error_count = 0
_last_error_time = 0

# 硬件对象实例
_timer = None
_led_controller = None
_mqtt_client = None
# 看门狗已移至主循环管理，此处不再需要_wdt变量

# =============================================================================
# LED控制器类
# =============================================================================

class LEDController:
    """LED控制器类 - 负责控制两个LED的状态指示"""
    
    def __init__(self, pin1: int, pin2: int):
        """初始化LED控制器"""
        self.led1 = machine.Pin(pin1, machine.Pin.OUT)
        self.led2 = machine.Pin(pin2, machine.Pin.OUT)
        self.led1.off()
        self.led2.off()
    
    def set_status(self, status: str):
        """设置LED状态"""
        status = status.lower()
        
        if status == 'normal':
            self.led1.on()
            self.led2.off()
        elif status == 'warning':
            self.led1.on()
            self.led2.on()
        elif status == 'error':
            self.led1.off()
            self.led2.on()
        elif status == 'safe_mode':
            self._blink_safe_mode()
        elif status == 'off':
            self.led1.off()
            self.led2.off()
    
    def _blink_safe_mode(self):
        """安全模式LED闪烁"""
        # 移除守护进程状态检查，让LED闪烁独立工作
        # 简化的安全模式LED闪烁逻辑 - 两个LED交替闪烁
        current_time = time.ticks_ms()
        blink_period = 300  # 300ms闪烁周期
        
        # 使用简单的时间戳方法计算闪烁状态
        blink_state = (current_time // blink_period) % 2
        
        if blink_state == 0:
            # 第一个状态：LED1亮，LED2灭
            self.led1.on()
            self.led2.off()
        else:
            # 第二个状态：LED1灭，LED2亮
            self.led1.off()
            self.led2.on()
        
        # 每30次调用打印一次调试信息（约3秒一次）
        if not hasattr(self, '_blink_debug_count'):
            self._blink_debug_count = 0
        self._blink_debug_count += 1
        
        if self._blink_debug_count % 30 == 0:
            print(f"[LED] 安全模式闪烁状态: {blink_state} (LED1: {'开' if blink_state == 0 else '关'}, LED2: {'关' if blink_state == 0 else '开'})")

# =============================================================================
# 系统监控函数
# =============================================================================

def _get_temperature():
    """获取MCU内部温度"""
    try:
        return esp32.mcu_temperature()
    except Exception:
        return None

def _get_memory_usage():
    """获取内存使用情况"""
    try:
        # 每10次监控才执行垃圾回收，优化性能
        if _monitor_count % 10 == 0:
            gc.collect()
        
        alloc = gc.mem_alloc()
        free = gc.mem_free()
        total = alloc + free
        percent = (alloc / total) * 100 if total > 0 else 0
        
        return {
            'alloc': alloc,
            'free': free,
            'total': total,
            'percent': percent
        }
    except Exception:
        return None

def _perform_health_check():
    """执行系统健康检查"""
    health_status = {
        'overall': True,
        'temperature': True,
        'memory': True,
        'errors': True,
        'details': {}
    }
    
    try:
        # 检查温度
        temp = _get_temperature()
        if temp is None:
            health_status['temperature'] = False
            health_status['details']['temperature'] = '读取失败'
        elif temp > 70:  # ESP32C3最高85°C，70°C作为警告线
            health_status['temperature'] = False
            health_status['details']['temperature'] = f'温度过高: {temp:.1f}°C'
        
        # 检查内存
        memory = _get_memory_usage()
        if memory is None:
            health_status['memory'] = False
            health_status['details']['memory'] = '读取失败'
        elif memory['percent'] > 85:
            health_status['memory'] = False
            health_status['details']['memory'] = f'内存使用过高: {memory["percent"]:.1f}%'
        
        # 检查错误计数
        if _error_count > 10:
            health_status['errors'] = False
            health_status['details']['errors'] = f'错误过多: {_error_count}'
        
        # 整体健康状态
        health_status['overall'] = all([
            health_status['temperature'],
            health_status['memory'],
            health_status['errors']
        ])
        
        return health_status
        
    except Exception as e:
        health_status['overall'] = False
        health_status['details']['health_check'] = f'检查失败: {e}'
        return health_status

# =============================================================================
# 安全模式管理
# =============================================================================

def _enter_safe_mode(reason: str):
    """进入安全模式"""
    global _safe_mode_active, _safe_mode_start_time
    
    if not _safe_mode_active:
        _safe_mode_active = True
        _safe_mode_start_time = time.ticks_ms()
        
        # 记录日志
        if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
            try:
                if hasattr(_mqtt_client, 'log'):
                    _mqtt_client.log("CRITICAL", f"进入安全模式: {reason}")
            except Exception:
                pass
        
        # 执行深度垃圾回收
        for _ in range(2):
            gc.collect()
            time.sleep_ms(50)

def _check_safe_mode_recovery():
    """检查是否可以从安全模式恢复"""
    global _safe_mode_active
    
    if not _safe_mode_active:
        return
    
    try:
        # 检查冷却时间
        cooldown_passed = time.ticks_diff(time.ticks_ms(), _safe_mode_start_time) > _daemon_config['safe_mode_cooldown']
        
        if not cooldown_passed:
            return
        
        # 检查温度
        temp = _get_temperature()
        temp_ok = temp is not None and temp < _daemon_config['temp_threshold'] - _daemon_config['temp_hysteresis']
        
        # 检查内存
        memory = _get_memory_usage()
        memory_ok = memory is not None and memory['percent'] < _daemon_config['memory_threshold'] - _daemon_config['memory_hysteresis']
        
        # 检查错误计数
        errors_ok = _error_count < _daemon_config['max_error_count'] // 2
        
        # 如果所有条件都满足，退出安全模式
        if temp_ok and memory_ok and errors_ok:
            _safe_mode_active = False
            
            # 记录日志
            if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
                try:
                    if hasattr(_mqtt_client, 'log'):
                        _mqtt_client.log("INFO", "退出安全模式")
                except Exception:
                    pass
            
            # 执行垃圾回收
            gc.collect()
    
    except Exception:
        pass

# =============================================================================
# 监控回调函数
# =============================================================================

def _monitor_callback(timer):
    """监控定时器回调函数"""
    global _error_count, _last_error_time, _monitor_count
    
    if not _daemon_active:
        return
    
    try:
        _monitor_count += 1
        current_time = time.ticks_ms()
        
        # 任务1：系统健康检查（看门狗喂狗已移至主循环）
        health = _perform_health_check()
        
        # 任务3：根据健康状态决定是否进入安全模式
        if not health['overall']:
            reason = ", ".join([f"{k}: {v}" for k, v in health['details'].items() if v])
            _enter_safe_mode(f"系统异常: {reason}")
        
        # 任务4：错误计数管理
        if _error_count > 0 and time.ticks_diff(current_time, _last_error_time) > 60000:  # 1分钟重置
            _error_count = 0
        
        # 任务5：系统状态记录（每30次监控一次）
        if _monitor_count % 30 == 0:
            _log_system_status()
        
        # 任务6：LED状态控制
        if _safe_mode_active:
            _led_controller.set_status('safe_mode')
            _check_safe_mode_recovery()
        else:
            # 根据健康状态设置LED
            if health['overall']:
                _led_controller.set_status('normal')
            else:
                _led_controller.set_status('warning')
        
        # 定期垃圾回收（每100次监控）
        if _monitor_count % 100 == 0:
            gc.collect()
        
    except Exception as e:
        _error_count += 1
        _last_error_time = time.ticks_ms()
        
        # 发送错误日志
        if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
            try:
                if hasattr(_mqtt_client, 'log'):
                    _mqtt_client.log("ERROR", f"监控错误: {e}")
            except Exception:
                pass

def _log_system_status():
    """记录系统状态"""
    if not _mqtt_client or not hasattr(_mqtt_client, 'is_connected') or not _mqtt_client.is_connected:
        return
    
    try:
        uptime = time.ticks_diff(time.ticks_ms(), _start_time) // 1000
        temp = _get_temperature()
        memory = _get_memory_usage()
        
        # 构建状态消息
        status_parts = [
            f"运行时间:{uptime}s",
            f"温度:{temp:.1f}°C" if temp else "温度:未知",
            f"内存:{memory['percent']:.1f}%" if memory else "内存:未知",
            f"错误:{_error_count}",
            f"安全模式:{'是' if _safe_mode_active else '否'}"
        ]
        
        status_msg = ", ".join(status_parts)
        
        if hasattr(_mqtt_client, 'log'):
            _mqtt_client.log("INFO", f"系统状态: {status_msg}")
        
    except Exception:
        pass

# =============================================================================
# 系统守护进程类
# =============================================================================

class SystemDaemon:
    """系统守护进程类"""
    
    def __init__(self):
        self._initialized = False
    
    def start(self) -> bool:
        """启动守护进程"""
        global _daemon_active, _start_time, _timer, _led_controller
        
        if self._initialized:
            return True
        
        try:
            print("[Daemon] 开始启动守护进程...")
            
            # 初始化硬件
            print(f"[Daemon] 初始化LED控制器，引脚: {_daemon_config['led_pins']}")
            _led_controller = LEDController(
                _daemon_config['led_pins'][0], 
                _daemon_config['led_pins'][1]
            )
            
            # 看门狗已移至主循环管理，守护进程不再负责看门狗
            
            # 初始化定时器
            print(f"[Daemon] 初始化定时器，间隔: {_daemon_config['monitor_interval']}ms")
            _timer = machine.Timer(_daemon_config['timer_id'])
            _timer.init(
                period=_daemon_config['monitor_interval'],
                mode=machine.Timer.PERIODIC,
                callback=_monitor_callback
            )
            
            # 设置状态
            _daemon_active = True
            _start_time = time.ticks_ms()
            self._initialized = True
            
            print("[Daemon] 守护进程启动成功")
            
            # 记录启动日志
            if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
                try:
                    if hasattr(_mqtt_client, 'log'):
                        _mqtt_client.log("INFO", "守护进程启动成功")
                except Exception:
                    pass
            
            return True
            
        except Exception as e:
            # 启动失败时清理资源
            if _timer:
                _timer.deinit()
                _timer = None
            
            # 看门狗已移至主循环管理，守护进程不再负责看门狗
            
            _daemon_active = False
            self._initialized = False
            
            # 记录错误日志
            if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
                try:
                    if hasattr(_mqtt_client, 'log'):
                        _mqtt_client.log("CRITICAL", f"守护进程启动失败: {e}")
                except Exception:
                    pass
            
            return False
    
    def stop(self):
        """停止守护进程"""
        global _daemon_active, _timer
        
        if _timer:
            _timer.deinit()
            _timer = None
        
        _daemon_active = False
        self._initialized = False
        
        if _led_controller:
            _led_controller.set_status('off')
        
        # 记录停止日志
        if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
            try:
                if hasattr(_mqtt_client, 'log'):
                    _mqtt_client.log("INFO", "守护进程已停止")
            except Exception:
                pass
        
        gc.collect()
    
    def get_status(self):
        """获取守护进程状态信息"""
        return {
            'active': _daemon_active,
            'safe_mode': _safe_mode_active,
            'temperature': _get_temperature(),
            'memory': _get_memory_usage(),
            'error_count': _error_count,
            'uptime': time.ticks_diff(time.ticks_ms(), _start_time) // 1000 if _daemon_active else 0,
            'monitor_count': _monitor_count
        }
    
    def force_memory_cleanup(self):
        """强制内存清理"""
        gc.collect()
        time.sleep_ms(100)
        gc.collect()
        return True

# =============================================================================
# 全局守护进程实例和公共接口
# =============================================================================

# 创建全局守护进程实例
_daemon = SystemDaemon()

def set_mqtt_client(mqtt_client):
    """设置MQTT客户端实例"""
    global _mqtt_client
    _mqtt_client = mqtt_client

def start_daemon() -> bool:
    """启动守护进程的公共接口"""
    return _daemon.start()

def stop_daemon():
    """停止守护进程的公共接口"""
    _daemon.stop()

def get_daemon_status():
    """获取守护进程状态的公共接口"""
    return _daemon.get_status()

def is_daemon_active() -> bool:
    """检查守护进程是否活跃"""
    return _daemon_active

def is_safe_mode() -> bool:
    """检查是否处于安全模式"""
    return _safe_mode_active

def get_system_health():
    """获取系统健康状态"""
    return _perform_health_check()

def increment_error_count():
    """增加错误计数"""
    global _error_count, _last_error_time
    _error_count += 1
    _last_error_time = time.ticks_ms()

def reset_error_count():
    """重置错误计数"""
    global _error_count
    _error_count = 0

def force_safe_mode(reason: str = "未知错误"):
    """强制进入安全模式"""
    global _safe_mode_active, _safe_mode_start_time, _led_controller
    
    print(f"[Daemon] 强制进入安全模式: {reason}")
    
    if not _safe_mode_active:
        _safe_mode_active = True
        _safe_mode_start_time = time.ticks_ms()
        
        # 记录日志
        if _mqtt_client and hasattr(_mqtt_client, 'is_connected') and _mqtt_client.is_connected:
            try:
                if hasattr(_mqtt_client, 'log'):
                    _mqtt_client.log("CRITICAL", f"强制进入安全模式: {reason}")
            except Exception:
                pass
        
        # 确保LED控制器已初始化
        if _led_controller is None:
            try:
                print("[Daemon] 初始化LED控制器用于安全模式")
                _led_controller = LEDController(
                    _daemon_config['led_pins'][0], 
                    _daemon_config['led_pins'][1]
                )
            except Exception as e:
                print(f"[Daemon] LED控制器初始化失败: {e}")
                _led_controller = None
        
        # 设置LED为安全模式闪烁
        if _led_controller:
            _led_controller.set_status('safe_mode')
        else:
            print("[Daemon] LED控制器不可用，无法设置安全模式LED")
        
        # 执行深度垃圾回收
        for _ in range(2):
            gc.collect()
            time.sleep_ms(50)
    
    return True

# =============================================================================
# 初始化
# =============================================================================

# 执行垃圾回收
gc.collect()
