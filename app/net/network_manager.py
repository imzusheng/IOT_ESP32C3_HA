# app/net/network_manager.py
"""
网络管理器
职责:
- 顺序编排 WiFi -> NTP -> MQTT 的连接流程
- 在主循环中检查 WiFi/MQTT 状态并触发必要事件

事件:
- WIFI_STATE_CHANGE: {"connected" | "disconnected"}
- MQTT_STATE_CHANGE: {"connected" | "disconnected"}

约束:
- 支持指数退避(由 mqtt.base_delay_ms/max_delay_ms/max_retries 控制)
- NTP 同步失败不阻塞后续 MQTT 连接
- WifiManager/NtpManager/MqttController 由本模块聚合管理
- 通过 _mqtt_connecting 与控制器内部标志避免重复连接
"""

import utime as time
import uasyncio as asyncio
from lib.logger import info, warning, error, debug
from lib.event_bus_lock import EVENTS
from lib.async_runtime import get_async_runtime
from utils import json_dumps, get_epoch_unix_s as util_get_epoch_unix_s
from ha import HomeAssistantHelper
from config import apply_overlay, save_overlay

class NetworkManager:
    """网络管理器: 负责 WiFi -> NTP -> MQTT 连接流程与状态维护"""
    
    def __init__(self, config, event_bus):
        """初始化"""
        self.config = config or {}
        self.event_bus = event_bus
        
        # 子配置
        self.wifi_config = (self.config or {}).get("wifi", {})
        self.ntp_config = (self.config or {}).get("ntp", {})
        self.mqtt_config = (self.config or {}).get("mqtt", {})
        
        # 组件
        self.wifi_manager = None
        self.ntp_manager = None
        self.mqtt_controller = None
        
        # 状态
        self.wifi_connected = False
        self.ntp_synced = False
        self.mqtt_connected = False

        # 防重入
        self._mqtt_connecting = False

        # MQTT 退避
        self.mqtt_base_delay = int(self.mqtt_config.get("base_delay_ms", 2000))
        self.mqtt_last_attempt = 0
        self.mqtt_max_delay = int(self.mqtt_config.get("max_delay_ms", 180000))
        self.mqtt_max_retries = int(self.mqtt_config.get("max_retries", -1))
        self.mqtt_retry_attempts = 0
        
        # WiFi 退避
        self.wifi_base_delay = int(self.wifi_config.get("base_delay_ms", 2000))
        self.wifi_max_delay = int(self.wifi_config.get("max_delay_ms", 180000))
        self.wifi_last_attempt = 0
        self.wifi_max_retries = int(self.wifi_config.get("max_retries", -1))
        self.wifi_retry_attempts = 0
        
        # 任务
        self._wifi_task = None
        self._mqtt_task = None
        self._status_check_task = None

        # LWT 设置标记(避免重复设置)
        self._lwt_configured = False
        
        self._init_components()
        # 初始化 HA 助手
        self.ha = HomeAssistantHelper(self.config, self.get_device_id, self.mqtt_publish)
        self._register_async_tasks()

    def _register_async_tasks(self):
        """注册异步任务"""
        try:
            runtime = get_async_runtime()
            self._wifi_task = runtime.create_task(self._wifi_connection_loop(), "wifi_connection")
            self._mqtt_task = runtime.create_task(self._mqtt_connection_loop(), "mqtt_connection")
            self._status_check_task = runtime.create_task(self._status_check_loop(), "status_check")
            debug("网络管理器异步任务注册完成", module="NET")
        except Exception as e:
            error("注册异步任务失败: {}", e, module="NET")

    def _init_components(self):
        """初始化组件"""
        try:
            from .wifi import WifiManager
            from .ntp import NtpManager
            from .mqtt import MqttController

            self.wifi_manager = WifiManager(self.wifi_config)
            self.ntp_manager = NtpManager(self.ntp_config)
            self.mqtt_controller = MqttController(self.mqtt_config)
            
            debug("网络组件初始化完成", module="NET")
        except Exception as e:
            error("网络组件初始化失败: {}", e, module="NET")
            raise

    # 工具: 重试与失败标记
    def _inc_attempts(self, attempts, max_retries):
        """attempts 自增, 支持 max_retries 限制, -1 表示无限"""
        try:
            if max_retries >= 0:
                return attempts + 1 if attempts < max_retries else attempts
            return attempts + 1
        except Exception:
            return attempts + 1

    def _wifi_mark_failure(self):
        """WiFi 失败标记: 更新时间戳并 attempts++"""
        self.wifi_last_attempt = time.ticks_ms()
        self.wifi_retry_attempts = self._inc_attempts(self.wifi_retry_attempts, self.wifi_max_retries)

    def _mqtt_mark_failure(self):
        """MQTT 失败标记: 更新时间戳并 attempts++"""
        self.mqtt_last_attempt = time.ticks_ms()
        self.mqtt_retry_attempts = self._inc_attempts(self.mqtt_retry_attempts, self.mqtt_max_retries)

    # 新增: 退避与抖动工具方法
    def _get_jitter_factor(self):
        """生成抖动因子 0.8~1.2"""
        try:
            import urandom
            rnd = urandom.getrandbits(16) / 65535.0
        except Exception:
            rnd = (time.ticks_ms() & 0xFFFF) / 65535.0
        return 0.8 + 0.4 * rnd

    def _calc_backoff_delay(self, base_delay, attempts, max_delay):
        """计算指数退避延迟并叠加抖动"""
        try:
            if attempts > 0:
                calc_delay = base_delay << (attempts - 1)
                delay = calc_delay if calc_delay < max_delay else max_delay
            else:
                delay = base_delay
            jitter_factor = self._get_jitter_factor()
            return int(delay * jitter_factor)
        except Exception:
            # 异常降级: 返回基础延迟
            return int(base_delay)

    async def _wifi_connection_loop(self):
        """WiFi 连接循环"""
        while True:
            try:
                await self._async_connect_wifi()
                await asyncio.sleep_ms(2000)
            except asyncio.CancelledError:
                debug("WiFi连接任务取消", module="NET")
                break
            except Exception as e:
                error("WiFi连接循环异常: {}", e, module="NET")
                await asyncio.sleep_ms(5000)
                
    async def _mqtt_connection_loop(self):
        """MQTT 连接循环"""
        while True:
            try:
                await self._async_connect_mqtt()
                await asyncio.sleep_ms(2000)
            except asyncio.CancelledError:
                debug("MQTT连接任务取消", module="NET")
                break
            except Exception as e:
                error("MQTT连接循环异常: {}", e, module="NET")
                await asyncio.sleep_ms(5000)
                
    async def _status_check_loop(self):
        """状态检查循环"""
        while True:
            try:
                await self._async_check_status()
                await asyncio.sleep_ms(500)
            except asyncio.CancelledError:
                debug("状态检查任务取消", module="NET")
                break
            except Exception as e:
                error("状态检查循环异常: {}", e, module="NET")
                await asyncio.sleep_ms(1000)
             
    async def _async_connect_wifi(self):
        """连接 WiFi: 指数退避 + 抖动"""
        try:
            if self.wifi_connected and self.wifi_manager and self.wifi_manager.get_is_connected():
                return True
        except Exception:
            pass
        
        now = time.ticks_ms()
        
        # 退避 + 抖动
        delay = self._calc_backoff_delay(self.wifi_base_delay, self.wifi_retry_attempts, self.wifi_max_delay)
        
        if self.wifi_last_attempt > 0:
            elapsed = time.ticks_diff(now, self.wifi_last_attempt)
            if delay - elapsed > 0:
                return False
        
        try:
            networks = self.wifi_config.get("networks", [])
            if not networks:
                ssid = self.wifi_config.get("ssid")
                password = self.wifi_config.get("password")
                if ssid:
                    networks = [{"ssid": ssid, "password": password}]
                else:
                    self._wifi_mark_failure()
                    return False
            
            available_networks = await self._async_scan_and_match_networks(networks)
            if not available_networks:
                self._wifi_mark_failure()
                return False
            
            for network in available_networks:
                ssid = network.get("ssid")
                password = network.get("password", "")
                if await self._async_attempt_wifi_connection(ssid, password):
                    self.wifi_connected = True
                    self.wifi_last_attempt = 0
                    self.wifi_retry_attempts = 0
                    info("WiFi连接成功: {}", ssid, module="NET")
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="connected")
                    return True
            
            self._wifi_mark_failure()
            return False
        except Exception as e:
            self._wifi_mark_failure()
            error("异步WiFi连接异常: {}", e, module="NET")
            return False
            
    async def _async_scan_and_match_networks(self, configured_networks):
        """扫描并匹配配置的网络"""
        try:
            scanned_networks = self.wifi_manager.scan_networks()
            if not scanned_networks:
                return []
            
            matched_networks = []
            for config_net in configured_networks:
                config_ssid = config_net.get("ssid")
                if not config_ssid:
                    continue
                for scanned_net in scanned_networks:
                    if scanned_net.get("ssid") == config_ssid:
                        matched_networks.append({
                            "ssid": config_ssid,
                            "password": config_net.get("password", ""),
                            "rssi": scanned_net.get("rssi", -100),
                            "bssid": scanned_net.get("bssid", "")
                        })
                        break
            matched_networks.sort(key=lambda x: x["rssi"], reverse=True)
            return matched_networks
        except Exception as e:
            error("异步扫描和匹配网络失败: {}", e, module="NET")
            return []
    
    async def _async_attempt_wifi_connection(self, ssid, password):
        """尝试连接单个 WiFi"""
        try:
            started = self.wifi_manager.connect(ssid, password)
            if not started:
                return False
            timeout_ms = int(self.wifi_config.get("connect_timeout_ms", 10000))
            poll_interval = 200
            start_ms = time.ticks_ms()
            while not self.wifi_manager.get_is_connected():
                if time.ticks_diff(time.ticks_ms(), start_ms) > timeout_ms:
                    break
                await asyncio.sleep_ms(poll_interval)
            return self.wifi_manager.get_is_connected()
        except Exception as e:
            error("异步WiFi连接尝试异常: {}", e, module="NET")
            return False
            
    async def _async_connect_mqtt(self):
        """连接 MQTT"""
        try:
            if not self.wifi_connected:
                return False
            if self.mqtt_connected and self.mqtt_controller and self.mqtt_controller.is_connected():
                return True
            if self._mqtt_connecting:
                return False

            now = time.ticks_ms()
            # 退避 + 抖动
            delay = self._calc_backoff_delay(self.mqtt_base_delay, self.mqtt_retry_attempts, self.mqtt_max_delay)
            if self.mqtt_last_attempt > 0:
                elapsed = time.ticks_diff(now, self.mqtt_last_attempt)
                if delay - elapsed > 0:
                    return False

            if not self.ntp_synced:
                await self._async_sync_ntp()

            # 在首次连接前配置 LWT(若支持), 使用 availability 主题
            try:
                if (not self._lwt_configured) and self.mqtt_controller and hasattr(self.mqtt_controller, "set_last_will"):
                    avail_topic = self.ha.availability_topic()
                    self.mqtt_controller.set_last_will(avail_topic, "offline", qos=0, retain=True)
                    self._lwt_configured = True
                    debug("已设置MQTT LWT: {} -> offline", avail_topic, module="NET")
            except Exception as _e:
                warning("设置MQTT LWT失败(降级为显式offline): {}", _e, module="NET")
                # 继续连接流程

            self._mqtt_connecting = True
            try:
                success = await self.mqtt_controller.connect_async()
                self.mqtt_last_attempt = time.ticks_ms()
                if success and self.mqtt_controller.is_connected():
                    self.mqtt_connected = True
                    self.mqtt_retry_attempts = 0
                    info("MQTT连接成功", module="NET")
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                    try:
                        # HA 可用性: 连接成功后发布 retained 可用性为 online
                        self.ha.publish_availability(True)
                        # 发布 Home Assistant Discovery 配置
                        self.ha.publish_discovery()
                        # 可选: 设备 announce
                        self.publish_announce()
                        # 新增: 配置通道订阅与回调
                        self._setup_mqtt_config_channel()
                        # 发布当前LED模式状态
                        try:
                            current_led_mode = self.config.get_nested("led_mode", "cruise")
                            self.mqtt_publish(f"device/{self.get_device_id()}/state/select/led_mode", current_led_mode, retain=True, qos=0)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    return True
                else:
                    self.mqtt_retry_attempts = self._inc_attempts(self.mqtt_retry_attempts, self.mqtt_max_retries)
                    return False
            finally:
                self._mqtt_connecting = False
        except Exception as e:
            self._mqtt_mark_failure()
            error("异步MQTT连接异常: {}", e, module="NET")
            return False

    async def _async_sync_ntp(self):
        """NTP 同步"""
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
                return True
        except Exception as e:
            error("异步NTP同步异常: {}", e, module="NET")
            return True

    async def _async_check_status(self):
        """状态检查"""
        try:
            if self.wifi_manager:
                wifi_is_connected = self.wifi_manager.get_is_connected()
                if self.wifi_connected and not wifi_is_connected:
                    warning("WiFi连接丢失", module="NET")
                    self.wifi_connected = False
                    # WiFi 掉线时显式断开 MQTT 并发布事件
                    if self.mqtt_connected:
                        try:
                            # 尝试在断开前发布 offline
                            if self.mqtt_controller and hasattr(self.mqtt_controller, "is_connected") and self.mqtt_controller.is_connected():
                                self.ha.publish_availability(False)
                        except Exception:
                            pass
                        try:
                            if self.mqtt_controller:
                                self.mqtt_controller.disconnect()
                        except Exception:
                            pass
                        self.mqtt_connected = False
                        self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                    self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
            if self.mqtt_controller:
                mqtt_is_connected = self.mqtt_controller.is_connected()
                if self.mqtt_connected and not mqtt_is_connected:
                    warning("MQTT连接丢失", module="NET")
                    self.mqtt_connected = False
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
                elif not self.mqtt_connected and mqtt_is_connected:
                    # 处理控制器已连接但本地标志为 False 的情况: 发布事件并发送 online
                    self.mqtt_connected = True
                    self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="connected")
                    try:
                        # HA 可用性: 连接成功后发布 retained 可用性为 online
                        self.ha.publish_availability(True)
                        # 发布 Home Assistant Discovery 配置
                        self.ha.publish_discovery()
                        # 新增: 配置通道订阅与回调
                        self._setup_mqtt_config_channel()
                        # 发布当前LED模式状态
                        try:
                            current_led_mode = self.config.get_nested("led_mode", "cruise")
                            self.mqtt_publish(f"device/{self.get_device_id()}/state/select/led_mode", current_led_mode, retain=True, qos=0)
                        except Exception:
                            pass
                    except Exception:
                        pass
                if self.mqtt_connected:
                    try:
                        await self.mqtt_controller.process_once()
                    except Exception:
                        pass
        except Exception as e:
            error("异步状态检查异常: {}", e, module="NET")

    def connect(self):
        """触发网络连接流程"""
        try:
            info("触发网络连接流程", module="NET")
            return True
        except Exception as e:
            error("网络连接异常: {}", e, module="NET")
            return False
            
    def disconnect(self):
        """断开网络连接"""
        debug("断开网络连接", module="NET")
        try:
            if self.mqtt_controller and self.mqtt_connected:
                try:
                    # 发布可用性为 offline (retained)
                    self.ha.publish_availability(False)
                except Exception:
                    pass
                self.mqtt_controller.disconnect()
                self.mqtt_connected = False
                self.event_bus.publish(EVENTS["MQTT_STATE_CHANGE"], state="disconnected")
            if self.wifi_manager and self.wifi_connected:
                self.wifi_manager.disconnect()
                self.wifi_connected = False
                self.event_bus.publish(EVENTS["WIFI_STATE_CHANGE"], state="disconnected")
            self.ntp_synced = False
            info("网络连接已断开", module="NET")
        except Exception as e:
            error("断开网络连接失败: {}", e, module="NET")
            
    def is_connected(self):
        """整体连通状态"""
        return self.wifi_connected and self.mqtt_connected
        
    def get_status(self):
        """获取状态"""
        return {"wifi": self.wifi_connected, "ntp": self.ntp_synced, "mqtt": self.mqtt_connected}

    def mqtt_publish(self, topic, data, retain=False, qos=0):
        """MQTT 发布(默认 JSON)"""
        try:
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

    def get_device_id(self):
        """获取设备ID(不可用返回 "unknown")"""
        try:
            if self.mqtt_controller and hasattr(self.mqtt_controller, "get_client_id"):
                cid = self.mqtt_controller.get_client_id()
                if cid:
                    return str(cid)
        except Exception:
            pass
        return "unknown"

    def get_device_topic(self, suffix):
        """拼接设备主题 device/{client_id}/{suffix}"""
        try:
            tail = str(suffix).strip("/")
            return "device/{}/{}".format(self.get_device_id(), tail)
        except Exception:
            return "device/{}/{}".format(self.get_device_id(), "unknown")



    def publish_announce(self):
        """发布设备 announce 信息, 供服务器侧自动注册"""
        try:
            info_payload = {
                "id": self.get_device_id(),
                "unix_s": self.get_epoch_unix_s(),
                "ip": self.wifi_manager.get_ip() if self.wifi_manager else None,
                "features": ["sht40", "ha_discovery"],
            }
            self.mqtt_publish(self.get_device_topic("announce"), info_payload, retain=False, qos=0)
        except Exception:
            pass

    def get_epoch_unix_s(self):
        """获取当前 Unix 时间戳(秒), 异常或不可用时返回 "N/A"""
        try:
            val = util_get_epoch_unix_s()
            return val if val is not None else "N/A"
        except Exception:
            return "N/A"

    def state_topic(self, sub: str) -> str:
        """统一的状态主题, 仅使用 HA 助手"""
        return self.ha.state_topic(sub)

    def availability_topic(self) -> str:
        """统一的可用性主题, 仅使用 HA 助手"""
        return self.ha.availability_topic()



    # 新增: MQTT 配置通道与回调处理
    def _config_stat_topic(self):
        try:
            return "stat/{}/config".format(self.get_device_id())
        except Exception:
            return "stat/{}/config".format("unknown")

    def _setup_mqtt_config_channel(self):
        """设置配置通道的回调与订阅
        订阅主题:
        - cmnd/<device_id>/config/set
        - cmnd/<device_id>/config/save
        - cmnd/<device_id>/config/reboot
        - cmnd/<device_id>/reboot (兼容)
        """
        try:
            if (not self.mqtt_controller) or (not self.mqtt_controller.is_connected()):
                return False
            # 设置回调(幂等)
            self.mqtt_controller.set_callback(self._on_mqtt_message)
            base = "cmnd/{}".format(self.get_device_id())
            topics = [
                base + "/config/set",
                base + "/config/save",
                base + "/config/reboot",
                base + "/reboot",
                base + "/config/button/reboot",
                base + "/config/select/led_mode",
            ]
            for tp in topics:
                try:
                    self.mqtt_controller.subscribe(tp, qos=0)
                except Exception:
                    pass
            debug("MQTT配置通道订阅完成", module="NET")
            return True
        except Exception as e:
            warning("配置通道订阅失败: {}", e, module="NET")
            return False

    def _json_loads(self, payload):
        """安全解析 JSON, 失败返回 None"""
        try:
            if isinstance(payload, (bytes, bytearray)):
                try:
                    payload = payload.decode("utf-8")
                except Exception:
                    payload = str(payload)
            try:
                import ujson as _j
            except Exception:
                import json as _j
            return _j.loads(payload)
        except Exception:
            return None

    # 安全与权限相关的辅助方法
    def _get_security_config(self):
        """读取 ble.security 配置, 返回 dict(auth, token)"""
        try:
            ble_cfg = (self.config or {}).get("ble", {}) or {}
            sec = ble_cfg.get("security", {}) or {}
            auth = sec.get("auth", "none") or "none"
            return {"auth": auth, "token": sec.get("token")}
        except Exception:
            return {"auth": "none", "token": None}

    def _is_authorized_for_config(self, data):
        """基于 ble.security 鉴权, 当前实现支持 auth==token 验证 payload.token"""
        try:
            sec = self._get_security_config()
            auth = (sec.get("auth") or "none").lower()
            if auth == "none":
                return True, None
            if auth == "token":
                token_cfg = sec.get("token")
                token_req = data.get("token") if isinstance(data, dict) else None
                if token_req is not None and str(token_req) == str(token_cfg):
                    return True, None
                return False, "unauthorized"
            return False, "unauthorized"
        except Exception:
            return False, "unauthorized"

    def _is_reboot_allowed(self):
        """根据 ble.config_service.allow_reboot 判断是否允许重启"""
        try:
            ble_cfg = (self.config or {}).get("ble", {}) or {}
            cs = ble_cfg.get("config_service", {}) or {}
            return bool(cs.get("allow_reboot", True))
        except Exception:
            return True

    def _publish_config_stat(self, obj):
        try:
            self.mqtt_publish(self._config_stat_topic(), obj, retain=False, qos=0)
        except Exception:
            pass

    def _schedule_reboot(self, delay_ms):
        try:
            runtime = get_async_runtime()
            async def _do_reboot(ms):
                try:
                    await asyncio.sleep_ms(int(ms) if ms and int(ms) > 0 else 0)
                except Exception:
                    pass
                try:
                    import machine
                    machine.reset()
                except Exception:
                    pass
            runtime.create_task(_do_reboot(delay_ms or 0), "delayed_reboot")
        except Exception as e:
            warning("调度重启失败: {}", e, module="NET")

    def _on_mqtt_message(self, topic, msg):
        """MQTT 消息回调: 处理配置通道命令"""
        try:
            t = topic.decode("utf-8") if isinstance(topic, (bytes, bytearray)) else str(topic)
        except Exception:
            t = str(topic)
        base = "cmnd/{}/".format(self.get_device_id())
        try:
            if not t.startswith(base):
                return
            # 解析 JSON 负载
            data = self._json_loads(msg) or {}
            # 指令分发
            if t == base + "config/set":
                # 权限校验
                ok_auth, err = self._is_authorized_for_config(data)
                if not ok_auth:
                    self._publish_config_stat({"ok": False, "msg": err or "unauthorized"})
                    return
                path = data.get("path")
                update = data.get("update")
                ok = False
                if isinstance(update, dict):
                    ok = apply_overlay(update_dict=update)
                elif isinstance(path, str) and ("value" in data):
                    ok = apply_overlay(path=path, value=data.get("value"))
                else:
                    self._publish_config_stat({"ok": False, "msg": "invalid payload for set"})
                    return
                self._publish_config_stat({"ok": bool(ok), "msg": "applied" if ok else "apply failed", "applied": data})
            elif t == base + "config/select/led_power":
                # LED开关控制
                try:
                    value = data if isinstance(data, bool) else str(data).lower() == "true"
                    ok = apply_overlay(path="led_enabled", value=value)
                    self._publish_config_stat({"ok": bool(ok), "msg": "applied" if ok else "apply failed", "applied": {"led_enabled": value}})
                    
                    # 立即应用LED状态
                    if ok:
                        from hw.led import play
                        if value:
                            current_mode = self.config.get_nested("led_mode", "cruise")
                            play(current_mode)
                        else:
                            play("off")
                except Exception as e:
                    self._publish_config_stat({"ok": False, "msg": str(e)})
            elif t == base + "config/select/led_mode":
                # LED模式选择
                try:
                    valid_modes = ["off", "blink", "pulse", "cruise", "sos"]
                    mode = str(data) if str(data) in valid_modes else "cruise"
                    ok = apply_overlay(path="led_mode", value=mode)
                    self._publish_config_stat({"ok": bool(ok), "msg": "applied" if ok else "apply failed", "applied": {"led_mode": mode}})
                    
                    # 立即应用LED模式
                    if ok:
                        from hw.led import play
                        led_enabled = self.config.get_nested("led_enabled", True)
                        if led_enabled:
                            play(mode)
                        
                        # 发布LED模式状态到Home Assistant
                        try:
                            self.mqtt_publish(f"device/{self.get_device_id()}/state/select/led_mode", mode, retain=True, qos=0)
                        except Exception:
                            pass
                except Exception as e:
                    self._publish_config_stat({"ok": False, "msg": str(e)})
            elif t == base + "config/save":
                # 权限校验
                ok_auth, err = self._is_authorized_for_config(data)
                if not ok_auth:
                    self._publish_config_stat({"ok": False, "msg": err or "unauthorized"})
                    return
                paths = data.get("paths")
                if paths is not None and not isinstance(paths, (list, tuple)):
                    self._publish_config_stat({"ok": False, "msg": "paths must be list"})
                    return
                ok = save_overlay(paths=paths)
                self._publish_config_stat({"ok": bool(ok), "msg": "saved" if ok else "save failed", "paths": paths or "all"})
            elif t == base + "config/button/reboot":
                # 按钮重启功能
                ok_auth, err = self._is_authorized_for_config(data)
                if not ok_auth:
                    self._publish_config_stat({"ok": False, "msg": err or "unauthorized"})
                    return
                if not self._is_reboot_allowed():
                    self._publish_config_stat({"ok": False, "msg": "reboot not allowed"})
                    return
                delay_ms = data.get("delay_ms", 0) if isinstance(data, dict) else 0
                self._publish_config_stat({"ok": True, "msg": "rebooting", "delay_ms": delay_ms})
                self._schedule_reboot(delay_ms)
            elif t == base + "config/reboot" or t == base + "reboot":
                # 权限与能力校验
                ok_auth, err = self._is_authorized_for_config(data)
                if not ok_auth:
                    self._publish_config_stat({"ok": False, "msg": err or "unauthorized"})
                    return
                if not self._is_reboot_allowed():
                    self._publish_config_stat({"ok": False, "msg": "reboot not allowed"})
                    return
                delay_ms = data.get("delay_ms", 0) if isinstance(data, dict) else 0
                self._publish_config_stat({"ok": True, "msg": "rebooting", "delay_ms": delay_ms})
                self._schedule_reboot(delay_ms)
            else:
                # 未知命令忽略
                pass
        except Exception as e:
            warning("处理配置指令异常: {}", e, module="NET")