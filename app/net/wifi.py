# app/net/wifi.py
"""
WiFi 管理器
职责:
- 提供 WiFi 网络扫描与信号强度排序, 供其他模块选择最优连接点
- 提供基础的连接/断开/状态检查接口, 集成到 NetworkManager 流程中

设计边界:
- 不包含复杂的多网络选择逻辑, 由 NetworkManager 或配置驱动
- 不含重试机制, 由上层 NetworkManager/FSM 统一处理
- 扫描结果按 RSSI 降序返回, 便于按信号强度决策

扩展建议:
- 可扩展支持企业级 WiFi(WPA2-Enterprise)
- 可集成信道质量评估与连接历史统计
"""
import network
import utime as time
from lib.logger import error, warning


class WifiManager:
    """
    WiFi 管理器

    仅提供基本的 WiFi 操作能力:
    - 扫描网络(按信号强度排序)
    - 连接指定网络
    - 断开连接
    """

    def __init__(self, config=None):
        """
        初始化 WiFi 管理器
        Args:
            config: WiFi 配置字典
        """
        self.config = config or {}
        self.wlan = network.WLAN(network.STA_IF)

        # 激活 WLAN 接口
        if not self.wlan.active():
            self.wlan.active(True)

    def scan_networks(self):
        """
        扫描可用网络并按信号强度排序

        Args:
            timeout_ms: 扫描超时时间(毫秒)

        Returns:
            list: 网络列表, 每个网络包含 {'ssid': str, 'rssi': int, 'bssid': bytes}
        """
        try:
            # 计算有效超时时间: 从配置读取, 否则回退到默认值
            timeout_ms = self.config.get("scan_timeout_ms", 10000)

            # 记录开始时间
            start_time = time.ticks_ms()

            # 执行扫描(阻塞)
            scan_results = self.wlan.scan()

            # 检查扫描是否超时
            elapsed = time.ticks_diff(time.ticks_ms(), start_time)
            if elapsed > timeout_ms:
                warning("WiFi扫描耗时过长: {}ms", elapsed, module="NET")

            networks = []

            for result in scan_results:
                # scan_result 格式: (ssid, bssid, channel, RSSI, authmode, hidden)
                ssid_bytes, bssid, _, rssi, _, _ = result
                try:
                    ssid = ssid_bytes.decode("utf-8")
                    networks.append({"ssid": ssid, "rssi": rssi, "bssid": bssid})
                except UnicodeError:
                    continue  # 忽略无法解码的 SSID

            # 按 RSSI 降序排序(信号强度从高到低)
            networks.sort(key=lambda x: x["rssi"], reverse=True)
            return networks

        except OSError as e:
            error("WiFi扫描失败: {}", e, module="NET")
            return []

    def connect(self, ssid, password):
        """
        连接到指定的 WiFi 网络

        Args:
            ssid (str): WiFi 网络名称
            password (str): WiFi 密码

        Returns:
            bool: 发起连接成功返回 True, 最终连接状态请配合 get_is_connected() 判定
        """
        try:
            self.wlan.connect(ssid, password)
            return True
        except Exception as e:
            error("WiFi连接失败: {}", e, module="NET")
            return False

    def disconnect(self):
        """
        断开 WiFi 连接

        Returns:
            bool: 断开成功返回 True
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
        检查 WiFi 是否已连接

        Returns:
            bool: 已连接返回 True
        """
        try:
            return self.wlan.isconnected()
        except Exception as e:
            error("WiFi状态检查失败: {}", e, module="NET")
            return False

    def get_ip(self):
        """
        获取当前 IPv4 地址

        Returns:
            str: 已连接时返回 IP, 异常或未连接时返回 "N/A"
        """
        try:
            if self.wlan and self.wlan.isconnected():
                cfg = self.wlan.ifconfig()
                if cfg and isinstance(cfg, (list, tuple)) and len(cfg) > 0:
                    return cfg[0]
        except Exception:
            pass
        return "N/A"
