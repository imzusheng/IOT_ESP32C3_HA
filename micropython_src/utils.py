# utils.py
"""
实用工具模块 - WiFi连接、NTP时间同步、LED控制 (重构版本)

这个模块提供了系统的核心功能，重构后具有以下特点：
1. 配置驱动：所有配置通过config模块获取
2. 事件驱动：通过事件总线发布状态变化和接收控制命令
3. 模块化设计：每个功能独立，减少耦合
4. 错误隔离：单个功能失败不影响其他功能

主要功能：
- WiFi连接管理：自动连接、重连、状态监控
- NTP时间同步：定期同步、时区处理
- LED硬件控制：PWM控制、多种灯效
- 系统状态查询：网络、时间、硬件状态
"""
import network
import time
import ntptime
import machine
import esp32
import uasyncio as asyncio
import config
import event_bus

# === 配置获取 (从config模块) ===
_wifi_config = config.get_wifi_config()
_ntp_config = config.get_ntp_config()
_led_config = config.get_led_config()

# --- WiFi & NTP 配置常量 (向后兼容) ---
# WiFi连接超时时间配置
# 作用：单次WiFi连接尝试的最大等待时间，超过此时间将放弃当前连接尝试
# 推荐值：10-30秒，根据网络环境调整
# 注意：过短可能导致连接失败，过长会延长启动时间
WIFI_CONNECT_TIMEOUT_S = _wifi_config.get('connect_timeout', 15)

# WiFi重连间隔时间配置
# 作用：WiFi连接失败后，下次重试前的等待时间
# 推荐值：30-120秒，平衡重连频率和功耗
# 注意：过短会增加功耗和发热，过长会影响网络恢复速度
WIFI_RETRY_INTERVAL_S = _wifi_config.get('retry_interval', 60)

# NTP重试间隔配置
# 作用：每次NTP同步重试之间的等待时间
# 推荐值：60秒，给网络和服务器充分响应时间
# 注意：无限重试机制，确保时间最终同步成功
NTP_RETRY_DELAY_S = _ntp_config.get('retry_delay', 60)

# 时区偏移配置
# 作用：将UTC时间转换为本地时间的小时偏移量
# 推荐值：根据实际时区设置（中国：8，美东：-5/-4，欧洲：1/2等）
# 注意：夏令时地区需要根据季节调整，中国无夏令时固定为8
TIMEZONE_OFFSET_HOURS = _ntp_config.get('timezone_offset', 8)

