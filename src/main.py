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
import net_bt

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

# 从配置中获取参数
CLIENT_ID = f"esp32c3-client-{machine.unique_id().hex()}"
MQTT_BROKER = config_manager.get('mqtt', 'broker', '192.168.1.2')
MQTT_PORT = config_manager.get('mqtt', 'port', 1883)
MQTT_TOPIC = config_manager.get('mqtt', 'topic', 'lzs/esp32c3')
MQTT_KEEPALIVE = config_manager.get('mqtt', 'keepalive', 60)
MAIN_LOOP_DELAY = config_manager.get('system', 'main_loop_delay', 300)
STATUS_REPORT_INTERVAL = config_manager.get('system', 'status_report_interval', 30)

# 初始化蓝牙功能
print("[Main] 初始化蓝牙功能...")
bt_enabled = config_manager.get('device', 'bluetooth_enabled', True)
if bt_enabled:
    bt_initialized = net_bt.is_bluetooth_active()
    if not bt_initialized:
        print("[Main] 蓝牙功能初始化失败")
    else:
        print("[Main] 蓝牙功能初始化成功")
else:
    print("[Main] 蓝牙功能已禁用")

loop_count = 0

# 初始化看门狗 - 在主循环中喂狗，确保系统稳定运行
_wdt_timeout = config_manager.get('daemon', 'wdt_timeout', 10000)
_wdt = machine.WDT(timeout=_wdt_timeout)

# 配置WiFi网络
wifi_networks = config_manager.get('wifi', 'networks', [])
if wifi_networks:
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

connection_successful = net_wifi.connect_wifi()

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
        time.sleep(5)
        machine.reset()
    else:
        # 进入深度睡眠节省电量
        machine.deepsleep(60000)
