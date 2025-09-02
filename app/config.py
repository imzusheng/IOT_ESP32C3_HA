# -*- coding: utf-8 -*-
"""
配置模块

所有配置项都在此文件中直接定义, 并附有详细说明。
通过 `get_config()` 函数可以安全地访问这些配置。
要修改配置, 直接编辑下面的 CONFIG 字典即可。
注释旨在帮助理解每个参数的用途、对项目的影响以及推荐的设定范围。
"""

# =============================================================================
# 配置数据 (唯一配置源)
# =============================================================================

CONFIG = {
    "daemon": {
        # 描述: 系统在进入安全模式或重启前, 允许累计的最大错误次数。
        # 影响: 这是一个容错机制, 避免因为瞬时或小概率的错误导致系统频繁重启。
        # 建议: 5-20 次。
        "max_error_count": 10,
        # 描述: 看门狗定时器(WDT)的超时时间, 单位为毫秒。
        # 影响: 如果主程序在指定时间内没有"喂狗"(feed), 看门狗将强制重启设备。这是防止固件死锁或主循环卡死的最后防线。
        # 建议: 60000-300000 毫秒, 必须远大于主循环的正常执行时间。
        "wdt_timeout": 60000,
        # 描述: 是否启用硬件看门狗。
        # 影响: 生产环境中强烈建议启用, 以保证设备在无人值守的情况下能从未知错误中自愈。开发调试时可关闭。
        # 建议: 生产环境 `True`, 开发环境 `False`。
        "wdt_enabled": True,
    },
    "system": {
        # 描述: 主循环(main loop)的延迟时间, 单位为毫秒。
        # 影响: 这是主循环每次迭代的间隔, 直接影响系统的响应速度和CPU使用率。值越小响应越快, 但CPU占用越高, 也越耗电。
        # 建议: 50-1000 毫秒。
        "main_loop_delay": 25,
    },
    "wifi": {
        # 描述: 可用的WiFi网络列表
        # 影响: NetworkManager将扫描并按RSSI强度排序后依次尝试连接配置的网络
        # 建议: 配置多个网络以提高连接成功率, 系统会自动选择信号最强的可用网络
        "networks": [
            {"ssid": "zsm60p", "password": "25845600"},
            {"ssid": "leju_software", "password": "leju123456"},
            {"ssid": "CMCC-pdRG", "password": "7k77ed5p"},
        ],
        # 描述: WiFi扫描超时时间, 单位毫秒
        # 影响: 控制 wlan.scan() 的期望耗时阈值, 用于告警/诊断, 防止扫描长时间阻塞事件循环
        # 建议: 5000-15000 毫秒, 视现场环境而定
        "scan_timeout_ms": 10000,
        # 描述: WiFi重连基础延迟时间, 单位毫秒
        # 影响: WiFi重连指数退避的起始延迟时间
        # 建议: 1000-5000毫秒, 避免过于频繁的重连
        "base_delay_ms": 3000,
        # 描述: WiFi重连最大延迟时间, 单位毫秒  
        # 影响: 防止指数退避延迟过长, 限制重连等待上限
        # 建议: 180000毫秒(3分钟), 符合用户要求
        "max_delay_ms": 60000,
        # 描述: WiFi最大重试次数
        # 影响: 设置为-1表示无限次重试, 配合指数退避和最大延迟防止打爆网络
        # 建议: 生产环境使用-1(无限), 开发调试可设置较小值
        "max_retries": 3,
    },
    "mqtt": {
        # 描述: MQTT服务器地址
        # 影响: 设备将连接到指定的MQTT服务器
        # 建议: 使用稳定的MQTT服务器地址
        "broker": "zusheng.cc",
        # 描述: MQTT服务器端口
        # 影响: MQTT服务器的连接端口
        # 建议: 默认1883, SSL连接使用8883
        "port": 1883,
        # 描述: MQTT用户名
        # 影响: MQTT服务器的认证用户名
        # 建议: 使用可靠的用户名
        "user": "",
        # 描述: MQTT密码
        # 影响: MQTT服务器的认证密码
        # 建议: 使用可靠的密码
        "password": "",
        # 描述: MQTT保持连接时间
        # 影响: 客户端与服务器之间的心跳间隔
        # 建议: 60-120秒
        "keepalive": 60,
        # 描述: MQTT重连基础延迟时间, 单位毫秒
        # 影响: MQTT重连指数退避的起始延迟时间
        # 建议: 1000-5000毫秒
        "base_delay_ms": 3000,
        # 描述: MQTT重连最大延迟时间, 单位毫秒
        # 影响: 限制指数退避的最大等待时间。用户要求3分钟上限。
        # 建议: 180000毫秒(3分钟)
        "max_delay_ms": 60000,
        # 描述: MQTT最大重试次数
        # 影响: 设置为-1表示无限次重试, 配合指数退避和最大延迟防止打爆网络
        # 建议: 生产环境使用-1(无限), 开发调试可设置较小值
        "max_retries": 3,
        # 描述: 是否将日志转发到 MQTT 主题
        # 影响: 开启后会占用带宽且可能阻塞网络 I/O, 只建议在调试阶段使用
        # 建议: 生产环境 False; 调试按需开启 True
        "enable_log_forward": False,
    },
    "ntp": {
        # 描述: NTP服务器地址
        # 影响: 设备将从此服务器同步时间
        # 建议: 使用可靠的NTP服务器
        "server": "ntp1.aliyun.com",
        # 描述: NTP同步超时时间
        # 影响: 等待NTP响应的最长时间
        # 建议: 5-10秒
        "timeout": 5000,
    },
    "ha": {
        # 描述: Home Assistant discovery 前缀
        # 影响: 构建 discovery 主题的根路径
        # 建议: 保持为 'homeassistant' 或与你的 HA 配置一致
        "discovery_prefix": "homeassistant",
        # 描述: 设备在 HA 中显示的名称(可选)
        "device_name": "Zusheng's ESP32C3",
        # 描述: 生产厂家(可选)
        "manufacturer": "Zusheng STU",
        # 描述: 型号(可选)
        "model": "C3",
        # 描述: 固件版本(可选)
        "sw_version": "2.3.0",
        # 描述: 传感器展示名称(可选)
        "temp_name": "Temperature",
        # 描述: 传感器展示名称(可选)
        "humi_name": "Humidity",
        # 描述: LED开关状态
        "led_enabled": True,
        # 描述: LED闪烁模式
        "led_mode": "cruise",
        # 描述: 按钮配置列表
        "buttons": [
            {
                "id": "reboot",
                "name": "重启设备",
                "icon": "mdi:restart",
                "type": "reboot",
                "params": {"delay_ms": 0}
            },
            {
                "id": "reset_wifi",
                "name": "重置WiFi",
                "icon": "mdi:wifi-off",
                "type": "reset",
                "params": {"target": "wifi"}
            },
            {
                "id": "led_power",
                "name": "LED开关",
                "icon": "mdi:lightbulb",
                "type": "toggle",
                "params": {"feature": "led_enabled", "default": True}
            },
            {
                "id": "led_mode",
                "name": "LED模式",
                "icon": "mdi:palette",
                "type": "select",
                "params": {
                    "feature": "led_mode",
                    "options": ["off", "blink", "pulse", "cruise", "sos"],
                    "default": "cruise"
                }
            }
        ],
    },
    # ==========================
    # BLE 配置段（新增）
    # ==========================
    "ble": {
        # 描述: 是否启用 BLE 功能
        # 影响: 关闭后不初始化 BLE 子系统, 节约资源
        # 建议: 开发与演示阶段保持 True, 量产可按需关闭
        "enabled": True,
        # 描述: 是否启用 HID 模式（HID over GATT）
        # 影响: 开启 HID 可作为遥控器/键鼠等; 但某些 Web Bluetooth 环境与 HID 并不兼容
        # 建议: 默认为 False 以兼容 Web Bluetooth
        "use_hid": False,
        # 描述: BLE GAP 设备名称
        # 影响: 影响被扫描与识别时的显示名称
        # 建议: 短而有辨识度, 避免占用过多广播字节
        "device_name": "ESP32-C3",
        # 描述: 广播参数
        # 影响: 广播间隔越短越容易被发现, 但更耗电
        # 建议: 100-1000ms, Demo 使用 150ms 比较灵敏
        "adv": {
            "interval_ms": 150,
        },
        # 描述: 服务开关
        # 影响: 控制标准与自定义服务是否注册
        # 建议: 根据需求按需开启
        "services": {
            "battery": True,         # 电池服务 (0x180F)
            "device_info": True,     # 设备信息服务 (0x180A)
            "env_sensing": False,    # 环境感知服务 (温湿度等)
            "uart": False,           # 自定义 UART/配置服务（后续实现）
            "ota": False,            # OTA 服务（后续实现）
        },
        # 描述: 安全配置（用于 BLE 配置服务的写入权限控制）
        # 影响: 决定是否需要鉴权才能修改配置/触发敏感操作
        # 建议: 开发阶段可为 "none"; 上线建议切换到 "token"
        "security": {
            "auth": "none",         # "none" | "token"
            "token": "changeme",    # 示例 token（请勿用于生产）
            "allowlist": [],         # 可选: 允许的中心设备地址列表
        },
        # 描述: 电量模拟配置（用于演示/测试通知）
        # 影响: 按周期调整电量并向订阅者通知
        # 建议: 开发演示可开启, 生产可关闭
        "simulation": {
            "battery": {
                "enabled": True,
                "start": 100,
                "step": -1,
                "min": 0,
                "period_ms": 10000,
                "strategy": "hardware",  # "hardware" | "software"
                "timer_id": 0,
            }
        },
        # 描述: 配置服务（通过 Web Bluetooth 修改配置）
        # 影响: 打开后将注册自定义服务, 接受 GET/SET/SAVE/REBOOT 等命令
        # 建议: 开发阶段开启; 生产按需启用并配合鉴权
        "config_service": {
            "enabled": True,
            "persistence_path": "/config.json",
            "allow_reboot": True,
        },
    },
}


