"""main.py - 依赖注入容器和系统启动"""

import utime as time
import machine

# 1. 导入所有类
from config import get_config
from lib.lock.event_bus import EventBus
from lib.logger import info, warn, debug, error
from fsm.core import create_state_machine
from net import NetworkManager
from hw.led import play as led_play, cleanup as led_cleanup

class MainController:
    """主控制器 - 负责系统初始化和事件订阅"""
    
    def __init__(self, config):
        self.config = config
        
        self.event_bus = EventBus()
        debug("EventBus初始化完成", module="Main")

        self.network_manager = NetworkManager(self.event_bus, config)
        debug("NetworkManager初始化完成", module="Main")

        # LED已重构为开箱即用模式，无需实例化
        debug("LED已准备就绪（开箱即用模式）", module="Main")
        
        # 创建状态机
        self.state_machine = create_state_machine(
            config=self.config,
            event_bus=self.event_bus,
            network_manager=self.network_manager
        )
        debug("状态机初始化完成", module="Main")
  
    def start_system(self):
        """启动系统 - 基于diff时间的主循环"""
        info("开始启动系统...", module="Main")
        try:
            main_loop_delay = self.config.get('system', {}).get('main_loop_delay', 50) 
            
            # 持续运行，直到收到关机信号
            last_stats_time = time.ticks_ms()
            
            while self.state_machine.get_current_state() != "SHUTDOWN":
                
                # 固定循环周期控制
                loop_start_time = time.ticks_ms()
                
                # 驱动EventBus
                self.event_bus.process_events()
                
                # 驱动状态机
                self.state_machine.update()
                
                # 喂看门狗
                self.state_machine.feed_watchdog()
                
                # 定期输出调试信息
                current_time = time.ticks_ms()
                if time.ticks_diff(current_time, last_stats_time) >= 10000:
                    debug("主循环运行中... 当前状态: {}", 
                          self.state_machine.get_current_state(), module="Main")
                    last_stats_time = current_time
                
                # 计算任务执行时间，确保固定循环周期
                elapsed_time = time.ticks_diff(time.ticks_ms(), loop_start_time)
                if elapsed_time < main_loop_delay:
                    # 如果任务执行时间小于设定周期，休眠剩余时间
                    remaining_time = main_loop_delay - elapsed_time
                    time.sleep_ms(remaining_time)
                else:
                    # 如果任务执行时间超过设定周期，记录警告
                    warn("主循环执行超时: {}ms > {}ms", elapsed_time, main_loop_delay, module="Main")
            
            # 如果到达这里，说明系统进入了SHUTDOWN状态
            info("系统已进入关机状态", module="Main")
            
        except KeyboardInterrupt:
            info("用户中断，正在关闭", module="Main")
            self.cleanup()
        except Exception as e:
            error(f"致命错误: {e}", module="Main")
            self.cleanup()
            # 系统重启
            machine.reset()
    
    def cleanup(self):
        """清理资源"""
        try:
            info("开始清理过程", module="Main")
            
            # 停止状态机
            if hasattr(self, 'state_machine') and self.state_machine:
                self.state_machine.force_state("SHUTDOWN")
            
            # 清理LED
            led_cleanup()
            
            # 断开网络连接
            if hasattr(self, 'network_manager') and self.network_manager:
                self.network_manager.disconnect_all()
            
            # 保存缓存
            
            info("清理完成", module="Main")
        except Exception as e:
            error(f"清理失败: {e}", module="Main")

def main():
    """主函数 - 系统入口点"""
    
    # 加载配置
    config = get_config()

    # 创建主控制器
    main_controller = MainController(config)
    
    # 启动系统
    main_controller.start_system()

if __name__ == "__main__":
    main()