# main.py
import machine
import esp32
import time
import gc
import sys
import os

# --- 1. 全局配置常量 ---
# LED引脚定义
LED_PIN_1 = 12
LED_PIN_2 = 13

# PWM呼吸灯效果配置
PWM_FREQ = 1000
MAX_BRIGHTNESS_U16 = 20000   # 限制最大亮度 (0-65535)，让光线更柔和
FADE_STEP = 256              # 每次亮度调整的步长，影响呼吸速度
MAIN_LOOP_DELAY_MS = 16      # 主循环的延迟(毫秒)，影响呼吸灯的平滑度

# 性能监控配置
PERF_MONITOR_INTERVAL_S = 10 # 打印性能报告的时间间隔 (秒)

# 安全模式配置
TEMPERATURE_THRESHOLD = 60.0 # 触发安全模式的MCU温度阈值 (摄氏度)
WDT_TIMEOUT_MS = 30000       # 看门狗超时时间 (毫秒)，给安全模式更多时间
BLINK_INTERVAL_MS = 200      # 安全模式下LED报警爆闪的时间间隔 (毫秒)
SAFE_MODE_COOLDOWN_MS = 5000 # 安全模式下的冷却时间 (毫秒)

# 状态标志
safe_mode_active = False     # 安全模式是否激活
safe_mode_start_time = 0     # 安全模式启动时间 (毫秒)
last_wdt_feed = 0            # 上次喂狗时间 (毫秒)

# --- 2. 辅助功能函数 ---

def format_uptime(ms):
    """将毫秒转换为人类可读的 D-H-M-S 格式"""
    s = ms // 1000
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    return f"{d}天{h:02d}时{m:02d}分{s:02d}秒"

def print_startup_banner():
    """打印详细的设备和固件启动信息"""
    print("\n" + "="*50)
    print("      ESP32-C3 守护程序 V3.2 正在启动...")
    print("="*50)
    print("--- 固件信息 ---")
    fw_info = sys.implementation
    print(f"实现名称 : {fw_info.name} v{fw_info.version[0]}.{fw_info.version[1]}.{fw_info.version[2]}")
    uname = os.uname()
    print(f"固件详情 : {uname.version}")
    print(f"目标板   : {uname.machine}")
    print("\n--- 硬件信息 ---")
    uid = machine.unique_id()
    print(f"唯一ID   : {'-'.join(['%02X' % byte for byte in uid])}")
    print(f"CPU频率  : {machine.freq() / 1000000} MHz")
    print("\n--- 文件系统信息 ---")
    try:
        s = os.statvfs('/')
        total_size_mb = (s[0] * s[2]) / 1024 / 1024
        free_size_mb = (s[0] * s[3]) / 1024 / 1024
        print(f"总空间   : {total_size_mb:.2f} MB")
        print(f"可用空间 : {free_size_mb:.2f} MB")
    except Exception as e:
        print(f"文件系统信息获取失败: {e}")
    print("="*50 + "\n")

def get_internal_temperature():
    """获取并返回MCU的内部核心温度 (摄氏度)"""
    try:
        return esp32.mcu_temperature()
    except Exception as e:
        print(f"读取温度时发生错误: {e}")
        return None

def enter_safe_mode():
    """进入安全模式：停止PWM，切换为GPIO强控制，等待人工干预"""
    global safe_mode_active, safe_mode_start_time, led1_pwm, led2_pwm
    
    if not safe_mode_active:
        print("\n" + "!"*50)
        print("!!!     严重警告：温度超限，进入硬件安全模式     !!!")
        print("!!!       等待人工干预，请检查设备状态         !!!")
        print("!"*50 + "\n")
        
        # 安全地释放PWM资源
        try:
            led1_pwm.deinit()
            led2_pwm.deinit()
        except Exception as e:
            print(f"PWM释放时出错: {e}")
        
        safe_mode_active = True
        safe_mode_start_time = time.ticks_ms()

def exit_safe_mode():
    """退出安全模式，重新初始化PWM"""
    global safe_mode_active, led1_pwm, led2_pwm
    
    print("温度已降至安全范围，退出安全模式...")
    try:
        # 重新初始化PWM
        led1_pwm = machine.PWM(machine.Pin(LED_PIN_1), freq=PWM_FREQ, duty_u16=0)
        led2_pwm = machine.PWM(machine.Pin(LED_PIN_2), freq=PWM_FREQ, duty_u16=0)
        safe_mode_active = False
        print("已成功退出安全模式，恢复正常运行")
    except Exception as e:
        print(f"退出安全模式时出错: {e}")

