# -*- coding: utf-8 -*-
#
# 文件名: mqtt_logger.py
# 功能: 通过 MQTT 发送日志的记录器
#
from umqtt.simple import MQTTClient
import time

class MqttLogger:
    def __init__(self, client_id, server, port=1883, user=None, password=None, topic='micropython/logs', keepalive=60):
        self.server = server
        self.topic = topic
        self.client = MQTTClient(client_id, server, port, user, password, keepalive=keepalive)
        self.is_connected = False
        print(f"[MQTT] MQTT 记录器已创建，将连接到 {server}，主题为 '{topic}'。")

    def connect(self):
        """连接到MQTT代理"""
        if self.is_connected:
            return True
        try:
            print("[MQTT] 正在连接到 MQTT 代理...")
            self.client.connect()
            self.is_connected = True
            print("[MQTT] ✅ MQTT 连接成功。")
            self.log("INFO", "Device online and ID is {client_id}.")
            return True
        except Exception as e:
            print(f"[MQTT] ❌ MQTT 连接失败: {e}")
            self.is_connected = False
            return False

    def log(self, level, message):
        """格式化并发送日志消息。"""
        if not self.is_connected:
            return
        try:
            now = time.localtime(time.time() + 8 * 3600)
            timestamp = f"{now[0]}-{now[1]:02d}-{now[2]:02d} {now[3]:02d}:{now[4]:02d}:{now[5]:02d}"
            log_message = f"[{level}] [{timestamp}] {message}"
            self.client.publish(self.topic, log_message)
            print(log_message)
        except Exception as e:
            print(f"[MQTT] ❌ 发送日志时发生错误: {e}")
            self.is_connected = False

    def disconnect(self):
        """断开连接"""
        if self.is_connected:
            self.client.disconnect()
            self.is_connected = False
            print("[MQTT] MQTT 已断开连接。")

    def check_connection(self):
        """仅检查心跳和连接状态"""
        try:
            self.client.check_msg()
        except Exception as e:
            if self.is_connected:
                print(f"[MQTT] 连接已断开: {e}")
            self.is_connected = False
