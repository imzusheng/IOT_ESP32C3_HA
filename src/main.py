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
import object_pool
import state_machine
import recovery_manager
import config

# =============================================================================
# 配置管理
# =============================================================================

def load_configuration(config_path='config.json'):
    """加载配置文件 - 使用配置管理器"""
    try:
        # 直接使用已导入的config模块获取配置
        config_data = config.get_config()
        print("[Main] 配置文件加载成功")
        return config_data
    except Exception as e:
        print(f"[Main] 配置文件加载失败: {e}")
        return None

def get_config_value(config_data, section, key=None, default=None):
    """获取配置值 - 使用配置管理器"""
    # 直接使用配置数据
    if key is None:
        return config_data.get(section, {})
    else:
        section_data = config_data.get(section, {})
        return section_data.get(key, default)

# =============================================================================
# 系统初始化
# =============================================================================

def initialize_system():
    """系统初始化 - 优化内存使用和状态管理"""
    print("[Main] 开始系统初始化...")
    
    # 使用对象池获取配置字典
    config_dict = object_pool.get_dict()
    
    # 加载配置
    config = load_configuration()
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
    
    # 从主配置文件加载WiFi配置
    net_wifi.load_wifi_config_from_main(config)
    
    # 从主配置文件加载守护进程配置
    sys_daemon.load_daemon_config_from_main(config)
    
    # 从主配置文件加载MQTT配置
    net_mqtt.load_mqtt_config_from_main(config)
    
    # 初始化看门狗
    initialize_watchdog(config)
    
    # 配置系统信息
    config_dict.update({
        'config': config,
        'client_id': client_id,
        'mqtt_broker': mqtt_broker,
        'mqtt_port': mqtt_port,
        'mqtt_topic': mqtt_topic,
        'mqtt_keepalive': mqtt_keepalive,
        'loop_delay': loop_delay,
        'status_interval': status_interval
    })
    
    print("[Main] 系统初始化完成")
    
    return config_dict

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
# 看门狗管理
# =============================================================================

_wdt = None
_wdt_last_feed = 0

def initialize_watchdog(config_data):
    """初始化硬件看门狗"""
    global _wdt, _wdt_last_feed
    
    try:
        wdt_enabled = get_config_value(config_data, 'daemon', 'wdt_enabled', False)
        wdt_timeout = get_config_value(config_data, 'daemon', 'wdt_timeout', 120000)
        
        if wdt_enabled:
            print(f"[Main] 启用硬件看门狗，超时时间: {wdt_timeout}ms")
            _wdt = machine.WDT(timeout=wdt_timeout)
            _wdt_last_feed = time.ticks_ms()
            return True
        else:
            print("[Main] 硬件看门狗已禁用")
            _wdt = None
            return False
            
    except Exception as e:
        print(f"[Main] 看门狗初始化失败: {e}")
        _wdt = None
        return False

def feed_watchdog():
    """喂狗操作"""
    global _wdt, _wdt_last_feed
    
    try:
        if _wdt:
            _wdt.feed()
            _wdt_last_feed = time.ticks_ms()
    except Exception as e:
        print(f"[Main] 喂狗失败: {e}")

def check_watchdog():
    """检查看门狗状态"""
    global _wdt_last_feed
    
    if _wdt:
        elapsed = time.ticks_diff(time.ticks_ms(), _wdt_last_feed)
        if elapsed > 60000:  # 超过1分钟未喂狗
            print(f"[Main] 警告：看门狗超过{elapsed}ms未喂狗")
            return False
    return True

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
    """检查系统健康状态 - 优化内存使用"""
    try:
        # 检查守护进程状态
        daemon_status = sys_daemon.get_daemon_status()
        
        # 检查内存状态
        memory_status = monitor_system_memory()
        
        # 检查错误统计
        error_stats = sys_error.get_error_stats()
        
        # 使用预分配的字典结构，避免每次创建新对象
        health_data = {
            'daemon': daemon_status,
            'memory': memory_status,
            'errors': error_stats
        }
        
        # 执行垃圾回收，释放临时变量
        gc.collect()
        
        return health_data
        
    except Exception as e:
        print(f"[Main] 系统健康检查失败: {e}")
        return None

