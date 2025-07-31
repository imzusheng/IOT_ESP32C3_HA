# -*- coding: utf-8 -*-
#
# 文件名: mqtt_logger.py
# 功能: 通过 MQTT 发送日志的记录器 (修正了重连逻辑)
#
from umqtt.simple import MQTTClient
import time
import machine

class MqttLogger:
    def __init__(self, client_id, server, port=1883, user=None, password=None, topic='micropython/logs', keepalive=60):
        self.server = server
        self.topic = topic
        self.client = MQTTClient(client_id, server, port, user, password, keepalive=keepalive)
        self.is_connected = False
        print(f"[Logger] MQTT 记录器已创建，将连接到 {server}，主题为 '{topic}'。")

    def connect(self):
        """连接到MQTT代理"""
        if self.is_connected:
            return True
        try:
            print("[Logger] 正在连接到 MQTT 代理...")
            self.client.connect()
            self.is_connected = True
            print("[Logger] ✅ MQTT 连接成功。")
            self.log("INFO", "Device online and logging started.") 
            return True
        except Exception as e:
            print(f"[Logger] ❌ MQTT 连接失败: {e}")
            self.is_connected = False
            return False

    def log(self, level, message):
        """格式化并发送日志消息。"""
        if not self.is_connected:
            # print(f"[Logger] (未发送，因未连接) [{level}] {message}") # 在主循环中已有提示，此处可省略
            return
        try:
            now = time.localtime(time.time() + 9 * 3600) # JST: UTC+9
            timestamp = f"{now[0]}-{now[1]:02d}-{now[2]:02d} {now[3]:02d}:{now[4]:02d}:{now[5]:02d}"
            log_message = f"[{level}] [{timestamp}] {message}"
            self.client.publish(self.topic, log_message)
            print(log_message)
        except Exception as e:
            print(f"[Logger] ❌ 发送日志时发生错误: {e}")
            self.is_connected = False

    def disconnect(self):
        """断开连接"""
        if self.is_connected:
            self.client.disconnect()
            self.is_connected = False
            print("[Logger] MQTT 已断开连接。")

    # [核心修改] 此函数现在只检查，不重连
    def check_connection(self):
        """
        仅检查心跳和连接状态。
        如果连接断开，只更新标志位，不执行任何重连操作。
        """
        try:
            self.client.check_msg()
        except Exception as e:
            # 如果 check_msg() 出错，说明连接已断开
            if self.is_connected: # 仅在状态变化时打印一次
                print(f"[Logger] 连接已断开: {e}")
            self.is_connected = False