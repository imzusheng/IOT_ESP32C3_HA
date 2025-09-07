# app/main.py
"""
ESP32C3 IoT 设备主程序
职责: 
- 统一完成配置加载、日志初始化、看门狗初始化、事件总线、网络管理器与状态机的装配
- 驱动主循环: 事件分发 → FSM 更新 → 网络循环 → 看门狗喂狗 → 周期性维护

架构关系: 
- EventBus 作为系统消息中枢, FSM/NetworkManager/其他模块通过事件解耦合
- FSM 负责系统状态演进与容错策略, NetworkManager 负责具体联网动作
- MainController 负责看门狗的初始化和喂狗, 确保统一管理
"""

import utime as time
import gc
import machine
import uasyncio as asyncio
from lib.logger import info, error, debug
from config import get_config
from lib.event_bus_lock import EventBus, EVENTS
from utils import check_memory, get_temperature, format_duration_ms
from daemon import Daemon


class MainController:
    """主控制器"""
    def __init__(self):
        self.config = get_config()
        self.daemon = Daemon()
        self.event_bus = EventBus()
        from net.network_manager import NetworkManager
        self.network_manager = NetworkManager(self.config, self.event_bus)
        
        # 状态机
        try:
            from state_machine import FSM
            self.state_machine = FSM(self.event_bus, self.config, self.network_manager)
        except Exception:
            self.state_machine = None
        
        # 系统状态
        self.last_stats_time = 0
        
        # 注册事件监听
        self._register_event_handlers()

    def _init_led(self):
        """LED初始化(如存在)"""
        try:
            if hasattr(machine, "Pin"):
                self.led = machine.Pin(2, machine.Pin.OUT)
                self.led.value(0)
        except Exception:
            self.led = None
    
    def _init_watchdog(self):
        """看门狗初始化(如存在)"""
        try:
            if hasattr(machine, "WDT"):
                self.wdt = machine.WDT(timeout=20000)
            else:
                self.wdt = None
        except Exception:
            self.wdt = None

    def _register_event_handlers(self):
        """注册事件处理器"""
        def on_wifi_change(event_name, state=None, **kwargs):
            debug("WIFI_STATE_CHANGE: {}", state, module="MAIN")
        def on_mqtt_change(event_name, state=None, **kwargs):
            debug("MQTT_STATE_CHANGE: {}", state, module="MAIN")
        self.event_bus.subscribe(EVENTS["WIFI_STATE_CHANGE"], on_wifi_change)
        self.event_bus.subscribe(EVENTS["MQTT_STATE_CHANGE"], on_mqtt_change)

    async def run(self):
        """运行主循环"""
        try:
            # 初始化
            self._init_led()
            self._init_watchdog()
            
            # Start daemon service only once
            self.daemon.start()
            
            # 主循环
            while True:
                current_time = time.ticks_ms()
                
                # 事件分发与状态机更新
                try:
                    if self.event_bus:
                        self.event_bus.process_events()
                    if self.state_machine:
                        self.state_machine.update()
                except Exception:
                    # 记录错误计数 - Only daemon interaction needed
                    self.daemon.incr_error(1)
                
                # 看门狗喂狗 - Main.py drives WDT as requested
                try:
                    if getattr(self, "wdt", None):
                        self.wdt.feed()
                except Exception:
                    pass
                
                # 定期维护
                self._periodic_maintenance(current_time)
                
                await asyncio.sleep_ms(50)
        except Exception as e:
            error("系统异常@{}: {}", "run", e, module="MAIN")

    def _periodic_maintenance(self, current_time):
        """定期维护任务"""
        # 每60秒执行一次
        if time.ticks_diff(current_time, self.last_stats_time) >= 30000 or self.last_stats_time == 0:
            self.last_stats_time = current_time
            
            # 垃圾回收
            gc.collect()
            
            # 输出统计信息
            mem = check_memory()
            free_kb = mem.get("free_kb", gc.mem_free() // 1024)
            percent_used = round(mem.get("percent", 0), 1)
            
            # 读取MCU内部温度
            temp_mcu = get_temperature()
            
            # 读取环境温湿度
            from hw.sht40 import read
            env_data = read()
            env_temp = env_data["temperature"] if isinstance(env_data, dict) else None
            env_hum = env_data["humidity"] if isinstance(env_data, dict) else None
            
            state = self.state_machine.get_current_state() if self.state_machine else "INIT"
            net_status = self.network_manager.get_status()
            
            info("系统状态 - 状态:{}, 内存:{}KB({:.0f}%), MCU温度:{}, 环境:{}°C/{}%, WiFi:{}, MQTT:{}", 
                 state, free_kb, percent_used, temp_mcu,
                 env_temp if env_temp is not None else "N/A",
                 env_hum if env_hum is not None else "N/A",
                 net_status['wifi'], net_status['mqtt'], 
                 module="MAIN")
            
            # 上报周期性指标到 MQTT
            try:
                try:
                    wifi_cfg = (self.config.get("wifi", {}) or {})
                    mqtt_cfg = (self.config.get("mqtt", {}) or {})
                    ntp_cfg = (self.config.get("ntp", {}) or {})
                    ble_cfg = (self.config.get("ble", {}) or {})
                    daemon_cfg = (self.config.get("daemon", {}) or {})

                    mqtt_keep_s = mqtt_cfg.get("keepalive")
                    mqtt_keep_ms = (int(mqtt_keep_s) * 1000) if mqtt_keep_s is not None else None

                    config_text = {
                        "mqtt_keepalive": format_duration_ms(mqtt_keep_ms) if mqtt_keep_ms is not None else "N/A",
                        "wifi_scan_timeout": format_duration_ms(wifi_cfg.get("scan_timeout_ms")) if wifi_cfg else "N/A",
                        "wifi_base_delay": format_duration_ms(wifi_cfg.get("base_delay_ms")) if wifi_cfg else "N/A",
                        "wifi_max_delay": format_duration_ms(wifi_cfg.get("max_delay_ms")) if wifi_cfg else "N/A",
                        "ntp_timeout": format_duration_ms(ntp_cfg.get("timeout")) if ntp_cfg else "N/A",
                        "ble_adv_interval": format_duration_ms(((ble_cfg.get("adv", {}) or {}).get("interval_ms"))) if ble_cfg else "N/A",
                        "wdt_timeout": format_duration_ms(daemon_cfg.get("wdt_timeout")) if daemon_cfg else "N/A",
                    }
                except Exception:
                    config_text = {}

                metrics = {
                    "uptime_ms": current_time,
                    "uptime_text": format_duration_ms(current_time),
                    "unix_s": self.network_manager.get_epoch_unix_s() if self.network_manager else None,
                    "state": state,
                    "config_text": config_text,
                    "mem": {
                        "free_kb": free_kb,
                        "percent": percent_used,
                    },
                    "mcu_temp_c": temp_mcu,
                    "env": {
                        "temperature": env_temp,
                        "humidity": env_hum,
                    },
                    "net": net_status,
                    # 诊断字段: 与配置只读展示对齐
                    "diag": {
                        "main_loop_delay_ms": (self.config.get("system", {}) or {}).get("main_loop_delay", 0),
                        "wdt_enabled": (self.config.get("daemon", {}) or {}).get("wdt_enabled", False),
                        "wdt_timeout_ms": (self.config.get("daemon", {}) or {}).get("wdt_timeout", 0),
                        
                        "loop_sleep_ms": 50,
                    }
                }
                if self.network_manager:
                    # 统一的 metrics 发布: device/<id>/state/metrics
                    try:
                        self.network_manager.ha.publish_metrics(metrics, retain=False, qos=0)
                    except Exception:
                        pass
                    # 分离的温湿度主题 -> 统一走 HA 助手发布
                    try:
                        self.network_manager.ha.publish_state(
                            temperature=env_temp if env_temp is not None else None,
                            humidity=env_hum if env_hum is not None else None,
                            retain=True,
                        )
                    except Exception:
                        pass
            except Exception:
                # 指标上报失败不影响主流程
                pass

def main():
    """主函数"""
    controller = MainController()
    asyncio.run(controller.run())


if __name__ == "__main__":
    main()
