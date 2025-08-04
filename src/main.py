# -*- coding: utf-8 -*-
"""
ESP32C3主程序 - 重构版本

简化的主程序，专注于核心功能：
- 系统初始化和配置加载
- WiFi连接管理
- MQTT通信
- 基础系统监控
- 安全模式处理
"""

import time
import machine
import gc
import ujson
import net_wifi
import net_mqtt
import sys_daemon
import sys_error

# =============================================================================
# 配置管理
# =============================================================================

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

# =============================================================================
# 系统初始化
# =============================================================================

def initialize_system():
    """系统初始化"""
    print("[Main] 开始系统初始化...")
    
    # 加载配置
    config = load_config()
    if not config:
        print("[Main] 配置加载失败，使用默认配置")
        config = {}
    
    # 生成客户端ID
    client_id = f"esp32c3-client-{machine.unique_id().hex()}"
    
    # 获取配置参数
    mqtt_broker = get_config_value(config, 'mqtt', 'broker', '192.168.1.2')
    mqtt_port = get_config_value(config, 'mqtt', 'port', 1883)
    mqtt_topic = get_config_value(config, 'mqtt', 'topic', 'lzs/esp32c3')
    mqtt_keepalive = get_config_value(config, 'mqtt', 'keepalive', 60)
    loop_delay = get_config_value(config, 'system', 'main_loop_delay', 300)
    status_interval = get_config_value(config, 'system', 'status_report_interval', 30)
    
    # 设置WiFi网络
    wifi_networks = get_config_value(config, 'wifi', 'networks', [])
    if wifi_networks:
        net_wifi.set_wifi_networks(wifi_networks)
        wifi_config = get_config_value(config, 'wifi', 'config', {})
        if wifi_config:
            net_wifi.set_wifi_config(**wifi_config)
    
    # 设置守护进程配置
    daemon_config = get_config_value(config, 'daemon', 'config', {})
    if daemon_config:
        sys_daemon.set_daemon_config(**daemon_config)
    
    print("[Main] 系统初始化完成")
    
    return {
        'config': config,
        'client_id': client_id,
        'mqtt_broker': mqtt_broker,
        'mqtt_port': mqtt_port,
        'mqtt_topic': mqtt_topic,
        'mqtt_keepalive': mqtt_keepalive,
        'loop_delay': loop_delay,
        'status_interval': status_interval
    }

# =============================================================================
# 网络连接
# =============================================================================

def connect_networks():
    """连接网络"""
    print("[Main] 开始网络连接...")
    
    # 连接WiFi
    wifi_connected = net_wifi.connect_wifi()
    if not wifi_connected:
        print("[Main] WiFi连接失败")
        return False, None
    
    print("[Main] 网络连接成功")
    return True, None

# =============================================================================
# MQTT客户端管理
# =============================================================================

def create_mqtt_client(client_id, broker, port=1883, topic='lzs/esp32c3', keepalive=60):
    """创建MQTT客户端"""
    try:
        mqtt_client = net_mqtt.MqttServer(
            client_id, broker, port=port, 
            topic=topic, keepalive=keepalive
        )
        
        # 连接MQTT
        if mqtt_client.connect():
            print("[Main] MQTT连接成功")
            return mqtt_client
        else:
            print("[Main] MQTT连接失败")
            return None
            
    except Exception as e:
        print(f"[Main] MQTT客户端创建失败: {e}")
        return None

# =============================================================================
# 系统监控
# =============================================================================

def monitor_system_memory():
    """监控系统内存"""
    try:
        free_memory = gc.mem_free()
        total_memory = 264192  # ESP32C3总内存约264KB
        memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100
        
        # 智能垃圾回收
        if memory_usage_percent > 95:
            print("[Main] 内存使用过高，执行强制垃圾回收")
            for _ in range(2):
                gc.collect()
                time.sleep_ms(50)
        elif memory_usage_percent > 85:
            print("[Main] 内存使用较高，执行预防性垃圾回收")
            gc.collect()
        
        return {
            'free': free_memory,
            'total': total_memory,
            'percent': memory_usage_percent
        }
        
    except Exception as e:
        print(f"[Main] 内存监控失败: {e}")
        return None

def check_system_health():
    """检查系统健康状态"""
    try:
        # 检查守护进程状态
        daemon_status = sys_daemon.get_daemon_status()
        
        # 检查内存状态
        memory_status = monitor_system_memory()
        
        # 检查错误统计
        error_stats = sys_error.get_error_stats()
        
        return {
            'daemon': daemon_status,
            'memory': memory_status,
            'errors': error_stats
        }
        
    except Exception as e:
        print(f"[Main] 系统健康检查失败: {e}")
        return None

