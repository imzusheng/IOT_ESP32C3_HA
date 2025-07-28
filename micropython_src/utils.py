# utils.py
"""
通用工具函数模块 (WiFi, NTP, 和 LED 控制)
"""
import network
import time
import ntptime
import machine
import esp32

# --- WiFi & NTP 配置常量 ---
WIFI_CONNECT_TIMEOUT_S = 15  # WiFi连接的超时时间（秒）
WIFI_RETRY_INTERVAL_S = 60   # WiFi重连间隔时间（秒）
WIFI_SCAN_RETRY_COUNT = 3    # WiFi扫描重试次数
WIFI_SCAN_RETRY_DELAY_S = 5  # WiFi扫描重试间隔（秒）
NTP_RETRY_COUNT = 3          # NTP时间同步的重试次数
NTP_RETRY_DELAY_S = 2        # 每次NTP重试前的等待时间（秒）
TIMEZONE_OFFSET_HOURS = 8    # 时区偏移小时数（中国标准时间 UTC+8）

# --- WiFi配置数组 ---
WIFI_CONFIGS = [
    {"ssid": "Lejurobot", "password": "Leju2022"},
    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
]

# --- LED 控制配置常量 ---
LED_PIN_1 = 12                  # LED 1 的主控引脚
LED_PIN_2 = 13                  # LED 2 的主控引脚
PWM_FREQ = 60                   # PWM 信号频率 (Hz)
MAX_BRIGHTNESS = 20000          # PWM 占空比的最大值 (范围: 0-65535)
FADE_STEP = 256                 # 呼吸灯效果中，每次亮度变化的步长

# --- LED 模块内部状态变量 ---
_led1_pwm = None
_led2_pwm = None
_effect_mode = 'off'  # 当前灯效模式
_brightness = 0       # 用于呼吸效果的当前亮度
_fade_direction = 1   # 用于呼吸效果的亮度变化方向

# ==================================================================
# 新增：LED 控制功能
# ==================================================================

def init_leds():
    """
    初始化控制LED的PWM硬件。
    由守护进程在启动时调用。
    """
    global _led1_pwm, _led2_pwm
    try:
        if _led1_pwm: _led1_pwm.deinit()
        if _led2_pwm: _led2_pwm.deinit()
        
        pin1 = machine.Pin(LED_PIN_1, machine.Pin.OUT)
        pin2 = machine.Pin(LED_PIN_2, machine.Pin.OUT)
        _led1_pwm = machine.PWM(pin1, freq=PWM_FREQ, duty_u16=0)
        _led2_pwm = machine.PWM(pin2, freq=PWM_FREQ, duty_u16=0)
        print("[LED] PWM 初始化成功")
        return True
    except Exception as e:
        print(f"[LED] [ERROR] PWM 初始化失败: {e}")
        _led1_pwm = None
        _led2_pwm = None
        return False

def deinit_leds():
    """
    关闭并释放PWM硬件资源。
    用于进入紧急安全模式。
    """
    global _led1_pwm, _led2_pwm
    try:
        if _led1_pwm: _led1_pwm.deinit()
        if _led2_pwm: _led2_pwm.deinit()
        _led1_pwm = None
        _led2_pwm = None
        print("[LED] PWM 已关闭")
    except Exception as e:
        print(f"[LED] [ERROR] PWM 关闭失败: {e}")

def set_effect(mode, led_num=1, brightness_u16=MAX_BRIGHTNESS):
    """
    设置一个预设的灯光效果。这是外部调用的主要接口。

    Args:
        mode (str): 效果模式 ('off', 'single_on', 'both_on', 'breathing').
        led_num (int): 对于 'single_on' 模式, 指定哪个LED灯 (1 或 2).
        brightness_u16 (int): 对于常亮模式, 指定亮度 (0-65535).
    """
    global _effect_mode, _brightness, _fade_direction
    
    if not _led1_pwm or not _led2_pwm:
        print("[LED] [WARNING] PWM未初始化，无法设置灯效。")
        return

    print(f"[LED] 设置灯效为: {mode}")
    _effect_mode = mode

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
        print(f"[LED] [WARNING] 未知的灯效模式: {mode}")
        _effect_mode = 'off' # 设为安全默认值

def update_led_effect():
    """
    根据当前设置的模式更新LED状态。
    这个函数应该被一个高频定时器（守护进程）周期性调用。
    对于静态效果（如常亮），此函数不执行任何操作以节省性能。
    """
    global _brightness, _fade_direction
    
    # 仅当处于'breathing'模式时才执行高频更新，大大降低其他模式下的CPU消耗
    if _effect_mode == 'breathing':
        if not _led1_pwm or not _led2_pwm:
            return

        _brightness += FADE_STEP * _fade_direction
        if _brightness >= MAX_BRIGHTNESS:
            _brightness = MAX_BRIGHTNESS
            _fade_direction = -1
        elif _brightness <= 0:
            _brightness = 0
            _fade_direction = 1
        
        _led1_pwm.duty_u16(_brightness)
        _led2_pwm.duty_u16(MAX_BRIGHTNESS - _brightness)

def wifi_connecting_blink():
    """
    WiFi连接时的LED闪烁指示：简化版本，减少CPU消耗
    """
    if not _led1_pwm or not _led2_pwm:
        return
    
    # 简化闪烁：只闪烁一次，减少sleep时间
    _led1_pwm.duty_u16(MAX_BRIGHTNESS)
    _led2_pwm.duty_u16(MAX_BRIGHTNESS)
    time.sleep(0.1)
    _led1_pwm.duty_u16(0)
    _led2_pwm.duty_u16(0)
    time.sleep(0.1)

