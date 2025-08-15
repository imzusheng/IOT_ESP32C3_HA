# app/net/index.py
# 极简网络统一控制器

import utime as time
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
from .wifi import WifiManager
from .ntp import NtpManager
from .mqtt import MqttController


class NetworkManager:
    """极简网络统一控制器 - 直接管理所有网络连接"""

    def __init__(self, event_bus, config=None):
        self.event_bus = event_bus
        self.config = config or {}

        # 初始化网络组件
        self.wifi = WifiManager(self.config.get("wifi", {}))
        self.ntp = NtpManager(self.config.get("ntp", {}))
        self.mqtt = MqttController(self.config.get("mqtt", {}), self.event_bus)

        # 连接状态
        self.state = "disconnected"  # disconnected, connecting, wifi_connected, fully_connected, error
        self.retry_count = 0
        self.max_retries = 3
        self.last_connection_attempt = 0
        self.retry_delay = 1000  # 1秒重试延迟

        # 连接时间戳
        self.last_status_check = 0
        self.status_check_interval = 5000  # 5秒检查一次

        # 重试时间管理
        self.next_retry_time = 0

        # 网络稳定性检查
        self.last_health_check = 0
        self.health_check_interval = 60000  # 60秒检查一次网络健康
        self.connection_quality_score = 100  # 连接质量评分 (0-100)
        self.last_connection_time = 0
        
        # MQTT重连状态管理
        self._mqtt_retry_count = 0
        self._last_mqtt_retry_time = 0
        self._mqtt_retry_intervals = [5000, 10000, 20000, 30000]  # 5s, 10s, 20s, 30s
        self._max_mqtt_retries = 10  # 最大重试次数，防止无限重连

        info("网络管理器初始化完成", module="NET")

    def loop(self):
        """主循环处理"""
        try:
            current_time = time.ticks_ms()

            # 定期检查连接状态
            if current_time - self.last_status_check > self.status_check_interval:
                self._check_connections()
                self.last_status_check = current_time

            # 网络健康检查（60秒一次）
            if current_time - self.last_health_check > self.health_check_interval:
                self._check_network_health()
                self.last_health_check = current_time

            # 处理重试逻辑（非阻塞）
            if (
                self.state in ["connecting", "wifi_connected"]
                and self.next_retry_time > 0
            ):
                if current_time >= self.next_retry_time:
                    info("执行延迟重试连接", module="NET")
                    self.next_retry_time = 0
                    self._connect_all()

            # 处理MQTT消息
            if self.mqtt.is_connected():
                self.mqtt.check_msg()

            # 在wifi_connected状态下主动尝试MQTT重连
            if self.state == "wifi_connected" and not self.mqtt.is_connected():
                self._handle_mqtt_reconnect()

        except Exception as e:
            error("网络管理器循环错误: {}", e, module="NET")
            self._handle_error(e)

    def connect(self):
        """启动网络连接"""
        if self.state == "disconnected":
            info("启动网络连接", module="NET")
            self.state = "connecting"
            self.retry_count = 0
            self._connect_all()
        else:
            warning("当前状态{}不允许启动连接", self.state, module="NET")

    def disconnect(self):
        """断开网络连接"""
        info("断开网络连接", module="NET")
        self.state = "disconnected"
        self._disconnect_all()

    def get_status(self):
        """获取网络状态"""
        return {
            "state": self.state,
            "wifi_connected": self.wifi.get_is_connected(),
            "mqtt_connected": self.mqtt.is_connected(),
            "ntp_synced": self.ntp.is_synced(),
            "retry_count": self.retry_count,
        }

    def is_connected(self):
        """检查是否已连接 - 基于WiFi状态"""
        return self.wifi.get_is_connected()

    def is_fully_connected(self):
        """检查是否完全连接 - WiFi和MQTT都连接"""
        return self.wifi.get_is_connected() and self.mqtt.is_connected()

    def is_wifi_connected(self):
        """检查WiFi是否已连接"""
        return self.wifi.get_is_connected()

    def is_mqtt_connected(self):
        """检查MQTT是否已连接"""
        return self.mqtt.is_connected()

    # MQTT相关接口
    def publish_mqtt_message(self, topic, message, retain=False, qos=0):
        """发布MQTT消息"""
        return self.mqtt.publish(topic, message, retain, qos)

    def subscribe_mqtt_topic(self, topic, qos=0):
        """订阅MQTT主题"""
        return self.mqtt.subscribe(topic, qos)

    def get_mqtt_status(self):
        """获取MQTT状态"""
        return self.mqtt.is_connected()

    # =============================================================================
    # 内部方法
    # =============================================================================

    def _connect_all(self):
        """连接所有网络服务 - 分离式连接，MQTT失败不影响WiFi"""
        try:
            # 1. 连接WiFi (关键连接，失败则触发完整重连)
            info("连接WiFi...", module="NET")
            wifi_config = self.config.get("wifi", {})

            # 检查配置格式 - 支持networks列表格式
            networks = wifi_config.get("networks", [])
            if not networks:
                raise Exception("WiFi配置缺少networks列表")

            # 扫描可用网络
            available_networks = self.wifi.scan_networks()
            info("找到 {} 个可用WiFi网络", len(available_networks), module="NET")

            # 选择最优网络（按信号强度和配置优先级）
            selected_network = self._select_best_network(available_networks, networks)
            if not selected_network:
                raise Exception("没有找到可用的WiFi网络")

            info(
                "尝试连接WiFi: {} (RSSI: {})",
                selected_network["ssid"],
                selected_network["rssi"],
                module="NET",
            )

            if not self.wifi.connect(
                selected_network["ssid"], selected_network["password"]
            ):
                raise Exception("WiFi连接失败")

            # 等待WiFi连接（优化等待时间，减少主循环阻塞）
            import time

            wait_start = time.ticks_ms()
            max_wait_time = 2000  # 减少到2秒，避免主循环超时
            while (
                not self.wifi.get_is_connected()
                and time.ticks_diff(time.ticks_ms(), wait_start) < max_wait_time
            ):
                time.sleep_ms(50)  # 减少睡眠时间，提高响应性

            if not self.wifi.get_is_connected():
                raise Exception("WiFi连接超时")

            info("WiFi连接成功: {}", selected_network["ssid"], module="NET")

            # 2. 同步NTP时间 (非关键连接，失败只记录警告)
            info("同步NTP时间...", module="NET")
            try:
                self.ntp.sync_time()
                info("NTP时间同步成功", module="NET")
            except Exception as ntp_error:
                warning(
                    "NTP时间同步失败，但不影响网络连接: {}", ntp_error, module="NET"
                )

            # 3. 连接MQTT (非关键连接，失败不影响WiFi连接状态)
            info("连接MQTT...", module="NET")
            mqtt_connected = False
            try:
                mqtt_connected = self.mqtt.connect()
                if mqtt_connected:
                    info("MQTT连接成功", module="NET")
                else:
                    warning("MQTT连接失败，WiFi连接保持正常", module="NET")
            except Exception as mqtt_error:
                # MQTT连接失败是预期的，不应该记录为警告，只记录debug
                debug("MQTT连接异常: {}，WiFi连接保持正常", mqtt_error, module="NET")
                mqtt_connected = False

            # 根据MQTT连接状态设置不同的连接状态
            if mqtt_connected:
                self.state = "fully_connected"
                self.connection_quality_score = 100  # 完全连接
                info("所有网络服务连接成功", module="NET")

                # 发布网络连接成功事件
                self.event_bus.publish(
                    EVENTS["SYSTEM_STATE_CHANGE"],
                    state="NETWORKING",
                    message="网络连接成功",
                )
            else:
                self.state = "wifi_connected"
                self.connection_quality_score = 70  # WiFi连接成功，MQTT失败
                info("WiFi连接成功，MQTT服务暂时不可用，继续尝试连接", module="NET")

                # 不发布连接成功事件，保持NETWORKING状态继续尝试MQTT连接
                self._mqtt_retry_count = 0
                self._last_mqtt_retry_time = time.ticks_ms()

            self.retry_count = 0
            self.last_connection_time = time.ticks_ms()

            # 清理WiFi重连时间戳和计数器
            for attr in ["_last_wifi_retry_time"]:
                if hasattr(self, attr):
                    delattr(self, attr)

        except Exception as e:
            error("网络连接失败: {}", e, module="NET")
            # 只有WiFi连接失败才触发完整重连
            if "WiFi" in str(e) or "wifi" in str(e).lower():
                self._handle_connection_failed(e)
            else:
                # NTP或MQTT失败，只设置状态为wifi_connected但降低评分
                self.state = "wifi_connected"
                self.connection_quality_score = 60
                warning("非关键网络服务失败，系统继续运行", module="NET")

    def _disconnect_all(self):
        """断开所有网络服务"""
        try:
            self.mqtt.disconnect()
            self.wifi.disconnect()
            info("所有网络服务已断开", module="NET")
        except Exception as e:
            error("断开网络连接失败: {}", e, module="NET")

    def _check_connections(self):
        """检查连接状态 - 智能重连机制"""
        try:
            wifi_ok = self.wifi.get_is_connected()
            mqtt_ok = self.mqtt.is_connected()

            # 如果WiFi断开，重新连接（减少重连频率）
            if not wifi_ok and self.state in ["wifi_connected", "fully_connected"]:
                current_time = time.ticks_ms()
                # 只有距离上次重连超过30秒才尝试重连，避免频繁重连
                if (
                    not hasattr(self, "_last_wifi_retry_time")
                    or current_time - self._last_wifi_retry_time > 30000
                ):
                    warning("WiFi连接断开，尝试重新连接", module="NET")
                    self._last_wifi_retry_time = current_time
                    self._handle_wifi_connection_failed(Exception("WiFi连接断开"))
                else:
                    debug("WiFi连接断开，等待重连冷却期", module="NET")

            # 如果MQTT断开但WiFi正常，只重连MQTT
            elif wifi_ok and not mqtt_ok and self.state in ["wifi_connected", "fully_connected"]:
                self._handle_mqtt_reconnect()

        except Exception as e:
            error("检查连接状态失败: {}", e, module="NET")

    def _handle_mqtt_reconnect(self):
        """统一处理MQTT重连逻辑"""
        current_time = time.ticks_ms()
        
        # 检查是否超过最大重试次数
        if self._mqtt_retry_count >= self._max_mqtt_retries:
            warning("MQTT重连次数超过最大限制({})，停止重连", self._max_mqtt_retries, module="NET")
            return
        
        # 检查是否需要重连
        if current_time - self._last_mqtt_retry_time < self._get_mqtt_retry_interval():
            return  # 还在冷却期
        
        # 执行重连
        debug("尝试MQTT重连 (次数: {}/{})", self._mqtt_retry_count + 1, self._max_mqtt_retries, module="NET")
        self._last_mqtt_retry_time = current_time
        
        if self.mqtt.connect():
            info("MQTT重连成功，系统完全连接", module="NET")
            self.state = "fully_connected"
            self.connection_quality_score = 100
            self._mqtt_retry_count = 0
            
            # 发布网络连接成功事件
            self.event_bus.publish(
                EVENTS["SYSTEM_STATE_CHANGE"],
                state="NETWORKING",
                message="网络连接成功",
            )
        else:
            debug("MQTT重连失败", module="NET")
            self._mqtt_retry_count += 1
            
            # 如果重连次数过多，记录警告
            if self._mqtt_retry_count >= len(self._mqtt_retry_intervals):
                warning("MQTT重连次数过多，检查网络配置", module="NET")
            
            # 计算下次重连间隔
            next_interval = self._get_mqtt_retry_interval()
            debug("下次MQTT重连间隔: {}秒", next_interval // 1000, module="NET")

    def _get_mqtt_retry_interval(self):
        """获取MQTT重连间隔"""
        if self._mqtt_retry_count < len(self._mqtt_retry_intervals):
            return self._mqtt_retry_intervals[self._mqtt_retry_count]
        else:
            return self._mqtt_retry_intervals[-1]  # 使用最大间隔

    def _handle_wifi_connection_failed(self, error_msg):
        """处理WiFi连接失败"""
        self.retry_count += 1
        error(
            "WiFi连接失败，重试次数: {}/{}",
            self.retry_count,
            self.max_retries,
            module="NET",
        )

        if self.retry_count >= self.max_retries:
            self.state = "error"
            error("达到最大重试次数，连接失败", module="NET")

            # 发布系统错误事件
            self.event_bus.publish(
                EVENTS["SYSTEM_ERROR"],
                error_type="wifi_connection_failed",
                error_message=str(error_msg),
            )
        else:
            self.state = "connecting"
            # 计算重试延迟（指数退避）
            delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 30000)
            info("{}秒后重试WiFi连接", delay // 1000, module="NET")

            # 设置下次重试时间，在loop中处理
            self.next_retry_time = time.ticks_ms() + delay

    def _handle_connection_failed(self, error_msg):
        """处理连接失败"""
        self.retry_count += 1
        error(
            "连接失败，重试次数: {}/{}",
            self.retry_count,
            self.max_retries,
            module="NET",
        )

        if self.retry_count >= self.max_retries:
            self.state = "error"
            error("达到最大重试次数，连接失败", module="NET")

            # 发布系统错误事件
            self.event_bus.publish(
                EVENTS["SYSTEM_ERROR"],
                error_type="network_connection_failed",
                error_message=str(error_msg),
            )
        else:
            self.state = "connecting"
            # 计算重试延迟（指数退避）
            delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 30000)
            info("{}秒后重试连接", delay // 1000, module="NET")

            # 设置下次重试时间，在loop中处理
            self.next_retry_time = time.ticks_ms() + delay

    def _handle_error(self, error_msg):
        """处理错误"""
        error("网络管理器错误: {}", error_msg, module="NET")
        self.state = "error"

        # 发布系统错误事件
        self.event_bus.publish(
            EVENTS["SYSTEM_ERROR"],
            error_type="network_manager_error",
            error_message=str(error_msg),
        )

    def _select_best_network(self, available_networks, configured_networks):
        """选择最优WiFi网络"""
        try:
            # 创建配置网络的字典，便于快速查找
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
                            "bssid": available["bssid"],
                        }
                    )

            if not matched_networks:
                return None

            # 按信号强度排序（RSSI值越大信号越强）
            matched_networks.sort(key=lambda x: x["rssi"], reverse=True)

            # 返回信号最强的网络
            best_network = matched_networks[0]
            info(
                "选择最优网络: {} (信号强度: {}dBm)",
                best_network["ssid"],
                best_network["rssi"],
                module="NET",
            )

            return best_network

        except Exception as e:
            error("选择最优网络失败: {}", e, module="NET")
            return None

    def _check_network_health(self):
        """检查网络连接健康状态"""
        try:
            wifi_ok = self.wifi.get_is_connected()
            mqtt_ok = self.mqtt.is_connected()

            # 简单的连接状态检查
            if wifi_ok and mqtt_ok:
                debug("网络连接正常", module="NET")
            elif wifi_ok:
                debug("WiFi正常，MQTT未连接", module="NET")
            else:
                warning("网络连接异常", module="NET")

        except Exception as e:
            debug("网络健康检查失败: {}", e, module="NET")

    def reset(self):
        """重置网络管理器"""
        info("重置网络管理器", module="NET")
        self.state = "disconnected"
        self.retry_count = 0
        self.next_retry_time = 0
        self.connection_quality_score = 100
        self.last_connection_time = 0
        # 重置MQTT重连状态
        self._mqtt_retry_count = 0
        self._last_mqtt_retry_time = 0
        # 清理重连时间戳和计数器
        for attr in [
            "_last_wifi_retry_time",
        ]:
            if hasattr(self, attr):
                delattr(self, attr)
        self._disconnect_all()
