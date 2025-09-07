# app/ha.py
"""
Home Assistant 帮助模块
- 封装 HA 发现, 状态, 可用性主题的构建与发布
- 与 NetworkManager 解耦合, 便于独立导入与测试

用法:
  ha = HomeAssistantHelper(config, get_device_id_fn, mqtt_publish_fn)
  ha.publish_discovery()
  ha.publish_availability(True)
  ha.publish_state(temperature=26.4, humidity=58.2)
"""
from lib.logger import info, warning, debug
from utils import json_dumps

class HomeAssistantHelper:
    def __init__(self, config, get_device_id_fn, mqtt_publish_fn):
        self.config = config or {}
        self._get_device_id = get_device_id_fn  # 可调用 -> str
        self._mqtt_publish = mqtt_publish_fn    # 可调用 -> (topic, payload, retain=False, qos=0)

    # -------- 配置相关工具 --------
    @property
    def discovery_prefix(self):
        try:
            ha_cfg = (self.config or {}).get("ha", {}) or {}
            prefix = ha_cfg.get("discovery_prefix")
            if not prefix:
                # 强制要求 ha.discovery_prefix 存在
                raise ValueError("ha.discovery_prefix 未配置")
            return str(prefix).strip("/")
        except Exception as e:
            # 若未配置, 抛出异常, 由调用方决定如何处理
            raise e

    def _device_info(self, device_id: str):
        ha_cfg = (self.config or {}).get("ha", {}) or {}
        device = {"identifiers": [device_id]}
        name = ha_cfg.get("device_name")
        manufacturer = ha_cfg.get("manufacturer")
        model = ha_cfg.get("model")
        sw = ha_cfg.get("sw_version")
        if name:
            device["name"] = name
        if manufacturer:
            device["manufacturer"] = manufacturer
        if model:
            device["model"] = model
        if sw:
            device["sw_version"] = sw
        return device

    # -------- 主题构建器 --------
    def availability_topic(self) -> str:
        device_id = self._safe_device_id()
        return f"device/{device_id}/availability"

    def state_topic(self, sub: str) -> str:
        device_id = self._safe_device_id()
        sub_tail = str(sub).strip("/")
        return f"device/{device_id}/state/{sub_tail}"

    def command_topic(self, sub: str) -> str:
        """构建命令主题 cmnd/<device_id>/<sub>"""
        device_id = self._safe_device_id()
        sub_tail = str(sub).strip("/")
        return f"cmnd/{device_id}/{sub_tail}"

    def _safe_device_id(self) -> str:
        try:
            did = self._get_device_id() if callable(self._get_device_id) else None
            return str(did) if did else "unknown"
        except Exception:
            return "unknown"

    def _get_security_token(self):
        """读取 ble.security.token (当 auth==token 时返回 token)"""
        try:
            ble_cfg = (self.config or {}).get("ble", {}) or {}
            sec = ble_cfg.get("security", {}) or {}
            auth = (sec.get("auth") or "none").lower()
            if auth == "token":
                return sec.get("token")
            return None
        except Exception:
            return None

    def _payload_press_str(self, obj: dict) -> str:
        """将对象编码成字符串, 作为 HA button 的 payload_press"""
        try:
            return json_dumps(obj)
        except Exception:
            try:
                import ujson as _j
            except Exception:
                import json as _j
            try:
                return _j.dumps(obj)
            except Exception:
                return "{}"

    # 新增: 配置快照脱敏工具与发布
    def _redact_config(self, obj):
        """递归脱敏配置中可能的敏感字段, 返回新对象
        - 屏蔽常见敏感键: password, token, secret, access_key, api_key
        - 保持结构, 非敏感字段原样返回
        """
        sensitive = {"password", "token", "secret", "access_key", "api_key"}
        try:
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    lk = str(k).lower()
                    if lk in sensitive:
                        out[k] = "***"
                    else:
                        out[k] = self._redact_config(v)
                return out
            if isinstance(obj, list):
                return [self._redact_config(v) for v in obj]
            return obj
        except Exception:
            return obj

    def publish_config_snapshot(self):
        """发布只读配置快照
        - 通过 json_attributes_topic 承载大部分配置
        - 仅发布状态与属性, 不提供任何 command_topic
        """
        try:
            # 发布属性(JSON 配置快照) 与 一个简单状态
            attrs_topic = self.state_topic("config_snapshot")
            state_topic = self.state_topic("config_state")
            safe_cfg = self._redact_config(self.config or {})
            self._mqtt_publish(attrs_topic, safe_cfg, retain=True, qos=0)
            self._mqtt_publish(state_topic, "ok", retain=True, qos=0)
            debug("已发布配置快照与状态: {}, {}", attrs_topic, state_topic, module="HA")
            return True
        except Exception as e:
            warning("发布配置快照失败: {}", e, module="HA")
            return False

    # -------- 发布器 --------
    def publish_discovery(self):
        """为温度与湿度传感器与配置按钮发布 HA 发现配置"""
        try:
            device_id = self._safe_device_id()
            device = self._device_info(device_id)
            availability = [{
                "topic": self.availability_topic(),
                "payload_available": "online",
                "payload_not_available": "offline",
            }]
            ha_cfg = (self.config or {}).get("ha", {}) or {}
            temp_name = ha_cfg.get("temp_name")
            hum_name = ha_cfg.get("hum_name")

            # 传感器配置
            temp_cfg = {
                "state_topic": self.state_topic("temperature"),
                "availability": availability,
                "unique_id": f"{device_id}_temperature",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "state_class": "measurement",
                "device": device,
            }
            temp_cfg["name"] = temp_name or "温度"

            hum_cfg = {
                "state_topic": self.state_topic("humidity"),
                "availability": availability,
                "unique_id": f"{device_id}_humidity",
                "unit_of_measurement": "%",
                "device_class": "humidity",
                "state_class": "measurement",
                "device": device,
            }
            hum_cfg["name"] = hum_name or "湿度"

            base = self.discovery_prefix
            t_topic = f"{base}/sensor/{device_id}/temperature/config"
            h_topic = f"{base}/sensor/{device_id}/humidity/config"
            self._mqtt_publish(t_topic, temp_cfg, retain=True, qos=0)
            self._mqtt_publish(h_topic, hum_cfg, retain=True, qos=0)

            # 只读配置快照 sensor (无命令, 仅属性)
            cfg_sensor = {
                "state_topic": self.state_topic("config_state"),
                "json_attributes_topic": self.state_topic("config_snapshot"),
                "availability": availability,
                "unique_id": f"{device_id}_config_snapshot",
                "name": ha_cfg.get("config_name") or "设备配置",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:cog",
            }
            cfg_topic = f"{base}/sensor/{device_id}/config_snapshot/config"
            self._mqtt_publish(cfg_topic, cfg_sensor, retain=True, qos=0)

            # 诊断只读传感器发现配置: 从 config_snapshot 与 metrics 提取显示
            diag_topics = []

            # LED 模式(sensor)
            led_mode_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ value_json.ha.led_mode }}",
                "availability": availability,
                "unique_id": f"{device_id}_led_mode",
                "name": "LED 模式",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:led-on",
            }
            topic_lm = f"{base}/sensor/{device_id}/led_mode/config"
            self._mqtt_publish(topic_lm, led_mode_cfg, retain=True, qos=0)
            diag_topics.append(topic_lm)

            # LED 使能(binary_sensor)
            led_enabled_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ 'ON' if value_json.ha.led_enabled else 'OFF' }}",
                "availability": availability,
                "unique_id": f"{device_id}_led_enabled",
                "name": "LED 使能",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:power",
            }
            topic_le = f"{base}/binary_sensor/{device_id}/led_enabled/config"
            self._mqtt_publish(topic_le, led_enabled_cfg, retain=True, qos=0)
            diag_topics.append(topic_le)

            # 主循环间隔(sensor, ms)
            loop_delay_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ value_json.system.main_loop_delay }}",
                "availability": availability,
                "unique_id": f"{device_id}_main_loop_delay",
                "name": "主循环延时",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:timer-sand",
                "unit_of_measurement": "ms",
                "state_class": "measurement",
            }
            topic_ld = f"{base}/sensor/{device_id}/main_loop_delay/config"
            self._mqtt_publish(topic_ld, loop_delay_cfg, retain=True, qos=0)
            diag_topics.append(topic_ld)

            # 移除看门狗使能实体：清理旧 discovery（空保留消息）
            topic_we = f"{base}/binary_sensor/{device_id}/wdt_enabled/config"
            self._mqtt_publish(topic_we, "", retain=True, qos=0)

            # 移除看门狗超时实体：清理旧 discovery（空保留消息）
            topic_wt = f"{base}/sensor/{device_id}/wdt_timeout/config"
            self._mqtt_publish(topic_wt, "", retain=True, qos=0)

            # 运行时长(文本) - 友好显示，如 "3 分钟" / "1.2 小时"
            uptime_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.uptime_text }}",
                "availability": availability,
                "unique_id": f"{device_id}_uptime_text",
                "name": "运行时长",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:clock-outline",
            }
            topic_up = f"{base}/sensor/{device_id}/uptime/config"
            self._mqtt_publish(topic_up, uptime_cfg, retain=True, qos=0)
            diag_topics.append(topic_up)

            # MCU 温度(sensor, °C)
            mcu_temp_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.mcu_temp_c }}",
                "availability": availability,
                "unique_id": f"{device_id}_mcu_temp_c",
                "name": "MCU 温度",
                "device": device,
                "entity_category": "diagnostic",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
                "icon": "mdi:thermometer",
            }
            topic_mt = f"{base}/sensor/{device_id}/mcu_temp_c/config"
            self._mqtt_publish(topic_mt, mcu_temp_cfg, retain=True, qos=0)
            diag_topics.append(topic_mt)

            # 内存使用率(sensor, %)
            mem_used_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ (value_json.mem.percent | float) | round(1) }}",
                "availability": availability,
                "unique_id": f"{device_id}_mem_used_percent",
                "name": "内存使用率",
                "device": device,
                "entity_category": "diagnostic",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:memory",
            }
            topic_mp = f"{base}/sensor/{device_id}/mem_used_percent/config"
            self._mqtt_publish(topic_mp, mem_used_cfg, retain=True, qos=0)
            diag_topics.append(topic_mp)

            # 内存剩余(sensor, KB)
            mem_free_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.mem.free_kb }}",
                "availability": availability,
                "unique_id": f"{device_id}_mem_free_kb",
                "name": "内存剩余",
                "device": device,
                "entity_category": "diagnostic",
                "unit_of_measurement": "KB",
                "state_class": "measurement",
                "icon": "mdi:memory",
            }
            topic_mf = f"{base}/sensor/{device_id}/mem_free_kb/config"
            self._mqtt_publish(topic_mf, mem_free_cfg, retain=True, qos=0)
            diag_topics.append(topic_mf)

            # 主循环实际休眠间隔(ms) - 来源 metrics.diag.loop_sleep_ms
            loop_sleep_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.diag.loop_sleep_ms }}",
                "availability": availability,
                "unique_id": f"{device_id}_loop_sleep_ms",
                "name": "循环休眠",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:timer-sand",
                "unit_of_measurement": "ms",
                "state_class": "measurement",
            }
            topic_ls = f"{base}/sensor/{device_id}/loop_sleep_ms/config"
            self._mqtt_publish(topic_ls, loop_sleep_cfg, retain=True, qos=0)
            diag_topics.append(topic_ls)

            # 上次喂狗间隔(文本) - 由设备侧统一格式化，避免 0.001 分钟等
            wdt_feed_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.diag.wdt_last_feed_text }}",
                "availability": availability,
                "unique_id": f"{device_id}_wdt_last_feed_text",
                "enabled_by_default": False,
                "name": "上次喂狗间隔",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:dog-service",
            }
            # 已禁用“上次喂狗间隔”实体的发布，减少界面噪音
            # 清理历史保留的该实体 Discovery（空 payload 覆盖保留消息）
            topic_wf = f"{base}/sensor/{device_id}/wdt_last_feed_ms/config"
            try:
                self._mqtt_publish(topic_wf, "", retain=True, qos=0)
            except Exception:
                pass

            # ===== 额外只读诊断(直接来源于 config_snapshot) =====
            # MQTT 服务器
            mqtt_broker_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ value_json.mqtt.broker }}",
                "availability": availability,
                "unique_id": f"{device_id}_mqtt_broker",
                "name": "MQTT 服务器",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:server-network",
            }
            topic_mb = f"{base}/sensor/{device_id}/mqtt_broker/config"
            self._mqtt_publish(topic_mb, mqtt_broker_cfg, retain=True, qos=0)
            diag_topics.append(topic_mb)

            # MQTT 保活(文本)
            mqtt_keep_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.config_text.mqtt_keepalive }}",
                "availability": availability,
                "unique_id": f"{device_id}_mqtt_keepalive",
                "name": "MQTT 保活",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:timer-outline",
            }
            topic_mk = f"{base}/sensor/{device_id}/mqtt_keepalive/config"
            self._mqtt_publish(topic_mk, mqtt_keep_cfg, retain=True, qos=0)
            diag_topics.append(topic_mk)

            # WiFi 扫描超时(文本)
            wifi_scan_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.config_text.wifi_scan_timeout }}",
                "availability": availability,
                "unique_id": f"{device_id}_wifi_scan_timeout",
                "name": "WiFi 扫描超时",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:wifi-settings",
            }
            topic_ws = f"{base}/sensor/{device_id}/wifi_scan_timeout/config"
            self._mqtt_publish(topic_ws, wifi_scan_cfg, retain=True, qos=0)
            diag_topics.append(topic_ws)

            # WiFi 基础延迟(文本)
            wifi_base_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.config_text.wifi_base_delay }}",
                "availability": availability,
                "unique_id": f"{device_id}_wifi_base_delay",
                "name": "WiFi 基础延迟",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:timer-sand",
            }
            topic_wb = f"{base}/sensor/{device_id}/wifi_base_delay/config"
            self._mqtt_publish(topic_wb, wifi_base_cfg, retain=True, qos=0)
            diag_topics.append(topic_wb)

            wifi_max_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.config_text.wifi_max_delay }}",
                "availability": availability,
                "unique_id": f"{device_id}_wifi_max_delay",
                "name": "WiFi 最大延迟",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:timer-cog",
            }
            topic_wm = f"{base}/sensor/{device_id}/wifi_max_delay/config"
            self._mqtt_publish(topic_wm, wifi_max_cfg, retain=True, qos=0)
            diag_topics.append(topic_wm)

            wifi_retry_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ value_json.wifi.max_retries }}",
                "availability": availability,
                "unique_id": f"{device_id}_wifi_max_retries",
                "name": "WiFi 最大重试次数",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:restart-alert",
            }
            topic_wr = f"{base}/sensor/{device_id}/wifi_max_retries/config"
            self._mqtt_publish(topic_wr, wifi_retry_cfg, retain=True, qos=0)
            diag_topics.append(topic_wr)

            # WiFi 网络数量
            wifi_count_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ (value_json.wifi.networks | default([])) | length }}",
                "availability": availability,
                "unique_id": f"{device_id}_wifi_networks_count",
                "name": "WiFi 网络数量",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:wifi",
            }
            topic_wn = f"{base}/sensor/{device_id}/wifi_networks_count/config"
            self._mqtt_publish(topic_wn, wifi_count_cfg, retain=True, qos=0)
            diag_topics.append(topic_wn)

            # NTP
            ntp_server_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ value_json.ntp.server }}",
                "availability": availability,
                "unique_id": f"{device_id}_ntp_server",
                "name": "NTP 服务器",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:clock",
            }
            topic_ns = f"{base}/sensor/{device_id}/ntp_server/config"
            self._mqtt_publish(topic_ns, ntp_server_cfg, retain=True, qos=0)
            diag_topics.append(topic_ns)

            ntp_timeout_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.config_text.ntp_timeout }}",
                "availability": availability,
                "unique_id": f"{device_id}_ntp_timeout",
                "name": "NTP 超时",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:timer-outline",
            }
            topic_nt = f"{base}/sensor/{device_id}/ntp_timeout/config"
            self._mqtt_publish(topic_nt, ntp_timeout_cfg, retain=True, qos=0)
            diag_topics.append(topic_nt)

            # Daemon 错误上限
            max_err_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ value_json.daemon.max_error_count }}",
                "availability": availability,
                "unique_id": f"{device_id}_max_error_count",
                "name": "最大错误次数",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:alert-decagram-outline",
            }
            topic_me = f"{base}/sensor/{device_id}/max_error_count/config"
            self._mqtt_publish(topic_me, max_err_cfg, retain=True, qos=0)
            diag_topics.append(topic_me)

            # BLE 开关与广播间隔
            ble_enabled_cfg = {
                "state_topic": self.state_topic("config_snapshot"),
                "value_template": "{{ 'ON' if value_json.ble.enabled else 'OFF' }}",
                "availability": availability,
                "unique_id": f"{device_id}_ble_enabled",
                "name": "BLE 使能",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:bluetooth",
            }
            topic_be = f"{base}/binary_sensor/{device_id}/ble_enabled/config"
            self._mqtt_publish(topic_be, ble_enabled_cfg, retain=True, qos=0)
            diag_topics.append(topic_be)

            ble_adv_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.config_text.ble_adv_interval }}",
                "availability": availability,
                "unique_id": f"{device_id}_ble_adv_interval",
                "name": "BLE 广播间隔",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:bluetooth-settings",
            }
            topic_ba = f"{base}/sensor/{device_id}/ble_adv_interval/config"
            self._mqtt_publish(topic_ba, ble_adv_cfg, retain=True, qos=0)
            diag_topics.append(topic_ba)

            # 固件与型号
            # 已移除固件版本实体配置
            topic_fv = f"{base}/sensor/{device_id}/fw_version/config"
            self._mqtt_publish(topic_fv, "", retain=True, qos=0)
            # diag_topics.append(topic_fv)  # 清理旧实体，不计入统计

            # 已移除设备型号实体配置
            topic_dm = f"{base}/sensor/{device_id}/device_model/config"
            self._mqtt_publish(topic_dm, "", retain=True, qos=0)
            # diag_topics.append(topic_dm)  # 清理旧实体，不计入统计

            # 配置化按钮系统: 仅保留 reboot, 其余全部忽略(实现只读)
            token = self._get_security_token()
            buttons = ha_cfg.get("buttons", [])
            button_topics = []
            for btn in buttons:
                if not isinstance(btn, dict):
                    continue
                btn_id = btn.get("id")
                if not btn_id:
                    continue
                btn_name = btn.get("name") or btn_id.title()
                btn_icon = btn.get("icon") or "mdi:gesture-tap-button"
                btn_type = btn.get("type", "button")
                btn_params = btn.get("params", {})

                # 只允许重启按钮，其余全部跳过
                if not (btn_type == "reboot" or btn_id == "reboot"):
                    continue

                payload = dict(btn_params) if isinstance(btn_params, dict) else {}
                if token is not None:
                    payload["token"] = token

                btn_cfg = {
                    "command_topic": self.command_topic(f"config/button/{btn_id}"),
                    "payload_press": self._payload_press_str(payload),
                    "availability": availability,
                    "unique_id": f"{device_id}_btn_{btn_id}",
                    "name": btn_name,
                    "device": device,
                    "entity_category": "config",
                    "icon": btn_icon,
                }
                btn_topic = f"{base}/button/{device_id}/{btn_id}/config"
                self._mqtt_publish(btn_topic, btn_cfg, retain=True, qos=0)
                button_topics.append(btn_topic)

            # 发布一次只读配置快照
            self.publish_config_snapshot()

            all_topics = [t_topic, h_topic, cfg_topic] + diag_topics + button_topics
            info("已发布 HA 发现配置: {}", ", ".join(all_topics), module="HA")
            return {"topics": all_topics}
        except Exception as e:
            warning("发布 HA 发现配置失败: {}", e, module="HA")
            return {"topics": []}

    def publish_availability(self, online: bool = True):
        try:
            topic = self.availability_topic()
            self._mqtt_publish(topic, "online" if online else "offline", retain=True, qos=0)
            debug("可用性已发布: {} -> {}", topic, "online" if online else "offline", module="HA")
            return True
        except Exception:
            return False

    def publish_state(self, temperature=None, humidity=None, retain=False):
        ok = True
        try:
            if temperature is not None:
                ok = bool(self._mqtt_publish(self.state_topic("temperature"), temperature, retain=retain, qos=0)) and ok
            if humidity is not None:
                ok = bool(self._mqtt_publish(self.state_topic("humidity"), humidity, retain=retain, qos=0)) and ok
        except Exception:
            ok = False
        return ok

    def publish_select_discovery(self, select_id: str, name: str, options: list, icon: str = "mdi:format-list-bulleted"):
        """为 select 实体发布 HA 发现配置"""
        try:
            device_id = self._safe_device_id()
            device = self._device_info(device_id)
            availability = [{
                "topic": self.availability_topic(),
                "payload_available": "online",
                "payload_not_available": "offline",
            }]
            
            select_cfg = {
                "command_topic": self.command_topic(f"config/select/{select_id}"),
                "state_topic": self.state_topic(f"select/{select_id}"),
                "availability": availability,
                "unique_id": f"{device_id}_select_{select_id}",
                "name": name,
                "device": device,
                "entity_category": "config",
                "icon": icon,
                "options": options,
            }
            
            topic = f"{self.discovery_prefix}/select/{device_id}/{select_id}/config"
            self._mqtt_publish(topic, select_cfg, retain=True, qos=0)
            info("已发布 HA select 发现配置: {}", topic, module="HA")
            return topic
        except Exception as e:
            warning("发布 HA select 发现配置失败: {}", e, module="HA")
            return None

    def publish_metrics(self, payload, retain=False, qos=0):
        try:
            topic = self.state_topic("metrics")
            return bool(self._mqtt_publish(topic, payload, retain=retain, qos=qos))
        except Exception:
            return False
