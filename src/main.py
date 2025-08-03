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
# 蓝牙扫描器模块
import ble_scanner

# 配置管理
class ConfigManager:
    """配置管理器 - 从JSON文件加载配置"""
    
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.config = None
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r') as f:
                self.config = ujson.load(f)
            print("[Main] 配置文件加载成功")
            return True
        except Exception as e:
            print(f"[Main] 配置文件加载失败: {e}")
            return False
    
    def get(self, section, key=None, default=None):
        """获取配置值"""
        if not self.config:
            return default
        
        if key is None:
            return self.config.get(section, default)
        
        section_config = self.config.get(section, {})
        return section_config.get(key, default)
    
    def set(self, section, key, value):
        """设置配置值"""
        if not self.config:
            return False
        
        if section not in self.config:
            self.config[section] = {}
        
        self.config[section][key] = value
        
        try:
            with open(self.config_path, 'w') as f:
                ujson.dump(self.config, f)
            return True
        except Exception as e:
            print(f"[Main] 保存配置失败: {e}")
            return False

# 初始化配置管理器
config_manager = ConfigManager()

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
MQTT_BROKER = config_manager.get('mqtt', 'broker', '192.168.1.2')
MQTT_PORT = config_manager.get('mqtt', 'port', 1883)
MQTT_TOPIC = config_manager.get('mqtt', 'topic', 'lzs/esp32c3')
MQTT_KEEPALIVE = config_manager.get('mqtt', 'keepalive', 60)
MAIN_LOOP_DELAY = config_manager.get('system', 'main_loop_delay', 300)
STATUS_REPORT_INTERVAL = config_manager.get('system', 'status_report_interval', 30)

# 初始化看门狗 - 在主循环中喂狗，确保系统稳定运行
_wdt_timeout = config_manager.get('daemon', 'wdt_timeout', 10000)
_wdt = machine.WDT(timeout=_wdt_timeout)

# 初始化蓝牙扫描器
_ble_scanner = None
_ble_scan_enabled = config_manager.get('bluetooth', 'scan_enabled', False)
_ble_scan_interval = config_manager.get('bluetooth', 'scan_interval', 300)  # 5分钟
_ble_max_devices = config_manager.get('bluetooth', 'max_devices', 10)
_ble_scan_duration = config_manager.get('bluetooth', 'scan_duration', 8000)
_ble_memory_threshold = config_manager.get('bluetooth', 'memory_threshold', 90)
_last_ble_scan = 0

if _ble_scan_enabled:
    print("[Main] 蓝牙扫描功能已启用")
    print(f"[Main] 扫描间隔: {_ble_scan_interval}秒, 最大设备数: {_ble_max_devices}")
    try:
        _ble_scanner = ble_scanner.get_ble_scanner()
        _ble_scanner.max_devices = _ble_max_devices  # 设置最大设备数
        if _ble_scanner.initialize():
            print("[Main] 蓝牙扫描器初始化成功")
        else:
            print("[Main] 蓝牙扫描器初始化失败")
            _ble_scanner = None
    except Exception as e:
        print(f"[Main] 蓝牙扫描器初始化异常: {e}")
        _ble_scanner = None

# 检查WiFi配置状态
wifi_networks = config_manager.get('wifi', 'networks', [])
has_wifi_config = len(wifi_networks) > 0

if has_wifi_config:
    print("[Main] 检测到WiFi配置，尝试连接...")
    
    # 配置WiFi网络
    net_wifi.set_wifi_networks(wifi_networks)
    
    # 配置WiFi参数
    wifi_config = config_manager.get('wifi', 'config', {})
    if wifi_config:
        net_wifi.set_wifi_config(**wifi_config)

    # 配置MQTT参数
    mqtt_config = config_manager.get('mqtt', 'config', {})
    if mqtt_config:
        net_mqtt.set_mqtt_config(**mqtt_config)

    # 配置守护进程参数
    daemon_config = config_manager.get('daemon', 'config', {})
    if daemon_config:
        sys_daemon.set_daemon_config(**daemon_config)

    # 尝试连接WiFi
    print("[Main] 正在连接WiFi...")
    connection_successful = net_wifi.connect_wifi()

    if connection_successful:
        print("[Main] WiFi连接成功")
    else:
        print("[Main] WiFi连接失败，蓝牙功能已停用")
        handle_critical_error("WiFi连接失败，蓝牙功能已停用", sys_error.ErrorType.NETWORK)