# =============================================================================
# 安全模式处理
# =============================================================================

def handle_safe_mode(mqtt_client=None):
    """处理安全模式"""
    print("[Main] 进入安全模式处理循环")
    
    # 如果还没有进入安全模式，则强制进入
    if not sys_daemon.is_safe_mode():
        sys_daemon.force_safe_mode("系统异常")
    
    # 安全模式循环
    safe_mode_count = 0
    while sys_daemon.is_safe_mode():
        try:
            # 安全模式下也要喂狗
            feed_watchdog()
            
            # 安全模式LED控制 - SOS模式
            # 使用守护进程的公共接口更新LED状态
            sys_daemon.update_safe_mode_led()
            
            # 短暂延迟，控制SOS闪烁频率
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
    """主循环 - 使用状态机模式和优化内存管理"""
    print("[Main] 开始状态机主循环")
    
    # 获取状态机实例
    sm = state_machine.get_state_machine()
    
    # 循环计数器和配置
    loop_count = 0
    status_interval = sys_config['status_interval']
    loop_delay = sys_config['loop_delay']
    
    # 使用对象池获取缓存字典
    health_cache = object_pool.get_dict()
    status_cache = object_pool.get_dict()
    
    # 预填充状态缓存
    status_cache.update({
        'active_str': object_pool.get_string('active'),
        'inactive_str': object_pool.get_string('inactive'),
        'enabled_str': object_pool.get_string('enabled'),
        'disabled_str': object_pool.get_string('disabled')
    })
    
    # 主循环
    while True:
        try:
            # 1. 系统基础维护
            _perform_system_maintenance()
            
            # 2. 更新状态机
            state_machine.update_state_machine()
            
            # 3. 根据当前状态执行相应处理
            current_state = state_machine.get_current_state()
            _handle_state_specific_tasks(current_state, sys_config, mqtt_client, health_cache, status_cache)
            
            # 4. 定期状态报告
            if loop_count % status_interval == 0:
                _perform_status_report(loop_count, mqtt_client, health_cache, status_cache)
            
            # 5. 内存管理和优化
            if loop_count % 100 == 0:  # 每100次循环执行一次内存优化
                _perform_memory_optimization(health_cache)
            
            loop_count += 1
            time.sleep_ms(loop_delay)
            
        except KeyboardInterrupt:
            print("[Main] 用户中断，退出程序")
            break
        except Exception as e:
            print(f"[Main] 主循环异常: {e}")
            # 使用恢复管理器处理错误
            error_data = {
                'mqtt_client': mqtt_client,
                'loop_count': loop_count,
                'state': state_machine.get_current_state()
            }
            recovery_manager.handle_error_with_recovery(
                "SYSTEM_ERROR", e, "MainLoop", "HIGH", error_data
            )
            state_machine.handle_state_event(state_machine.StateEvent.SYSTEM_ERROR)
            time.sleep_ms(1000)
        
        finally:
            # 确保状态机持续运行
            if loop_count % 1000 == 0:
                state_machine.update_state_machine()

def _perform_system_maintenance():
    """执行系统基础维护任务"""
    # 喂狗
    feed_watchdog()
    
    # 检查看门狗状态
    if not check_watchdog():
        print("[Main] 看门狗状态异常，尝试恢复...")
        feed_watchdog()
        state_machine.handle_state_event(state_machine.StateEvent.WATCHDOG_TIMEOUT)