# =============================================================================
# 覆盖层与运行时配置
# =============================================================================

# Runtime overlay persistence path
try:
    _PERSISTENCE_PATH = CONFIG.get("ble", {}).get("config_service", {}).get("persistence_path", "/config.json")
except Exception:
    _PERSISTENCE_PATH = "/config.json"

# Safe import of json utils with graceful fallback
try:
    from utils.json_utils import load_json_file as _load_json_file, atomic_write_json as _atomic_write_json
except Exception:
    _load_json_file = None
    _atomic_write_json = None

    def _fallback_load_json(path, default=None):
        try:
            import ujson as _uj
        except Exception:
            try:
                import json as _uj
            except Exception:
                _uj = None
        try:
            with open(path, "r") as f:
                s = f.read()
            if _uj:
                return _uj.loads(s)
            return default if default is not None else {}
        except Exception:
            return default if default is not None else {}

    def _fallback_atomic_write(path, data):
        try:
            try:
                import ujson as _uj
            except Exception:
                import json as _uj
            with open(path, "w") as f:
                f.write(_uj.dumps(data))
                try:
                    f.flush()
                except Exception:
                    pass
            return True
        except Exception:
            return False

    _load_json_file = _fallback_load_json
    _atomic_write_json = _fallback_atomic_write

