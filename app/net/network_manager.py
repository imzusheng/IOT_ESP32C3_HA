# app/net/network_manager.py
"""
网络管理器
职责：
- 顺序编排 WiFi → NTP → MQTT 的连接流程，替代早期的独立 NET FSM
- 在主循环中持续检查 WiFi/MQTT 状态并触发必要的事件
- 对外暴露 connect()/disconnect()/loop()/get_status()/force_reconnect() 等接口

事件约定：
- 当 WiFi 状态变化时发布 EVENTS["WIFI_STATE_CHANGE"]，state ∈ {"connected","disconnected"}
- 当 MQTT 状态变化时发布 EVENTS["MQTT_STATE_CHANGE"]，state ∈ {"connected","disconnected"}

设计边界与约束：
- 不实现指数退避与重试策略（由上层 FSM 或后续版本统一治理）
- NTP 同步失败不会阻塞后续 MQTT 连接
- WifiManager/NtpManager/MqttController 由本模块聚合管理，配置来自 app/config.py

扩展建议：
- 可在不破坏接口的前提下引入退避/重试策略
- 可将连接状态与统计指标上报到事件总线或系统状态接口
"""

import utime as time
import uasyncio as asyncio
# 移除不必要的导入: network, gc
from lib.logger import info, warning, error, debug
from lib.lock.event_bus import EVENTS
from lib.async_runtime import get_runtime

