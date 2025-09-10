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
        
        # 添加自动界面配置提示
        device["suggested_area"] = "设备控制"
        device["configuration_url"] = f"http://{device_id}.local"
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
        """为温度与湿度传感器、风扇thermostat控制发布 HA 发现配置"""
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
            fan_name = ha_cfg.get("fan_name", "风扇")

            # 温度传感器
            temp_cfg = {
                "state_topic": self.state_topic("temperature"),
                "availability": availability,
                "unique_id": f"{device_id}_temperature",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "state_class": "measurement",
                "device": device,
                "name": temp_name or "温度",
            }

            # 湿度传感器
            hum_cfg = {
                "state_topic": self.state_topic("humidity"),
                "availability": availability,
                "unique_id": f"{device_id}_humidity",
                "unit_of_measurement": "%",
                "device_class": "humidity",
                "state_class": "measurement",
                "device": device,
                "name": hum_name or "湿度",
            }

            # LED状态传感器 (只读)
            led_status_cfg = {
                "state_topic": self.state_topic("led_status"),
                "availability": availability,
                "unique_id": f"{device_id}_led_status",
                "name": "LED状态",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:led-on",
            }

            # 风扇控制 - 使用 fan 实体
            fan_cfg = {
                "name": f"{fan_name}控制",
                "unique_id": f"{device_id}_fan",
                "device": device,
                "availability": availability,
                "state_topic": self.state_topic("fan_state"),
                "command_topic": self.command_topic("fan_state"),
                "speed_state_topic": self.state_topic("fan_speed"),
                "speed_command_topic": self.command_topic("fan_speed"),
                "percentage_state_topic": self.state_topic("fan_speed_percent"),
                "percentage_command_topic": self.command_topic("fan_speed_percent"),
                "speeds": ["off", "10%", "30%", "60%", "90%"],
                "percentage_value_template": "{{ value }}",
                "speed_value_template": "{{ value }}",
            }

            base = self.discovery_prefix
            t_topic = f"{base}/sensor/{device_id}/temperature/config"
            h_topic = f"{base}/sensor/{device_id}/humidity/config"
            led_topic = f"{base}/sensor/{device_id}/led_status/config"
            fan_topic = f"{base}/fan/{device_id}/fan/config"
            self._mqtt_publish(t_topic, temp_cfg, retain=True, qos=0)
            self._mqtt_publish(h_topic, hum_cfg, retain=True, qos=0)
            self._mqtt_publish(led_topic, led_status_cfg, retain=True, qos=0)
            self._mqtt_publish(fan_topic, fan_cfg, retain=True, qos=0)

            # 诊断传感器
            diag_topics = []

            # 运行时长(文本)
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

            # MCU 温度
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

            # 内存使用率
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

            # 内存剩余
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

            # 系统状态
            system_status_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.status_text }}",
                "availability": availability,
                "unique_id": f"{device_id}_system_status",
                "name": "系统状态",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:information",
            }
            topic_ss = f"{base}/sensor/{device_id}/system_status/config"
            self._mqtt_publish(topic_ss, system_status_cfg, retain=True, qos=0)
            diag_topics.append(topic_ss)

            # 网络状态
            network_status_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.network_status_text }}",
                "availability": availability,
                "unique_id": f"{device_id}_network_status",
                "name": "网络状态",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:network",
            }
            topic_ns = f"{base}/sensor/{device_id}/network_status/config"
            self._mqtt_publish(topic_ns, network_status_cfg, retain=True, qos=0)
            diag_topics.append(topic_ns)

            # 错误计数
            error_count_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.error_count }}",
                "availability": availability,
                "unique_id": f"{device_id}_error_count",
                "name": "错误计数",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:alert-circle",
            }
            topic_ec = f"{base}/sensor/{device_id}/error_count/config"
            self._mqtt_publish(topic_ec, error_count_cfg, retain=True, qos=0)
            diag_topics.append(topic_ec)

            # 最后错误时间
            last_error_cfg = {
                "state_topic": self.state_topic("metrics"),
                "value_template": "{{ value_json.last_error_time }}",
                "availability": availability,
                "unique_id": f"{device_id}_last_error_time",
                "name": "最后错误时间",
                "device": device,
                "entity_category": "diagnostic",
                "icon": "mdi:clock-alert",
            }
            topic_let = f"{base}/sensor/{device_id}/last_error_time/config"
            self._mqtt_publish(topic_let, last_error_cfg, retain=True, qos=0)
            diag_topics.append(topic_let)

            # 重启按钮
            token = self._get_security_token()
            buttons = ha_cfg.get("buttons", [])
            button_topics = []
            
            for btn in buttons:
                if not isinstance(btn, dict):
                    continue
                btn_id = btn.get("id")
                if not btn_id or btn_id != "reboot":
                    continue
                    
                btn_name = btn.get("name") or "重启设备"
                btn_icon = btn.get("icon") or "mdi:restart"
                btn_params = btn.get("params", {})

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
                    "confirmation": {
                        "text": "确定要重启设备吗？此操作将断开所有连接。"
                    }
                    }
                btn_topic = f"{base}/button/{device_id}/{btn_id}/config"
                self._mqtt_publish(btn_topic, btn_cfg, retain=True, qos=0)
                button_topics.append(btn_topic)

            all_topics = [t_topic, h_topic, led_topic, fan_topic] + diag_topics + button_topics
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

    def publish_state(self, temperature=None, humidity=None, fan_state=None, fan_speed=None, fan_speed_percent=None, led_status=None, retain=False):
        ok = True
        try:
            if temperature is not None:
                ok = bool(self._mqtt_publish(self.state_topic("temperature"), str(temperature), retain=retain, qos=0)) and ok
            if humidity is not None:
                ok = bool(self._mqtt_publish(self.state_topic("humidity"), str(humidity), retain=retain, qos=0)) and ok
            if fan_state is not None:
                ok = bool(self._mqtt_publish(self.state_topic("fan_state"), str(fan_state), retain=retain, qos=0)) and ok
            if fan_speed is not None:
                ok = bool(self._mqtt_publish(self.state_topic("fan_speed"), str(fan_speed), retain=retain, qos=0)) and ok
            if fan_speed_percent is not None:
                ok = bool(self._mqtt_publish(self.state_topic("fan_speed_percent"), str(fan_speed_percent), retain=retain, qos=0)) and ok
            if led_status is not None:
                ok = bool(self._mqtt_publish(self.state_topic("led_status"), str(led_status), retain=retain, qos=0)) and ok
        except Exception:
            ok = False
        return ok



    def publish_metrics(self, payload, retain=False, qos=0):
        try:
            topic = self.state_topic("metrics")
            return bool(self._mqtt_publish(topic, payload, retain=retain, qos=qos))
        except Exception:
            return False
