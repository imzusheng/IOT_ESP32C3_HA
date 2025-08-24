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
from utils import check_memory, get_temperature




class MainController:
    """主控制器"""
    def __init__(self):
        self.config = get_config()
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
    
    def _emit_system_error(self, where, err):
        try:
            error("系统异常@{}: {}", where, err, module="MAIN")
        except Exception:
            pass

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
                    pass
                
                # 看门狗喂狗
                try:
                    if getattr(self, "wdt", None):
                        self.wdt.feed()
                except Exception:
                    pass
                
                # 定期维护
                self._periodic_maintenance(current_time)
                
                await asyncio.sleep_ms(50)
        except Exception as e:
            self._emit_system_error("main.run", e)

    def _periodic_maintenance(self, current_time):
        """定期维护任务"""
        # 每60秒执行一次
        if time.ticks_diff(current_time, self.last_stats_time) >= 60000 or self.last_stats_time == 0:
            self.last_stats_time = current_time
            
            # 垃圾回收
            gc.collect()
            
            # 输出统计信息(移除性能显示)
            mem = check_memory()
            free_kb = mem.get("free_kb", gc.mem_free() // 1024)
            percent_used = mem.get("percent", 0)
            
            # 读取MCU内部温度
            temp = get_temperature()
            
            # 读取环境温湿度
            from hw.sht40 import read
            env_data = read()
            
            state = self.state_machine.get_current_state() if self.state_machine else "INIT"
            net_status = self.network_manager.get_status()
            
            info("系统状态 - 状态:{}, 内存:{}KB({:.0f}%), 温度:{}, 环境:{}°C/{}%, WiFi:{}, MQTT:{}", 
                 state, free_kb, percent_used, temp,
                 env_data["temperature"] if env_data["temperature"] is not None else "N/A",
                 env_data["humidity"] if env_data["humidity"] is not None else "N/A",
                 net_status['wifi'], net_status['mqtt'], 
                 module="MAIN")
            
            # 上报周期性指标到 MQTT, 默认以 JSON 格式
            try:
                payload = {
                    # 设备运行时长(毫秒)
                    "uptime_ms": current_time,
                    # 若已完成NTP同步, 附加当前 1970-based UNIX 秒; 否则为 None
                    "unix_s": self.network_manager.get_epoch_unix_s() if self.network_manager else None,
                    "state": state,
                    "mem": {
                        "free_kb": free_kb,
                        "percent": percent_used,
                    },
                    "temp_c": temp,
                    "env": {
                        "temperature": env_data.get("temperature") if isinstance(env_data, dict) else None,
                        "humidity": env_data.get("humidity") if isinstance(env_data, dict) else None,
                    },
                    "net": net_status,
                }
                # 使用包含设备ID的标准主题 device/<client_id>/metrics
                if self.network_manager:
                    topic = self.network_manager.get_device_topic("metrics")
                    self.network_manager.mqtt_publish(topic, payload, retain=False, qos=0)
            except Exception:
                # 指标上报失败不影响主流程
                pass

def main():
    """主函数"""
    controller = MainController()
    asyncio.run(controller.run())


if __name__ == "__main__":
    main()