# --- WiFi配置数组 ---
# WiFi网络配置列表
# 作用：定义设备可以连接的WiFi网络列表，系统会按顺序尝试连接
# 配置格式：每个配置包含"ssid"（网络名称）和"password"（密码）
# 使用说明：
#   1. 系统会扫描可用网络，然后按配置顺序尝试连接
#   2. 连接到第一个可用的网络后停止尝试
#   3. 可以添加多个网络作为备选（家庭、办公室、热点等）
#   4. 建议将最常用的网络放在前面
# 安全注意：密码明文存储，请确保代码安全
WIFI_CONFIGS = _wifi_config.get('networks', [
    {"ssid": "Lejurobot", "password": "Leju2022"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
])

# --- LED 控制配置常量 (向后兼容) ---
# LED引脚配置
# 作用：定义控制LED的GPIO引脚号
# 推荐值：根据硬件设计选择可用的GPIO引脚
# 注意：确保引脚支持PWM输出，避免与其他功能冲突
LED_PIN_1 = _led_config.get('pin_1', 12)  # LED 1 的主控引脚
LED_PIN_2 = _led_config.get('pin_2', 13)  # LED 2 的主控引脚

# PWM频率配置
# 作用：控制PWM信号的频率，影响LED的闪烁和调光效果
# 推荐值：50-1000Hz，平衡视觉效果和功耗
# 注意：过低会产生可见闪烁，过高会增加功耗和电磁干扰
PWM_FREQ = _led_config.get('pwm_freq', 60)

# LED最大亮度配置
# 作用：定义PWM占空比的最大值，控制LED的最大亮度
# 推荐值：10000-30000（ESP32的PWM范围0-65535）
# 注意：过高会增加功耗和发热，过低会影响可见度
MAX_BRIGHTNESS = _led_config.get('max_brightness', 20000)

# 呼吸灯渐变步长配置
# 作用：控制呼吸灯效果中每次亮度变化的幅度
# 推荐值：128-512，平衡动画流畅度和CPU占用
# 注意：过小会使动画过慢，过大会使动画不够平滑
FADE_STEP = _led_config.get('fade_step', 256)

# === LED 模块内部状态变量 ===
# 这些变量用于跟踪LED硬件状态和当前效果
# 注意：这些是模块内部变量，外部代码不应直接访问
_led1_pwm = None           # LED 1 的PWM对象
_led2_pwm = None           # LED 2 的PWM对象
_leds_initialized = False  # LED硬件初始化状态标志
_current_effect = None     # 当前活跃的灯效名称
_effect_params = {}        # 当前灯效的参数
_led1_brightness = 0       # LED 1 当前亮度值
_led2_brightness = 0       # LED 2 当前亮度值
_safe_mode_active = False  # 安全模式状态

# 兼容性变量（保持向后兼容）
_effect_mode = 'off'      # 当前灯效模式
_brightness = 0           # 呼吸灯当前亮度值
_fade_direction = 1       # 呼吸灯亮度变化方向

# === LED事件处理函数 ===
def _subscribe_to_led_events():
    """
    订阅LED相关的事件
    """
    event_bus.subscribe('led_set_effect', _on_led_set_effect)
    event_bus.subscribe('led_set_brightness', _on_led_set_brightness)
    event_bus.subscribe('led_emergency_off', _on_led_emergency_off)
    print("[LED] 已订阅LED控制事件")

def _on_led_set_effect(event_data):
    """
    处理设置LED效果的事件
    """
    mode = event_data.get('mode', 'off')
    led_num = event_data.get('led_num', 1)
    brightness = event_data.get('brightness', MAX_BRIGHTNESS)
    set_effect(mode, led_num, brightness)

def _on_led_set_brightness(event_data):
    """
    处理设置LED亮度的事件
    """
    led_num = event_data.get('led_num', 1)
    brightness = event_data.get('brightness', MAX_BRIGHTNESS)
    
    if not _led1_pwm or not _led2_pwm:
        return
    
    if led_num == 1:
        _led1_pwm.duty_u16(brightness)
    elif led_num == 2:
        _led2_pwm.duty_u16(brightness)
    elif led_num == 0:  # 两个LED都设置
        _led1_pwm.duty_u16(brightness)
        _led2_pwm.duty_u16(brightness)

def _on_led_emergency_off(event_data):
    """
    处理紧急关闭LED的事件
    """
    print("[LED] 收到紧急关闭信号")
    set_effect('off')
    event_bus.publish('led_emergency_off_completed')

# --- 异步任务管理变量 ---
# 异步任务状态控制
_tasks_running = False
_wifi_task = None
_ntp_task = None
_led_task = None
_wifi_connected = False
_ntp_synced = False

# --- 事件回调函数列表 ---
_wifi_connected_callbacks = []
_ntp_synced_callbacks = []

# ==================================================================
# 新增：LED 控制功能
# ==================================================================

def init_leds():
    """
    初始化LED硬件
    
    功能：
    - 创建PWM对象控制LED
    - 设置初始状态为关闭
    - 通过事件总线发布初始化状态
    - 订阅LED控制事件
    
    返回值：
    - True: 初始化成功
    - False: 初始化失败
    
    注意：
    - 必须在使用LED功能前调用
    - 重复调用是安全的
    - 失败时会打印错误信息并通过事件总线发布
    """
    global _led1_pwm, _led2_pwm, _leds_initialized
    
    try:
        # 如果已经初始化，先清理
        if _led1_pwm: _led1_pwm.deinit()
        if _led2_pwm: _led2_pwm.deinit()
        
        # 创建PWM对象
        pin1 = machine.Pin(LED_PIN_1, machine.Pin.OUT)
        pin2 = machine.Pin(LED_PIN_2, machine.Pin.OUT)
        _led1_pwm = machine.PWM(pin1, freq=PWM_FREQ, duty_u16=0)
        _led2_pwm = machine.PWM(pin2, freq=PWM_FREQ, duty_u16=0)
        
        _leds_initialized = True
        
        print(f"[LED] 初始化成功 - 引脚: {LED_PIN_1}, {LED_PIN_2}, 频率: {PWM_FREQ}Hz")
        
        # 通过事件总线发布初始化成功事件
        event_bus.publish('led_initialized', success=True)
        
        # 订阅LED控制事件
        _subscribe_to_led_events()
        
        return True
        
    except Exception as e:
        error_msg = f"LED初始化失败: {e}"
        print(f"[LED] [ERROR] {error_msg}")
        
        # 通过事件总线发布初始化失败事件
        event_bus.publish('led_initialized', success=False, error=error_msg)
        event_bus.publish('log_critical', message=error_msg)
        
        _led1_pwm = None
        _led2_pwm = None
        return False

def deinit_leds():
    """
    关闭并释放PWM硬件资源。
    用于进入紧急安全模式。
    """
    global _led1_pwm, _led2_pwm, _leds_initialized
    try:
        if _led1_pwm: _led1_pwm.deinit()
        if _led2_pwm: _led2_pwm.deinit()
        _led1_pwm = None
        _led2_pwm = None
        _leds_initialized = False
        
        print("[LED] PWM 已关闭")
        
        # 通过事件总线发布LED关闭事件
        event_bus.publish('led_deinitialized')
        
    except Exception as e:
        error_msg = f"PWM 关闭失败: {e}"
        print(f"[LED] [ERROR] {error_msg}")
        event_bus.publish('log_error', message=error_msg)

def set_effect(mode, led_num=1, brightness_u16=MAX_BRIGHTNESS):
    """
    设置一个预设的灯光效果。这是外部调用的主要接口。

    Args:
        mode (str): 效果模式 ('off', 'single_on', 'both_on', 'breathing').
        led_num (int): 对于 'single_on' 模式, 指定哪个LED灯 (1 或 2).
        brightness_u16 (int): 对于常亮模式, 指定亮度 (0-65535).
    """
    global _effect_mode, _brightness, _fade_direction, _current_effect, _effect_params
    
    if not _led1_pwm or not _led2_pwm:
        error_msg = "PWM未初始化，无法设置灯效"
        print(f"[LED] [WARNING] {error_msg}")
        event_bus.publish('log_warning', message=error_msg)
        return

    print(f"[LED] 设置灯效为: {mode}")
    _effect_mode = mode
    _current_effect = mode
    _effect_params = {'led_num': led_num, 'brightness_u16': brightness_u16}

    if mode == 'off':
        _led1_pwm.duty_u16(0)
        _led2_pwm.duty_u16(0)
    elif mode == 'single_on':
        if led_num == 1:
            _led1_pwm.duty_u16(brightness_u16)
            _led2_pwm.duty_u16(0)
        else:
            _led1_pwm.duty_u16(0)
            _led2_pwm.duty_u16(brightness_u16)
    elif mode == 'both_on':
        _led1_pwm.duty_u16(brightness_u16)
        _led2_pwm.duty_u16(brightness_u16)
    elif mode == 'breathing':
        # 重置呼吸效果的起始状态，以便从头开始动画
        _brightness = 0
        _fade_direction = 1
    else:
        error_msg = f"未知的灯效模式: {mode}"
        print(f"[LED] [WARNING] {error_msg}")
        event_bus.publish('log_warning', message=error_msg)
        _effect_mode = 'off' # 设为安全默认值
        _current_effect = 'off'
    
    # 通过事件总线发布灯效变化事件
    event_bus.publish('led_effect_changed', 
                     effect=_current_effect, 
                     params=_effect_params)

# 注意：update_led_effect() 函数已被 led_effect_task() 异步任务替代
# 保留此注释以说明架构变更：从同步定时器调用改为异步任务处理

async def wifi_connecting_blink():
    """
    WiFi连接时的LED闪烁指示：异步版本
    """
    if not _led1_pwm or not _led2_pwm:
        return
    
    # 异步闪烁：使用asyncio.sleep实现非阻塞延时
    _led1_pwm.duty_u16(MAX_BRIGHTNESS)
    _led2_pwm.duty_u16(MAX_BRIGHTNESS)
    await asyncio.sleep_ms(100)  # 异步等待100ms
    _led1_pwm.duty_u16(0)
    _led2_pwm.duty_u16(0)
    await asyncio.sleep_ms(100)  # 异步等待100ms

async def led_effect_task():
    """
    LED效果异步任务：处理呼吸灯和其他动态效果
    """
    global _brightness, _fade_direction
    
    while _tasks_running:
        try:
            # 仅当处于'breathing'模式时才执行动画更新
            if _effect_mode == 'breathing':
                if _led1_pwm and _led2_pwm:
                    _brightness += FADE_STEP * _fade_direction
                    if _brightness >= MAX_BRIGHTNESS:
                        _brightness = MAX_BRIGHTNESS
                        _fade_direction = -1
                    elif _brightness <= 0:
                        _brightness = 0
                        _fade_direction = 1
                    
                    _led1_pwm.duty_u16(_brightness)
                    _led2_pwm.duty_u16(MAX_BRIGHTNESS - _brightness)
                
                # 呼吸灯更新间隔
                await asyncio.sleep_ms(50)
            else:
                # 非动画模式下，降低检查频率
                await asyncio.sleep_ms(500)
        except Exception as e:
            print(f"[LED] 异步任务错误: {e}")
            await asyncio.sleep_ms(1000)

# ==================================================================
# WiFi与NTP功能 (保持不变)
# ==================================================================

async def scan_available_networks():
    """
    扫描可用的WiFi网络 - 异步版本
    返回: 可用网络的SSID列表
    """
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
        await asyncio.sleep_ms(1000)  # 异步等待WiFi模块激活
    
    print("[WiFi] 正在扫描可用网络...")
    try:
        networks = wlan.scan()
        if networks:
            available_ssids = [net[0].decode('utf-8') for net in networks]
            print(f"[WiFi] 发现 {len(available_ssids)} 个网络")
            return available_ssids
        else:
            print("[WiFi] 扫描结果为空")
            return []
    except Exception as e:
        print(f"[WiFi] [ERROR] 扫描网络失败: {e}")
        return []

async def _trigger_wifi_connected_callbacks():
    """
    触发WiFi连接成功的回调函数
    """
    for callback in _wifi_connected_callbacks:
        try:
            # 在MicroPython中，直接await调用回调函数
            # 假设所有注册的回调都是async函数
            await callback()
        except Exception as e:
            print(f"[CALLBACK] WiFi连接回调错误: {e}")

async def _trigger_ntp_synced_callbacks():
    """
    触发NTP同步成功的回调函数
    """
    for callback in _ntp_synced_callbacks:
        try:
            # 在MicroPython中，直接await调用回调函数
            # 假设所有注册的回调都是async函数
            await callback()
        except Exception as e:
            print(f"[CALLBACK] NTP同步回调错误: {e}")

def register_wifi_connected_callback(callback):
    """
    注册WiFi连接成功的回调函数
    """
    if callback not in _wifi_connected_callbacks:
        _wifi_connected_callbacks.append(callback)
        print(f"[CALLBACK] 已注册WiFi连接回调: {callback.__name__}")

def register_ntp_synced_callback(callback):
    """
    注册NTP同步成功的回调函数
    """
    if callback not in _ntp_synced_callbacks:
        _ntp_synced_callbacks.append(callback)
        print(f"[CALLBACK] 已注册NTP同步回调: {callback.__name__}")

async def connect_wifi():
    """
    WiFi智能连接函数 - 异步版本，单次尝试
    从配置数组中搜索并连接可用的WiFi网络
    返回: 连接成功返回True，失败返回False
    """
    global _wifi_connected
    
    print("[WiFi] 开始智能WiFi连接...")
    event_bus.publish('wifi_connecting')
    wlan = network.WLAN(network.STA_IF)
    
    if not wlan.active():
        wlan.active(True)

    # 检查是否已连接
    if wlan.isconnected():
        ssid = wlan.config('essid')
        ip = wlan.ifconfig()[0]
        print("[WiFi] 网络已连接。")
        print(f"[WiFi] IP地址: {ip}")
        if not _wifi_connected:
            _wifi_connected = True
            # 触发WiFi连接成功回调
            await _trigger_wifi_connected_callbacks()
            event_bus.publish('wifi_connected', ssid=ssid, ip=ip, reconnect=False)
        return True

    # 扫描可用网络
    available_networks = await scan_available_networks()
    if not available_networks:
        error_msg = "未发现任何可用网络"
        print(f"[WiFi] [ERROR] {error_msg}")
        event_bus.publish('wifi_scan_failed')
        event_bus.publish('log_warning', message=error_msg)
        return False

    # 尝试连接配置中的第一个可用网络
    for config in WIFI_CONFIGS:
        ssid = config["ssid"]
        password = config["password"]
        
        if ssid in available_networks:
            print(f"[WiFi] 尝试连接到: {ssid}")
            event_bus.publish('wifi_trying', ssid=ssid)
            
            # 开始连接过程
            wlan.connect(ssid, password)
            
            # 异步等待连接，使用asyncio.sleep
            start_time = time.time()
            blink_count = 0
            while not wlan.isconnected():
                if time.time() - start_time > WIFI_CONNECT_TIMEOUT_S:
                    error_msg = f"连接 {ssid} 超时"
                    print(f"\n[WiFi] [ERROR] {error_msg}！")
                    event_bus.publish('wifi_timeout', ssid=ssid)
                    break
                
                # 每2秒闪烁一次LED
                blink_count += 1
                if blink_count % 40 == 0:  # 50ms * 40 = 2秒
                    await wifi_connecting_blink()
                
                # 异步等待，不阻塞其他任务
                await asyncio.sleep_ms(50)
            
            if wlan.isconnected():
                ip_info = wlan.ifconfig()
                ip = ip_info[0]
                print(f"\n[WiFi] [SUCCESS] 成功连接到: {ssid}")
                print(f"[WiFi] IP地址: {ip}")
                _wifi_connected = True
                # 触发WiFi连接成功回调
                await _trigger_wifi_connected_callbacks()
                event_bus.publish('wifi_connected', ssid=ssid, ip=ip, reconnect=True)
                event_bus.publish('log_info', message=f"WiFi连接成功: {ssid} ({ip})")
                return True
            else:
                error_msg = f"连接 {ssid} 失败"
                print(f"[WiFi] [WARNING] {error_msg}")
                event_bus.publish('wifi_error', ssid=ssid, error=error_msg)
                # 单次尝试失败后直接退出，不再尝试其他网络
                break
    
    error_msg = "WiFi连接失败"
    print(f"[WiFi] [ERROR] {error_msg}")
    _wifi_connected = False
    event_bus.publish('wifi_failed')
    event_bus.publish('log_warning', message=error_msg)
    return False

async def wifi_task():
    """
    WiFi连接异步任务：负责WiFi连接和重连管理
    """
    global _wifi_connected
    
    # 初次连接尝试
    print("[WiFi] 启动WiFi连接任务...")
    await connect_wifi()
    
    # 连接监控和重连循环
    while _tasks_running:
        try:
            # 检查温度，如果过高则跳过连接尝试
            try:
                temp = esp32.mcu_temperature()
                if temp and temp > 42.0:
                    print(f"[WiFi] 温度过高 ({temp:.1f}°C)，跳过WiFi连接检查")
                    await asyncio.sleep(60)  # 高温时延长检查间隔
                    continue
            except:
                pass
            
            wlan = network.WLAN(network.STA_IF)
            if not wlan.isconnected():
                if _wifi_connected:
                    print("[WiFi] 检测到WiFi连接丢失，尝试重连...")
                    _wifi_connected = False
                    # 设置呼吸灯表示等待连接
                    set_effect('breathing')
                
                # 尝试重连
                success = await connect_wifi()
                if success:
                    print("[WiFi] 重连成功")
                    # 设置常亮灯表示连接成功
                    set_effect('single_on', led_num=1)
                    await asyncio.sleep(60)  # 连接成功后60秒检查一次
                else:
                    await asyncio.sleep(WIFI_RETRY_INTERVAL_S)  # 连接失败后等待重试间隔
            else:
                if not _wifi_connected:
                    _wifi_connected = True
                    print("[WiFi] WiFi连接状态已恢复")
                    set_effect('single_on', led_num=1)
                
                # 连接正常时，降低检查频率
                await asyncio.sleep(30)
                
        except Exception as e:
            print(f"[WiFi] WiFi任务错误: {e}")
            await asyncio.sleep(10)


def get_local_time():
    """
    获取本地时间（考虑时区偏移）
    返回: 本地时间元组 (年, 月, 日, 时, 分, 秒, 星期, 年内天数)
    """
    try:
        utc_time = time.localtime()
        # 计算时区偏移后的时间戳
        utc_timestamp = time.mktime(utc_time)
        local_timestamp = utc_timestamp + (TIMEZONE_OFFSET_HOURS * 3600)
        local_time = time.localtime(local_timestamp)
        return local_time
    except Exception as e:
        print(f"[TIME] [ERROR] 获取本地时间失败: {e}")
        return time.localtime()

def format_time(time_tuple):
    """
    格式化时间显示
    参数: time_tuple - 时间元组
    返回: 格式化的时间字符串
    """
    try:
        year, month, day, hour, minute, second = time_tuple[:6]
        return f"{year}年{month:02d}月{day:02d}日 {hour:02d}:{minute:02d}:{second:02d}"
    except:
        return "时间格式错误"

async def sync_ntp_time():
    """通过NTP同步设备的实时时钟（RTC）并显示本地时间 - 异步版本
    单次尝试，不阻塞
    """
    global _ntp_synced
    
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        error_msg = "未连接到WiFi，无法同步时间"
        print(f"[NTP] [ERROR] {error_msg}。")
        event_bus.publish('ntp_no_wifi')
        event_bus.publish('log_warning', message=error_msg)
        return False

    try:
        print("[NTP] 正在尝试同步网络时间...")
        event_bus.publish('ntp_syncing')
        ntptime.settime()
        
        if time.localtime()[0] > 2023:
            utc_time = time.localtime()
            local_time = get_local_time()
            
            print("[NTP] [SUCCESS] 时间同步成功！")
            print(f"[NTP] UTC时间: {format_time(utc_time)}")
            print(f"[NTP] 本地时间: {format_time(local_time)} (UTC+{TIMEZONE_OFFSET_HOURS})")
            _ntp_synced = True
            # 触发NTP同步成功回调
            await _trigger_ntp_synced_callbacks()
            event_bus.publish('ntp_synced', 
                            utc_time=format_time(utc_time),
                            local_time=format_time(local_time),
                            timezone_offset=TIMEZONE_OFFSET_HOURS)
            event_bus.publish('log_info', message=f"时间同步成功: {format_time(local_time)}")
            return True
    except Exception as e:
        error_msg = f"时间同步失败: {e}"
        print(f"[NTP] [WARNING] {error_msg}")
        event_bus.publish('ntp_failed', error=str(e))
        event_bus.publish('log_warning', message=error_msg)
        return False

async def _on_wifi_connected():
    """
    WiFi连接成功后的回调函数：立即尝试NTP同步
    """
    print("[NTP] WiFi连接成功，立即尝试时间同步...")
    await sync_ntp_time()

async def ntp_task():
    """
    NTP时间同步异步任务：负责定期同步时间
    """
    global _ntp_synced
    
    print("[NTP] 启动NTP同步任务...")
    
    # 注册WiFi连接成功的回调，实现事件驱动的NTP同步
    register_wifi_connected_callback(_on_wifi_connected)
    
    while _tasks_running:
        try:
            # 定期检查并重新同步时间（每24小时）
            if _wifi_connected and _ntp_synced:
                # 如果已经同步过，等待24小时后重新同步
                await asyncio.sleep(24 * 3600)  # 24小时
                if _wifi_connected:
                    print("[NTP] 定期重新同步时间...")
                    _ntp_synced = False  # 重置状态以允许重新同步
                    await sync_ntp_time()
            else:
                # 如果还未同步，等待较短时间后重试
                await asyncio.sleep(NTP_RETRY_DELAY_S)
                if _wifi_connected and not _ntp_synced:
                    await sync_ntp_time()
                    
        except Exception as e:
             print(f"[NTP] NTP任务错误: {e}")
             await asyncio.sleep(30)

# ==================================================================
# 异步任务管理器
# ==================================================================

async def start_all_tasks():
    """
    启动所有异步任务
    """
    global _tasks_running, _wifi_task, _ntp_task, _led_task
    
    print("[ASYNC] 启动异步任务管理器...")
    _tasks_running = True
    
    # 设置初始灯效（呼吸灯表示等待连接）
    set_effect('breathing')
    
    # 创建并启动所有异步任务
    _wifi_task = asyncio.create_task(wifi_task())
    _ntp_task = asyncio.create_task(ntp_task())
    _led_task = asyncio.create_task(led_effect_task())
    
    print("[ASYNC] 所有异步任务已启动")
    
    # 等待所有任务完成（实际上会一直运行）
    try:
        await asyncio.gather(_wifi_task, _ntp_task, _led_task)
    except Exception as e:
        print(f"[ASYNC] 任务管理器错误: {e}")
    finally:
        await stop_all_tasks()

async def stop_all_tasks():
    """
    停止所有异步任务
    """
    global _tasks_running, _wifi_task, _ntp_task, _led_task
    
    print("[ASYNC] 停止所有异步任务...")
    _tasks_running = False
    
    # 取消所有任务
    for task in [_wifi_task, _ntp_task, _led_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    print("[ASYNC] 所有异步任务已停止")

def get_system_status():
    """
    获取系统状态信息
    返回: 包含系统状态的字典
    """
    status = {
        'wifi_connected': _wifi_connected,
        'ntp_synced': _ntp_synced,
        'tasks_running': _tasks_running,
        'current_time': None,
        'ip_address': None,
        'temperature': None
    }
    
    # 获取当前时间
    if _ntp_synced:
        try:
            local_time = get_local_time()
            status['current_time'] = format_time(local_time)
        except:
            status['current_time'] = "时间获取失败"
    
    # 获取IP地址
    if _wifi_connected:
        try:
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                status['ip_address'] = wlan.ifconfig()[0]
        except:
            pass
    
    # 获取温度
    try:
        status['temperature'] = esp32.mcu_temperature()
    except:
        pass
    
    return status

def print_system_status():
    """
    打印系统状态报告
    """
    status = get_system_status()
    print("\n" + "="*50)
    print("           系统状态报告")
    print("="*50)
    print(f"WiFi连接状态: {'已连接' if status['wifi_connected'] else '未连接'}")
    if status['ip_address']:
        print(f"IP地址: {status['ip_address']}")
    print(f"时间同步状态: {'已同步' if status['ntp_synced'] else '未同步'}")
    if status['current_time']:
        print(f"当前时间: {status['current_time']}")
    print(f"异步任务状态: {'运行中' if status['tasks_running'] else '已停止'}")
    if status['temperature']:
        print(f"MCU温度: {status['temperature']:.1f}°C")
    print("="*50 + "\n")

def run_async_system():
    """
    运行异步系统的主入口函数
    这是外部调用的主要接口
    """
    print("[SYSTEM] 启动异步系统...")
    try:
        asyncio.run(start_all_tasks())
    except KeyboardInterrupt:
        print("\n[SYSTEM] 收到中断信号，正在停止系统...")
    except Exception as e:
        print(f"[SYSTEM] 系统错误: {e}")
    finally:
        print("[SYSTEM] 异步系统已停止")

# 注意：wifi_connection_loop() 兼容性函数已移除
# 新架构使用 wifi_task() 异步任务和事件驱动模式