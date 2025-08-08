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
import net_wifi
import net_mqtt
import sys_daemon
from lib.sys import logger as sys_error
from lib.sys import memo as object_pool
from lib import utils
from lib.sys import fsm as state_machine
from lib.sys import erm as recovery_manager
from lib.sys import led as led_preset
import config

# =============================================================================
# 配置管理
# =============================================================================

def load_configuration():
    """加载配置文件 - 使用配置管理器"""
    try:
        # 直接使用已导入的config模块获取配置
        config_data = config.get_config()
        print("[Main] Config loaded successfully")
        return config_data
    except Exception as e:
        print(f"[Main] Config load failed: {e}")
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
    print("[Main] Starting system initialization...")
    
    # 使用对象池获取配置字典
    config_dict = object_pool.get_dict()
    
    # 加载配置
    config = load_configuration()
    if not config:
        print("[Main] Config load failed, using defaults")
        config = {}
    
    # 生成客户端ID
    client_id = f"esp32c3-client-{machine.unique_id().hex()}"
    
    # 获取配置参数
    mqtt_broker = get_config_value(config, 'mqtt', 'broker', '192.168.3.15')
    mqtt_port = get_config_value(config, 'mqtt', 'port', 1883)
    mqtt_topic = get_config_value(config, 'mqtt', 'topic', 'lzs/esp32c3')
    mqtt_keepalive = get_config_value(config, 'mqtt', 'keepalive', 60)
    loop_delay = get_config_value(config, 'system', 'main_loop_delay', 300)
    status_interval = get_config_value(config, 'system', 'status_report_interval', 30)
    
    # 获取LED引脚配置
    led_pins = get_config_value(config, 'daemon', 'led_pins', [12, 13])
    
    # 早期初始化LED控制器
    print("[Main] Initializing LED controller...")
    try:
        # 创建全局LED控制器实例
        global led_controller
        led_controller = led_preset.LEDPatternController(led_pins)
        if led_controller:
            print("[Main] LED controller initialized successfully")
            # 设置初始状态为巡航模式
            led_controller.play('cruise')
            print("[Main] LED set to cruise mode")
        else:
            print("[Main] LED controller initialization failed")
    except Exception as e:
        print(f"[Main] ERROR: LED controller initialization error: {e}")
    
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
    
    print("[Main] System initialization complete")
    
    return config_dict

# =============================================================================
# 网络连接
# =============================================================================

def connect_networks():
    """连接网络"""
    print("[Main] Starting network connection...")
    
    # 连接WiFi
    wifi_connected = net_wifi.connect_wifi()
    if not wifi_connected:
        print("[Main] WiFi connection failed")
        return False, None
    
    print("[Main] Network connection successful")
    return True, None

# =============================================================================
# MQTT客户端管理
# =============================================================================

def create_mqtt_client(client_id, broker, port=1883, topic='lzs/esp32c3', keepalive=60):
    """创建并初始化全局MQTT客户端实例"""
    try:
        # 使用服务模块初始化客户端
        mqtt_client = net_mqtt.init_client(
            client_id, broker, port=port, 
            topic=topic, keepalive=keepalive
        )
        
        # 尝试连接MQTT，但即使失败也返回客户端对象
        # 这样可以在错误状态下继续使用退避重连机制
        if mqtt_client.connect():
            print("[Main] MQTT connection successful")
        else:
            print("[Main] MQTT connection failed - will retry in error state")
        
        return mqtt_client
            
    except Exception as e:
        print(f"[Main] MQTT client creation failed: {e}")
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
        
        # 验证超时参数
        if wdt_timeout < 1000:
            print(f"[Main] Warning: WDT timeout too short ({wdt_timeout}ms), using minimum 1000ms")
            wdt_timeout = 1000
        elif wdt_timeout > 300000:
            print(f"[Main] Warning: WDT timeout too long ({wdt_timeout}ms), using maximum 300000ms")
            wdt_timeout = 300000
        
        if wdt_enabled:
            print(f"[Main] Hardware watchdog enabled, timeout: {wdt_timeout}ms")
            
            # 尝试不同的 WDT 初始化方式
            try:
                # 方法1: 使用 timeout 参数（标准方式）
                _wdt = machine.WDT(timeout=wdt_timeout)
                print("[Main] WDT initialized with timeout parameter")
            except TypeError as e:
                print(f"[Main] WDT timeout parameter failed: {e}")
                try:
                    # 方法2: 使用 position 参数（某些版本）
                    _wdt = machine.WDT(wdt_timeout)
                    print("[Main] WDT initialized with positional parameter")
                except Exception as e2:
                    print(f"[Main] WDT positional parameter failed: {e2}")
                    try:
                        # 方法3: 使用毫秒参数
                        _wdt = machine.WDT(timeout_ms=wdt_timeout)
                        print("[Main] WDT initialized with timeout_ms parameter")
                    except Exception as e3:
                        print(f"[Main] WDT timeout_ms parameter failed: {e3}")
                        print("[Main] All WDT initialization methods failed, disabling watchdog")
                        _wdt = None
                        return False
            
            _wdt_last_feed = time.ticks_ms()
            return True
        else:
            print("[Main] Hardware watchdog disabled")
            _wdt = None
            return False
            
    except Exception as e:
        print(f"[Main] Watchdog initialization failed: {e}")
        _wdt = None
        return False

