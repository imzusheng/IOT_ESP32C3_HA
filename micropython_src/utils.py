# utils.py
"""
通用工具函数模块 (WiFi, NTP, 和 LED 控制)
"""
import network
import time
import ntptime
import machine

# --- WiFi & NTP 配置常量 ---
WIFI_CONNECT_TIMEOUT_S = 15  # WiFi连接的超时时间（秒）
NTP_RETRY_COUNT = 3          # NTP时间同步的重试次数
NTP_RETRY_DELAY_S = 2        # 每次NTP重试前的等待时间（秒）

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

# ==================================================================
# WiFi与NTP功能 (保持不变)
# ==================================================================

def connect_wifi(ssid, password):
    """
    连接到指定的WiFi网络。
    (此函数代码未改变)
    """
    print("[WiFi] 开始连接...")
    wlan = network.WLAN(network.STA_IF)
    
    if not wlan.active():
        wlan.active(True)

    if wlan.isconnected():
        print("[WiFi] 网络已连接。")
        print(f"[WiFi] IP地址: {wlan.ifconfig()[0]}")
        return True

    print(f"[WiFi] 正在连接到网络: {ssid}...")
    wlan.connect(ssid, password)

    start_time = time.time()
    while not wlan.isconnected():
        if time.time() - start_time > WIFI_CONNECT_TIMEOUT_S:
            print(f"\n[WiFi] [ERROR] 连接超时（超过 {WIFI_CONNECT_TIMEOUT_S} 秒）！")
            wlan.active(False)
            return False
        print(".", end="")
        time.sleep(1)
    
    print("\n[WiFi] [SUCCESS] 连接成功！")
    ip_info = wlan.ifconfig()
    print(f"[WiFi] IP地址: {ip_info[0]}")
    return True


def sync_ntp_time():
    """通过NTP同步设备的实时时钟（RTC）。"""
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
                print("[NTP] [SUCCESS] 时间同步成功！")
                print(f"[NTP] 当前UTC时间: {time.localtime()}")
                return True
        except Exception as e:
            print(f"[NTP] [WARNING] 时间同步失败: {e}")
            if i < NTP_RETRY_COUNT - 1:
                print(f"[NTP] {NTP_RETRY_DELAY_S}秒后重试...")
                time.sleep(NTP_RETRY_DELAY_S)
    
    print("\n[NTP] [ERROR] 经过多次尝试后，NTP时间同步最终失败！")
    return False