def _handle_state_specific_tasks(current_state, sys_config, mqtt_client, health_cache, status_cache):
    """根据状态执行特定任务"""
    if current_state == state_machine.SystemState.RUNNING:
        _handle_running_state(sys_config, mqtt_client, health_cache, status_cache)
    elif current_state == state_machine.SystemState.NETWORKING:
        _handle_networking_state(sys_config, mqtt_client)
    elif current_state == state_machine.SystemState.SAFE_MODE:
        _handle_safe_mode_state(mqtt_client)
    elif current_state == state_machine.SystemState.WARNING:
        _handle_warning_state(sys_config, mqtt_client, health_cache)
    elif current_state == state_machine.SystemState.ERROR:
        _handle_error_state(mqtt_client)
    elif current_state == state_machine.SystemState.RECOVERY:
        _handle_recovery_state(sys_config, mqtt_client)

def _handle_running_state(sys_config, mqtt_client, health_cache, status_cache):
    """处理运行状态"""
    # 系统监控 - 重用字典对象
    health = check_system_health()
    if health:
        health_cache.update(health)
    
    # 检查系统健康状态
    if health_cache.get('memory', {}).get('percent', 0) > 90:
        state_machine.handle_state_event(state_machine.StateEvent.MEMORY_CRITICAL)
    
    # MQTT连接检查
    if mqtt_client and not mqtt_client.is_connected:
        print("[Main] MQTT断开，尝试重连...")
        if mqtt_client.connect():
            print("[Main] MQTT重连成功")
        else:
            state_machine.handle_state_event(state_machine.StateEvent.NETWORK_FAILED)

def _handle_networking_state(sys_config, mqtt_client):
    """处理网络连接状态"""
    # 网络连接已在初始化时完成，这里主要监控
    wifi_connected = net_wifi.get_wifi_status().get('connected', False)
    if not wifi_connected:
        state_machine.handle_state_event(state_machine.StateEvent.NETWORK_FAILED)
    else:
        # 网络连接成功，尝试创建MQTT客户端
        if mqtt_client and not mqtt_client.is_connected:
            if mqtt_client.connect():
                state_machine.handle_state_event(state_machine.StateEvent.NETWORK_SUCCESS)

def _handle_safe_mode_state(mqtt_client):
    """处理安全模式状态"""
    # 安全模式处理
    if sys_daemon.is_safe_mode():
        handle_safe_mode(mqtt_client)

def _handle_warning_state(sys_config, mqtt_client, health_cache):
    """处理警告状态"""
    # 警告状态监控
    health = check_system_health()
    if health:
        health_cache.update(health)
    
    # 检查是否恢复正常
    if health_cache.get('daemon', {}).get('active', False):
        if health_cache.get('memory', {}).get('percent', 0) < 70:
            state_machine.handle_state_event(state_machine.StateEvent.RECOVERY_SUCCESS)

def _handle_error_state(mqtt_client):
    """处理错误状态"""
    # 错误状态处理
    print("[Main] 处理错误状态...")
    time.sleep_ms(1000)  # 等待恢复

def _handle_recovery_state(sys_config, mqtt_client):
    """处理恢复状态"""
    # 恢复状态处理
    print("[Main] 处理恢复状态...")
    
    # 尝试恢复网络连接
    wifi_connected = net_wifi.connect_wifi()
    if wifi_connected:
        print("[Main] 网络恢复成功")
        state_machine.handle_state_event(state_machine.StateEvent.RECOVERY_SUCCESS)
    else:
        print("[Main] 网络恢复失败")
        state_machine.handle_state_event(state_machine.StateEvent.RECOVERY_FAILED)

def _perform_status_report(loop_count, mqtt_client, health_cache, status_cache):
    """执行状态报告"""
    if not (health_cache and mqtt_client and mqtt_client.is_connected):
        return
    
    try:
        # 使用缓存字符串构建状态消息
        daemon_status = status_cache['active_str'] if health_cache.get('daemon', {}).get('active', False) else status_cache['inactive_str']
        wdt_status = status_cache['enabled_str'] if _wdt else status_cache['disabled_str']
        memory_percent = health_cache.get('memory', {}).get('percent', 0)
        current_state = state_machine.get_current_state()
        
        # 构建状态消息
        status_msg = object_pool.get_cached_string(
            "Loop:{},状态:{},内存:{:.1f}%,守护进程:{},看门狗:{}", 
            loop_count, current_state, memory_percent, daemon_status, wdt_status
        )
        
        mqtt_client.log("INFO", status_msg)
        print(f"[Main] {status_msg}")
        
    except Exception as e:
        print(f"[Main] 状态报告失败: {e}")