# In-memory overlay and merged runtime config
_OVERLAY = {}
_RUNTIME_CONFIG = None


def _deep_copy(obj):
    """Shallow-friendly deep copy for dict/list primitives"""
    try:
        if isinstance(obj, dict):
            return {k: _deep_copy(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [ _deep_copy(v) for v in obj ]
        return obj
    except Exception:
        return obj


def _deep_merge(base, overlay):
    """Return a new dict by deep merging overlay onto base"""
    if not isinstance(base, dict):
        return _deep_copy(overlay) if isinstance(overlay, dict) else overlay
    result = _deep_copy(base)
    try:
        if isinstance(overlay, dict):
            for k, v in overlay.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k] = _deep_merge(result[k], v)
                else:
                    result[k] = _deep_copy(v)
        return result
    except Exception:
        return result


def _deep_get(d, path, default=None):
    try:
        if not path:
            return d
        cur = d
        parts = path.split(".") if isinstance(path, str) else list(path)
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur
    except Exception:
        return default


def _deep_set(d, path, value, create_missing=True):
    try:
        parts = path.split(".") if isinstance(path, str) else list(path)
        cur = d
        for i, p in enumerate(parts):
            is_last = i == len(parts) - 1
            if is_last:
                try:
                    cur[p] = value
                except Exception:
                    return False
                return True
            # ensure dict level
            if p not in cur or not isinstance(cur[p], dict):
                if not create_missing:
                    return False
                cur[p] = {}
            cur = cur[p]
        return True
    except Exception:
        return False


def _load_overlay_from_file(path):
    data = _load_json_file(path, default={}) if _load_json_file else {}
    return data if isinstance(data, dict) else {}


def _init_runtime_config():
    global _OVERLAY, _RUNTIME_CONFIG
    try:
        _OVERLAY = _load_overlay_from_file(_PERSISTENCE_PATH)
    except Exception:
        _OVERLAY = {}
    _RUNTIME_CONFIG = _deep_merge(CONFIG, _OVERLAY)


# initialize merged runtime config at import time
_init_runtime_config()


def reload_overlay(path=None):
    """Reload overlay file and rebuild runtime config"""
    global _OVERLAY, _RUNTIME_CONFIG
    try:
        p = path or _PERSISTENCE_PATH
        _OVERLAY = _load_overlay_from_file(p)
        _RUNTIME_CONFIG = _deep_merge(CONFIG, _OVERLAY)
        return True
    except Exception:
        return False


def apply_overlay(update_dict=None, path=None, value=None):
    """Apply overlay to in-memory runtime config only
    - update_dict: dict of partial overlay
    - or use path/value to set a single key path
    Returns True on success
    """
    global _OVERLAY, _RUNTIME_CONFIG
    try:
        if update_dict and isinstance(update_dict, dict):
            # deep merge onto overlay
            _OVERLAY = _deep_merge(_OVERLAY, update_dict)
        elif path is not None:
            if not isinstance(_OVERLAY, dict):
                _OVERLAY = {}
            _deep_set(_OVERLAY, path, value, create_missing=True)
        else:
            return False
        _RUNTIME_CONFIG = _deep_merge(CONFIG, _OVERLAY)
        return True
    except Exception:
        return False


def save_overlay(paths=None, persistence_path=None):
    """Persist current overlay to json atomically
    - paths: optional list of top-level or dotted paths to restrict what to persist
    - persistence_path: override path; default to _PERSISTENCE_PATH
    If paths is None, write whole overlay
    """
    try:
        target_path = persistence_path or _PERSISTENCE_PATH
        data = _OVERLAY if isinstance(_OVERLAY, dict) else {}
        if paths and isinstance(paths, (list, tuple)):
            # build a minimal dict containing selected paths
            minimal = {}
            for p in paths:
                val = _deep_get(data, p, default=None)
                if val is None:
                    continue
                # create nested structure in minimal
                _deep_set(minimal, p, val, create_missing=True)
            data = minimal
        return True if _atomic_write_json and _atomic_write_json(target_path, data) else False
    except Exception:
        return False


# =============================================================================
# 配置访问接口
# =============================================================================


def get_config(section=None, key=None, default=None):
    """
    从模块内部的 CONFIG 字典中安全地获取配置值。

    Args:
        section (str, optional): 配置段名称。如果为None, 返回整个配置字典。
        key (str, optional): 配置键名。如果为None, 返回整个配置段。
        default: 默认值, 当指定的键不存在时返回。

    Returns:
        配置值或配置字典。
    """
    cfg = _RUNTIME_CONFIG if isinstance(_RUNTIME_CONFIG, dict) else CONFIG
    if section is None:
        return cfg

    section_data = cfg.get(section, {})

    if key is None:
        return section_data

    return section_data.get(key, default)


# =============================================================================
# 初始化
# =============================================================================

# Configuration module loaded silently
