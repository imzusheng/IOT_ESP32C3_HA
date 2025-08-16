# app/net/wifi.py
# 简化版WiFi管理器, 只提供基本的WiFi操作功能
import network
from lib.logger import debug, info, warning, error


class WifiManager:
    """
    WiFi管理器

    只提供基本的WiFi操作功能：
    - 扫描网络(按信号强度排序)
    - 连接指定网络
    - 断开连接
    """

    def __init__(self, config=None):
        """
        初始化WiFi管理器
        :param config: WiFi配置字典
        """
        self.config = config or {}
        self.wlan = network.WLAN(network.STA_IF)

        # 激活WLAN接口
        if not self.wlan.active():
            self.wlan.active(True)

    def scan_networks(self, timeout_ms=10000):
        """
        扫描可用网络并按信号强度排序

        Args:
            timeout_ms: 扫描超时时间(毫秒)

        Returns:
            list: 网络列表, 每个网络包含 {'ssid': str, 'rssi': int, 'bssid': bytes}
        """
        try:
            import time

            # 记录开始时间
            start_time = time.ticks_ms()

            # 执行扫描
            scan_results = self.wlan.scan()

            # 检查扫描是否超时
            elapsed = time.ticks_diff(time.ticks_ms(), start_time)
            if elapsed > timeout_ms:
                warn("WiFi扫描耗时过长: {}ms", elapsed, module="NET")

            networks = []

            for result in scan_results:
                # scan_result格式: (ssid, bssid, channel, RSSI, authmode, hidden)
                ssid_bytes, bssid, _, rssi, _, _ = result
                try:
                    ssid = ssid_bytes.decode("utf-8")
                    networks.append({"ssid": ssid, "rssi": rssi, "bssid": bssid})
                except UnicodeError:
                    continue  # 忽略无法解码的SSID

            # 按RSSI降序排序(信号强度从高到低)
            networks.sort(key=lambda x: x["rssi"], reverse=True)
            return networks

        except OSError as e:
            error("WiFi扫描失败: {}", e, module="NET")
            return []

    def connect(self, ssid, password):
        """
        连接到指定的WiFi网络

        Args:
            ssid (str): WiFi网络名称
            password (str): WiFi密码

        Returns:
            bool: 连接成功返回True
        """
        try:
            self.wlan.connect(ssid, password)
            return True
        except Exception as e:
            error("WiFi连接失败: {}", e, module="NET")
            return False

    def disconnect(self):
        """
        断开WiFi连接

        Returns:
            bool: 断开成功返回True
        """
        try:
            if self.wlan.isconnected():
                self.wlan.disconnect()
            return True
        except Exception as e:
            error("WiFi断开失败: {}", e, module="NET")
            return False

    def get_is_connected(self):
        """
        检查WiFi是否已连接

        Returns:
            bool: 已连接返回True
        """
        try:
            return self.wlan.isconnected()
        except Exception as e:
            error("WiFi状态检查失败: {}", e, module="NET")
            return False
