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
    counter = 0

    # --- [核心修改] 采用更健壮的主循环逻辑 ---
    while True:
        if logger.is_connected:
            # 1. 如果连接正常，就检查心跳
            logger.check_connection()

            # 2. 按计划发送日志
            if time.time() - last_log_time >= 5:
                counter += 1
                logger.log("INFO", f"Main loop running, counter: {counter}")
                last_log_time = time.time()
        else:
            # 3. 如果连接断开，则采用退避策略尝试重连
            #    每隔10秒才尝试重连一次，避免骚扰服务器
            if time.time() - last_reconnect_attempt > 10:
                print("[Main] MQTT 连接已断开，正在尝试重连...")
                logger.connect() # 尝试重新连接
                last_reconnect_attempt = time.time()

        # 每次循环短暂休眠，避免CPU空转
        time.sleep_ms(200)

else:
    print("\n[Main] ❌ 网络连接失败。")
    # 可以选择重启或休眠
    # machine.deepsleep(60000)