def safe_mode_loop():
    """安全模式下的循环处理"""
    global last_wdt_feed
    
    # 切换为GPIO输出进行爆闪
    try:
        led1 = machine.Pin(LED_PIN_1, machine.Pin.OUT)
        led2 = machine.Pin(LED_PIN_2, machine.Pin.OUT)
        
        current_time = time.ticks_ms()
        
        # 爆闪LED报警
        if time.ticks_diff(current_time, safe_mode_start_time) % (BLINK_INTERVAL_MS * 2) < BLINK_INTERVAL_MS:
            led1.on()
            led2.off()
        else:
            led1.off()
            led2.on()
            
        # 在安全模式下也要定期喂狗，但频率降低
        if time.ticks_diff(current_time, last_wdt_feed) > 2000:  # 每2秒喂一次
            wdt.feed()
            last_wdt_feed = current_time
            
    except Exception as e:
        print(f"安全模式循环出错: {e}")

def check_system_recovery():
    """检查系统是否可以从安全模式恢复"""
    current_temp = get_internal_temperature()
    current_time = time.ticks_ms()
    
    # 温度降至安全范围且已在安全模式停留足够时间
    if (current_temp and current_temp < TEMPERATURE_THRESHOLD - 5.0 and  # 5度滞后防抖
        time.ticks_diff(current_time, safe_mode_start_time) > SAFE_MODE_COOLDOWN_MS):
        return True
    return False

# --- 3. 初始化 ---
print_startup_banner()

# 初始化PWM和看门狗
try:
    led1_pwm = machine.PWM(machine.Pin(LED_PIN_1), freq=PWM_FREQ, duty_u16=0)
    led2_pwm = machine.PWM(machine.Pin(LED_PIN_2), freq=PWM_FREQ, duty_u16=0)
    wdt = machine.WDT(timeout=WDT_TIMEOUT_MS) # 激活看门狗
    last_wdt_feed = time.ticks_ms()
    print("硬件初始化成功")
except Exception as e:
    print(f"初始化失败: {e}")
    machine.reset()

time.sleep(1) # 短暂延时，确保启动信息显示完全

# --- 4. 主程序循环与状态变量 ---
start_ticks_ms = time.ticks_ms()
last_perf_check_ms = start_ticks_ms
brightness = 0
fade_direction = 1 # 1 表示变亮, -1 表示变暗

print("初始化完成，主循环已启动...")

while True:
    try:
        current_ticks_ms = time.ticks_ms()
        
        # 安全模式处理
        if safe_mode_active:
            safe_mode_loop()
            # 检查是否可以退出安全模式
            if check_system_recovery():
                exit_safe_mode()
            time.sleep_ms(MAIN_LOOP_DELAY_MS)
            continue
        
        # 正常喂狗
        if time.ticks_diff(current_ticks_ms, last_wdt_feed) > 1000:  # 每秒喂一次
            wdt.feed()
            last_wdt_feed = current_ticks_ms

        # 更新LED呼吸灯亮度
        brightness += FADE_STEP * fade_direction
        if brightness >= MAX_BRIGHTNESS_U16:
            brightness = MAX_BRIGHTNESS_U16
            fade_direction = -1 # 切换为变暗
        elif brightness <= 0:
            brightness = 0
            fade_direction = 1 # 切换为变亮
        
        # 安全地设置PWM
        try:
            led1_pwm.duty_u16(brightness)
            led2_pwm.duty_u16(MAX_BRIGHTNESS_U16 - brightness) # 第二个LED亮度互补
        except Exception as e:
            print(f"PWM设置出错: {e}")

        # 检查核心温度
        current_temp = get_internal_temperature()
        if current_temp and current_temp >= TEMPERATURE_THRESHOLD:
            enter_safe_mode() # 如果温度超限，则进入安全模式
            continue

        # 定期打印性能报告
        if time.ticks_diff(current_ticks_ms, last_perf_check_ms) >= PERF_MONITOR_INTERVAL_S * 1000:
            uptime_str = format_uptime(time.ticks_diff(current_ticks_ms, start_ticks_ms))
            gc.collect() # 执行一次垃圾回收，获取更准确的内存信息
            mem_alloc_kb = gc.mem_alloc() / 1024
            mem_free_kb = gc.mem_free() / 1024
            mem_total_kb = mem_alloc_kb + mem_free_kb
            mem_percent = (mem_alloc_kb / mem_total_kb) * 100 if mem_total_kb > 0 else 0

            print("\n" + "----- 系统状态面板 -----")
            print(f"运行时间: {uptime_str}")
            print(f"内部温度: {current_temp:.2f} °C" if current_temp else "读取失败")
            print(f"内存使用: {mem_alloc_kb:.2f}KB / {mem_total_kb:.2f}KB ({mem_percent:.1f}%)")
            print(f"运行状态: {'安全模式' if safe_mode_active else '正常运行'}")
            print("--------------------------")
            
            last_perf_check_ms = current_ticks_ms # 更新最后检查时间

        time.sleep_ms(MAIN_LOOP_DELAY_MS)
        
    except Exception as e:
        print(f"主循环出错: {e}")
        time.sleep_ms(1000)  # 出错时暂停1秒再继续