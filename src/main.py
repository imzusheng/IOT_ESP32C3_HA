# -*- coding: utf-8 -*-
import time
import machine
import gc
import wifi_manager
import mqtt
import daemon

# --- MQTT 配置 ---
MQTT_BROKER = "192.168.1.2"
MQTT_TOPIC = "lzs/esp32c3"
CLIENT_ID = f"esp32c3-client-{machine.unique_id().hex()}"

loop_count = 0

connection_successful = wifi_manager.connect_wifi()

if connection_successful:
    print("\n[Main] WiFi Connected")

    mqtt_server = mqtt.MqttServer(CLIENT_ID, MQTT_BROKER, topic=MQTT_TOPIC)
    mqtt_server.connect()
    
    # 设置MQTT客户端给守护进程
    daemon.set_mqtt_client(mqtt_server)
    
    # 启动守护进程
    daemon_started = daemon.start_daemon()
    if not daemon_started:
        print("[Main] 守护进程启动失败")

    while True:
        if loop_count % 30 == 0:
            print(gc.mem_free())
            gc.collect()
            print(gc.mem_free())

            # 检查守护进程状态
            daemon_status = daemon.get_daemon_status()
            if daemon.is_safe_mode():
                print("[Main] 系统处于安全模式，暂停正常操作")
                time.sleep(1)
                continue

            if not mqtt_server.is_connected:
                print("\033[1;31m[Main] MQTT Disconnected, Reconnecting...\033[0m")
                mqtt_server.connect()
            else:
                # mqtt_server.log("INFO", "Ping")
                mqtt_server.check_connection()
            
            # 发送守护进程状态信息
            mqtt_server.log("INFO", f"Loop count: {loop_count}, 守护进程: {'活跃' if daemon_status['active'] else '停止'}, 安全模式: {'是' if daemon_status['safe_mode'] else '否'}")

        loop_count += 1
        # 每次循环短暂休眠，避免CPU空转
        time.sleep_ms(300)

else:
    print("\n[Main] WiFi Connect Failed, Deep Sleep")
    # machine.deepsleep(60000)
    # machine.reset()
