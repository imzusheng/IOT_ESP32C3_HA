# app/net/network_manager.py
"""
网络管理器
职责: 
- 顺序编排 WiFi → NTP → MQTT 的连接流程, 替代早期的独立 NET FSM
- 在主循环中持续检查 WiFi/MQTT 状态并触发必要的事件

事件约定: 
- 当 WiFi 状态变化时发布 EVENTS["WIFI_STATE_CHANGE"], state ∈ {"connected","disconnected"}
- 当 MQTT 状态变化时发布 EVENTS["MQTT_STATE_CHANGE"], state ∈ {"connected","disconnected"}

设计边界与约束: 
- 实现指数退避策略(由配置 mqtt.base_delay_ms/max_delay_ms/max_retries 控制)
- NTP 同步失败不会阻塞后续 MQTT 连接
- WifiManager/NtpManager/MqttController 由本模块聚合管理, 配置来自 app/config.py
- 内置"连接中"防重入保护(_mqtt_connecting + MqttController._connecting), 避免重复触发与重复日志

扩展建议: 
- 可在不破坏接口的前提下引入更灵活的退避/重试策略
- 可将连接状态与统计指标上报到事件总线或系统状态接口
"""

import utime as time
import uasyncio as asyncio
from lib.logger import info, warning, error, debug
from lib.event_bus_lock import EVENTS
from lib.async_runtime import get_async_runtime
from utils import json_dumps, get_epoch_unix_s as util_get_epoch_unix_s

