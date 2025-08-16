# app/net/network_manager.py
# 极简网络管理器 - 异步非阻塞调用，只暴露连接和断开函数

import utime as time
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
from .wifi import WifiManager
from .mqtt import MqttController
from .ntp import NtpManager


class NetworkManager:
    """
    极简网络管理器

    特性：
    - 只暴露connect()和disconnect()两个函数
    - 异步非阻塞调用
    - 内部流程：WiFi → NTP(成功失败都不影响) → MQTT(失败后定时重连)
    - 通过事件总线通知连接结果
    """

    def __init__(self, event_bus, config=None):
        """
        初始化极简网络管理器
        :param event_bus: 事件总线实例
        :param config: 网络配置字典
        """
        self.event_bus = event_bus
        self.config = config or {}

        # 初始化基础组件
        self.wifi = WifiManager(self.config.get("wifi", {}))
        self.ntp = NtpManager(self.config.get("ntp", {}))
        self.mqtt = MqttController(self.config.get("mqtt", {}), event_bus)

        # 简单状态管理
        self._state = "disconnected"  # disconnected, connecting, connected
        self._connecting = False  # 防止重复连接

        # MQTT重连管理
        self._mqtt_retry_enabled = True
        self._last_mqtt_retry = 0
        self._mqtt_retry_interval = 10000  # 10秒重连间隔

        info("网络管理器初始化完成", module="NET")

    def connect(self):
        """
        启动网络连接 - 异步非阻塞

        Returns:
            bool: 连接启动成功返回True，失败返回False
        """
        if self._connecting:
            warning("网络连接正在进行中", module="NET")
            return True

        if self._state == "connected":
            info("网络已连接", module="NET")
            return True

        info("启动网络连接...", module="NET")
        self._connecting = True
        self._state = "connecting"

        try:
            # 启动连接流程
            success = self._connect_wifi()
            if not success:
                self._handle_connection_failed("WiFi连接失败")
                return False

            # 等待WiFi连接稳定
            self._wait_wifi_stable()

            # NTP同步（失败不影响连接流程）
            self._sync_ntp()

            # MQTT连接
            success = self._connect_mqtt()
            if not success:
                # MQTT连接失败不应该导致整个网络连接失败
                # 只记录错误，继续运行
                warning("MQTT连接失败，但WiFi连接成功，系统继续运行", module="NET")
                # 发布部分成功事件
                self.event_bus.publish(
                    EVENTS["SYSTEM_STATE_CHANGE"],
                    state="running",
                    message="WiFi连接成功，MQTT连接失败",
                )
                return True  # WiFi连接成功，返回True

            # 连接成功
            self._state = "connected"
            self._connecting = False
            info("网络连接成功", module="NET")

            # 发布成功事件
            self.event_bus.publish(
                EVENTS["SYSTEM_STATE_CHANGE"], state="running", message="网络连接成功"
            )

            return True

        except Exception as e:
            error("网络连接异常: {}", e, module="NET")
            self._handle_connection_failed(str(e))
            return False

    def disconnect(self):
        """
        断开网络连接

        Returns:
            bool: 断开成功返回True
        """
        info("断开网络连接...", module="NET")

        try:
            # 停止MQTT重连
            self._mqtt_retry_enabled = False

            # 断开MQTT
            if self.mqtt:
                self.mqtt.disconnect()

            # 断开WiFi
            if self.wifi:
                self.wifi.disconnect()

            self._state = "disconnected"
            self._connecting = False

            info("网络连接已断开", module="NET")

            # 发布断开事件
            self.event_bus.publish(
                EVENTS["SYSTEM_STATE_CHANGE"],
                state="DISCONNECTED",
                message="网络连接断开",
            )

            return True

        except Exception as e:
            error("断开网络连接失败: {}", e, module="NET")
            return False

    def loop(self):
        """
        主循环处理 - 处理MQTT重连和消息检查
        """
        try:
            # 首先检查WiFi连接状态
            if self._state == "connected" and not self.wifi.get_is_connected():
                warning("WiFi连接断开，需要重新连接", module="NET")
                self._state = "disconnected"
                return

            # 检查MQTT连接状态
            if self._state == "connected" and not self.mqtt.is_connected():
                warning("MQTT连接断开，准备重连", module="NET")
                self._retry_mqtt()

            # 处理MQTT重连
            if self._mqtt_retry_enabled and self.wifi.get_is_connected():
                current_time = time.ticks_ms()
                if (
                    not self.mqtt.is_connected()
                    and current_time - self._last_mqtt_retry
                    >= self._mqtt_retry_interval
                ):
                    self._retry_mqtt()

            # 检查MQTT消息
            if self.mqtt.is_connected():
                self.mqtt.check_msg()

        except Exception as e:
            error("网络循环处理异常: {}", e, module="NET")

    def reconnect_mqtt(self):
        """
        专门用于MQTT重连的接口 - 供状态机调用
        不影响WiFi连接状态
        """
        try:
            if self._state != "connected":
                warning("网络未处于连接状态，跳过MQTT重连", module="NET")
                return False

            if not self.wifi.get_is_connected():
                warning("WiFi未连接，跳过MQTT重连", module="NET")
                return False

            if self.mqtt.is_connected():
                debug("MQTT已连接，无需重连", module="NET")
                return True

            info("开始MQTT重连（保持WiFi连接）", module="NET")
            return self._retry_mqtt()

        except Exception as e:
            error("MQTT重连异常: {}", e, module="NET")
            return False

    def is_connected(self):
        """
        检查网络是否已连接

        Returns:
            bool: 已连接返回True
        """
        return self._state == "connected" and self.wifi.get_is_connected()

    def get_status(self):
        """
        获取网络状态

        Returns:
            dict: 状态信息
        """
        return {
            "state": self._state,
            "wifi_connected": self.wifi.get_is_connected(),
            "mqtt_connected": self.mqtt.is_connected(),
            "ntp_synced": self.ntp.is_synced(),
            "connecting": self._connecting,
        }

    # MQTT相关接口
    def publish_mqtt_message(self, topic, message, retain=False, qos=0):
        """发布MQTT消息"""
        if not self.mqtt.is_connected():
            return False
        return self.mqtt.publish(topic, message, retain, qos)

    def subscribe_mqtt_topic(self, topic, qos=0):
        """订阅MQTT主题"""
        if not self.mqtt.is_connected():
            return False
        return self.mqtt.subscribe(topic, qos)

    # =============================================================================
    # 内部方法
    # =============================================================================

    def _connect_wifi(self):
        """连接WiFi"""
        try:
            wifi_config = self.config.get("wifi", {})
            networks = wifi_config.get("networks", [])
            if not networks:
                raise Exception("WiFi配置缺少networks列表")

            # 如果WiFi已连接，直接返回成功
            if self.wifi.get_is_connected():
                debug("WiFi已连接，跳过连接", module="NET")
                return True

            # 选择信号最强的网络
            available_networks = self.wifi.scan_networks()
            selected_network = self._select_best_network(available_networks, networks)
            if not selected_network:
                raise Exception("没有找到可用的WiFi网络")

            info("连接WiFi: {}", selected_network["ssid"], module="NET")

            # 连接WiFi
            if not self.wifi.connect(
                selected_network["ssid"], selected_network["password"]
            ):
                raise Exception("WiFi连接失败")

            # 等待连接
            wait_start = time.ticks_ms()
            while (
                not self.wifi.get_is_connected()
                and time.ticks_diff(time.ticks_ms(), wait_start) < 5000
            ):
                time.sleep_ms(100)

            if not self.wifi.get_is_connected():
                raise Exception("WiFi连接超时")

            info("WiFi连接成功", module="NET")
            return True

        except Exception as e:
            error("WiFi连接失败: {}", e, module="NET")
            return False

    def _wait_wifi_stable(self):
        """等待WiFi连接稳定"""
        try:
            info("等待WiFi连接稳定...", module="NET")
            # 等待2秒让WiFi连接完全稳定
            stable_start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), stable_start) < 2000:
                # 检查WiFi是否仍然连接
                if not self.wifi.get_is_connected():
                    warning("WiFi连接在稳定期间断开", module="NET")
                    break
                time.sleep_ms(100)
            info("WiFi连接稳定完成", module="NET")
        except Exception as e:
            warning("WiFi稳定等待异常: {}", e, module="NET")

    def _sync_ntp(self):
        """同步NTP时间"""
        try:
            info("同步NTP时间...", module="NET")
            if self.ntp.sync_time():
                info("NTP时间同步成功", module="NET")
            else:
                warning("NTP时间同步失败，继续执行", module="NET")
        except Exception as e:
            warning("NTP同步异常: {}", e, module="NET")

    def _connect_mqtt(self):
        """连接MQTT"""
        try:
            if not self.mqtt:
                warning("MQTT控制器未初始化", module="NET")
                return False

            # 再次检查WiFi连接状态
            if not self.wifi.get_is_connected():
                warning("WiFi未连接，跳过MQTT连接", module="NET")
                return False

            if self.mqtt.is_connected():
                debug("MQTT已连接，跳过连接", module="NET")
                return True

            info("连接MQTT...", module="NET")

            if not self.mqtt.connect():
                raise Exception("MQTT连接失败")

            info("MQTT连接成功", module="NET")
            return True

        except Exception as e:
            error("MQTT连接失败: {}", e, module="NET")
            return False

    def _retry_mqtt(self):
        """重连MQTT - 返回重连结果"""
        try:
            if not self._mqtt_retry_enabled:
                return False

            # 检查WiFi连接状态
            if not self.wifi.get_is_connected():
                warning("WiFi未连接，跳过MQTT重连", module="NET")
                return False

            self._last_mqtt_retry = time.ticks_ms()
            info("尝试重连MQTT...", module="NET")

            if self._connect_mqtt():
                info("MQTT重连成功", module="NET")
                # 发布重连成功事件
                self.event_bus.publish(
                    EVENTS["SYSTEM_STATE_CHANGE"],
                    state="running",
                    message="MQTT重连成功",
                )
                return True
            else:
                warning("MQTT重连失败，10秒后重试", module="NET")
                return False

        except Exception as e:
            error("MQTT重连异常: {}", e, module="NET")
            return False

    def _select_best_network(self, available_networks, configured_networks):
        """选择最优WiFi网络"""
        try:
            # 创建配置网络的字典
            config_dict = {net["ssid"]: net for net in configured_networks}

            # 筛选出配置中存在的网络
            matched_networks = []
            for available in available_networks:
                ssid = available["ssid"]
                if ssid in config_dict:
                    matched_networks.append(
                        {
                            "ssid": ssid,
                            "password": config_dict[ssid]["password"],
                            "rssi": available["rssi"],
                        }
                    )

            if not matched_networks:
                return None

            # 按信号强度排序
            matched_networks.sort(key=lambda x: x["rssi"], reverse=True)

            # 返回信号最强的网络
            return matched_networks[0]

        except Exception as e:
            error("选择最优网络失败: {}", e, module="NET")
            return None

    def _handle_connection_failed(self, error_msg):
        """处理连接失败"""
        self._state = "disconnected"
        self._connecting = False

        error("连接失败: {}", error_msg, module="NET")

        # 发布失败事件
        self.event_bus.publish(
            EVENTS["SYSTEM_ERROR"],
            error_type="network_connection_failed",
            error_message=error_msg,
        )
