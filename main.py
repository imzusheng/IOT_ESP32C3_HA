# -*- coding: utf-8 -*-
import time
import machine
import wifi_manager
import mqtt_logger

# --- MQTT 配置 ---
MQTT_BROKER = "192.168.3.15"
MQTT_TOPIC = "lzs/esp32c3"
CLIENT_ID = f"esp32c3-client-{machine.unique_id().hex()}"

# --- 程序主入口 ---
print("===================================")
print("      主程序启动 (main.py)         ")
print("===================================")

connection_successful = wifi_manager.connect_wifi()

if connection_successful:
    print("\n[Main] ✅ 网络初始化成功。")

    logger = mqtt_logger.MqttLogger(CLIENT_ID, MQTT_BROKER, topic=MQTT_TOPIC)

    # 初始尝试连接一次
    logger.connect()

    last_log_time = time.time()
    last_reconnect_attempt = time.time()

    while True:
        if logger.is_connected:
            logger.check_connection()

        else:
            if time.time() - last_reconnect_attempt > 10:
                print("[Main] MQTT 连接已断开，正在尝试重连...")
                logger.connect()
                last_reconnect_attempt = time.time()

        # 每次循环短暂休眠，避免CPU空转
        time.sleep_ms(200)

else:
    print("\n[Main] ❌ 网络连接失败。")
    machine.deepsleep(60000)
