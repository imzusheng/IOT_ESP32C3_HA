# -*- coding: utf-8 -*-
"""
ESP32C3主程序

集成集中配置管理、WiFi连接、MQTT通信和守护进程功能。
提供稳定可靠的IoT设备运行环境。
"""
import time
import machine
import gc
import wifi_manager
import mqtt
import daemon
import config

# 从配置中获取参数
CLIENT_ID = f"esp32c3-client-{machine.unique_id().hex()}"
MQTT_BROKER = config.MQTTConfig.BROKER
MQTT_PORT = config.MQTTConfig.PORT
MQTT_TOPIC = config.MQTTConfig.TOPIC
MQTT_KEEPALIVE = config.MQTTConfig.KEEPALIVE
MAIN_LOOP_DELAY = config.SystemConfig.MAIN_LOOP_DELAY
STATUS_REPORT_INTERVAL = config.SystemConfig.STATUS_REPORT_INTERVAL

# 初始化配置
if not config.is_config_valid():
    print("[Main] 配置验证失败，请检查配置")
    machine.reset()

loop_count = 0

connection_successful = wifi_manager.connect_wifi()

if connection_successful:
    print("\n[Main] WiFi Connected")

    # 创建MQTT客户端
    mqtt_server = mqtt.MqttServer(CLIENT_ID, MQTT_BROKER, port=MQTT_PORT, topic=MQTT_TOPIC, keepalive=MQTT_KEEPALIVE)
    mqtt_server.connect()
    
    # 设置MQTT客户端给守护进程
    daemon.set_mqtt_client(mqtt_server)
    
    # 启动守护进程
    daemon_started = daemon.start_daemon()
    if not daemon_started:
        print("[Main] 守护进程启动失败")

    while True:
        if loop_count % STATUS_REPORT_INTERVAL == 0:
            # 内存管理和报告
            free_memory = gc.mem_free()
            total_memory = 264192  # ESP32C3总内存约264KB
            memory_usage_percent = ((total_memory - free_memory) / total_memory) * 100
            
            print(f"[Main] 内存: {free_memory} 字节 ({memory_usage_percent:.1f}%)")
            
            # 根据配置进行垃圾回收
            if memory_usage_percent > config.DaemonConfig.GC_FORCE_THRESHOLD:
                print("[Main] 内存使用过高，执行强制垃圾回收")
                gc.collect()
                free_memory_after = gc.mem_free()
                memory_usage_after = ((total_memory - free_memory_after) / total_memory) * 100
                print(f"[Main] 内存回收后: {free_memory_after} 字节 ({memory_usage_after:.1f}%)")
            elif config.SystemConfig.DEBUG_MODE:
                gc.collect()
                print(f"[Main] 内存回收后: {gc.mem_free()} 字节")

            # 检查守护进程状态
            daemon_status = daemon.get_daemon_status()
            if daemon.is_safe_mode():
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
    if config.SystemConfig.AUTO_RESTART_ENABLED:
        print("[Main] 5秒后重启设备...")
        time.sleep(5)
        machine.reset()
    else:
        # 进入深度睡眠节省电量
        machine.deepsleep(60000)
