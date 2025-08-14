# app/net/index.py
# 网络统一控制器

import utime as time
from lib.logger import debug, info, warning, error
from lib.lock.event_bus import EVENTS
from .wifi import WifiManager
from .ntp import NtpManager
from .mqtt import MqttController

# 状态常量
STATE_DISCONNECTED, STATE_CONNECTING, STATE_CONNECTED = 0, 1, 2
STATE_NAMES = ["DISCONNECTED", "CONNECTING", "CONNECTED"]

class NetworkManager:
    """网络统一控制器 - 管理 WiFi→NTP→MQTT 完整流程"""
    
    def __init__(self, event_bus):
        self.event_bus = event_bus
        
        # 内置网络配置
        config = {
            'wifi': {
                'networks': [
                    {"ssid": "zsm60p", "password": "25845600"},
                    {"ssid": "leju_software", "password": "leju123456"},
                    {"ssid": "CMCC-pdRG", "password": "7k77ed5p"}
                ]
            },
            'mqtt': {
                'broker': '192.168.3.15', 'port': 1883,
                'user': '', 'password': '', 'keepalive': 60
            },
            'ntp': {
                'ntp_server': 'ntp1.aliyun.com',
                'ntp_max_attempts': 3, 'ntp_retry_interval': 2
            }
        }

        # 初始化组件
        self.wifi = WifiManager(config['wifi'])
        self.ntp = NtpManager(config['ntp'])
        self.mqtt = MqttController(config['mqtt'])
        
        # 状态管理
        self._reset_state()
        
        # 配置参数
        self.max_retries = 5
        self.retry_delay = 2000
        self.connection_timeout = 30000  # 减少超时时间，避免长时间阻塞

    def _reset_state(self):
        """重置状态"""
        self.current_state = STATE_DISCONNECTED
        self.state_start_time = time.ticks_ms()
        self.retry_count = 0
        self.wifi_connected = False
        self.mqtt_connected = False

    def _get_elapsed_time(self):
        """获取状态持续时间"""
        return time.ticks_diff(time.ticks_ms(), self.state_start_time)

    def _transition_to_state(self, new_state):
        """状态转换"""
        if new_state != self.current_state:
            self.current_state = new_state
            self.state_start_time = time.ticks_ms()
            self._publish_state_change()

    def _update_connection_status(self):
        """更新并检测连接状态变化"""
        # 检查WiFi状态
        wifi_status = self.wifi.get_is_connected()
        if wifi_status != self.wifi_connected:
            self.wifi_connected = wifi_status
        
        # 检查MQTT状态并发布变化事件
        mqtt_status = self.mqtt.is_connected()
        if mqtt_status != self.mqtt_connected:
            self.mqtt_connected = mqtt_status
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], 
                                 state='connected' if mqtt_status else 'disconnected')

    def _check_connection_success(self):
        """检查连接是否成功"""
        if self.current_state == STATE_CONNECTING and self.wifi_connected and self.mqtt_connected:
            self._transition_to_state(STATE_CONNECTED)
            self.retry_count = 0
            info("网络连接完成", module="NET")

    def _check_timeouts(self):
        """统一检查各种超时"""
        if self.current_state != STATE_CONNECTING:
            return
            
        elapsed = self._get_elapsed_time()
        
        # 连接超时检查
        if elapsed > self.connection_timeout:
            warning("连接超时({}ms)", elapsed, module="NET")
            self._handle_connection_failed()
            return
        
        # 重试超时检查
        if hasattr(self, 'retry_time') and time.ticks_diff(time.ticks_ms(), self.retry_time) >= 0:
            info("重连时间到达, 开始重试", module="NET")
            self._start_connection_process()

    def _handle_connection_failed(self):
        """处理连接失败"""
        self.retry_count += 1
        
        if self.retry_count <= self.max_retries:
            info("连接失败, {}秒后重试 (第{}/{}次)", 
                 self.retry_delay // 1000, self.retry_count, self.max_retries, module="NET")
            self.retry_time = time.ticks_ms() + self.retry_delay
        else:
            error("达到最大重试次数, 断开连接", module="NET")
            self._transition_to_state(STATE_DISCONNECTED)
            self._disconnect_all()

    def _start_connection_process(self):
        """开始连接流程"""
        self.state_start_time = time.ticks_ms()
        if hasattr(self, 'retry_time'):
            delattr(self, 'retry_time')
        self._connect_wifi()

    def _connect_wifi(self):
        """WiFi连接逻辑"""
        if self.wifi_connected:
            info("WiFi已连接, 直接连接MQTT", module="NET")
            self._connect_mqtt()
            return

        # 发布连接状态
        self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], state="connecting")
        
        # 扫描并连接网络
        networks = self._scan_and_connect_wifi()
        if not networks:
            self._handle_connection_failed()

    def _scan_and_connect_wifi(self):
        """扫描并尝试连接WiFi网络"""
        info("扫描WiFi网络...", module="NET")
        networks = self.wifi.scan_networks(timeout_ms=5000)  # 限制扫描时间为5秒
        
        if not networks:
            error("未找到可用WiFi网络", module="NET")
            return False

        # 尝试连接已配置的网络
        available_ssids = {net['ssid']: net.get('rssi', 'N/A') for net in networks}
        configured_networks = self.wifi.config['networks']
        
        info("发现{}个网络,配置{}个", len(networks), len(configured_networks), module="NET")

        for config in configured_networks:
            ssid = config['ssid']
            if ssid in available_ssids:
                debug("尝试连接WiFi: {} (RSSI: {})", ssid, available_ssids[ssid], module="NET")
                
                if self._attempt_wifi_connection(ssid, config.get('password')):
                    return True

        # 所有网络连接失败
        error("所有WiFi网络连接失败", module="NET")
        self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], 
                             state="disconnected", error="连接失败")
        return False

    def _attempt_wifi_connection(self, ssid, password):
        """尝试连接单个WiFi网络"""
        if not self.wifi.connect(ssid, password):
            error("WiFi连接命令失败: {}", ssid, module="NET")
            return False

        # 等待连接建立(10秒超时)
        info("WiFi连接命令已发送, 等待连接建立...", module="NET")
        start_time = time.ticks_ms()
        
        while time.ticks_diff(time.ticks_ms(), start_time) < 10000:
            if self.wifi.get_is_connected():
                info("WiFi连接成功: {}", ssid, module="NET")
                self.event_bus.publish(EVENTS['WIFI_STATE_CHANGE'], 
                                     state="connected", ssid=ssid)
                self._sync_ntp()  # 同步时间
                self._connect_mqtt()  # 连接MQTT
                return True
            time.sleep_ms(200)
        
        warning("WiFi连接超时: {}", ssid, module="NET")
        return False

    def _connect_mqtt(self):
        """MQTT连接逻辑"""
        if self.mqtt_connected:
            info("MQTT已连接", module="NET")
            return

        info("开始MQTT连接, WiFi状态: {}", self.wifi_connected, module="NET")
        self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], state="connecting")

        try:
            if self.mqtt.connect():
                info("MQTT连接初始化成功", module="NET")
            else:
                error("MQTT初始化失败", module="NET")
                self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], 
                                     state="disconnected", error="连接失败")
        except Exception as e:
            error("MQTT连接异常: {}", e, module="NET")
            self.event_bus.publish(EVENTS['MQTT_STATE_CHANGE'], 
                                 state="disconnected", error=str(e))

    def _sync_ntp(self):
        """NTP时间同步"""
        if not self.wifi_connected:
            return

        try:
            info("开始NTP同步...", module="NET")
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state="started")
            
            success = self.ntp.sync_time()
            state = "success" if success else "failed"
            
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], state=state)
            info("NTP同步{}", "成功" if success else "失败", module="NET")
            
        except Exception as e:
            warning("NTP同步异常: {}", e, module="NET")
            self.event_bus.publish(EVENTS['NTP_STATE_CHANGE'], 
                                 state="failed", error=str(e))

    def _disconnect_all(self):
        """断开所有连接"""
        try:
            if self.mqtt_connected:
                self.mqtt.disconnect()
            if self.wifi_connected:
                self.wifi.disconnect()
                
            self.wifi_connected = False
            self.mqtt_connected = False
            
            # 发布断开事件
            for event in [EVENTS['WIFI_STATE_CHANGE'], EVENTS['MQTT_STATE_CHANGE']]:
                self.event_bus.publish(event, state="disconnected")
                
            info("所有网络已断开", module="NET")
        except Exception as e:
            error("断开连接错误: {}", e, module="NET")

    def _publish_state_change(self):
        """发布状态变化事件"""
        state_name = STATE_NAMES[self.current_state].lower()
        self.event_bus.publish("network_state_change", state=state_name)

    # =============================================================================
    # 公共接口方法
    # =============================================================================

    def loop(self):
        """主循环处理"""
        try:
            self._update_connection_status()
            self._check_connection_success()
            self._check_timeouts()
        except Exception as e:
            error("网络管理器循环错误: {}", e, module="NET")
            self._handle_connection_failed()

    def connect(self):
        """启动网络连接"""
        info("当前状态: {}", STATE_NAMES[self.current_state], module="NET")
        
        if self.current_state == STATE_DISCONNECTED:
            debug("启动网络连接", module="NET")
            self._transition_to_state(STATE_CONNECTING)
            self._start_connection_process()
        else:
            warning("状态{}不允许启动连接", STATE_NAMES[self.current_state], module="NET")

    def disconnect(self):
        """断开网络连接"""
        self._transition_to_state(STATE_DISCONNECTED)
        self._disconnect_all()

    def get_status(self):
        """获取网络状态"""
        return {
            'state': STATE_NAMES[self.current_state],
            'wifi_connected': self.wifi_connected,
            'mqtt_connected': self.mqtt_connected,
            'retry_count': self.retry_count
        }

    def is_connected(self):
        """检查是否已连接"""
        connected = self.current_state == STATE_CONNECTED
        debug("连接检查 - 状态:{}, WiFi:{}, MQTT:{}, 结果:{}", 
              STATE_NAMES[self.current_state], self.wifi_connected, 
              self.mqtt_connected, connected, module="NET")
        return connected

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