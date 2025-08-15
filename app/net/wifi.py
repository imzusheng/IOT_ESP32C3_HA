# app/net/wifi.py
# 增强版WiFi管理器, 提供完整的WiFi连接管理功能
import network
import utime as time
from lib.logger import debug, info, warning, error

class WifiManager:
    """
    WiFi管理器
    
    提供完整的WiFi连接管理功能：
    - 扫描网络(按信号强度排序)
    - 连接指定网络(带超时和重连)
    - 连接状态监控
    - 信号质量评估
    - 自动重连机制
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
        
        # 连接状态管理
        self._connection_start_time = 0
        self._last_signal_strength = 0
        self._connection_retry_count = 0
        self._max_retries = 3
        self._last_scan_time = 0
        self._scan_cache = None
        self._scan_cache_duration = 10000  # 10秒缓存
        
        # 配置参数
        self._connection_timeout = self.config.get('connection_timeout', 15000)  # 15秒
        self._retry_delay = self.config.get('retry_delay', 2000)  # 2秒
        self._min_signal_strength = self.config.get('min_signal_strength', -80)  # 最小信号强度

    def scan_networks(self, timeout_ms=10000):
        """
        扫描可用网络并按信号强度排序（带缓存）
        
        Args:
            timeout_ms: 扫描超时时间(毫秒)
        
        Returns:
            list: 网络列表, 每个网络包含 {'ssid': str, 'rssi': int, 'bssid': bytes}
        """
        current_time = time.ticks_ms()
        
        # 检查缓存是否有效
        if (self._scan_cache and 
            current_time - self._last_scan_time < self._scan_cache_duration):
            debug("使用WiFi扫描缓存", module="NET")
            return self._scan_cache
        
        try:
            # 记录开始时间
            start_time = time.ticks_ms()
            
            # 执行扫描
            scan_results = self.wlan.scan()
            
            # 检查扫描是否超时
            elapsed = time.ticks_diff(time.ticks_ms(), start_time)
            if elapsed > timeout_ms:
                warning("WiFi扫描耗时过长: {}ms", elapsed, module="NET")
            
            networks = []
            
            for result in scan_results:
                # scan_result格式: (ssid, bssid, channel, RSSI, authmode, hidden)
                ssid_bytes, bssid, _, rssi, _, _ = result
                try:
                    ssid = ssid_bytes.decode('utf-8')
                    # 过滤信号质量过差的网络
                    if rssi >= self._min_signal_strength:
                        networks.append({
                            'ssid': ssid,
                            'rssi': rssi,
                            'bssid': bssid,
                            'quality': self._calculate_signal_quality(rssi)
                        })
                except UnicodeError:
                    continue  # 忽略无法解码的SSID
            
            # 按RSSI降序排序(信号强度从高到低)
            networks.sort(key=lambda x: x['rssi'], reverse=True)
            
            # 更新缓存
            self._scan_cache = networks
            self._last_scan_time = current_time
            
            return networks
            
        except OSError as e:
            error("WiFi扫描失败: {}", e, module="NET")
            return []
    
    def _calculate_signal_quality(self, rssi):
        """计算信号质量评分 (0-100)"""
        if rssi >= -50:
            return 100  # 优秀
        elif rssi >= -60:
            return 80   # 良好
        elif rssi >= -70:
            return 60   # 一般
        elif rssi >= -80:
            return 40   # 较差
        else:
            return 20   # 很差

    def connect(self, ssid, password):
        """
        连接到指定的WiFi网络（带超时和重连）
        
        Args:
            ssid (str): WiFi网络名称
            password (str): WiFi密码
            
        Returns:
            bool: 连接成功返回True
        """
        try:
            # 如果已经连接，先断开
            if self.wlan.isconnected():
                self.disconnect()
            
            # 记录连接开始时间
            self._connection_start_time = time.ticks_ms()
            
            # 发起连接
            debug("尝试连接WiFi: {}", ssid, module="NET")
            self.wlan.connect(ssid, password)
            
            # 等待连接建立
            return self._wait_for_connection()
            
        except Exception as e:
            error("WiFi连接失败: {}", e, module="NET")
            return False
    
    def _wait_for_connection(self):
        """等待WiFi连接建立"""
        start_time = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), start_time) < self._connection_timeout:
            if self.wlan.isconnected():
                # 连接成功，记录信号强度
                self._last_signal_strength = self._get_signal_strength()
                self._connection_retry_count = 0
                info("WiFi连接成功，信号强度: {}dBm", self._last_signal_strength, module="NET")
                return True
            
            # 短暂休眠避免CPU占用过高
            time.sleep_ms(100)
        
        # 连接超时
        warning("WiFi连接超时 ({}ms)", self._connection_timeout, module="NET")
        return False
    
    def _get_signal_strength(self):
        """获取当前信号强度（使用缓存优化）"""
        try:
            # 获取当前连接的信号强度
            if self.wlan.isconnected():
                # 获取当前连接的SSID
                current_ssid = None
                try:
                    current_ssid = self.wlan.config('ssid')
                    if isinstance(current_ssid, bytes):
                        current_ssid = current_ssid.decode('utf-8')
                except:
                    pass
                
                # 在扫描结果中找到当前连接的网络
                if current_ssid:
                    networks = self.scan_networks(2000)  # 使用缓存快速获取
                    for network in networks:
                        if network['ssid'] == current_ssid:
                            return network['rssi']
                
                return -70  # 默认值
        except:
            pass
        
        return -70  # 获取失败时的默认值

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
        return self.wlan.isconnected()

