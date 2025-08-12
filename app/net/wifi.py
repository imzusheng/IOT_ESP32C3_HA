# app/net/wifi.py
import network
import utime as time
import gc
try:
    import ntptime  # MicroPython NTP 客户端
except Exception:
    ntptime = None
from lib.logger import get_global_logger
from lib.event_bus.events_const import EVENTS

class WifiManager:
    """
    WiFi连接管理器 (重构版本)
    
    管理WiFi连接, 采用非阻塞模式, 通过事件总线报告状态。
    支持多网络选择、RSSI排序、自动重连和健壮的错误处理。
    
    特性:
    - 非阻塞连接模式
    - 自动信号强度排序
    - 指数退避重连策略
    - 事件驱动状态报告
    - 联网成功后自动执行 NTP 同步(使用阿里云时间源)
    """
    # 连接状态
    STATUS_DISCONNECTED = 0
    STATUS_CONNECTING = 1
    STATUS_CONNECTED = 2
    STATUS_ERROR = 3

    def __init__(self, event_bus, config):
        """
        :param event_bus: EventBus 实例
        :param config: WiFi 配置字典, 包含 'networks', 'timeout', 'retry_delay'
        """
        self.event_bus = event_bus
        self.config = config
        self.logger = get_global_logger()
        
        # StaticCache 集成: 记录上次连接成功的网络, 优化重连策略(低侵入)
        self.static_cache = None
        try:
            from lib.static_cache import StaticCache
            # 如果系统中有全局的 static_cache, 尝试获取引用(避免多实例)
            # 暂时创建独立实例, 后续可优化为依赖注入方式
            self.static_cache = StaticCache("wifi_cache.json")
        except Exception:
            # 静默处理 StaticCache 不可用的情况
            pass
        
        self.wlan = network.WLAN(network.STA_IF)
        self.status = self.STATUS_DISCONNECTED
        self.last_attempt_time = 0
        self.connection_start_time = 0
        self.target_network = None
        
        # NTP 同步标记, 避免重复同步
        self._ntp_synced = False
        self._ntp_attempts = 0
        self._last_connect_event = 0  # 防止重复连接事件
        
        # 激活WLAN接口
        if not self.wlan.active():
            self.logger.info("激活WLAN接口...", module="WiFi")
            self.wlan.active(True)

    def is_connected(self):
        """检查WiFi是否已连接。"""
        # 综合检查：内部状态和实际连接状态必须都为真
        return (self.status == self.STATUS_CONNECTED and 
                self.wlan.isconnected())

    def connect(self):
        """开始连接到最佳可用WiFi网络, 非阻塞。"""
        if self.status == self.STATUS_CONNECTING or self.status == self.STATUS_CONNECTED:
            return

        self.logger.info("开始WiFi连接过程...", module="WiFi")
        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="connecting", module="WiFi")
        
        best_network = self._find_best_network()
        if not best_network:
            self.logger.warning("未找到配置的WiFi网络。", module="WiFi")
            self.status = self.STATUS_ERROR
            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", reason="NO_NETWORKS_FOUND", module="WiFi")
            return

        self.target_network = best_network
        self._attempt_connection()

    def _find_best_network(self):
        """扫描并找到信号最好的已配置网络。"""
        self.logger.info("扫描网络...", module="WiFi")
        try:
            scan_results = self.wlan.scan()
        except OSError as e:
            self.logger.error(f"WiFi扫描错误: {e}", module="WiFi")
            return None
            
        configured_ssids = {net['ssid'] for net in self.config.get('networks', [])}
        
        found_networks = []
        for ssid_bytes, _, _, rssi, _, _ in scan_results:
            try:
                ssid = ssid_bytes.decode('utf-8')
                if ssid in configured_ssids:
                    found_networks.append({'ssid': ssid, 'rssi': rssi})
            except UnicodeError:
                continue # 忽略无法解码的SSID
        
        if not found_networks:
            return None
        
        # 优先选择上次成功连接的网络(如果在扫描结果中且信号足够)
        last_successful_ssid = None
        if self.static_cache:
            try:
                last_successful_ssid = self.static_cache.get('last_successful_ssid')
                if last_successful_ssid:
                    for net in found_networks:
                        if net['ssid'] == last_successful_ssid and net['rssi'] > -70:  # 信号强度阈值
                            self.logger.info(f"使用缓存的成功网络: {last_successful_ssid} (信号强度: {net['rssi']})", module="WiFi")
                            # 查找完整的网络配置，同时添加rssi信息
                            for net_config in self.config.get('networks', []):
                                if net_config['ssid'] == last_successful_ssid:
                                    # 创建网络配置的副本，添加rssi信息
                                    network_config = net_config.copy()
                                    network_config['rssi'] = net['rssi']
                                    return network_config
            except Exception:
                # 静默处理缓存读取错误
                pass
        
        # 如果缓存网络不可用, 按RSSI排序
        found_networks.sort(key=lambda x: x['rssi'], reverse=True)
        best_ssid = found_networks[0]['ssid']
        self.logger.info(f"找到最佳网络: {best_ssid} (信号强度: {found_networks[0]['rssi']})", module="WiFi")
        
        # 从原始配置中查找密码并返回整个网络配置，同时添加rssi信息
        for net_config in self.config.get('networks', []):
            if net_config['ssid'] == best_ssid:
                # 创建网络配置的副本，添加rssi信息
                network_config = net_config.copy()
                network_config['rssi'] = found_networks[0]['rssi']
                return network_config
        return None

    def _attempt_connection(self):
        """尝试连接到目标网络。"""
        if not self.target_network:
            return

        # 合并连接尝试日志, 使用结构化格式
        self.logger.info("连接WiFi - ssid={}, rssi={}", 
                       self.target_network['ssid'], 
                       self.target_network.get('rssi', 'unknown'), 
                       module="WiFi")
        self.status = self.STATUS_CONNECTING
        self.connection_start_time = time.ticks_ms()
        self.wlan.connect(self.target_network['ssid'], self.target_network['password'])

    def disconnect(self):
        """断开WiFi连接。"""
        if self.wlan.isconnected():
            self.wlan.disconnect()
        self.status = self.STATUS_DISCONNECTED
        self.logger.info("WiFi已断开连接", module="WiFi")
        # 直接日志记录即可，无需通过事件总线重复发布日志
        # 断开连接后重置 NTP 状态，便于下次成功后再次同步
        self._ntp_synced = False
        self._ntp_attempts = 0
        self._last_connect_event = 0
        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", reason="MANUAL_DISCONNECT", module="WiFi")

    def update(self):
        """
        在主循环中定期调用, 处理连接状态变化。
        """
        # 状态机逻辑
        if self.status == self.STATUS_CONNECTING:
            # 检查是否连接成功
            if self.wlan.isconnected():
                self.status = self.STATUS_CONNECTED
                ip_info = self.wlan.ifconfig()
                
                # 添加调试日志
                self.logger.info("WiFi已连接到AP，获取IP信息: {}", ip_info, module="WiFi")
                
                # 检查 IP 地址是否有效
                if ip_info and ip_info[0] and ip_info[0] != "0.0.0.0":
                    ip_address = ip_info[0]
                    ssid = self.target_network.get('ssid', 'unknown')
                    
                    # 防止重复连接事件
                    now = time.ticks_ms()
                    if time.ticks_diff(now, self._last_connect_event) > 5000:  # 5秒防重复
                        self._last_connect_event = now
                        
                        # 合并WiFi连接成功日志, 使用结构化格式
                        self.logger.info("WiFi已连接 - ip={}, ssid={}", ip_address, ssid, module="WiFi")
                        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="connected", ip=ip_address, ssid=ssid, module="WiFi")
                        
                        # 联网成功后尝试进行 NTP 时间同步
                        self._try_ntp_sync()
                else:
                    self.logger.warning("WiFi已连接但未获取有效IP地址: {}, 重试中...", ip_info, module="WiFi")
                    self.wlan.disconnect()
                    # 重新开始连接过程, 不改变状态
                    self.connection_start_time = time.ticks_ms()
                    
            # 检查是否连接超时
            elif time.ticks_diff(time.ticks_ms(), self.connection_start_time) > self.config.get('timeout', 15) * 1000:
                self.logger.warning("WiFi连接超时。", module="WiFi")
                # 统一使用logger记录即可，不再通过事件总线重复发布
                self.logger.warning("WiFi连接超时 - 网络: {}", self.target_network['ssid'], module="WiFi")
                self.wlan.disconnect() # 确保停止尝试
                self.status = self.STATUS_ERROR
                self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", reason="TIMEOUT", ssid=self.target_network.get('ssid'), module="WiFi")
                self.last_attempt_time = time.ticks_ms()

        elif self.status == self.STATUS_CONNECTED:
            # 持续检查连接是否丢失
            if not self.wlan.isconnected():
                self.logger.warning("WiFi连接丢失。", module="WiFi")
                # 统一使用logger记录即可，不再通过事件总线重复发布
                self.status = self.STATUS_DISCONNECTED
                self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", reason="CONNECTION_LOST", module="WiFi")
                self.last_attempt_time = time.ticks_ms()
                # 重置 NTP 同步状态
                self._ntp_synced = False
                self._ntp_attempts = 0
                self._last_connect_event = 0
                # 连接稳定时, 更新 StaticCache 记录成功网络(防抖写入)
                if self.static_cache and self.target_network:
                    try:
                        current_ssid = self.target_network.get('ssid')
                        if current_ssid:
                            # 记录成功连接的网络, 用于下次优先选择
                            self.static_cache.set('last_successful_ssid', current_ssid)
                            # 记录连接成功的时间戳
                            self.static_cache.set('last_connection_time', time.ticks_ms())
                    except Exception:
                        # 静默处理缓存写入错误
                        pass

        elif self.status in (self.STATUS_DISCONNECTED, self.STATUS_ERROR):
            # 检查是否到了重试时间
            retry_delay_ms = self.config.get('retry_delay', 30) * 1000
            if time.ticks_diff(time.ticks_ms(), self.last_attempt_time) > retry_delay_ms:
                self.connect() # 重新开始连接流程
        
        gc.collect()

    # --------------------------- NTP 同步逻辑 ---------------------------
    def _try_ntp_sync(self):
        """尝试执行 NTP 时间同步(带重试与事件上报)。"""
        if self._ntp_synced:
            return
        if not self.wlan.isconnected():
            return
        if ntptime is None:
            # 环境不支持 ntptime(可能是PC端), 跳过但报告失败事件
            self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="failed", reason="NTP_MODULE_NOT_AVAILABLE", module="WiFi")
            self.logger.warning("NTP模块不可用, 跳过时间同步", module="WiFi")
            return
        
        # 通过配置允许自定义 NTP 服务器, 默认使用阿里云 NTP 池
        ntp_server = self.config.get('ntp_server', 'ntp1.aliyun.com')
        max_attempts = int(self.config.get('ntp_max_attempts', 3))
        retry_interval = int(self.config.get('ntp_retry_interval', 2))  # 秒
        
        try:
            if hasattr(ntptime, 'host'):
                ntptime.host = ntp_server  # 设置 NTP 服务器
        except Exception:
            # 某些端口的 ntptime 不支持设置 host, 忽略
            pass
        
        # 发布开始事件(只发布一次)
        self.logger.info("NTP同步开始 - 服务器={}", ntp_server, module="WiFi")
        self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="started", ntp_server=ntp_server, module="WiFi")
        
        # 在执行阻塞操作前，暂停事件总线定时器
        self.event_bus.stop_timer()
        
        try:
            for i in range(max_attempts):
                self._ntp_attempts = i + 1
                try:
                    # ntptime.settime() 是一个阻塞操作
                    ntptime.settime()
                    # 成功
                    self._ntp_synced = True
                    timestamp = time.time()
                    
                    self.logger.info("NTP同步成功 - 服务器={}, 尝试次数={}, 时间戳={}",
                                   ntp_server, self._ntp_attempts, timestamp, module="WiFi")
                    
                    self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="success", ntp_server=ntp_server, attempts=self._ntp_attempts, timestamp=timestamp, module="WiFi")
                    break # 成功后退出循环
                except Exception as e:
                    self.logger.warning("NTP同步失败, 尝试 {}/{}: {}", self._ntp_attempts, max_attempts, str(e), module="WiFi")
                    if i == max_attempts - 1:
                        self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="failed", error=str(e), attempts=self._ntp_attempts, ntp_server=ntp_server, module="WiFi")
                    else:
                        time.sleep(retry_interval)
        finally:
            # 无论NTP同步成功与否，都恢复事件总线定时器
            self.event_bus.start_timer()
