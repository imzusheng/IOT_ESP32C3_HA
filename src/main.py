# -*- coding: utf-8 -*-
"""
ESP32C3主程序

集成集中配置管理、WiFi连接、MQTT通信和守护进程功能。
提供稳定可靠的IoT设备运行环境。
"""
import time
import machine
import gc
import ujson
import net_wifi
import net_mqtt
import sys_daemon
import sys_error
# 蓝牙扫描器模块 - 暂时屏蔽
# import ble_scanner

# 配置管理 - 使用统一的JSON配置文件
def load_config(config_path='config.json'):
    """加载配置文件"""
    try:
        with open(config_path, 'r') as f:
            config = ujson.load(f)
        print("[Main] 配置文件加载成功")
        return config
    except Exception as e:
        print(f"[Main] 配置文件加载失败: {e}")
        return None

def get_config_value(config, section, key=None, default=None):
    """获取配置值"""
    if not config:
        return default
    
    if key is None:
        return config.get(section, default)
    
    section_config = config.get(section, {})
    return section_config.get(key, default)

# 初始化配置
config = load_config()

# 全局错误处理函数
def handle_critical_error(error_msg, error_type=None):
    """处理严重错误，进入安全模式"""
    print(f"[Main] 严重错误: {error_msg}")
    
    # 记录错误到错误处理系统
    if error_type:
        try:
            sys_error.handle_error(error_type, Exception(error_msg), "Main", sys_error.ErrorSeverity.CRITICAL)
        except Exception as e:
            print(f"[Main] 错误处理失败: {e}")
    
    # 强制进入安全模式
    try:
        sys_daemon.force_safe_mode(error_msg)
        print("[Main] 已进入安全模式，LED闪烁提示，请按RST重启")
    except Exception as e:
        print(f"[Main] 安全模式激活失败: {e}")
    
    # 进入无限循环，等待手动重启
    while True:
        try:
            # 尝试喂狗，防止看门狗重启
            _wdt.feed()
        except:
            pass
        time.sleep_ms(1000)

# 从配置中获取参数
CLIENT_ID = f"esp32c3-client-{machine.unique_id().hex()}"
MQTT_BROKER = get_config_value(config, 'mqtt', 'broker', '192.168.1.2')
MQTT_PORT = get_config_value(config, 'mqtt', 'port', 1883)
MQTT_TOPIC = get_config_value(config, 'mqtt', 'topic', 'lzs/esp32c3')
MQTT_KEEPALIVE = get_config_value(config, 'mqtt', 'keepalive', 60)
MAIN_LOOP_DELAY = get_config_value(config, 'system', 'main_loop_delay', 300)
STATUS_REPORT_INTERVAL = get_config_value(config, 'system', 'status_report_interval', 30)

# 软件看门狗实现 - 超时触发安全模式而非重启
class SoftwareWatchdog:
    def __init__(self, timeout_ms):
        self.timeout_ms = timeout_ms
        self.last_feed_time = time.ticks_ms()
        self.enabled = True
        print(f"[WDT] 软件看门狗已初始化，超时时间: {timeout_ms}ms")
    
    def feed(self):
        """喂狗"""
        if self.enabled:
            self.last_feed_time = time.ticks_ms()
    
    def check(self):
        """检查是否超时，超时则进入安全模式"""
        if not self.enabled:
            return False
        
        elapsed = time.ticks_diff(time.ticks_ms(), self.last_feed_time)
        if elapsed > self.timeout_ms:
            print(f"[WDT] 看门狗超时 ({elapsed}ms)，进入安全模式")
            self.enabled = False  # 防止重复触发
            return True
        return False
    
    def reset(self):
        """重置看门狗"""
        self.last_feed_time = time.ticks_ms()
        self.enabled = True

# 初始化软件看门狗
_wdt_timeout = get_config_value(config, 'daemon', 'wdt_timeout', 10000)
_wdt = SoftwareWatchdog(_wdt_timeout)

# 蓝牙功能已暂时屏蔽
_ble_scan_enabled = False
print("[Main] 蓝牙功能已暂时屏蔽")

# 检查WiFi配置状态
wifi_networks = get_config_value(config, 'wifi', 'networks', [])
has_wifi_config = len(wifi_networks) > 0

if has_wifi_config:
    print("[Main] 检测到WiFi配置，尝试连接...")
    
    # 配置WiFi网络
    net_wifi.set_wifi_networks(wifi_networks)
    
    # 配置WiFi参数
    wifi_config = get_config_value(config, 'wifi', 'config', {})
    if wifi_config:
        net_wifi.set_wifi_config(**wifi_config)

    # 配置MQTT参数
    mqtt_config = get_config_value(config, 'mqtt', 'config', {})
    if mqtt_config:
        net_mqtt.set_mqtt_config(**mqtt_config)

    # 配置守护进程参数
    daemon_config = get_config_value(config, 'daemon', 'config', {})
    if daemon_config:
        sys_daemon.set_daemon_config(**daemon_config)

    # 尝试连接WiFi
    print("[Main] 正在连接WiFi...")
    connection_successful = net_wifi.connect_wifi()

    if connection_successful:
        print("[Main] WiFi连接成功")
    else:
        print("[Main] WiFi连接失败")
        handle_critical_error("WiFi连接失败", sys_error.ErrorType.NETWORK)

