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
        self.wifi = WifiManager(self.config.get('wifi', {}))
        self.ntp = NtpManager(self.config.get('ntp', {}))
        self.mqtt = MqttController(self.config.get('mqtt', {}))
        
        # 连接状态
        self.state = 'disconnected'  # disconnected, connecting, connected, error
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
        self.health_check_interval = 30000  # 30秒检查一次网络健康
        self.connection_quality_score = 100  # 连接质量评分 (0-100)
        self.last_connection_time = 0
        
        info("网络管理器初始化完成", module="NET")
    
    def loop(self):
        """主循环处理"""
        try:
            current_time = time.ticks_ms()
            
            # 定期检查连接状态
            if current_time - self.last_status_check > self.status_check_interval:
                self._check_connections()
                self.last_status_check = current_time
            
            # 网络健康检查（30秒一次）
            if current_time - self.last_health_check > self.health_check_interval:
                self._check_network_health()
                self.last_health_check = current_time
            
            # 处理重试逻辑（非阻塞）
            if self.state == 'connecting' and self.next_retry_time > 0:
                if current_time >= self.next_retry_time:
                    info("执行延迟重试连接", module="NET")
                    self.next_retry_time = 0
                    self._connect_all()
            
            # 处理MQTT消息
            if self.mqtt.is_connected():
                self.mqtt.check_msg()
                
        except Exception as e:
            error("网络管理器循环错误: {}", e, module="NET")
            self._handle_error(e)
    
    def connect(self):
        """启动网络连接"""
        if self.state == 'disconnected':
            info("启动网络连接", module="NET")
            self.state = 'connecting'
            self.retry_count = 0
            self._connect_all()
        else:
            warning("当前状态{}不允许启动连接", self.state, module="NET")
    
    def disconnect(self):
        """断开网络连接"""
        info("断开网络连接", module="NET")
        self.state = 'disconnected'
        self._disconnect_all()
    
    def get_status(self):
        """获取网络状态"""
        return {
            'state': self.state,
            'wifi_connected': self.wifi.get_is_connected(),
            'mqtt_connected': self.mqtt.is_connected(),
            'ntp_synced': self.ntp.is_synced(),
            'retry_count': self.retry_count
        }
    
    def is_connected(self):
        """检查是否已连接 - 基于WiFi状态"""
        return self.wifi.get_is_connected()
    
    def is_fully_connected(self):
        """检查是否完全连接 - WiFi和MQTT都连接"""
        return self.wifi.get_is_connected() and self.mqtt.is_connected()
    
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
        """连接所有网络服务"""
        try:
            # 1. 连接WiFi
            info("连接WiFi...", module="NET")
            wifi_config = self.config.get('wifi', {})
            
            # 检查配置格式 - 支持networks列表格式
            networks = wifi_config.get('networks', [])
            if not networks:
                raise Exception("WiFi配置缺少networks列表")
            
            # 扫描可用网络
            available_networks = self.wifi.scan_networks()
            info("找到 {} 个可用WiFi网络", len(available_networks), module="NET")
            
            # 选择最优网络（按信号强度和配置优先级）
            selected_network = self._select_best_network(available_networks, networks)
            if not selected_network:
                raise Exception("没有找到可用的WiFi网络")
            
            info("尝试连接WiFi: {} (RSSI: {})", selected_network['ssid'], selected_network['rssi'], module="NET")
            
            if not self.wifi.connect(selected_network['ssid'], selected_network['password']):
                raise Exception("WiFi连接失败")
            
            # 等待WiFi连接（减少等待时间）
            import time
            wait_start = time.ticks_ms()
            while not self.wifi.get_is_connected() and time.ticks_diff(time.ticks_ms(), wait_start) < 3000:
                time.sleep_ms(100)
            
            if not self.wifi.get_is_connected():
                raise Exception("WiFi连接超时")
            
            info("WiFi连接成功: {}", selected_network['ssid'], module="NET")
            
            # 2. 同步NTP时间
            info("同步NTP时间...", module="NET")
            self.ntp.sync_time()
            
            # 3. 连接MQTT
            info("连接MQTT...", module="NET")
            if not self.mqtt.connect():
                raise Exception("MQTT连接失败")
            
            # 连接成功
            self.state = 'connected'
            self.retry_count = 0
            self.last_connection_time = time.ticks_ms()
            self.connection_quality_score = 100  # 重置连接质量评分
            info("所有网络服务连接成功", module="NET")
            
            # 清理重连时间戳
            for attr in ['_last_wifi_retry_time', '_last_mqtt_retry_time', 'mqtt_retry_count']:
                if hasattr(self, attr):
                    delattr(self, attr)
            
            # 发布事件
            self.event_bus.publish(EVENTS['SYSTEM_STATE_CHANGE'], 
                                 state='NETWORKING', 
                                 message='网络连接成功')
            
        except Exception as e:
            error("网络连接失败: {}", e, module="NET")
            self._handle_connection_failed(e)
    
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
            if not wifi_ok and self.state == 'connected':
                current_time = time.ticks_ms()
                # 只有距离上次重连超过30秒才尝试重连，避免频繁重连
                if not hasattr(self, '_last_wifi_retry_time') or current_time - self._last_wifi_retry_time > 30000:
                    warning("WiFi连接断开，尝试重新连接", module="NET")
                    self._last_wifi_retry_time = current_time
                    self._handle_wifi_connection_failed(Exception("WiFi连接断开"))
                else:
                    debug("WiFi连接断开，等待重连冷却期", module="NET")
            
            # 如果MQTT断开但WiFi正常，只重连MQTT（快速重连）
            elif wifi_ok and not mqtt_ok and self.state == 'connected':
                current_time = time.ticks_ms()
                # MQTT重连间隔较短，5秒即可
                if not hasattr(self, '_last_mqtt_retry_time') or current_time - self._last_mqtt_retry_time > 5000:
                    warning("MQTT连接断开，尝试重新连接", module="NET")
                    self._last_mqtt_retry_time = current_time
                    if self.mqtt.connect():
                        info("MQTT重连成功", module="NET")
                        # 重连成功后重置计数器
                        if hasattr(self, 'mqtt_retry_count'):
                            delattr(self, 'mqtt_retry_count')
                    else:
                        error("MQTT重连失败", module="NET")
                        # MQTT重连计数器独立管理
                        self.mqtt_retry_count = getattr(self, 'mqtt_retry_count', 0) + 1
                        if self.mqtt_retry_count >= 5:  # MQTT重连5次失败后触发完整重连
                            warning("MQTT重连次数过多，触发完整网络重连", module="NET")
                            delattr(self, 'mqtt_retry_count')
                            self._handle_connection_failed(Exception("MQTT重连失败"))
                else:
                    debug("MQTT连接断开，等待重连冷却期", module="NET")
                    
        except Exception as e:
            error("检查连接状态失败: {}", e, module="NET")
    
    def _handle_wifi_connection_failed(self, error_msg):
        """处理WiFi连接失败"""
        self.retry_count += 1
        error("WiFi连接失败，重试次数: {}/{}", self.retry_count, self.max_retries, module="NET")
        
        if self.retry_count >= self.max_retries:
            self.state = 'error'
            error("达到最大重试次数，连接失败", module="NET")
            
            # 发布系统错误事件
            self.event_bus.publish(EVENTS['SYSTEM_ERROR'], 
                                 error_type="wifi_connection_failed",
                                 error_message=str(error_msg))
        else:
            self.state = 'connecting'
            # 计算重试延迟（指数退避）
            delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 30000)
            info("{}秒后重试WiFi连接", delay // 1000, module="NET")
            
            # 设置下次重试时间，在loop中处理
            self.next_retry_time = time.ticks_ms() + delay
    
    def _handle_connection_failed(self, error_msg):
        """处理连接失败"""
        self.retry_count += 1
        error("连接失败，重试次数: {}/{}", self.retry_count, self.max_retries, module="NET")
        
        if self.retry_count >= self.max_retries:
            self.state = 'error'
            error("达到最大重试次数，连接失败", module="NET")
            
            # 发布系统错误事件
            self.event_bus.publish(EVENTS['SYSTEM_ERROR'], 
                                 error_type="network_connection_failed",
                                 error_message=str(error_msg))
        else:
            self.state = 'connecting'
            # 计算重试延迟（指数退避）
            delay = min(self.retry_delay * (2 ** (self.retry_count - 1)), 30000)
            info("{}秒后重试连接", delay // 1000, module="NET")
            
            # 设置下次重试时间，在loop中处理
            self.next_retry_time = time.ticks_ms() + delay
    
    def _handle_error(self, error_msg):
        """处理错误"""
        error("网络管理器错误: {}", error_msg, module="NET")
        self.state = 'error'
        
        # 发布系统错误事件
        self.event_bus.publish(EVENTS['SYSTEM_ERROR'], 
                             error_type="network_manager_error",
                             error_message=str(error_msg))
    
    def _select_best_network(self, available_networks, configured_networks):
        """选择最优WiFi网络"""
        try:
            # 创建配置网络的字典，便于快速查找
            config_dict = {net['ssid']: net for net in configured_networks}
            
            # 筛选出配置中存在的网络
            matched_networks = []
            for available in available_networks:
                ssid = available['ssid']
                if ssid in config_dict:
                    matched_networks.append({
                        'ssid': ssid,
                        'password': config_dict[ssid]['password'],
                        'rssi': available['rssi'],
                        'bssid': available['bssid']
                    })
            
            if not matched_networks:
                return None
            
            # 按信号强度排序（RSSI值越大信号越强）
            matched_networks.sort(key=lambda x: x['rssi'], reverse=True)
            
            # 返回信号最强的网络
            best_network = matched_networks[0]
            info("选择最优网络: {} (信号强度: {}dBm)", best_network['ssid'], best_network['rssi'], module="NET")
            
            return best_network
            
        except Exception as e:
            error("选择最优网络失败: {}", e, module="NET")
            return None
    
    def _check_network_health(self):
        """检查网络连接健康状态"""
        try:
            wifi_ok = self.wifi.get_is_connected()
            mqtt_ok = self.mqtt.is_connected()
            
            # 更新连接质量评分
            if wifi_ok and mqtt_ok:
                # 完全连接，缓慢恢复评分
                self.connection_quality_score = min(100, self.connection_quality_score + 5)
                if not self.last_connection_time:
                    self.last_connection_time = time.ticks_ms()
            elif wifi_ok:
                # 只有WiFi，评分中等
                self.connection_quality_score = max(40, self.connection_quality_score - 2)
            else:
                # 无连接，快速降低评分
                self.connection_quality_score = max(0, self.connection_quality_score - 10)
            
            # 根据评分输出状态信息
            if self.connection_quality_score >= 90:
                debug("网络健康状态: 优秀 ({})", self.connection_quality_score, module="NET")
            elif self.connection_quality_score >= 70:
                debug("网络健康状态: 良好 ({})", self.connection_quality_score, module="NET")
            elif self.connection_quality_score >= 50:
                warning("网络健康状态: 一般 ({})", self.connection_quality_score, module="NET")
            elif self.connection_quality_score >= 30:
                warning("网络健康状态: 较差 ({})", self.connection_quality_score, module="NET")
            else:
                error("网络健康状态: 极差 ({})", self.connection_quality_score, module="NET")
            
            # 如果评分过低且状态为已连接，可能存在隐藏问题
            if self.connection_quality_score < 30 and self.state == 'connected':
                warning("网络连接质量过低，执行诊断检查", module="NET")
                self._diagnose_connection_issues()
                
        except Exception as e:
            error("网络健康检查失败: {}", e, module="NET")
    
    def _diagnose_connection_issues(self):
        """诊断连接问题"""
        try:
            info("开始网络连接诊断...", module="NET")
            
            # 检查WiFi信号强度
            if hasattr(self.wifi, 'get_rssi'):
                try:
                    rssi = self.wifi.get_rssi()
                    info("WiFi信号强度: {} dBm", rssi, module="NET")
                    if rssi < -80:
                        warning("WiFi信号较弱，可能影响连接稳定性", module="NET")
                except:
                    debug("无法获取WiFi信号强度", module="NET")
            
            # 检查MQTT连接状态
            if self.mqtt.is_connected():
                info("MQTT连接正常", module="NET")
            else:
                warning("MQTT连接异常", module="NET")
            
            # 检查连接持续时间
            if self.last_connection_time > 0:
                uptime = time.ticks_diff(time.ticks_ms(), self.last_connection_time)
                uptime_seconds = uptime // 1000
                info("网络连接持续时间: {} 秒", uptime_seconds, module="NET")
                
                # 如果连接时间过长但评分低，建议重启
                if uptime_seconds > 3600 and self.connection_quality_score < 50:
                    warning("网络连接时间过长但质量下降，建议重启网络连接", module="NET")
                    self.state = 'connecting'
                    self.retry_count = 0
                    
        except Exception as e:
            error("连接诊断失败: {}", e, module="NET")
    
    def reset(self):
        """重置网络管理器"""
        info("重置网络管理器", module="NET")
        self.state = 'disconnected'
        self.retry_count = 0
        self.next_retry_time = 0
        self.connection_quality_score = 100
        self.last_connection_time = 0
        # 清理重连时间戳
        for attr in ['_last_wifi_retry_time', '_last_mqtt_retry_time', 'mqtt_retry_count']:
            if hasattr(self, attr):
                delattr(self, attr)
        self._disconnect_all()