# =============================================================================
# 安全模式处理
# =============================================================================

def handle_safe_mode(mqtt_client=None):
    """处理安全模式"""
    print("[Main] 进入安全模式处理循环")
    
    # 强制进入安全模式（这会初始化LED控制器）
    sys_daemon.force_safe_mode("系统异常")
    
    # 安全模式循环
    safe_mode_count = 0
    while sys_daemon.is_safe_mode():
        try:
            # 安全模式LED控制 - 闪烁模式
            # 通过守护进程的LED控制器实现闪烁效果
            daemon_status = sys_daemon.get_daemon_status()
            if daemon_status and hasattr(sys_daemon, '_led_controller') and sys_daemon._led_controller:
                # 使用LED控制器的闪烁功能
                sys_daemon._led_controller.update_safe_mode_led()
            
            # 短暂延迟，控制闪烁频率
            time.sleep_ms(100)
            
            # 每100次循环检查一次恢复条件
            safe_mode_count += 1
            if safe_mode_count % 100 == 0:
                sys_daemon.check_safe_mode_recovery()
                if not sys_daemon.is_safe_mode():
                    print("[Main] 安全模式已退出")
                    break
                    
        except Exception as e:
            print(f"[Main] 安全模式处理异常: {e}")
            time.sleep_ms(500)

# =============================================================================
# 主循环
# =============================================================================

def main_loop(sys_config, mqtt_client):
    """主循环"""
    print("[Main] 开始主循环")
    
    loop_count = 0
    status_interval = sys_config['status_interval']
    loop_delay = sys_config['loop_delay']
    
    while True:
        try:
            # 系统监控
            health = check_system_health()
            
            # 检查安全模式
            if sys_daemon.is_safe_mode():
                handle_safe_mode(mqtt_client)
                continue
            
            # MQTT连接检查
            if mqtt_client and not mqtt_client.is_connected:
                print("[Main] MQTT断开，尝试重连...")
                mqtt_client.connect()
            
            # 定期状态报告
            if loop_count % status_interval == 0:
                if health and mqtt_client and mqtt_client.is_connected:
                    status_msg = f"Loop:{loop_count}, 内存:{health['memory']['percent']:.1f}%, 守护进程:{'活跃' if health['daemon']['active'] else '停止'}"
                    mqtt_client.log("INFO", status_msg)
                    
                    # 打印到串口
                    print(f"[Main] {status_msg}")
            
            loop_count += 1
            time.sleep_ms(loop_delay)
            
        except KeyboardInterrupt:
            print("[Main] 用户中断，退出程序")
            break
        except Exception as e:
            print(f"[Main] 主循环异常: {e}")
            sys_error.handle_error("SYSTEM_ERROR", e, "MainLoop")
            time.sleep_ms(1000)

# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序入口"""
    try:
        print("=== ESP32-C3 IoT设备启动 ===")
        
        # 系统初始化
        sys_config = initialize_system()
        
        # 网络连接
        wifi_connected, error_msg = connect_networks()
        if not wifi_connected:
            print("[Main] 网络连接失败，进入安全模式")
            sys_daemon.force_safe_mode("网络连接失败")
            handle_safe_mode()
            return
        
        # 创建MQTT客户端
        mqtt_client = create_mqtt_client(
            sys_config['client_id'],
            sys_config['mqtt_broker'],
            sys_config['mqtt_port'],
            sys_config['mqtt_topic'],
            sys_config['mqtt_keepalive']
        )
        
        if mqtt_client:
            # 设置MQTT客户端给其他模块
            sys_daemon.set_mqtt_client(mqtt_client)
            sys_error.set_mqtt_client(mqtt_client)
        
        # 启动守护进程
        daemon_started = sys_daemon.start_daemon()
        if not daemon_started:
            print("[Main] 守护进程启动失败")
        
        # LED功能测试
        print("[Main] 测试LED功能...")
        led_test_result = sys_daemon.test_led_functionality()
        if led_test_result:
            print("[Main] LED功能测试通过")
        else:
            print("[Main] LED功能测试失败")
        
        # 进入主循环
        main_loop(sys_config, mqtt_client)
        
    except Exception as e:
        print(f"[Main] 主程序异常: {e}")
        sys_error.handle_error("FATAL_ERROR", e, "Main")
        
        # 进入安全模式
        sys_daemon.force_safe_mode("主程序异常")
        handle_safe_mode()

# =============================================================================
# 程序入口
# =============================================================================

if __name__ == "__main__":
    main()