def _perform_memory_optimization(health_cache):
    """执行内存优化"""
    try:
        # 使用内存优化器检查内存
        memory_info = object_pool.check_memory()
        
        if memory_info and memory_info['percent'] > 85:
            print(f"[Main] 执行内存优化，当前使用率: {memory_info['percent']:.1f}%")
            
            # 清理健康缓存
            health_cache.clear()
            
            # 执行垃圾回收
            gc.collect()
            
            # 获取内存统计
            stats = object_pool.get_memory_stats()
            print(f"[Main] 内存优化完成: {stats}")
        
    except Exception as e:
        print(f"[Main] 内存优化失败: {e}")

# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序入口 - 集成状态机管理"""
    try:
        print("=== ESP32-C3 IoT设备启动 ===")
        
        # 获取状态机实例
        sm = state_machine.get_state_machine()
        
        # 初始状态：系统初始化
        print("[Main] 状态: 系统初始化")
        
        # 系统初始化
        sys_config = initialize_system()
        
        # 初始化完成，转换到网络连接状态
        if sm.handle_state_event(state_machine.StateEvent.INIT_COMPLETE):
            print("[Main] 状态转换: 网络连接")
        
        # 网络连接
        wifi_connected, error_msg = connect_networks()
        if not wifi_connected:
            print("[Main] 网络连接失败，进入警告状态")
            sm.handle_state_event(state_machine.StateEvent.NETWORK_FAILED)
            sys_daemon.force_safe_mode("网络连接失败")
        else:
            print("[Main] 网络连接成功")
            sm.handle_state_event(state_machine.StateEvent.NETWORK_SUCCESS)
        
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
            print("[Main] MQTT客户端配置完成")
        else:
            print("[Main] MQTT客户端创建失败")
            sm.handle_state_event(state_machine.StateEvent.SYSTEM_ERROR)
        
        # 启动守护进程
        daemon_started = sys_daemon.start_daemon()
        if not daemon_started:
            print("[Main] 守护进程启动失败")
            sm.handle_state_event(state_machine.StateEvent.SYSTEM_ERROR)
        else:
            print("[Main] 守护进程启动成功")
        
        # LED功能测试（仅调试模式）
        debug_mode = get_config_value(sys_config['config'], 'system', 'debug_mode', False)
        if debug_mode:
            print("[Main] 测试LED功能...")
            led_test_result = sys_daemon.test_led_functionality()
            if led_test_result:
                print("[Main] LED功能测试通过")
            else:
                print("[Main] LED功能测试失败")
        
        # 检查最终状态并进入主循环
        final_state = sm.get_current_state()
        print(f"[Main] 初始化完成，当前状态: {final_state}")
        
        # 如果处于正常运行状态，转换到运行状态
        if final_state == state_machine.SystemState.NETWORKING and wifi_connected:
            sm.handle_state_event(state_machine.StateEvent.NETWORK_SUCCESS)
        
        # 进入主循环
        main_loop(sys_config, mqtt_client)
        
    except Exception as e:
        print(f"[Main] 主程序异常: {e}")
        # 使用恢复管理器处理致命错误
        error_data = {
            'mqtt_client': mqtt_client if 'mqtt_client' in locals() else None,
            'sys_config': sys_config if 'sys_config' in locals() else None
        }
        recovery_manager.handle_error_with_recovery(
            "FATAL_ERROR", e, "Main", "CRITICAL", error_data
        )
        
        # 进入安全模式
        sys_daemon.force_safe_mode("主程序异常")
        handle_safe_mode()

# =============================================================================
# 程序入口
# =============================================================================

if __name__ == "__main__":
    main()