def feed_watchdog():
    """喂狗操作"""
    global _wdt, _wdt_last_feed
    
    try:
        if _wdt:
            _wdt.feed()
            _wdt_last_feed = time.ticks_ms()
        else:
            # 如果看门狗未初始化，记录但不报错
            pass
    except Exception as e:
        print(f"[Main] Watchdog feed failed: {e}")
        # 喂狗失败时，尝试重新初始化看门狗
        try:
            _wdt = None
            print("[Main] Watchdog disabled due to feed failure")
        except:
            pass

def check_watchdog():
    """检查看门狗状态"""
    global _wdt_last_feed
    
    try:
        if _wdt:
            elapsed = time.ticks_diff(time.ticks_ms(), _wdt_last_feed)
            if elapsed > config.get_config('daemon', 'safe_mode_cooldown', 60000):  # 超过安全模式冷却时间未喂狗
                print(f"[Main] Warning: watchdog not fed for {elapsed}ms")
                return False
        return True
    except Exception as e:
        print(f"[Main] Watchdog check failed: {e}")
        return False

# =============================================================================
# 系统监控
# =============================================================================

def monitor_system_memory():
    """监控系统内存"""
    try:
        # 使用utils模块的内存检查函数
        memory_status = utils.check_memory()
        
        if memory_status:
            # 智能垃圾回收
            if memory_status['percent'] > 95:
                print("[Main] High memory usage, forcing garbage collection")
                for _ in range(2):
                    gc.collect()
                    time.sleep_ms(50)
            elif memory_status['percent'] > 85:
                print("[Main] High memory usage, preventive garbage collection")
                gc.collect()
            
            return memory_status
        
        return None
        
    except Exception as e:
        print(f"[Main] Memory monitoring failed: {e}")
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
        
        # 检查温度状态
        temp = utils.get_temperature()
        temp_status = {'value': temp, 'celsius': f"{temp:.1f}" if temp is not None else "N/A"}
        
        # 使用预分配的字典结构，避免每次创建新对象
        health_data = {
            'daemon': daemon_status,
            'memory': memory_status,
            'errors': error_stats,
            'temperature': temp_status
        }
        
        # 执行垃圾回收，释放临时变量
        gc.collect()
        
        return health_data
        
    except Exception as e:
        print(f"[Main] System health check failed: {e}")
        # 系统健康检查失败时触发系统警告事件
        state_machine.handle_event(state_machine.StateEvent.SYSTEM_WARNING)
        return None

# =============================================================================
# 安全模式处理
# =============================================================================

def handle_safe_mode(mqtt_client=None):
    """处理安全模式 - 非阻塞方式"""
    print("[Main] Entering safe mode processing")
    
    # 如果还没有进入安全模式，则强制进入
    if not sys_daemon.is_safe_mode():
        print("[Main] Forcing safe mode entry...")
        sys_daemon.force_safe_mode("系统异常")
        print("[Main] Safe mode forced, LED should be showing SOS pattern")
    
    # 安全模式处理现在由状态机统一处理
    # LED更新由LED模块的硬件定时器或uasyncio自动处理
    print("[Main] Safe mode processing delegated to state machine")
    
    # 安全模式下的特殊处理（如果需要）
    if sys_daemon.is_safe_mode():
        # 深度垃圾回收
        for _ in range(2):
            gc.collect()
            time.sleep_ms(50)

# =============================================================================
# 主循环
# =============================================================================

