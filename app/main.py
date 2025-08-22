# app/main.py
"""
ESP32C3 IoT 设备主程序
职责：
- 统一完成配置加载、日志初始化、看门狗初始化、事件总线、网络管理器与状态机的装配
- 驱动主循环：事件分发 → FSM 更新 → 网络循环 → 看门狗喂狗 → 周期性维护

架构关系：
- EventBus 作为系统消息中枢, FSM/NetworkManager/其他模块通过事件解耦合
- FSM 负责系统状态演进与容错策略, NetworkManager 负责具体联网动作
- MainController 负责看门狗的初始化和喂狗，确保统一管理
"""

import utime as time
import gc
import machine
import uasyncio as asyncio
from lib.logger import info, error, debug
from config import get_config
from lib.lock.event_bus import EventBus


class MainController:
    """
    主控制器
    统一管理系统初始化、状态机和网络连接
    """
    
    def __init__(self):
        """初始化主控制器"""
        self.config = None
        self.event_bus = None
        self.state_machine = None
        self.network_manager = None
        self.wdt = None
        
        # 维护任务定时
        self.last_stats_time = 0
 
    def _init_led(self):
        """初始化LED"""
        try:
            from hw.led import play
            # LED 控制器采用硬件定时器驱动，完全独立于主循环
            # 初始进入 blink 模式，表示正在初始化
            play('blink')
        except Exception as e:
            error("初始化LED失败: {}", e, module="MAIN")

    def _init_watchdog(self):
        """初始化硬件看门狗
        说明：
        - 从配置读取 wdt_enabled 与 wdt_timeout 默认启用且 120000ms
        - 仅在启用时创建 machine.WDT 实例
        """
        try:
            enabled = get_config('daemon', 'wdt_enabled', True)
            timeout = int(get_config('daemon', 'wdt_timeout', 120000))
            if enabled:
                self.wdt = machine.WDT(timeout=timeout)
            else:
                self.wdt = None
        except Exception as e:
            self.wdt = None
            error("初始化看门狗失败: {}", e, module="MAIN")

    def initialize(self):
        """初始化系统"""
        try:
            info("=== ESP32C3系统启动 ===", module="MAIN")
            
            self.config = get_config()
            info("配置加载完成", module="MAIN")
            
            # 初始化看门狗
            self._init_watchdog()
            
            # 初始化LED
            self._init_led()
            
            # 初始化事件总线
            self.event_bus = EventBus()
            debug("事件总线初始化完成", module="MAIN")
            
            # 初始化网络管理器
            from net.network_manager import NetworkManager
            self.network_manager = NetworkManager(self.config, self.event_bus)
            debug("网络管理器初始化完成", module="MAIN")
            
            # 初始化状态机
            from fsm.core import FSM
            self.state_machine = FSM(
                self.event_bus, 
                self.config, 
                self.network_manager
            )
            debug("状态机初始化完成", module="MAIN")
            
            info("=== 系统初始化完成 ===", module="MAIN")
            return True
            
        except Exception as e:
            error("系统初始化失败: {}", e, module="MAIN")
            return False
            
    async def run(self):
        """异步主循环入口"""
        if not self.initialize():
            error("系统初始化失败, 无法启动", module="MAIN")
            return
        try:
            await self._main_loop_async()
        except asyncio.CancelledError:
            info("主循环任务取消", module="MAIN")
        except Exception as e:
            error("主循环异常: {}", e, module="MAIN")

    async def _main_loop_async(self):
        """主控制循环 (异步)
        职责：
        - 更新状态机
        - 定期喂看门狗
        - 周期性维护任务(内存回收、状态上报)
        """
        info("进入主控制循环(异步)", module="MAIN")
        # 采用固定周期运行，避免对CPU占用过高
        loop_delay = get_config('system', 'main_loop_delay', 100)
        
        while True:
            try:
                # 状态机更新
                if self.state_machine:
                    self.state_machine.update()
                
                # 喂看门狗保持在主循环中，避免掩盖死锁
                if self.wdt:
                    self.wdt.feed()

                await asyncio.sleep_ms(loop_delay)
            except Exception as e:
                error("主循环异常: {}", e, module="MAIN")
                await asyncio.sleep_ms(loop_delay)
            # 6. 维护
            current_time = time.ticks_ms()
            self._periodic_maintenance(current_time)
        
    def _periodic_maintenance(self, current_time):
        """定期维护任务"""
        # 每60秒执行一次
        if time.ticks_diff(current_time, self.last_stats_time) >= 60000 or self.last_stats_time == 0:
            self.last_stats_time = current_time
            
            # 垃圾回收
            gc.collect()
            
            # 输出统计信息(移除性能显示)
            from utils.helpers import check_memory, get_temperature
            mem = check_memory()
            free_kb = mem.get("free_kb", gc.mem_free() // 1024)
            percent_used = mem.get("percent", 0)
            
            # 读取MCU内部温度
            temp = get_temperature()
            
            # 读取环境温湿度
            from hw.sht40 import read
            env_data = read()
            
            state = self.state_machine.get_current_state()
            net_status = self.network_manager.get_status()
            
            info("系统状态 - 状态:{}, 内存:{}KB({:.0f}%), 温度:{}, 环境:{}°C/{}%, WiFi:{}, MQTT:{}", 
                 state, free_kb, percent_used, temp,
                 env_data["temperature"] if env_data["temperature"] is not None else "N/A",
                 env_data["humidity"] if env_data["humidity"] is not None else "N/A",
                 net_status['wifi'], net_status['mqtt'], 
                 module="MAIN")

def main():
    """主函数"""
    controller = MainController()
    asyncio.run(controller.run())


if __name__ == "__main__":
    main()