else:
    print("[Main] 未检测到WiFi配置")
    handle_critical_error("未检测到WiFi配置", sys_error.ErrorType.CONFIG)

loop_count = 0

if connection_successful:
    print("\n[Main] WiFi Connected")

    # 创建MQTT客户端
    mqtt_server = net_mqtt.MqttServer(CLIENT_ID, MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC, keepalive=MQTT_KEEPALIVE)
    mqtt_server.connect()
    
    # 设置MQTT客户端给守护进程
    sys_daemon.set_mqtt_client(mqtt_server)
    
    # 启动守护进程
    daemon_started = sys_daemon.start_daemon()
    if not daemon_started:
        print("[Main] 守护进程启动失败")

    while True:
        # 检查软件看门狗
        if _wdt.check():
            print("[Main] 看门狗超时，强制进入安全模式")
            # 确保LED控制器已初始化
            if not hasattr(sys_daemon, '_led_controller') or sys_daemon._led_controller is None:
                print("[Main] 初始化LED控制器用于安全模式")
                import machine
                led_pins = [12, 13]
                sys_daemon._led_controller = sys_daemon.LEDController(led_pins[0], led_pins[1])
            # 强制进入安全模式
            sys_daemon.force_safe_mode("看门狗超时")
            _wdt.reset()  # 重置看门狗
        else:
            # 正常喂狗
            _wdt.feed()
        
        if loop_count % STATUS_REPORT_INTERVAL == 0:
            # 内存管理和报告
            free_memory = gc.mem_free()
            total_memory = 264192  # ESP32C3总内存约264KB
            memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100
            
            print(f"[Main] 内存: {free_memory} 字节 ({memory_usage_percent:.1f}%)")
            
            # 智能垃圾回收策略
            gc_force_threshold = get_config_value(config, 'daemon', 'gc_force_threshold', 95)
            gc_warning_threshold = gc_force_threshold - 10  # 警告阈值
            debug_mode = get_config_value(config, 'system', 'debug_mode', False)
            
            if memory_usage_percent > gc_force_threshold:
                print("[Main] 内存使用过高，执行强制垃圾回收")
                # 执行深度垃圾回收
                for _ in range(2):
                    gc.collect()
                    time.sleep_ms(50)
                free_memory_after = gc.mem_free()
                memory_usage_after = ((total_memory - free_memory_after) / total_memory) * 100
                print(f"[Main] 内存回收后: {free_memory_after} 字节 ({memory_usage_after:.1f}%)")
            elif memory_usage_percent > gc_warning_threshold:
                print("[Main] 内存使用较高，执行预防性垃圾回收")
                gc.collect()
            elif debug_mode or loop_count % 10 == 0:  # 调试模式或每10次循环回收一次
                gc.collect()
                if debug_mode:
                    print(f"[Main] 内存回收后: {gc.mem_free()} 字节")

            # 检查守护进程状态
            daemon_status = sys_daemon.get_daemon_status()
            if sys_daemon.is_safe_mode():
                print("[Main] 系统处于安全模式，暂停正常操作")
                time.sleep(1)
                continue

            # MQTT连接检查
            if not mqtt_server.is_connected:
                print("\033[1;31m[Main] MQTT断开，重新连接...\033[0m")
                mqtt_server.connect()
            else:
                mqtt_server.check_connection()
            
            # 蓝牙功能已暂时屏蔽
            # 原蓝牙扫描代码已移除

            # 发送系统状态信息
            status_msg = f"Loop: {loop_count}, 守护进程: {'活跃' if daemon_status['active'] else '停止'}, 安全模式: {'是' if daemon_status['safe_mode'] else '否'}"
            mqtt_server.log("INFO", status_msg)

        loop_count += 1
        # 使用配置的延迟时间，避免CPU空转
        time.sleep_ms(MAIN_LOOP_DELAY)

else:
    print("\n[Main] WiFi连接失败，进入安全模式")
    safe_mode_loop_count = 0
    while True:
        # 在安全模式下持续检查看门狗
        if _wdt.check():
            print("[Main] 安全模式下看门狗超时，重置看门狗")
            _wdt.reset()
        else:
            # 正常喂狗
            _wdt.feed()
        
        # 持续更新LED闪烁状态
        try:
            # 检查LED控制器是否已初始化，如果没有则直接初始化
            if not hasattr(sys_daemon, '_led_controller') or sys_daemon._led_controller is None:
                print("[Main] 初始化LED控制器用于安全模式")
                # 直接创建LED控制器实例
                import machine
                led_pins = [12, 13]  # 使用默认LED引脚
                sys_daemon._led_controller = sys_daemon.LEDController(led_pins[0], led_pins[1])
            
            # 更新LED闪烁状态 - 使用新的更新方法
            sys_daemon._led_controller.update_safe_mode_led()
            
            # 每50次循环打印一次调试信息
            if safe_mode_loop_count % 50 == 0:
                print(f"[Main] 安全模式LED状态更新中...")
        except Exception as e:
            print(f"[Main] LED状态更新失败: {e}")
        
        safe_mode_loop_count += 1
        
        time.sleep_ms(200)  # 200ms延迟，配合500ms闪烁周期确保良好效果
