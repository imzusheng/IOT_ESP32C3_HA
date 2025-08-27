# app/ha.py
"""
Home Assistant 帮助模块
- 封装 HA 发现, 状态, 可用性主题的构建与发布
- 与 NetworkManager 解耦, 便于独立导入与测试

用法:
  ha = HomeAssistantHelper(config, get_device_id_fn, mqtt_publish_fn)
  ha.publish_discovery()
  ha.publish_availability(True)
  ha.publish_state(temperature=26.4, humidity=58.2)
"""
from lib.logger import info, warning, debug

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

    def _safe_device_id(self) -> str:
        try:
            did = self._get_device_id() if callable(self._get_device_id) else None
            return str(did) if did else "unknown"
        except Exception:
            return "unknown"

    # -------- 发布器 --------
    def publish_discovery(self):
        """为温度与湿度传感器发布 HA 发现配置"""
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

            temp_cfg = {
                "state_topic": self.state_topic("temperature"),
                "availability": availability,
                "unique_id": f"{device_id}_temperature",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "state_class": "measurement",
                "device": device,
            }
            if temp_name:
                temp_cfg["name"] = temp_name

            hum_cfg = {
                "state_topic": self.state_topic("humidity"),
                "availability": availability,
                "unique_id": f"{device_id}_humidity",
                "unit_of_measurement": "%",
                "device_class": "humidity",
                "state_class": "measurement",
                "device": device,
            }
            if hum_name:
                hum_cfg["name"] = hum_name

            base = self.discovery_prefix
            t_topic = f"{base}/sensor/{device_id}/temperature/config"
            h_topic = f"{base}/sensor/{device_id}/humidity/config"
            self._mqtt_publish(t_topic, temp_cfg, retain=True, qos=0)
            self._mqtt_publish(h_topic, hum_cfg, retain=True, qos=0)
            info("已发布 HA 发现配置: {} , {}", t_topic, h_topic, module="HA")
            return {"topics": [t_topic, h_topic]}
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

    def publish_metrics(self, payload, retain=False, qos=0):
        try:
            topic = self.state_topic("metrics")
            return bool(self._mqtt_publish(topic, payload, retain=retain, qos=qos))
        except Exception:
            return False