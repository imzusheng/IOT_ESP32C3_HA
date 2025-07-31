# -*- coding: utf-8 -*-
import time
import machine
import wifi_manager
import mqtt

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

    while True:
        if loop_count % 30 == 0:
            print(gc.mem_free())
            gc.collect()
            print(gc.mem_free())

            if not mqtt_server.is_connected:
                print("\033[1;31m[Main] MQTT Disconnected, Reconnecting...\033[0m")
                mqtt_server.connect()
            else:
                # mqtt_server.log("INFO", "Ping")
                mqtt_server.check_connection()
            mqtt_server.log("INFO", f"Loop count: {loop_count}")

        loop_count += 1
        # 每次循环短暂休眠，避免CPU空转
        time.sleep_ms(300)

else:
    print("\n[Main] WiFi Connect Failed, Deep Sleep")
    # machine.deepsleep(60000)
    # machine.reset()