# ==================================================================
# WiFi与NTP功能 (保持不变)
# ==================================================================

def scan_available_networks():
    """
    扫描可用的WiFi网络 - 优化版本，增加重试机制
    返回: 可用网络的SSID列表
    """
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
        time.sleep(1)  # 等待WiFi模块激活
    
    for attempt in range(WIFI_SCAN_RETRY_COUNT):
        print(f"[WiFi] 正在扫描可用网络... (尝试 {attempt + 1}/{WIFI_SCAN_RETRY_COUNT})")
        try:
            networks = wlan.scan()
            if networks:
                available_ssids = [net[0].decode('utf-8') for net in networks]
                print(f"[WiFi] 发现 {len(available_ssids)} 个网络")
                return available_ssids
            else:
                print("[WiFi] 扫描结果为空")
        except Exception as e:
            print(f"[WiFi] [ERROR] 扫描网络失败: {e}")
        
        if attempt < WIFI_SCAN_RETRY_COUNT - 1:
            print(f"[WiFi] {WIFI_SCAN_RETRY_DELAY_S}秒后重试扫描...")
            time.sleep(WIFI_SCAN_RETRY_DELAY_S)
    
    print("[WiFi] [ERROR] 多次扫描后仍未发现网络")
    return []

def connect_wifi():
    """
    WiFi智能连接函数 - 使用新的多网络配置机制
    从配置数组中搜索并连接可用的WiFi网络
    返回: 连接成功返回True，失败返回False
    """
    print("[WiFi] 开始智能WiFi连接...")
    wlan = network.WLAN(network.STA_IF)
    
    if not wlan.active():
        wlan.active(True)

    # 检查是否已连接
    if wlan.isconnected():
        print("[WiFi] 网络已连接。")
        print(f"[WiFi] IP地址: {wlan.ifconfig()[0]}")
        return True

    # 扫描可用网络
    available_networks = scan_available_networks()
    if not available_networks:
        print("[WiFi] [ERROR] 未发现任何可用网络")
        return False

    # 尝试连接配置中的网络
    for config in WIFI_CONFIGS:
        ssid = config["ssid"]
        password = config["password"]
        
        if ssid in available_networks:
            print(f"[WiFi] 尝试连接到: {ssid}")
            
            # 开始连接过程，显示LED闪烁指示
            wlan.connect(ssid, password)
            
            start_time = time.time()
            blink_counter = 0
            while not wlan.isconnected():
                if time.time() - start_time > WIFI_CONNECT_TIMEOUT_S:
                    print(f"\n[WiFi] [ERROR] 连接 {ssid} 超时！")
                    break
                
                # 减少LED闪烁频率，每3秒闪烁一次
                blink_counter += 1
                if blink_counter % 15 == 0:  # 每15个循环（约3秒）闪烁一次
                    wifi_connecting_blink()
                
                time.sleep(0.2)  # 短暂等待，减少CPU占用
            
            if wlan.isconnected():
                print(f"\n[WiFi] [SUCCESS] 成功连接到: {ssid}")
                ip_info = wlan.ifconfig()
                print(f"[WiFi] IP地址: {ip_info[0]}")
                # 连接成功后关闭LED
                set_effect('off')
                return True
            else:
                print(f"[WiFi] [WARNING] 连接 {ssid} 失败，尝试下一个网络")
    
    print("[WiFi] [ERROR] 所有配置的网络都连接失败")
    # 连接失败后关闭LED
    set_effect('off')
    return False

def wifi_connection_loop():
    """
    WiFi连接循环 - 如果未连接则重试，包含温度保护机制
    返回: 连接成功返回True
    """
    retry_count = 0
    while True:
        # 检查温度，如果过高则延长等待时间
        try:
            temp = esp32.mcu_temperature()
            if temp and temp > 42.0:  # 温度超过42度时减少活动
                print(f"[WiFi] 温度过高 ({temp:.1f}°C)，延长重试间隔到120秒")
                extended_interval = 120
            else:
                extended_interval = WIFI_RETRY_INTERVAL_S
        except:
            extended_interval = WIFI_RETRY_INTERVAL_S
        
        if connect_wifi():
            return True
        
        retry_count += 1
        print(f"[WiFi] 连接失败 (第{retry_count}次)，{extended_interval}秒后重试...")
        time.sleep(extended_interval)


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

def sync_ntp_time():
    """通过NTP同步设备的实时时钟（RTC）并显示本地时间。"""
    print("\n[NTP] 开始使用 ntptime.settime() 同步网络时间...")
    
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("[NTP] [ERROR] 未连接到WiFi，无法同步时间。")
        return False

    for i in range(NTP_RETRY_COUNT):
        try:
            print(f"[NTP] 正在尝试同步... (第 {i+1}/{NTP_RETRY_COUNT} 次)")
            ntptime.settime()
            
            if time.localtime()[0] > 2023:
                utc_time = time.localtime()
                local_time = get_local_time()
                
                print("[NTP] [SUCCESS] 时间同步成功！")
                print(f"[NTP] UTC时间: {format_time(utc_time)}")
                print(f"[NTP] 本地时间: {format_time(local_time)} (UTC+{TIMEZONE_OFFSET_HOURS})")
                return True
        except Exception as e:
            print(f"[NTP] [WARNING] 时间同步失败: {e}")
            if i < NTP_RETRY_COUNT - 1:
                print(f"[NTP] {NTP_RETRY_DELAY_S}秒后重试...")
                time.sleep(NTP_RETRY_DELAY_S)
    
    print("\n[NTP] [ERROR] 经过多次尝试后，NTP时间同步最终失败！")
    return False