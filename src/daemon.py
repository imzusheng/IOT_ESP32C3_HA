# -*- coding: utf-8 -*-
"""
守护进程模块

为ESP32C3设备提供系统监控和安全保护功能：
- LED状态指示（引脚12,13）
- 温度监控和安全模式
- 看门狗保护
- 内存监控
- 系统状态报告
- MQTT日志集成
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

# =============================================================================
# 全局配置常量
# =============================================================================

# LED配置
LED_PIN_1 = 12                    # LED1引脚号（状态指示）
LED_PIN_2 = 13                    # LED2引脚号（警告指示）

# 温度监控配置
TEMP_THRESHOLD = 60.0             # 温度阈值（摄氏度）
# 范围：50-80°C，推荐：60°C
# 影响：超过此值将进入安全模式，防止硬件损坏

# 安全模式配置
SAFE_MODE_COOLDOWN = 30000        # 安全模式冷却时间（毫秒）
# 范围：10-60秒，推荐：30秒
# 影响：在此时间内不会自动退出安全模式，确保系统稳定

# 看门狗配置
WDT_TIMEOUT = 8000                # 看门狗超时时间（毫秒）
# 范围：1000-32000ms，推荐：8000ms
# 影响：超过此时间不喂狗将导致系统重启，防止死锁

# 定时器配置
TIMER_ID = 0                      # 监控定时器编号
# 范围：0-3，推荐：0
# 影响：使用指定的硬件定时器，避免与其他模块冲突

# 监控间隔配置
MONITOR_INTERVAL = 1000 * 30     # 监控间隔（毫秒）
# 范围：1000-60000ms，推荐：30000ms
# 影响：监控频率，间隔越短响应越快但占用更多资源

# 内存监控配置
MEMORY_THRESHOLD = 90             # 内存使用阈值（百分比）
# 范围：70-95%，推荐：90%
# 影响：超过此值将进入安全模式，防止内存耗尽

# 错误处理配置
MAX_ERROR_COUNT = 5              # 最大错误计数
ERROR_RESET_INTERVAL = 60000     # 错误重置间隔（毫秒）
# 范围：30-300秒，推荐：60秒
# 影响：在此时间内错误超过最大值将进入安全模式

# =============================================================================
# 全局状态变量
# =============================================================================

# 守护进程状态
_daemon_active = False            # 守护进程是否活跃
_safe_mode_active = False        # 是否处于安全模式
_safe_mode_start_time = 0        # 安全模式开始时间（毫秒时间戳）
_start_time = 0                  # 守护进程启动时间（毫秒时间戳）
_monitor_count = 0               # 监控次数计数器

# 错误处理状态
_error_count = 0                  # 错误计数器
_last_error_time = 0             # 最后一次错误时间（毫秒时间戳）

# 硬件对象实例
_wdt = None                      # 看门狗实例
_timer = None                    # 监控定时器实例
_led_controller = None           # LED控制器实例
_mqtt_client = None              # MQTT客户端实例

# =============================================================================
# LED控制器类
# =============================================================================

class LEDController:
    """
    LED控制器类
    
    负责控制两个LED的状态指示：
    - LED1（引脚12）：主要状态指示
    - LED2（引脚13）：辅助状态指示
    
    状态说明：
    - normal: LED1亮，LED2灭（正常运行）
    - warning: LED1亮，LED2亮（警告状态）
    - error: LED1灭，LED2亮（错误状态）
    - safe_mode: 交替闪烁（安全模式）
    - off: 全部关闭（关闭状态）
    """
    
    def __init__(self, pin1, pin2):
        """
        初始化LED控制器
        
        Args:
            pin1 (int): LED1引脚号
            pin2 (int): LED2引脚号
        """
        self.led1 = machine.Pin(pin1, machine.Pin.OUT)
        self.led2 = machine.Pin(pin2, machine.Pin.OUT)
        self.led1.off()
        self.led2.off()
    
    def set_status(self, status):
        """
        设置LED状态
        
        Args:
            status (str): 状态类型 ('normal', 'warning', 'error', 'safe_mode', 'off')
            
        Raises:
            ValueError: 当状态参数无效时
        """
        valid_statuses = ['normal', 'warning', 'error', 'safe_mode', 'off']
        if status not in valid_statuses:
            raise ValueError(f"无效的LED状态: {status}. 有效状态: {valid_statuses}")
        
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
            self._blink_alternating()
        elif status == 'off':
            self.led1.off()
            self.led2.off()
    
    def _blink_alternating(self):
        """
        交替闪烁LED（安全模式专用）
        
        使用全局_safe_mode_start_time计算闪烁相位，确保两个LED交替闪烁
        闪烁周期：500ms（250ms亮，250ms灭）
        """
        global _safe_mode_start_time
        current_time = time.ticks_ms()
        cycle_time = 500  # 500ms周期
        position = (current_time - _safe_mode_start_time) % cycle_time
        
        if position < cycle_time // 2:
            self.led1.on()
            self.led2.off()
        else:
            self.led1.off()
            self.led2.on()

# =============================================================================
# 系统监控函数
# =============================================================================

def _get_temperature():
    """
    获取MCU内部温度
    
    Returns:
        float: 温度值（摄氏度），失败时返回None
        
    注意：
        - ESP32C3内部温度传感器精度约为±2°C
        - 温度读取可能失败，需要异常处理
        - 正常工作温度范围：-40°C到85°C
    """
    try:
        return esp32.mcu_temperature()
    except:
        return None

def _get_memory_usage():
    """
    获取内存使用情况
    
    Returns:
        dict: 包含内存信息的字典 {
            'alloc': 已分配内存字节数,
            'free': 可用内存字节数,
            'total': 总内存字节数,
            'percent': 内存使用百分比
        }，失败时返回None
            
    注意：
        - ESP32C3通常有400KB SRAM
        - 内存使用超过90%时应进入安全模式
        - 每10次调用才执行垃圾回收，优化性能
    """
    try:
        # 全局变量用于跟踪垃圾回收计数
        global _monitor_count
        
        # 每10次调用才执行垃圾回收，优化性能
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
    except:
        return None

# =============================================================================
# 安全模式管理
# =============================================================================

def _enter_safe_mode(reason):
    """
    进入紧急安全模式
    
    当检测到系统异常时，进入安全模式并记录日志
    
    Args:
        reason (str): 进入安全模式的原因
        
    全局变量影响：
        - _safe_mode_active: 设置为True
        - _safe_mode_start_time: 记录当前时间戳
        
    注意：
        - 只有当前不处于安全模式时才会执行
        - 进入安全模式会发送MQTT日志
        - 安全模式下LED将交替闪烁
    """
    global _safe_mode_active, _safe_mode_start_time
    
    if not _safe_mode_active:
        _safe_mode_active = True
        _safe_mode_start_time = time.ticks_ms()
        
        # 发送MQTT日志
        if _mqtt_client and _mqtt_client.is_connected:
            _mqtt_client.log("CRITICAL", f"进入安全模式: {reason}")
        
        # 执行垃圾回收
        gc.collect()

def _check_safe_mode_recovery():
    """
    检查是否可以从安全模式恢复
    
    恢复条件：
    1. 温度降低到阈值以下10°C
    2. 安全模式持续时间超过冷却时间
    
    全局变量影响：
        - _safe_mode_active: 满足条件时设置为False
        
    注意：
        - 只有当前处于安全模式时才会检查
        - 恢复时会发送MQTT日志
        - 温度传感器读取失败时不会退出安全模式
    """
    global _safe_mode_active
    
    if _safe_mode_active:
        temp = _get_temperature()
        cooldown_passed = time.ticks_diff(time.ticks_ms(), _safe_mode_start_time) > SAFE_MODE_COOLDOWN
        
        # 只有温度读取成功且低于阈值时才考虑退出安全模式
        if temp is not None and temp < TEMP_THRESHOLD - 10 and cooldown_passed:
            _safe_mode_active = False
            
            # 发送MQTT日志
            if _mqtt_client and _mqtt_client.is_connected:
                _mqtt_client.log("INFO", "退出安全模式")
            
            # 执行垃圾回收
            gc.collect()

# =============================================================================
# 监控回调函数
# =============================================================================

def _monitor_callback(timer):
    """
    监控定时器回调函数
    
    这是守护进程的核心函数，定期执行以下任务：
    1. 喂狗（防止系统重启）
    2. 温度监控
    3. 内存监控
    4. 错误计数管理
    5. 系统状态记录
    6. LED状态控制
    7. 安全模式管理
    
    Args:
        timer: 定时器对象
        
    全局变量影响：
        - _monitor_count: 每次调用递增
        - _error_count: 错误时递增
        - _last_error_time: 错误时更新
        
    注意：
        - 只有守护进程活跃时才会执行
        - 包含异常处理，错误不会中断监控
        - 每30次监控记录一次系统状态
    """
    global _error_count, _last_error_time, _monitor_count
    
    if not _daemon_active:
        return
    
    try:
        _monitor_count += 1
        current_time = time.ticks_ms()
        
        # 任务1：喂狗（最高优先级）
        if _wdt:
            _wdt.feed()
        
        # 任务2：温度监控
        temp = _get_temperature()
        if temp and temp >= TEMP_THRESHOLD:
            _enter_safe_mode(f"温度过高: {temp:.1f}°C")
        
        # 任务3：内存监控
        memory = _get_memory_usage()
        if memory and memory['percent'] > MEMORY_THRESHOLD:
            _enter_safe_mode(f"内存使用过高: {memory['percent']:.1f}%")
        
        # 任务4：错误计数管理
        if _error_count > MAX_ERROR_COUNT and time.ticks_diff(current_time, _last_error_time) < ERROR_RESET_INTERVAL:
            _enter_safe_mode(f"错误过多: {_error_count}")
        
        # 任务5：系统状态记录（每30次监控一次）
        if _monitor_count % 30 == 0:
            _log_system_status(temp, memory)
        
        # 任务6：LED状态控制
        if _safe_mode_active:
            _led_controller.set_status('safe_mode')
            _check_safe_mode_recovery()
        else:
            # 根据系统状态设置LED
            if temp and temp > TEMP_THRESHOLD - 10:
                _led_controller.set_status('warning')
            elif memory and memory['percent'] > MEMORY_THRESHOLD - 10:
                _led_controller.set_status('warning')
            else:
                _led_controller.set_status('normal')
        
        # 定期垃圾回收（每100次监控）
        if _monitor_count % 100 == 0:
            gc.collect()
        
    except Exception as e:
        _error_count += 1
        _last_error_time = time.ticks_ms()
        
        # 发送错误日志到MQTT
        if _mqtt_client and _mqtt_client.is_connected:
            _mqtt_client.log("ERROR", f"监控错误: {e}")

def _log_system_status(temp, memory):
    """
    记录系统状态到MQTT
    
    Args:
        temp (float): 温度值
        memory (dict): 内存信息字典
        
    注意：
        - 只在MQTT连接时发送日志
        - 使用固定格式便于解析
        - 包含运行时间、温度、内存、错误计数等信息
        - 使用bytearray优化内存使用
    """
    if not _mqtt_client or not _mqtt_client.is_connected:
        return
    
    try:
        uptime = time.ticks_diff(time.ticks_ms(), _start_time) // 1000
        temp_str = f"{temp:.1f}°C" if temp else "未知"
        
        if memory:
            mem_str = f"{memory['percent']:.1f}% ({memory['free']//1024}KB空闲)"
        else:
            mem_str = "未知"
        
        # 使用bytearray优化内存使用，减少字符串拼接
        msg_parts = [
            "运行时间: ", str(uptime), "s, 温度: ", temp_str, 
            ", 内存: ", mem_str, ", 错误: ", str(_error_count)
        ]
        
        # 直接拼接为字符串发送
        status_msg = "".join(msg_parts)
        _mqtt_client.log("INFO", status_msg)
        
    except Exception as e:
        # 日志发送失败时不影响主流程
        pass

# =============================================================================
# 系统守护进程类
# =============================================================================

class SystemDaemon:
    """
    系统守护进程类
    
    负责管理和协调所有守护进程功能：
    - 硬件初始化（LED、看门狗、定时器）
    - 监控任务调度
    - 状态管理
    - 资源清理
    """
    
    def __init__(self):
        """
        初始化守护进程实例
        
        属性：
            _initialized (bool): 是否已初始化
        """
        self._initialized = False
    
    def start(self):
        """
        启动守护进程
        
        Returns:
            bool: 启动是否成功
            
        全局变量影响：
            _daemon_active: 设置为True
            _start_time: 记录启动时间
            _wdt: 创建看门狗实例
            _timer: 创建定时器实例
            _led_controller: 创建LED控制器实例
            
        注意：
            - 如果已经启动则直接返回True
            - 初始化失败时会进行资源清理
            - 启动成功后会发送MQTT日志
        """
        global _daemon_active, _start_time, _wdt, _timer, _led_controller
        
        if self._initialized:
            return True
        
        try:
            # 初始化硬件
            _led_controller = LEDController(LED_PIN_1, LED_PIN_2)
            _wdt = machine.WDT(timeout=WDT_TIMEOUT)
            _timer = machine.Timer(TIMER_ID)
            _timer.init(period=MONITOR_INTERVAL, mode=machine.Timer.PERIODIC, callback=_monitor_callback)
            
            # 设置状态
            _daemon_active = True
            _start_time = time.ticks_ms()
            self._initialized = True
            
            # 发送启动日志
            if _mqtt_client and _mqtt_client.is_connected:
                _mqtt_client.log("INFO", "守护进程启动成功")
            
            return True
            
        except Exception as e:
            # 启动失败时清理资源
            if _timer:
                _timer.deinit()
                _timer = None
            if _wdt:
                try:
                    _wdt.deinit()
                except Exception as e:
                    # 看门狗清理失败，记录错误但继续清理
                    if _mqtt_client and _mqtt_client.is_connected:
                        _mqtt_client.log("ERROR", f"看门狗清理失败: {e}")
                _wdt = None
            
            _daemon_active = False
            self._initialized = False
            
            # 发送错误日志
            if _mqtt_client and _mqtt_client.is_connected:
                _mqtt_client.log("CRITICAL", f"守护进程启动失败: {e}")
            
            return False
    
    def stop(self):
        """
        停止守护进程
        
        全局变量影响：
            _daemon_active: 设置为False
            _timer: 停止并释放定时器
            
        注意：
            - 看门狗保持运行以保护系统
            - LED会关闭
            - 发送停止日志到MQTT
        """
        global _daemon_active, _timer
        
        if _timer:
            _timer.deinit()
            _timer = None
        
        _daemon_active = False
        self._initialized = False
        
        if _led_controller:
            _led_controller.set_status('off')
        
        # 发送停止日志
        if _mqtt_client and _mqtt_client.is_connected:
            _mqtt_client.log("INFO", "守护进程已停止")
        
        # 执行垃圾回收
        gc.collect()
    
    def get_status(self):
        """
        获取守护进程状态信息
        
        Returns:
            dict: 状态信息字典 {
                'active': 是否活跃,
                'safe_mode': 是否安全模式,
                'temperature': 当前温度,
                'memory': 内存信息,
                'error_count': 错误计数,
                'uptime': 运行时间（秒）
            }
        """
        return {
            'active': _daemon_active,
            'safe_mode': _safe_mode_active,
            'temperature': _get_temperature(),
            'memory': _get_memory_usage(),
            'error_count': _error_count,
            'uptime': time.ticks_diff(time.ticks_ms(), _start_time) // 1000 if _daemon_active else 0
        }

# =============================================================================
# 全局守护进程实例和公共接口
# =============================================================================

# 创建全局守护进程实例
_daemon = SystemDaemon()

def set_mqtt_client(mqtt_client):
    """
    设置MQTT客户端实例
    
    Args:
        mqtt_client: MQTT客户端实例，必须有is_connected属性和log方法
        
    注意：
        - 必须在启动守护进程前调用
        - 用于发送守护进程日志到MQTT服务器
    """
    global _mqtt_client
    _mqtt_client = mqtt_client

def start_daemon():
    """
    启动守护进程的公共接口
    
    Returns:
        bool: 启动是否成功
        
    注意：
        - 这是主要的启动接口
        - 在main.py中调用
    """
    return _daemon.start()

def stop_daemon():
    """
    停止守护进程的公共接口
    
    注意：
        - 停止守护进程但保持看门狗运行
        - 主要用于系统维护
    """
    _daemon.stop()

def get_daemon_status():
    """
    获取守护进程状态的公共接口
    
    Returns:
        dict: 状态信息字典
        
    注意：
        - 用于监控系统状态
        - 在main.py中定期调用
    """
    return _daemon.get_status()

def is_daemon_active():
    """
    检查守护进程是否活跃
    
    Returns:
        bool: 是否活跃
        
    注意：
        - 快速检查守护进程状态
        - 直接检查全局变量避免竞态条件
    """
    return _daemon_active

def is_safe_mode():
    """
    检查是否处于安全模式
    
    Returns:
        bool: 是否安全模式
        
    注意：
        - 用于安全模式判断
        - 在main.py中用于暂停正常操作
        - 直接检查全局变量避免竞态条件
    """
    return _safe_mode_active