else:
    print("[Main] 未检测到WiFi配置，蓝牙功能已停用")
    handle_critical_error("未检测到WiFi配置，蓝牙功能已停用", sys_error.ErrorType.CONFIG)

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
        # 在主循环中喂狗（最高优先级），确保系统稳定运行
        _wdt.feed()
        
        if loop_count % STATUS_REPORT_INTERVAL == 0:
            # 内存管理和报告
            free_memory = gc.mem_free()
            total_memory = 264192  # ESP32C3总内存约264KB
            memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100
            
            print(f"[Main] 内存: {free_memory} 字节 ({memory_usage_percent:.1f}%)")
            
            # 根据配置进行垃圾回收
            gc_force_threshold = config_manager.get('daemon', 'gc_force_threshold', 95)
            debug_mode = config_manager.get('system', 'debug_mode', False)
            
            if memory_usage_percent > gc_force_threshold:
                print("[Main] 内存使用过高，执行强制垃圾回收")
                gc.collect()
                free_memory_after = gc.mem_free()
                memory_usage_after = ((total_memory - free_memory_after) / total_memory) * 100
                print(f"[Main] 内存回收后: {free_memory_after} 字节 ({memory_usage_after:.1f}%)")
            elif debug_mode:
                gc.collect()
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
            
            # 蓝牙设备扫描
            if _ble_scan_enabled and _ble_scanner:
                current_time = time.time()
                if current_time - _last_ble_scan >= _ble_scan_interval:
                    # 检查内存使用情况
                    free_memory = gc.mem_free()
                    total_memory = 264192  # ESP32C3总内存约264KB
                    memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100
                    
                    if memory_usage_percent > _ble_memory_threshold:
                        print(f"[Main] 内存使用过高 ({memory_usage_percent:.1f}%)，跳过蓝牙扫描")
                        _last_ble_scan = current_time
                        continue
                    
                    print("[Main] 开始蓝牙设备扫描...")
                    try:
                        # 执行垃圾回收
                        gc.collect()
                        
                        # 开始扫描
                        if _ble_scanner.start_scan(_ble_scan_duration):
                            # 等待扫描完成
                            scan_start = time.ticks_ms()
                            scan_timeout = _ble_scan_duration + 2000  # 扫描时间 + 2秒缓冲
                            while _ble_scanner.scanning:
                                if time.ticks_diff(time.ticks_ms(), scan_start) > scan_timeout:
                                    print("[Main] 蓝牙扫描超时")
                                    break
                                time.sleep_ms(100)
                            
                            # 获取扫描结果
                            devices = _ble_scanner.get_scan_results_sorted_by_rssi()
                            
                            if devices:
                                print(f"[Main] 发现 {len(devices)} 个蓝牙设备")
                                
                                # 发送设备信息到MQTT
                                device_list = []
                                for device in devices[:5]:  # 限制发送前5个设备
                                    device_info = {
                                        'address': device.get('address', ''),
                                        'name': device.get('name', ''),
                                        'rssi': device.get('rssi', -100)
                                    }
                                    device_list.append(device_info)
                                
                                # 发送蓝牙扫描结果
                                ble_msg = {
                                    'type': 'ble_scan',
                                    'device_count': len(devices),
                                    'devices': device_list,
                                    'timestamp': current_time
                                }
                                mqtt_server.log("BLE", ujson.dumps(ble_msg))
                            else:
                                print("[Main] 未发现蓝牙设备")
                                
                            # 清空扫描结果
                            _ble_scanner.clear_scan_results()
                        
                        _last_ble_scan = current_time
                        
                        # 执行垃圾回收
                        gc.collect()
                        
                    except Exception as e:
                        print(f"[Main] 蓝牙扫描异常: {e}")
                        # 发生错误时重置扫描器
                        try:
                            _ble_scanner.deinitialize()
                            _ble_scanner.initialize()
                        except:
                            pass

            # 发送系统状态信息
            status_msg = f"Loop: {loop_count}, 守护进程: {'活跃' if daemon_status['active'] else '停止'}, 安全模式: {'是' if daemon_status['safe_mode'] else '否'}"
            mqtt_server.log("INFO", status_msg)

        loop_count += 1
        # 使用配置的延迟时间，避免CPU空转
        time.sleep_ms(MAIN_LOOP_DELAY)

else:
    print("\n[Main] WiFi连接失败，进入深度睡眠")
    # 如果配置了自动重启，则重启设备
    auto_restart_enabled = config_manager.get('system', 'auto_restart_enabled', False)
    if auto_restart_enabled:
        print("[Main] 5秒后重启设备...")
        print("[Main] 进入安全模式，请手动重启设备")
        handle_critical_error("WiFi连接失败，需要手动重启", sys_error.ErrorType.NETWORK)
    else:
        # 进入深度睡眠节省电量
        machine.deepsleep(60000)
