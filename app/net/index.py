# app/net/index.py
# 网络统一控制器 - 管理WiFi、NTP、MQTT的连接流程和重连机制
import utime as time
from lib.logger import get_global_logger
from lib.event_bus.events_const import EVENTS
from .wifi import WifiManager
from .ntp import NtpManager
from .mqtt import MqttController

class NetworkManager:
    """
    网络统一控制器
    
    负责管理WiFi、NTP、MQTT的连接流程和重连机制：
    - 统一的连接流程：WiFi → NTP → MQTT
    - 统一的指数退避重连机制
    - 事件订阅和发布中心化
    - 状态管理和错误处理
    """
    
    def __init__(self, event_bus, config):
        """
        初始化网络管理器
        
        Args:
            event_bus: EventBus实例
            config: 网络配置字典
        """
        self.event_bus = event_bus
        self.config = config
        self.logger = get_global_logger()
        
        # 初始化各个网络组件
        self.wifi = WifiManager(config.get('wifi', {}))
        self.ntp = NtpManager(config.get('ntp', {}))
        self.mqtt = MqttController(config.get('mqtt', {}))
        
        # 设置MQTT的事件总线
        self.mqtt.set_event_bus(event_bus)
        
        # 连接状态
        self.wifi_connected = False
        self.ntp_synced = False
        self.mqtt_connected = False
        
        # 重连计数和时间戳
        self.wifi_failures = 0
        self.ntp_failures = 0
        self.mqtt_failures = 0
        
        self.last_wifi_attempt = 0
        self.last_ntp_attempt = 0
        self.last_mqtt_attempt = 0
        
        # 重连配置
        self.backoff_base = config.get('backoff_base', 2)
        self.backoff_multiplier = config.get('backoff_multiplier', 2)
        self.max_backoff_time = config.get('max_backoff_time', 300)
        self.max_retries = config.get('max_retries', 5)
        
        # 订阅系统事件
        self._setup_event_subscriptions()
    
    def _setup_event_subscriptions(self):
        """设置事件订阅"""
        # 订阅系统状态变化事件
        self.event_bus.subscribe(EVENTS.SYSTEM_STATE_CHANGE, self._on_system_state_change)
        # 订阅WiFi状态变化事件
        self.event_bus.subscribe(EVENTS.WIFI_STATE_CHANGE, self._on_wifi_state_change)
        # 订阅MQTT状态变化事件
        self.event_bus.subscribe(EVENTS.MQTT_STATE_CHANGE, self._on_mqtt_state_change)
    
    def _on_system_state_change(self, state, info=None):
        """
        处理系统状态变化事件
        
        Args:
            state: 系统状态
            info: 附加信息
        """
        if state == 'networking':
            self.logger.info("系统进入网络状态，开始连接流程", module="Network")
            self.start_connection_flow()
        elif state == 'shutdown':
            self.logger.info("系统关闭，断开网络连接", module="Network")
            self.disconnect_all()
    
    def _on_wifi_state_change(self, state, info=None):
        """
        处理WiFi状态变化事件
        
        Args:
            state: WiFi状态
            info: 附加信息
        """
        if state == 'disconnected':
            self.wifi_connected = False
            # WiFi断开时，MQTT也会断开
            if self.mqtt_connected:
                self.mqtt_connected = False
                self.logger.info("WiFi断开，MQTT连接已丢失", module="Network")
    
    def _on_mqtt_state_change(self, state, info=None):
        """
        处理MQTT状态变化事件
        
        Args:
            state: MQTT状态
            info: 附加信息
        """
        if state == 'disconnected':
            self.mqtt_connected = False
    
    def _calculate_backoff_delay(self, failures):
        """
        计算指数退避延迟时间
        
        Args:
            failures: 失败次数
            
        Returns:
            int: 延迟时间（秒）
        """
        if failures == 0:
            return 0
        
        delay = min(
            self.backoff_base * (self.backoff_multiplier ** (failures - 1)),
            self.max_backoff_time
        )
        return int(delay)
    
    def _should_retry(self, failures, last_attempt):
        """
        检查是否应该重试
        
        Args:
            failures: 失败次数
            last_attempt: 上次尝试时间戳
            
        Returns:
            bool: 是否应该重试
        """
        if failures >= self.max_retries:
            return False
        
        delay = self._calculate_backoff_delay(failures)
        if delay == 0:
            return True
        
        now = time.ticks_ms()
        return time.ticks_diff(now, last_attempt) >= delay * 1000
    
    def connect_wifi(self):
        """
        连接WiFi网络
        
        Returns:
            bool: 连接成功返回True
        """
        if self.wifi_connected and self.wifi.get_is_connected():
            return True
        
        if not self._should_retry(self.wifi_failures, self.last_wifi_attempt):
            return False
        
        self.last_wifi_attempt = time.ticks_ms()
        self.logger.info("尝试连接WiFi网络", module="Network")
        
        # 发布连接开始事件
        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="connecting")
        
        # 扫描网络
        networks = self.wifi.scan_networks()
        if not networks:
            self.wifi_failures += 1
            self.logger.error("未找到可用的WiFi网络", module="Network")
            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", error="未找到网络")
            return False
        
        # 尝试连接配置中的网络
        wifi_config = self.config.get('wifi', {})
        wifi_networks = wifi_config.get('networks', [])
        
        if not wifi_networks:
            self.wifi_failures += 1
            self.logger.error("WiFi配置中没有网络信息", module="Network")
            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", error="配置错误")
            return False
        
        # 按信号强度排序网络，优先连接信号最强的配置网络
        connected = False
        for network in networks:
            ssid = network['ssid']
            
            # 检查是否在配置的网络列表中
            for network_config in wifi_networks:
                if network_config.get('ssid') == ssid:
                    password = network_config.get('password')
                    
                    self.logger.info("尝试连接WiFi: {} (信号强度: {})", ssid, network['rssi'], module="Network")
                    
                    if self.wifi.connect(ssid, password):
                        # 等待连接建立
                        time.sleep_ms(1000)
                        
                        if self.wifi.get_is_connected():
                            self.wifi_connected = True
                            self.wifi_failures = 0
                            self.logger.info("WiFi连接成功: {}", ssid, module="Network")
                            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="connected", ssid=ssid)
                            connected = True
                            break
                        else:
                            self.logger.warning("WiFi连接超时: {}", ssid, module="Network")
                    else:
                        self.logger.warning("WiFi连接失败: {}", ssid, module="Network")
            
            if connected:
                break
        
        if not connected:
            self.wifi_failures += 1
            self.logger.error("所有配置的WiFi网络连接失败", module="Network")
            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", error="连接失败")
        
        return connected
    
    def sync_ntp(self):
        """
        同步NTP时间
        
        Returns:
            bool: 同步成功返回True
        """
        if self.ntp_synced:
            return True
        
        if not self.wifi_connected:
            self.logger.debug("WiFi未连接，跳过NTP同步", module="Network")
            return False
        
        if not self._should_retry(self.ntp_failures, self.last_ntp_attempt):
            return False
        
        self.last_ntp_attempt = time.ticks_ms()
        self.logger.info("开始NTP时间同步", module="Network")
        
        # 发布同步开始事件
        self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="started")
        
        try:
            if self.ntp.sync_time():
                self.ntp_synced = True
                self.ntp_failures = 0
                self.logger.info("NTP同步成功", module="Network")
                self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="success")
                return True
            else:
                self.ntp_failures += 1
                self.logger.error("NTP同步失败", module="Network")
                self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="failed")
                return False
        except Exception as e:
            self.ntp_failures += 1
            self.logger.error("NTP同步异常: {}", e, module="Network")
            self.event_bus.publish(EVENTS.NTP_STATE_CHANGE, state="failed", error=str(e))
            return False
    
    def connect_mqtt(self):
        """
        连接MQTT服务器
        
        Returns:
            bool: 连接成功返回True
        """
        if self.mqtt_connected and self.mqtt.is_connected():
            return True
        
        if not self.wifi_connected:
            self.logger.warning("WiFi未连接，跳过MQTT连接", module="Network")
            return False
        
        if not self._should_retry(self.mqtt_failures, self.last_mqtt_attempt):
            return False
        
        # 检查MQTT配置
        mqtt_config = self.config.get('mqtt', {})
        if not mqtt_config.get('broker'):
            self.logger.error("MQTT配置中缺少broker地址", module="Network")
            return False
        
        self.last_mqtt_attempt = time.ticks_ms()
        self.logger.info("开始连接MQTT服务器: {}", mqtt_config.get('broker'), module="Network")
        
        try:
            if self.mqtt.connect():
                # 等待连接建立
                time.sleep_ms(500)
                
                if self.mqtt.is_connected():
                    self.mqtt_connected = True
                    self.mqtt_failures = 0
                    self.logger.info("MQTT连接成功", module="Network")
                    return True
                else:
                    self.mqtt_failures += 1
                    self.logger.error("MQTT连接超时", module="Network")
                    return False
            else:
                self.mqtt_failures += 1
                self.logger.error("MQTT连接失败", module="Network")
                return False
        except Exception as e:
            self.mqtt_failures += 1
            self.logger.error("MQTT连接异常: {}", e, module="Network")
            return False
    
    def start_connection_flow(self):
        """
        启动连接流程：WiFi → NTP → MQTT
        
        Returns:
            bool: 连接流程成功返回True
        """
        self.logger.info("启动网络连接流程", module="Network")
        
        # 步骤1: 连接WiFi
        if not self.connect_wifi():
            self.logger.error("WiFi连接失败，停止连接流程", module="Network")
            return False
        
        # 步骤2: NTP同步（可选，不影响MQTT连接）
        self.sync_ntp()
        
        # 步骤3: 连接MQTT
        if not self.connect_mqtt():
            self.logger.warning("MQTT连接失败，但WiFi已连接", module="Network")
            # WiFi连接成功，但MQTT失败，仍然返回True
            return True
        
        self.logger.info("网络连接流程完成", module="Network")
        return True
    
    def check_connections(self):
        """
        检查所有连接状态，必要时重连
        
        Returns:
            bool: 所有连接正常返回True
        """
        all_ok = True
        
        # 检查WiFi连接
        if not self.wifi_connected or not self.wifi.get_is_connected():
            self.wifi_connected = False
            self.logger.warning("WiFi连接丢失", module="Network")
            self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected", error="连接丢失")
            
            # 尝试重连WiFi
            if not self.connect_wifi():
                all_ok = False
            else:
                # WiFi重连成功，尝试重连MQTT
                if not self.connect_mqtt():
                    all_ok = False
        else:
            # WiFi连接正常，检查MQTT连接
            if not self.mqtt_connected or not self.mqtt.is_connected():
                self.mqtt_connected = False
                self.logger.warning("MQTT连接丢失", module="Network")
                
                # 尝试重连MQTT
                if not self.connect_mqtt():
                    all_ok = False
        
        # 检查NTP同步状态（可选）
        if self.wifi_connected and not self.ntp_synced:
            # 可以尝试重新同步NTP
            self.sync_ntp()
        
        return all_ok
    
    def disconnect_all(self):
        """
        断开所有网络连接
        """
        self.logger.info("断开所有网络连接", module="Network")
        
        # 断开MQTT
        if self.mqtt_connected:
            self.mqtt.disconnect()
            self.mqtt_connected = False
        
        # 断开WiFi
        if self.wifi_connected:
            self.wifi.disconnect()
            self.wifi_connected = False
        
        # 重置NTP状态
        self.ntp_synced = False
        
        # 发布断开连接事件
        self.event_bus.publish(EVENTS.WIFI_STATE_CHANGE, state="disconnected")
        self.event_bus.publish(EVENTS.MQTT_STATE_CHANGE, state="disconnected")
    
    def loop(self):
        """
        主循环处理函数
        """
        # 运行MQTT循环
        self.mqtt.loop()
        
        # 定期检查连接状态（每30秒检查一次）
        current_time = time.ticks_ms()
        if not hasattr(self, '_last_check_time'):
            self._last_check_time = 0
        
        if time.ticks_diff(current_time, self._last_check_time) > 30000:  # 30秒
            self._last_check_time = current_time
            self.check_connections()
    
    def reset_failures(self):
        """
        重置所有失败计数器
        """
        self.wifi_failures = 0
        self.ntp_failures = 0
        self.mqtt_failures = 0
        self.logger.info("重置网络失败计数器", module="Network")
    
    def get_status(self):
        """
        获取网络连接状态
        
        Returns:
            dict: 网络状态信息
        """
        return {
            'wifi_connected': self.wifi_connected,
            'ntp_synced': self.ntp_synced,
            'mqtt_connected': self.mqtt_connected,
            'wifi_failures': self.wifi_failures,
            'ntp_failures': self.ntp_failures,
            'mqtt_failures': self.mqtt_failures,
            'last_wifi_attempt': self.last_wifi_attempt,
            'last_ntp_attempt': self.last_ntp_attempt,
            'last_mqtt_attempt': self.last_mqtt_attempt
        }