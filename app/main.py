# app/main.py
"""
ESP32C3 IoT 设备主程序
职责：
- 统一完成配置加载、日志初始化、事件总线、网络管理器与状态机的装配
- 驱动主循环：事件分发 → FSM 更新 → 网络循环 → 看门狗喂狗 → 周期性维护

架构关系：
- EventBus 作为系统消息中枢，FSM/NetworkManager/其他模块通过事件解耦
- FSM 负责系统状态演进与容错策略，NetworkManager 负责具体联网动作
- MainController 不直接耦合业务细节，仅协调整体生命周期

维护说明：
- 主循环默认 100ms 周期，可视需要在配置中抽象
- 统计输出与 GC 在 30s 周期执行，避免频繁抖动
"""

import utime as time
import gc
from lib.logger import info, warning, error, debug
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
        
        # 运行控制
        self.running = False
        self.last_loop_time = 0
        self.loop_interval = 100  # 100ms主循环间隔
        
        # 性能监控
        self.loop_count = 0
        self.last_stats_time = 0
        
    def initialize(self):
        """初始化系统"""
        try:
            info("=== ESP32C3系统启动 ===", module="MAIN")
            
            # 1. 加载配置
            from config import get_config
            self.config = get_config()
            info("配置加载完成", module="MAIN")
            
            # 2. 日志系统为零配置、全局可用，无需手动初始化
            info("日志系统准备就绪", module="MAIN")
            
            # 3. 初始化事件总线
            self.event_bus = EventBus()
            info("事件总线初始化完成", module="MAIN")
            
            # 4. 初始化网络管理器
            from net.network_manager import NetworkManager
            self.network_manager = NetworkManager(self.config, self.event_bus)
            info("网络管理器初始化完成", module="MAIN")
            
            # 5. 初始化状态机
            from fsm.core import FSM
            self.state_machine = FSM(
                self.event_bus, 
                self.config, 
                self.network_manager
            )
            info("状态机初始化完成", module="MAIN")
            
            # 6. 初始化LED
            self._init_led()
            
            info("=== 系统初始化完成 ===", module="MAIN")
            return True
            
        except Exception as e:
            error("系统初始化失败: {}", e, module="MAIN")
            return False
            
    def _init_led(self):
        """初始化LED"""
        try:
            from hw.led import init_led
            init_led()
            info("LED初始化完成", module="MAIN")
        except Exception as e:
            error("LED初始化失败: {}", e, module="MAIN")
            
    def run(self):
        """运行主循环"""
        if not self.initialize():
            error("系统初始化失败，无法启动", module="MAIN")
            return
            
        self.running = True
        self.last_loop_time = time.ticks_ms()
        
        info("=== 进入主循环 ===", module="MAIN")
        
        try:
            while self.running:
                self._main_loop()
                
        except KeyboardInterrupt:
            info("收到中断信号，正在关闭系统", module="MAIN")
        except Exception as e:
            error("主循环异常: {}", e, module="MAIN")
        finally:
            self._cleanup()
            
    def _main_loop(self):
        """主循环逻辑"""
        current_time = time.ticks_ms()
        
        # 控制循环频率
        elapsed = time.ticks_diff(current_time, self.last_loop_time)
        if elapsed < self.loop_interval:
            time.sleep_ms(self.loop_interval - elapsed)
            current_time = time.ticks_ms()
            
        self.last_loop_time = current_time
        self.loop_count += 1
        
        try:
            # 1. 更新事件总线
            self.event_bus.process_events()
            
            # 2. 更新状态机
            self.state_machine.update()
            
            # 3. 更新网络管理器
            self.network_manager.loop()
            
            # 4. 喂看门狗
            self.state_machine.feed_watchdog()
            
            # 5. 定期垃圾回收和统计
            self._periodic_maintenance(current_time)
            
        except Exception as e:
            error("主循环执行异常: {}", e, module="MAIN")
            
    def _periodic_maintenance(self, current_time):
        """定期维护任务"""
        # 每30秒执行一次
        if time.ticks_diff(current_time, self.last_stats_time) >= 30000:
            self.last_stats_time = current_time
            
            # 垃圾回收
            gc.collect()
            
            # 输出统计信息
            free_mem = gc.mem_free()
            state = self.state_machine.get_current_state()
            net_status = self.network_manager.get_status()
            
            info("系统状态 - 状态:{}, 内存:{}KB, 循环:{}, WiFi:{}, MQTT:{}", 
                 state, free_mem//1024, self.loop_count,
                 net_status['wifi'], net_status['mqtt'], 
                 module="MAIN")
                 
            self.loop_count = 0  # 重置循环计数
            
    def _cleanup(self):
        """清理资源"""
        info("正在清理系统资源", module="MAIN")
        
        try:
            # 停止状态机
            if self.state_machine:
                info("停止状态机", module="MAIN")
                
            # 断开网络连接
            if self.network_manager:
                self.network_manager.disconnect()
                info("网络连接已断开", module="MAIN")
                
            # 清理LED
            try:
                from hw.led import cleanup_led
                cleanup_led()
                info("LED已清理", module="MAIN")
            except:
                pass
                
            # 最终垃圾回收
            gc.collect()
            
            info("系统资源清理完成", module="MAIN")
            
        except Exception as e:
            error("清理资源时发生异常: {}", e, module="MAIN")
            
    def stop(self):
        """停止系统"""
        info("收到停止信号", module="MAIN")
        self.running = False
        
    def get_system_info(self):
        """获取系统信息"""
        try:
            return {
                "state": self.state_machine.get_current_state() if self.state_machine else "UNKNOWN",
                "network": self.network_manager.get_status() if self.network_manager else {},
                "memory": gc.mem_free(),
                "uptime": time.ticks_ms(),
                "loop_count": self.loop_count
            }
        except Exception as e:
            error("获取系统信息失败: {}", e, module="MAIN")
            return {}
            
    def force_network_reconnect(self):
        """强制网络重连"""
        if self.network_manager:
            return self.network_manager.force_reconnect()
        return False
        
    def force_state_change(self, state_name):
        """强制状态改变"""
        if self.state_machine:
            self.state_machine.force_state(state_name)


def main():
    """主函数"""
    controller = MainController()
    controller.run()


if __name__ == "__main__":
    main()
