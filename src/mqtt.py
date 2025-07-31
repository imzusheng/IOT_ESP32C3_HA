# -*- coding: utf-8 -*-
#
# mqtt.py
# MQTT 服务器
#
from umqtt.simple import MQTTClient
import time

class MqttServer:
    def __init__(self, client_id, server, port=1883, user=None, password=None, topic='micropython/logs', keepalive=60):
        self.server = server
        self.topic = topic
        self.client = MQTTClient(client_id, server, port, user, password, keepalive=keepalive)
        self.is_connected = False
        print(f"[MQTT] MQTT Logger Created, Connecting to {server}, Topic: '{topic}'")

    def connect(self):
        """连接到MQTT代理"""
        if self.is_connected:
            return True
        try:
            self.client.connect()
            self.is_connected = True
            print("\033[1;32m[MQTT] MQTT Logger Connected.\033[0m")
            self.log("INFO", f"Device online and ID is {self.client.client_id}.")
            return True
        except Exception as e:
            print(f"\033[1;31m[MQTT] MQTT Logger Connection Failed: {e}\033[0m")
            self.is_connected = False
            return False

    def log(self, level, message):
        """格式化并发送日志消息。"""
        if not self.is_connected:
            return
        try:
            # 计算时间
            t = time.localtime(time.time())
            # 用bytearray拼接，减少内存分配
            log_ba = bytearray()
            log_ba.extend(f"[{level}] [".encode())
            log_ba.extend(f"{t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}".encode())
            log_ba.extend(f"] {message}".encode())
            self.client.publish(self.topic, log_ba)
        except Exception as e:
            print(f"\033[1;31m[MQTT] Error Sending Log: {e}\033[0m")
            self.is_connected = False
            gc.collect()

    def disconnect(self):
        """断开连接"""
        if self.is_connected:
            self.client.disconnect()
            self.is_connected = False
            print("\033[1;31m[MQTT] MQTT Logger Disconnected.\033[0m")

    def check_connection(self):
        """仅检查心跳和连接状态"""
        try:
            self.client.check_msg()
        except Exception as e:
            if self.is_connected:
                print(f"\033[1;31m[MQTT] Connection Lost: {e}\033[0m")
            self.is_connected = False