def main_loop(sys_config, mqtt_client, main_start_time):
    """主循环 - 使用状态机模式和优化内存管理"""
    print("[Main] Starting state machine main loop")
    
    # 获取状态机实例
    sm = state_machine.get_state_machine()
    
    # 循环计数器和配置
    loop_count = 0
    status_interval = sys_config['status_interval']
    loop_delay = sys_config['loop_delay']
    
    # --- 内存优化: 预定义状态字符串模板 ---
    core_msg_template = "[Main] Loop:{},state:{},uptime:{}s,memory:{:.1f}%,temp:{},daemon:{},watchdog:{}"
    
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
            
            # 5. 定期状态报告
            if loop_count % status_interval == 0:
                # --- 内存优化: 传入预定义的模板 ---
                _perform_status_report(loop_count, mqtt_client, health_cache, status_cache, main_start_time, core_msg_template)
            
            # 6. 内存管理和优化
            if loop_count % 100 == 0:  # 每100次循环执行一次内存优化
                _perform_memory_optimization(health_cache)
            
            loop_count += 1
            time.sleep_ms(loop_delay)
            
        except KeyboardInterrupt:
            print("[Main] User interrupted, exiting program")
            break
        except Exception as e:
            print(f"[Main] Main loop error: {e}")
            # 使用恢复管理器处理错误
            error_data = {
                'loop_count': loop_count,
                'state': state_machine.get_current_state()
            }
            recovery_manager.handle_error_with_recovery(
                "SYSTEM_ERROR", e, "MainLoop", "HIGH", error_data
            )
            state_machine.handle_event(state_machine.StateEvent.SYSTEM_ERROR)
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
        print("[Main] Watchdog status abnormal, attempting recovery...")
        feed_watchdog()
        state_machine.handle_event(state_machine.StateEvent.WATCHDOG_TIMEOUT)

def _update_led_for_state(current_state):
    """根据状态更新LED显示 - 现在由状态机自动处理，保留此函数以保持兼容性"""
    # LED状态现在由状态机自动处理，无需在此处手动设置
    # 此函数保留以保持代码兼容性，防止可能的调用错误
    pass

def _handle_state_specific_tasks(current_state, sys_config, mqtt_client, health_cache, status_cache):
    """根据状态执行特定任务"""
    # 首先根据状态更新LED显示
    _update_led_for_state(current_state)
    
    # 状态机已经内置了状态处理逻辑，这里只需要处理一些特定于main.py的逻辑
    if current_state == state_machine.SystemState.RUNNING:
        # 运行状态下的额外处理
        if mqtt_client and not mqtt_client.is_connected:
            print("[Main] MQTT disconnected, attempting reconnect...")
            if mqtt_client.connect():
                print("[Main] MQTT reconnection successful")
            else:
                state_machine.handle_event(state_machine.StateEvent.NETWORK_FAILED)
        
        # 系统监控 - 重用字典对象
        health = check_system_health()
        if health:
            health_cache.update(health)
            
            # 检查系统健康状态
            if health_cache.get('memory', {}).get('percent', 0) > 90:
                state_machine.handle_event(state_machine.StateEvent.MEMORY_CRITICAL)
    
    elif current_state == state_machine.SystemState.NETWORKING:
        # 网络连接状态下的额外处理
        if mqtt_client and not mqtt_client.is_connected:
            if mqtt_client.connect():
                state_machine.handle_event(state_machine.StateEvent.NETWORK_SUCCESS)

def _perform_status_report(loop_count, mqtt_client, health_cache, status_cache, main_start_time, core_template):
    """执行状态报告 - 经过内存优化并保持日志格式一致"""
    if not health_cache:
        return
    
    try:
        # 计算系统运行时间
        uptime = time.ticks_diff(time.ticks_ms(), main_start_time) // 1000
        
        # 使用缓存字符串构建状态消息
        daemon_status = status_cache['active_str'] if health_cache.get('daemon', {}).get('active', False) else status_cache['inactive_str']
        wdt_status = status_cache['enabled_str'] if _wdt else status_cache['disabled_str']
        memory_percent = health_cache.get('memory', {}).get('percent', 0)
        
        # --- 内存优化: 使用 memo.get_string 获取状态名的缓存实例 ---
        current_state_name = object_pool.get_string(state_machine.get_current_state())
        
        # 使用健康缓存中的温度信息
        temp_str = health_cache.get('temperature', {}).get('celsius', 'N/A')
        
        # --- 内存优化: 使用预定义的模板格式化核心消息 ---
        core_msg = core_template.format(
            loop_count, current_state_name, uptime, memory_percent, temp_str, daemon_status, wdt_status
        )
        
        # --- 日志格式修正 ---
        # 1. 为本地控制台打印完整的带时间戳的日志
        timestamp = utils.get_formatted_time()
        console_log_msg = "[INFO][" + timestamp + "]" + core_msg
        print(console_log_msg)

        # 2. 如果MQTT客户端存在且已连接，则发送核心消息
        #    net_mqtt.log() 会自动处理 [INFO] 和时间戳前缀
        if mqtt_client and mqtt_client.is_connected:
            mqtt_client.log("INFO", core_msg)
        
    except Exception as e:
        print(f"[Main] Status report failed: {e}")
        # 状态报告失败时触发系统警告事件，以便LED能够响应
        state_machine.handle_event(state_machine.StateEvent.SYSTEM_WARNING)