class NetworkManager:
    """
    网络管理器
    直接管理WiFi→NTP→MQTT连接流程，无需独立的NET FSM
    """
    
    def __init__(self, config, event_bus):
        """初始化网络管理器"""
        self.config = config or {}
        self.event_bus = event_bus
        
        # 子配置缓存，避免硬编码与重复取值
        self.wifi_config = (self.config or {}).get("wifi", {})
        self.ntp_config = (self.config or {}).get("ntp", {})
        self.mqtt_config = (self.config or {}).get("mqtt", {})
        
        # 网络组件
        self.wifi_manager = None
        self.ntp_manager = None
        self.mqtt_controller = None
        
        # 连接状态
        self.wifi_connected = False
        self.ntp_synced = False
        self.mqtt_connected = False

        # 无限退避重试策略
        self.mqtt_base_delay = int(self.mqtt_config.get("base_delay_ms", 2000))  # 基础延迟 2秒
        self.mqtt_last_attempt = 0
        
        # WiFi 无限退避重试策略
        self.wifi_base_delay = int(self.wifi_config.get("base_delay_ms", 2000))  # 基础延迟 2秒
        self.wifi_max_delay = int(self.wifi_config.get("max_delay_ms", 180000))  # 最大延迟 3分钟
        self.wifi_last_attempt = 0
        
        # 异步任务管理
        self._wifi_task = None
        self._mqtt_task = None
        self._status_check_task = None
        
        # 初始化组件
        self._init_components()
        
        # 注册异步任务
        self._register_async_tasks()
        
    def _register_async_tasks(self):
        """注册异步任务到运行时"""
        try:
            runtime = get_runtime()
            # 注册 WiFi 连接任务 (每2秒检查一次)
            self._wifi_task = runtime.create_task(
                self._wifi_connection_loop(), 
                "wifi_connection"
            )
            # 注册 MQTT 连接任务 (每2秒检查一次)
            self._mqtt_task = runtime.create_task(
                self._mqtt_connection_loop(), 
                "mqtt_connection"
            )
            # 注册状态检查任务 (每500ms检查一次)
            self._status_check_task = runtime.create_task(
                self._status_check_loop(), 
                "status_check"
            )
            debug("网络管理器异步任务注册完成", module="NET")
        except Exception as e:
            error("注册异步任务失败: {}", e, module="NET")
            
    def _init_components(self):
        """初始化网络组件"""
        try:
            # 使用包内相对导入，保持与现有文件结构一致
            from .wifi import WifiManager
            from .ntp import NtpManager
            from .mqtt import MqttController

            # 按子配置实例化
            self.wifi_manager = WifiManager(self.wifi_config)
            self.ntp_manager = NtpManager(self.ntp_config)
            self.mqtt_controller = MqttController(self.mqtt_config, self.event_bus)
            
            debug("网络组件初始化完成", module="NET")
            
        except Exception as e:
            error("网络组件初始化失败: {}", e, module="NET")
            raise
            
    async def _wifi_connection_loop(self):
        """WiFi 连接协程循环"""
        while True:
            try:
                await self._async_connect_wifi()
                await asyncio.sleep_ms(2000)  # 每2秒检查一次
            except asyncio.CancelledError:
                debug("WiFi连接任务取消", module="NET")
                break
            except Exception as e:
                error("WiFi连接循环异常: {}", e, module="NET")
                await asyncio.sleep_ms(5000)  # 异常时延长间隔
                
    async def _mqtt_connection_loop(self):
        """MQTT 连接协程循环"""
        while True:
            try:
                await self._async_connect_mqtt()
                await asyncio.sleep_ms(2000)  # 每2秒检查一次
            except asyncio.CancelledError:
                debug("MQTT连接任务取消", module="NET")
                break
            except Exception as e:
                error("MQTT连接循环异常: {}", e, module="NET")
                await asyncio.sleep_ms(5000)  # 异常时延长间隔
                
    async def _status_check_loop(self):
        """状态检查协程循环"""
        while True:
            try:
                await self._async_check_status()
                await asyncio.sleep_ms(500)  # 每500ms检查一次
            except asyncio.CancelledError:
                debug("状态检查任务取消", module="NET")
                break
            except Exception as e:
                error("状态检查循环异常: {}", e, module="NET")
                await asyncio.sleep_ms(1000)  # 异常时延长间隔
             
    async def _async_connect_wifi(self):
        """异步 WiFi 连接方法"""
        try:
            if self.wifi_connected and self.wifi_manager and self.wifi_manager.get_is_connected():
                return True

            # 退避重试检查
            now = time.ticks_ms()
            delay = self.wifi_base_delay
            
            if self.wifi_last_attempt > 0:
                remaining = delay - time.ticks_diff(now, self.wifi_last_attempt)
                if remaining > 0:
                    return False

            # 获取网络配置列表
            networks = self.wifi_config.get("networks", [])
            if not networks:
                # 兼容旧配置格式
                ssid = self.wifi_config.get("ssid")
                password = self.wifi_config.get("password")
                if ssid:
                    networks = [{"ssid": ssid, "password": password}]
                else:
                    return False
            
            # 扫描可用网络
            available_networks = await self._async_scan_and_match_networks(networks)
            if not available_networks:
                self.wifi_last_attempt = now
                return False
            
            # 按RSSI降序尝试连接
            for network in available_networks:
                ssid = network["ssid"]
                password = network["password"]
                
                if await self._async_attempt_wifi_connection(ssid, password):
                    self.wifi_connected = True
                    self.wifi_last_attempt = 0  # 重置延迟计时
                    info("WiFi连接成功: {}", ssid, module="NET")
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="connected")
                    return True
            
            # 所有网络连接失败
            self.wifi_last_attempt = now
            return False
                
        except Exception as e:
            self.wifi_last_attempt = time.ticks_ms()
            error("异步WiFi连接异常: {}", e, module="NET")
            return False
            
    async def _async_scan_and_match_networks(self, configured_networks):
        """异步扫描并匹配配置的网络"""
        try:
            # 扫描可用网络 (非阻塞)
            scanned_networks = self.wifi_manager.scan_networks()
            
            if not scanned_networks:
                return []
            
            # 匹配配置的网络
            matched_networks = []
            for config_net in configured_networks:
                config_ssid = config_net.get("ssid")
                if not config_ssid:
                    continue
                    
                # 在扫描结果中查找匹配的SSID
                for scanned_net in scanned_networks:
                    if scanned_net.get("ssid") == config_ssid:
                        matched_networks.append({
                            "ssid": config_ssid,
                            "password": config_net.get("password", ""),
                            "rssi": scanned_net.get("rssi", -100),
                            "bssid": scanned_net.get("bssid", "")
                        })
                        break
            
            # 按RSSI降序排序
            matched_networks.sort(key=lambda x: x["rssi"], reverse=True)
            return matched_networks
            
        except Exception as e:
            error("异步扫描和匹配网络失败: {}", e, module="NET")
            return []
    
    async def _async_attempt_wifi_connection(self, ssid, password):
        """异步尝试连接指定的WiFi网络"""
        try:
            # 调用WiFi管理器连接
            started = self.wifi_manager.connect(ssid, password)
            if not started:
                return False
            
            # 异步等待连接结果
            timeout_ms = int(self.wifi_config.get("connect_timeout_ms", 10000))
            poll_interval = 200
            start_ms = time.ticks_ms()
            
            while not self.wifi_manager.get_is_connected():
                if time.ticks_diff(time.ticks_ms(), start_ms) > timeout_ms:
                    break
                await asyncio.sleep_ms(poll_interval)  # 非阻塞等待
            
            return self.wifi_manager.get_is_connected()
            
        except Exception as e:
            error("异步WiFi连接尝试异常: {}", e, module="NET")
            return False
            
    async def _async_connect_mqtt(self):
        """异步 MQTT 连接方法"""
        try:
            if not self.wifi_connected:
                return False
                
            if self.mqtt_connected and self.mqtt_controller and self.mqtt_controller.is_connected():
                return True

            # 退避重试检查
            now = time.ticks_ms()
            delay = self.mqtt_base_delay
            
            if self.mqtt_last_attempt > 0:
                remaining = delay - time.ticks_diff(now, self.mqtt_last_attempt)
                if remaining > 0:
                    return False

            # 先同步NTP时间
            if not self.ntp_synced:
                await self._async_sync_ntp()

            # 异步连接MQTT
            success = await self.mqtt_controller.connect_async()
            self.mqtt_last_attempt = now
            if success and self.mqtt_controller.is_connected():
                self.mqtt_connected = True
                self.mqtt_last_attempt = 0  # 重置延迟计时
                info("MQTT连接成功", module="NET")
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                return True
            else:
                self.mqtt_last_attempt = now
                return False
        except Exception as e:
            self.mqtt_last_attempt = time.ticks_ms()
            error("异步MQTT连接异常: {}", e, module="NET")
            return False
            
    async def _async_sync_ntp(self):
        """异步 NTP 同步方法"""
        try:
            if self.ntp_synced:
                return True
                
            success = self.ntp_manager.sync_time()
            
            if success:
                self.ntp_synced = True
                info("NTP时间同步成功", module="NET")
                return True
            else:
                warning("NTP时间同步失败（忽略，继续MQTT连接）", module="NET")
                return True  # NTP失败不阻止MQTT连接
                
        except Exception as e:
            error("异步NTP同步异常: {}", e, module="NET")
            return True  # NTP失败不阻止MQTT连接
            
    async def _async_check_status(self):
        """异步状态检查方法"""
        try:
            # 检查WiFi状态
            if self.wifi_manager:
                is_connected = self.wifi_manager.get_is_connected()
                
                if self.wifi_connected and not is_connected:
                    # WiFi连接丢失
                    warning("WiFi连接丢失", module="NET")
                    self.wifi_connected = False
                    self.mqtt_connected = False  # WiFi断开时MQTT也会断开
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
                    
                elif not self.wifi_connected and is_connected:
                    # WiFi重新连接
                    debug("WiFi重新连接", module="NET")
                    self.wifi_connected = True
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="connected")
            
            # 检查MQTT状态
            if self.mqtt_controller:
                is_connected = self.mqtt_controller.is_connected()
                
                if self.mqtt_connected and not is_connected:
                    # MQTT连接丢失
                    warning("MQTT连接丢失", module="NET")
                    self.mqtt_connected = False
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                    
                elif not self.mqtt_connected and is_connected:
                    # MQTT重新连接
                    debug("MQTT重新连接", module="NET")
                    self.mqtt_connected = True
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                    
                # MQTT消息处理（异步）
                if self.mqtt_connected:
                    await self.mqtt_controller.check_msg_async()
                    
        except Exception as e:
            error("异步状态检查异常: {}", e, module="NET")
            
    def connect(self):
        """
        启动网络连接流程 - 异步版本的同步包装
        返回: bool - 是否成功启动连接流程
        """
        try:
            # 注意：这是一个同步包装，实际连接由异步任务处理
            # 这里只是触发连接尝试，不等待结果
            info("触发网络连接流程", module="NET")
            return True
            
        except Exception as e:
            error("网络连接异常: {}", e, module="NET")
            return False
    
    # 旧的同步扫描和匹配方法已删除，使用 _async_scan_and_match_networks 替代
    
    # 旧的同步WiFi连接尝试方法已删除，使用 _async_attempt_wifi_connection 替代
            
    # 旧的同步 WiFi 连接方法已删除，使用 _async_connect_wifi 替代
            
    # 旧的同步 NTP 同步方法已删除，使用 _async_sync_ntp 替代
            
    # 旧的同步 MQTT 连接方法已删除，使用 _async_connect_mqtt 替代
            
    def disconnect(self):
        """断开所有网络连接"""
        debug("断开网络连接", module="NET")
        
        try:
            # 断开MQTT
            if self.mqtt_controller and self.mqtt_connected:
                self.mqtt_controller.disconnect()
                self.mqtt_connected = False
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                
            # 断开WiFi
            if self.wifi_manager and self.wifi_connected:
                self.wifi_manager.disconnect()
                self.wifi_connected = False
                self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
                
            # 重置状态
            self.ntp_synced = False
            
            info("网络连接已断开", module="NET")
            
        except Exception as e:
            error("断开网络连接失败: {}", e, module="NET")
            
    def is_connected(self):
        """检查网络连接状态"""
        return self.wifi_connected and self.mqtt_connected
        
    def get_status(self):
        """获取网络状态"""
        return {
            "wifi": self.wifi_connected,
            "ntp": self.ntp_synced,
            "mqtt": self.mqtt_connected
        }
        
    # 旧的同步 loop 方法已删除，网络管理现在完全由异步任务处理
            
    # 旧的同步状态检查方法已删除，使用 _async_check_status 替代
            
    async def force_reconnect(self):
        """强制重新连接"""
        info("强制重新连接网络", module="NET")
        # 重置重连计时器，允许即时重试
        self.mqtt_last_attempt = 0
        self.wifi_last_attempt = 0
        self.disconnect()
        await asyncio.sleep_ms(1000)  # 异步等待1秒
        return self.connect()


# 兼容性函数
def create_network_manager(config, event_bus):
    """创建网络管理器实例（保持兼容性）"""
    return NetworkManager(config, event_bus)


# 全局实例管理（保持兼容性）
_network_manager_instance = None

def get_network_manager():
    """获取全局网络管理器实例"""
    return _network_manager_instance

def create_global_network_manager(config, event_bus):
    """创建全局网络管理器实例"""
    global _network_manager_instance
    _network_manager_instance = NetworkManager(config, event_bus)
    return _network_manager_instance