class NetworkManager:
    """
    网络管理器
    直接管理WiFi→NTP→MQTT连接流程, 无需独立的NET FSM
    """
    
    def __init__(self, config, event_bus):
        """初始化网络管理器"""
        self.config = config or {}
        self.event_bus = event_bus
        
        # 子配置缓存, 避免硬编码与重复取值
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

        # 连接中状态控制, 避免重复触发连接请求
        self._mqtt_connecting = False

        # 无限退避重试策略
        self.mqtt_base_delay = int(self.mqtt_config.get("base_delay_ms", 2000))  # 基础延迟 2秒
        self.mqtt_last_attempt = 0
        # 新增: MQTT 指数退避控制参数
        self.mqtt_max_delay = int(self.mqtt_config.get("max_delay_ms", 180000))  # 最大延迟 3分钟
        self.mqtt_max_retries = int(self.mqtt_config.get("max_retries", -1))    # -1 表示无限重试
        self.mqtt_retry_attempts = 0  # 当前连续失败次数, 用于指数退避
        
        # WiFi 无限退避重试策略
        self.wifi_base_delay = int(self.wifi_config.get("base_delay_ms", 2000))  # 基础延迟 2秒
        self.wifi_max_delay = int(self.wifi_config.get("max_delay_ms", 180000))  # 最大延迟 3分钟
        self.wifi_last_attempt = 0
        # 新增: WiFi 指数退避控制参数(与 MQTT 对齐, 支持可选 max_retries, 默认无限)
        self.wifi_max_retries = int(self.wifi_config.get("max_retries", -1))
        self.wifi_retry_attempts = 0  # 当前 WiFi 重试次数
        
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
            runtime = get_async_runtime()
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
            # 使用包内相对导入, 保持与现有文件结构一致
            from .wifi import WifiManager
            from .ntp import NtpManager
            from .mqtt import MqttController

            # 按子配置实例化
            self.wifi_manager = WifiManager(self.wifi_config)
            self.ntp_manager = NtpManager(self.ntp_config)
            self.mqtt_controller = MqttController(self.mqtt_config)
            
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
        """尝试连接 WiFi, 采用指数退避 + 抖动策略, 统一由 NetworkManager 管理重试节奏"""
        # 已连接则直接返回, 避免重复触发
        try:
            if self.wifi_connected and self.wifi_manager and self.wifi_manager.get_is_connected():
                return True
        except Exception:
            pass
        
        now = time.ticks_ms()
        
        # 退避重试检查: 首次尝试立即执行, 随后指数退避并封顶到 max_delay, 加入±20%抖动
        if self.wifi_retry_attempts > 0:
            calc_delay = self.wifi_base_delay << (self.wifi_retry_attempts - 1)
            delay = calc_delay if calc_delay < self.wifi_max_delay else self.wifi_max_delay
        else:
            delay = self.wifi_base_delay
        # 抖动: 0.8x ~ 1.2x, urandom 优先, 退化到时间基准
        try:
            import urandom
            rnd = urandom.getrandbits(16) / 65535.0
        except Exception:
            rnd = (time.ticks_ms() & 0xFFFF) / 65535.0
        jitter_factor = 0.8 + 0.4 * rnd
        delay = int(delay * jitter_factor)
        
        if self.wifi_last_attempt > 0:
            elapsed = time.ticks_diff(now, self.wifi_last_attempt)
            remaining = delay - elapsed
            if remaining > 0:
                return False
        
        try:
            # 获取网络配置列表
            networks = self.wifi_config.get("networks", [])
            if not networks:
                # 兼容旧配置格式
                ssid = self.wifi_config.get("ssid")
                password = self.wifi_config.get("password")
                if ssid:
                    networks = [{"ssid": ssid, "password": password}]
                else:
                    # 无配置可用, 记一次失败并退出
                    self.wifi_last_attempt = time.ticks_ms()
                    if self.wifi_max_retries >= 0:
                        if self.wifi_retry_attempts < self.wifi_max_retries:
                            self.wifi_retry_attempts += 1
                    else:
                        self.wifi_retry_attempts += 1
                    return False
            
            # 扫描并匹配可用网络(按RSSI降序)
            available_networks = await self._async_scan_and_match_networks(networks)
            if not available_networks:
                self.wifi_last_attempt = time.ticks_ms()
                if self.wifi_max_retries >= 0:
                    if self.wifi_retry_attempts < self.wifi_max_retries:
                        self.wifi_retry_attempts += 1
                else:
                    self.wifi_retry_attempts += 1
                return False
            
            # 逐个尝试连接(按信号强度从高到低)
            for network in available_networks:
                ssid = network.get("ssid")
                password = network.get("password", "")
                if await self._async_attempt_wifi_connection(ssid, password):
                    self.wifi_connected = True
                    # 连接成功: 重置退避计数; last_attempt清零, 允许后续流程立即推进
                    self.wifi_last_attempt = 0
                    self.wifi_retry_attempts = 0
                    info("WiFi连接成功: {}", ssid, module="NET")
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="connected")
                    return True
            
            # 所有候选网络均未连接成功: 记录一次失败并递增退避计数
            self.wifi_last_attempt = time.ticks_ms()
            if self.wifi_max_retries >= 0:
                if self.wifi_retry_attempts < self.wifi_max_retries:
                    self.wifi_retry_attempts += 1
            else:
                self.wifi_retry_attempts += 1
            return False
        except Exception as e:
            # 异常视为一次失败尝试
            self.wifi_last_attempt = time.ticks_ms()
            if self.wifi_max_retries >= 0:
                if self.wifi_retry_attempts < self.wifi_max_retries:
                    self.wifi_retry_attempts += 1
            else:
                self.wifi_retry_attempts += 1
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
            
            # 已连接则直接返回, 避免重复触发
            if self.mqtt_connected and self.mqtt_controller and self.mqtt_controller.is_connected():
                return True

            # 如果当前已有连接尝试在进行, 避免重复触发
            if self._mqtt_connecting:
                return False

            # 退避重试检查
            now = time.ticks_ms()
            # 指数退避: delay = base * 2^(attempts-1), 首次失败后开始指数增长, 限制到 max_delay
            if self.mqtt_retry_attempts > 0:
                calc_delay = self.mqtt_base_delay << (self.mqtt_retry_attempts - 1)
                delay = calc_delay if calc_delay < self.mqtt_max_delay else self.mqtt_max_delay
            else:
                delay = self.mqtt_base_delay
            
            if self.mqtt_last_attempt > 0:
                elapsed = time.ticks_diff(now, self.mqtt_last_attempt)
                remaining = delay - elapsed
                if remaining > 0:
                    return False

            # 先同步NTP时间
            if not self.ntp_synced:
                await self._async_sync_ntp()

            # 异步连接MQTT
            self._mqtt_connecting = True
            try:
                success = await self.mqtt_controller.connect_async()
                # 结束时刻用于下一次退避基准
                self.mqtt_last_attempt = time.ticks_ms()
                if success and self.mqtt_controller.is_connected():
                    self.mqtt_connected = True
                    # 连接成功重置退避计数
                    self.mqtt_retry_attempts = 0
                    info("MQTT连接成功", module="NET")
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                    
                      
                    # 上线提示: 连接成功后发送一次 retained 的 online 消息
                    try:
                        online_payload = {
                            "status": "online",
                            "uptime_ms": time.ticks_ms(),
                            # 若已完成NTP同步, 附加当前 1970-based UNIX 秒
                            "unix_s": self.get_epoch_unix_s(),
                        }
                        # retained 以便后续订阅均可立即获知设备当前在线状态
                        self.mqtt_publish(self.get_device_topic("online"), online_payload, retain=True, qos=0)
                    except Exception:
                        pass
                    return True
                else:
                    # 连接失败, 递增退避计数(-1 表示无限制)
                    if self.mqtt_max_retries >= 0:
                        if self.mqtt_retry_attempts < self.mqtt_max_retries:
                            self.mqtt_retry_attempts += 1
                    else:
                        self.mqtt_retry_attempts += 1
                    return False
            finally:
                # 标记连接尝试结束, 允许后续重试
                self._mqtt_connecting = False
        except Exception as e:
            # 异常也视为一次失败尝试
            self.mqtt_last_attempt = time.ticks_ms()
            if self.mqtt_max_retries >= 0:
                if self.mqtt_retry_attempts < self.mqtt_max_retries:
                    self.mqtt_retry_attempts += 1
            else:
                self.mqtt_retry_attempts += 1
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
                warning("NTP时间同步失败(忽略, 继续MQTT连接)", module="NET")
                return True  # NTP失败不阻止MQTT连接
                
        except Exception as e:
            error("异步NTP同步异常: {}", e, module="NET")
            return True  # NTP失败不阻止MQTT连接

    async def _async_check_status(self):
        """异步状态检查方法"""
        try:
            # 检查WiFi状态
            if self.wifi_manager:
                wifi_is_connected = self.wifi_manager.get_is_connected()
                
                # 仅在断开时发布事件(连接成功事件由连接流程负责)
                if self.wifi_connected and not wifi_is_connected:
                    warning("WiFi连接丢失", module="NET")
                    self.wifi_connected = False
                    self.mqtt_connected = False  # WiFi断开时MQTT也会断开
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
                    info("WiFi状态变化: {}", self.wifi_connected, module="NET")
            
            # 检查MQTT状态
            if self.mqtt_controller:
                mqtt_is_connected = self.mqtt_controller.is_connected()
                
                # 仅在断开时发布事件(连接成功事件由连接流程负责)
                if self.mqtt_connected and not mqtt_is_connected:
                    warning("MQTT连接丢失", module="NET")
                    self.mqtt_connected = False
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                elif not self.mqtt_connected and mqtt_is_connected:
                    # 仅同步内部标志, 事件由连接流程负责
                    self.mqtt_connected = True
                
                # MQTT消息处理(异步), 避免异常中断状态检查
                if self.mqtt_connected:
                    try:
                        await self.mqtt_controller.process_once()
                    except Exception as _e:
                        # 由 MqttController 内部负责标记连接状态与日志, 这里避免重复日志
                        pass
            
        except Exception as e:
            error("异步状态检查异常: {}", e, module="NET")

    """
    ================================
    外部调用接口
    ================================
    """

    def connect(self):
        """
        启动网络连接流程(触发异步连接任务)
        返回: bool - 是否成功启动连接流程
        """
        try:
            info("触发网络连接流程", module="NET")
            return True
            
        except Exception as e:
            error("网络连接异常: {}", e, module="NET")
            return False
            
    def disconnect(self):
        """断开所有网络连接"""
        debug("断开网络连接", module="NET")
        
        try:
            # 断开MQTT
            if self.mqtt_controller and self.mqtt_connected:
                # 下线提示: 主动断开前发送一次 retained 的 offline 消息
                try:
                    offline_payload = {
                        "status": "offline",
                        "uptime_ms": time.ticks_ms(),
                        # 若已完成NTP同步, 附加当前 1970-based UNIX 秒
                        "unix_s": self.get_epoch_unix_s(),
                    }
                    self.mqtt_publish(self.get_device_topic("online"), offline_payload, retain=True, qos=0)
                except Exception:
                    pass
            
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

    # ================================
    # MQTT 对外发布接口
    # ================================
    def mqtt_publish(self, topic, data, retain=False, qos=0):
        """MQTT 发布统一入口(默认JSON)
        - 默认将对象序列化为 JSON 字符串; 若 data 为 str/bytes 则原样发送
        返回: bool, 未连接时返回 False
        """
        try:
            # 连接状态检查: 确保控制器存在且处于已连接
            if (not self.mqtt_controller) or (not self.mqtt_connected):
                return False
            if hasattr(self.mqtt_controller, "is_connected") and (not self.mqtt_controller.is_connected()):
                return False

            payload = data if isinstance(data, (bytes, bytearray, str)) else json_dumps(data)
            if self.mqtt_controller:
                return self.mqtt_controller.publish(topic, payload, retain, qos)
            return False
        except Exception as e:
            error("MQTT发布异常: {}", e, module="NET")
            return False

    # ================================
    # 设备ID与主题工具
    # ================================
    def get_device_id(self):
        """获取当前设备的 MQTT client_id(字符串, ASCII)
        若不可用则返回 "unknown"
        """
        try:
            if self.mqtt_controller and hasattr(self.mqtt_controller, "get_client_id"):
                cid = self.mqtt_controller.get_client_id()
                if cid:
                    return str(cid)
        except Exception:
            pass
        return "unknown"

    def get_device_topic(self, suffix):
        """根据后缀构造标准设备主题: device/{client_id}/{suffix}
        例: get_device_topic("online") -> device/<id>/online
        """
        try:
            tail = str(suffix).strip("/")
            return "device/{}/{}".format(self.get_device_id(), tail)
        except Exception:
            return "device/{}/{}".format(self.get_device_id(), "unknown")

    def get_epoch_unix_s(self):
        """返回 1970-based UNIX 时间戳(秒)
        - 若未完成 NTP 同步则返回 None
        - MicroPython 大多数端口 time.time() 基于 2000-01-01, 需要加上 946684800 偏移
        - 若底层已为 1970-based(> 946684800), 则直接返回
        - 统一复用 utils.get_epoch_unix_s 转换逻辑
        """
        try:
            if not self.ntp_synced:
                return None
            return util_get_epoch_unix_s()
        except Exception:
            return None