def _perform_memory_optimization(health_cache):
    """执行内存优化"""
    try:
        # 使用内存优化器检查内存
        memory_info = utils.check_memory()
        
        if memory_info and memory_info['percent'] > 85:
            print(f"[Main] Memory optimization, current usage: {memory_info['percent']:.1f}%")
            
            # 清理健康缓存
            health_cache.clear()
            
            # 执行垃圾回收
            gc.collect()
            
            # 获取内存统计
            stats = object_pool.get_all_stats()
            print(f"[Main] Memory optimization complete: {stats}")
        
    except Exception as e:
        print(f"[Main] Memory optimization failed: {e}")
        # 内存优化失败可能表示内存严重问题，触发内存临界事件
        state_machine.handle_event(state_machine.StateEvent.MEMORY_CRITICAL)


# =============================================================================
# 主程序入口
# =============================================================================

def main():
    """主程序入口 - 集成状态机管理"""
    try:
        print("=== ESP32-C3 IoT Device Starting ===")
        
        # 记录系统启动时间
        main_start_time = time.ticks_ms()
        
        # 获取状态机实例
        sm = state_machine.get_state_machine()
        
        # 初始状态：系统初始化
        print("[Main] Status: System initialization")
        
        # 系统初始化
        sys_config = initialize_system()
        
        # 初始化完成，转换到网络连接状态
        if state_machine.handle_event(state_machine.StateEvent.INIT_COMPLETE):
            print("[Main] State transition: Network connection")
        
        # 网络连接
        print("[Main] Starting network connection...")
        wifi_connected, error_msg = connect_networks()
        if not wifi_connected:
            print("[Main] Network connection failed")
            print("[Main] Entering warning state due to network failure")
            state_machine.handle_event(state_machine.StateEvent.NETWORK_FAILED)
            print("[Main] Forcing safe mode due to network failure")
            sys_daemon.force_safe_mode("网络连接失败")
            print("[Main] Safe mode activated, LED should show SOS pattern")
        else:
            state_machine.handle_event(state_machine.StateEvent.NETWORK_SUCCESS)
        
        # 创建MQTT客户端
        mqtt_client = create_mqtt_client(
            sys_config['client_id'],
            sys_config['mqtt_broker'],
            sys_config['mqtt_port'],
            sys_config['mqtt_topic'],
            sys_config['mqtt_keepalive']
        )
        
        # 检查MQTT客户端是否已通过服务初始化
        if net_mqtt.is_ready():
            print("[Main] MQTT client has been initialized via service.")
        else:
            print("[Main] MQTT client creation failed - continuing without MQTT")
        
        # 启动守护进程
        daemon_started = sys_daemon.start_daemon()
        if not daemon_started:
            print("[Main] Daemon startup failed")
            state_machine.handle_event(state_machine.StateEvent.SYSTEM_ERROR)
        else:
            print("[Main] Daemon startup successful")
        
        # LED功能测试（仅调试模式）
        debug_mode = get_config_value(sys_config['config'], 'system', 'debug_mode', False)
        if debug_mode:
            print("[Main] Testing LED functionality...")
            try:
                # 测试LED控制器
                if 'led_controller' in globals():
                    led_controller.play('blink')
                    print("[Main] LED functionality test passed")
                else:
                    print("[Main] LED controller not available")
            except Exception as e:
                print(f"[Main] LED functionality test failed: {e}")
        
        # 检查最终状态并进入主循环
        final_state = sm.get_current_state()
        print(f"[Main] Initialization complete, current state: {final_state}")
        
        # 如果处于正常运行状态，转换到运行状态
        if final_state == state_machine.SystemState.NETWORKING and wifi_connected:
            state_machine.handle_event(state_machine.StateEvent.NETWORK_SUCCESS)
        
        # 进入主循环
        main_loop(sys_config, mqtt_client, main_start_time)
        
    except Exception as e:
        print(f"[Main] Main program error: {e}")
        # 使用恢复管理器处理致命错误
        error_data = {
            'sys_config': sys_config if 'sys_config' in locals() else None
        }
        recovery_manager.handle_error_with_recovery(
            "FATAL_ERROR", e, "Main", "CRITICAL", error_data
        )
        
        # 进入安全模式
        sys_daemon.force_safe_mode("主程序异常")
        handle_safe_mode()
        
    finally:
        # 程序退出时清理LED资源
        try:
            if 'led_controller' in globals():
                globals()['led_controller'].cleanup()
                print("[Main] LED controller cleaned up")
        except Exception as e:
            print(f"[Main] LED controller cleanup failed: {e}")

# =============================================================================
# 程序入口
# =============================================================================

if __name__ == "__main__":
    main()