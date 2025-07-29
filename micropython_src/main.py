# main.py
"""
主程序入口 - IoT ESP32C3 系统 (重构版本)

这个文件是整个IoT系统的核心控制器，重构后具有以下特点：
1. 事件驱动架构：所有模块通过事件总线通信
2. 配置驱动：所有配置通过config模块管理
3. 模块化设计：各模块独立，减少耦合
4. 错误隔离：单个模块失败不影响整体系统

系统架构：
- 事件总线：核心通信机制，连接所有模块
- 守护进程：负责硬件监控、看门狗、安全模式
- 异步任务：处理WiFi连接、NTP同步、LED效果
- 配置管理：集中管理所有系统配置
- 日志系统：事件驱动的日志记录和处理

设计原则：
- 事件驱动：模块间通过事件通信，避免直接依赖
- 配置驱动：避免硬编码，提高可维护性
- 稳定性优先：关键功能独立运行
- 异步非阻塞：避免单点阻塞影响系统
- 错误隔离：单个模块失败不影响整体
- 资源优化：合理使用内存和CPU资源
"""

import gc
import machine
import uasyncio as asyncio

# 导入项目模块
import config
import core  # 使用合并的核心模块
import utils
import daemon
from config import get_event_id, DEBUG, EV_PERFORMANCE_REPORT, EV_SYSTEM_HEARTBEAT, EV_LOW_MEMORY_WARNING, EV_SYSTEM_STARTING, EV_SYSTEM_STOPPED, EV_SYSTEM_SHUTTING_DOWN, EV_ASYNC_SYSTEM_STARTING, EV_ASYNC_TASKS_STARTED, EV_ASYNC_TASKS_CLEANUP_STARTED, EV_ASYNC_TASKS_CLEANUP_COMPLETED

# =============================================================================
# 温度优化配置 (合并自temp_optimization.py)
# =============================================================================

# 温度分级配置
TEMP_THRESHOLDS = {
    'normal': 35.0,      # 正常温度阈值
    'warning': 40.0,     # 警告温度阈值
    'critical': 45.0,    # 危险温度阈值
    'emergency': 50.0,   # 紧急温度阈值
}

# 不同温度级别的配置调整
TEMP_LEVEL_CONFIGS = {
    'normal': {
        'main_interval_ms': 5000,
        'monitor_interval_ms': 30000,
        'scheduler_interval_ms': 200,
        'pwm_freq': 60,
        'max_brightness': 20000,
        'led_interval_ms': 50,
        'wifi_check_interval_s': 30,
    },
    'warning': {
        'main_interval_ms': 8000,
        'monitor_interval_ms': 45000,
        'scheduler_interval_ms': 400,
        'pwm_freq': 40,
        'max_brightness': 15000,
        'led_interval_ms': 80,
        'wifi_check_interval_s': 45,
    },
    'critical': {
        'main_interval_ms': 10000,
        'monitor_interval_ms': 60000,
        'scheduler_interval_ms': 800,
        'pwm_freq': 30,
        'max_brightness': 8000,
        'led_interval_ms': 100,
        'wifi_check_interval_s': 60,
    },
    'emergency': {
        'main_interval_ms': 15000,
        'monitor_interval_ms': 120000,
        'scheduler_interval_ms': 1500,
        'pwm_freq': 20,
        'max_brightness': 3000,
        'led_interval_ms': 200,
        'wifi_check_interval_s': 300,
    }
}

def get_temperature_level(current_temp):
    """根据当前温度确定温度级别"""
    if current_temp >= TEMP_THRESHOLDS['emergency']:
        return 'emergency'
    elif current_temp >= TEMP_THRESHOLDS['critical']:
        return 'critical'
    elif current_temp >= TEMP_THRESHOLDS['warning']:
        return 'warning'
    else:
        return 'normal'

def get_optimized_config_for_temp(current_temp):
    """根据当前温度获取优化后的配置"""
    temp_level = get_temperature_level(current_temp)
    return TEMP_LEVEL_CONFIGS[temp_level].copy()

def check_and_optimize(current_temp):
    """检查温度并返回优化信息"""
    temp_level = get_temperature_level(current_temp)
    optimized_config = get_optimized_config_for_temp(current_temp)
    
    optimization_info = {
        'current_temp': current_temp,
        'temp_level': temp_level,
        'optimized_config': optimized_config,
        'recommendations': []
    }
    
    # 根据温度级别添加建议
    if temp_level == 'warning':
        optimization_info['recommendations'].extend([
            "降低LED亮度到75%",
            "延长监控间隔到45秒",
            "调度器间隔调整到400ms"
        ])
    elif temp_level == 'critical':
        optimization_info['recommendations'].extend([
            "降低LED亮度到40%",
            "延长监控间隔到60秒",
            "调度器间隔调整到800ms"
        ])
    elif temp_level == 'emergency':
        optimization_info['recommendations'].extend([
            "紧急降低LED亮度到15%",
            "延长监控间隔到120秒",
            "调度器间隔调整到1.5秒"
        ])
    
    return optimization_info

async def main_business_loop():
    """
    主业务循环 - 系统核心运行逻辑 (重构版本)
    
    这个函数是系统的心脏，重构后具有以下特点：
    1. 事件驱动：通过事件总线监听和发布系统事件
    2. 配置驱动：使用config模块获取循环参数
    3. 模块化：各功能独立，减少耦合
    4. 错误隔离：单个任务失败不影响整体循环
    
    主要功能：
    - 定期处理日志队列
    - 执行垃圾回收
    - 系统状态监控
    - 发布系统心跳事件
    - 错误恢复机制
    
    设计特点：
    - 异步非阻塞：不影响其他任务运行
    - 事件驱动：通过事件总线与其他模块通信
    - 配置驱动：循环间隔等参数从配置获取
    - 错误隔离：单个任务失败不影响整体循环
    - 资源管理：主动进行内存管理
    
    注意：
    - 这个循环会一直运行，直到系统关闭
    - 所有操作都包含异常处理
    - 通过事件总线发布系统状态
    """
    if DEBUG:
        print("\n[MAIN] 启动主业务循环...")
    
    # 从配置获取循环参数
    general_config = config.get_general_config()
    loop_interval = general_config.get('main_loop_interval', 5)
    gc_interval = general_config.get('gc_interval_loops', 20)
    status_check_interval = general_config.get('status_check_interval_loops', 12)
    
    loop_count = 0
    
    # 发布主循环启动事件
    core.publish(get_event_id('main_loop_started'))
    
    try:
        while True:
            loop_count += 1
            
            # 1. 处理日志队列（使用core模块的简化日志）
            try:
                # 简化的日志处理，由core模块自动管理
                pass
            except Exception as e:
                print(f"[MAIN] [ERROR] 日志处理失败: {e}")
                core.publish(get_event_id('log_critical'), message=f"日志处理失败: {e}")
            
            # 2. 定期状态报告和心跳
            if loop_count % status_check_interval == 0:
                 if DEBUG:
                     print(f"\n[MAIN] 系统运行正常，循环计数: {loop_count}")
                 core.publish(EV_SYSTEM_HEARTBEAT, loop_count=loop_count)
                 
                 # 获取并发布系统状态
                 try:
                     status = core.get_system_status()  # 使用core模块的系统状态
                     core.publish(get_event_id('system_status_check'), status=status, loop_count=loop_count)
                     
                     # 检查关键状态并发布相应事件
                     if not status.get('wifi_connected', False):
                         if DEBUG:
                             print("[MAIN] [WARNING] WiFi连接丢失")
                         core.publish(get_event_id('wifi_disconnected_detected'))
                         core.publish(get_event_id('log_warning'), message="WiFi连接丢失")
                     
                     # 简化时间检查（移除NTP依赖）
                     
                 except Exception as e:
                     print(f"[MAIN] [ERROR] 系统状态检查失败: {e}")
                     core.publish(get_event_id('log_critical'), message=f"系统状态检查失败: {e}")
            
            # 3. 定期垃圾回收
            if loop_count % gc_interval == 0:
                try:
                    gc.collect()
                    mem_info = core.get_memory_info()  # 使用core模块的内存信息
                    if DEBUG:
                        print(f"[MAIN] 执行垃圾回收，可用内存: {mem_info['free']} bytes")
                    
                    # 发布内存状态事件
                    core.publish(get_event_id('memory_status'), 
                                memory_info=mem_info, 
                                loop_count=loop_count)
                    
                    # 内存使用检查
                    low_memory_threshold = general_config.get('low_memory_threshold', 10000)
                    if mem_info['free'] < low_memory_threshold:
                        if DEBUG:
                            print(f"[MAIN] [WARNING] 内存不足: {mem_info['free']} bytes")
                        core.publish(EV_LOW_MEMORY_WARNING, free_bytes=mem_info['free'])
                        core.publish(get_event_id('log_warning'), message=f"内存不足: {mem_info['free']} bytes")
                        
                except Exception as e:
                    print(f"[MAIN] [ERROR] 垃圾回收失败: {e}")
                    core.publish(get_event_id('log_critical'), message=f"垃圾回收失败: {e}")
            
            # 使用异步睡眠而不是lightsleep，避免暂停看门狗定时器
            # lightsleep会暂停所有定时器，包括看门狗喂养定时器，导致看门狗超时
            if DEBUG:
                print(f"[MAIN] 主循环完成，等待 {loop_interval} 秒...")
            await asyncio.sleep(loop_interval)
            
            # 防止循环计数器溢出
            if loop_count >= 1000000:
                loop_count = 0
                core.publish(get_event_id('loop_counter_reset'))
            
    except asyncio.CancelledError:
        if DEBUG:
            print("\n[MAIN] 主业务循环已停止")
        core.publish(get_event_id('main_loop_stopped'))
    except Exception as e:
        print(f"\n[MAIN] [ERROR] 主业务循环异常: {e}")
        core.publish(get_event_id('log_critical'), message=f"主业务循环异常: {e}")

async def system_coordinator_task():
    """
    系统协调员任务：负责监听系统状态并应用优化策略
    
    这个任务实现了动态温度优化功能：
    1. 订阅守护进程的性能报告事件
    2. 根据温度变化应用优化策略
    3. 通过事件总线发布配置更新命令
    4. 协调各模块的功耗管理
    """
    if DEBUG:
        print("[COORDINATOR] 启动系统协调员任务...")
    
    # 订阅守护进程的性能报告事件
    def on_performance_report(**kwargs):
        temp = kwargs.get('temperature')
        if temp is not None:
            # 使用本地温度优化函数检查并获取优化配置
            optimization_info = check_and_optimize(temp)
            new_config = optimization_info['optimized_config']
            
            # 通过事件总线发布配置更新命令
            core.publish(get_event_id('config_update'), 
                        source='temp_optimizer', 
                        config=new_config,
                        temp_level=optimization_info['temp_level'])
            
            # 发布温度优化日志
            if optimization_info['recommendations']:
                recommendations_str = ', '.join(optimization_info['recommendations'])
                core.publish(get_event_id('log_info'), 
                            message=f"温度优化建议: {recommendations_str}")
    
    # 订阅性能报告事件
    core.subscribe(EV_PERFORMANCE_REPORT, on_performance_report)
    
    try:
        while True:
            # 系统协调员任务本身使用较长的休眠时间
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        if DEBUG:
            print("[COORDINATOR] 系统协调员任务已停止")
    except Exception as e:
        print(f"[COORDINATOR] [ERROR] 系统协调员任务异常: {e}")
        core.publish(get_event_id('log_critical'), message=f"系统协调员任务异常: {e}")

def start_critical_daemon():
    """
    启动关键系统守护进程 (重构版本)
    
    使用事件总线和配置管理启动守护进程：
    1. 初始化事件总线
    2. 加载系统配置
    3. 启动守护进程
    4. 发布系统启动事件
    
    返回:
        bool: 启动成功返回True，失败返回False
    """
    try:
        if DEBUG:
            print("[MAIN] 初始化事件总线...")
        core.init_event_bus()
        
        if DEBUG:
            print("[MAIN] 加载系统配置...")
        config.load_all_configs()
        
        if DEBUG:
            print("[MAIN] 启动守护进程...")
        daemon_result = daemon.start_critical_daemon()
        
        if daemon_result:
            if DEBUG:
                print("[MAIN] 守护进程启动成功")
            core.publish(get_event_id('daemon_started'))
            core.publish(get_event_id('log_info'), message="守护进程启动成功")
            return True
        else:
            if DEBUG:
                print("[MAIN] [ERROR] 守护进程启动失败")
            core.publish(get_event_id('daemon_start_failed'))
            core.publish(get_event_id('log_critical'), message="守护进程启动失败")
            return False
            
    except Exception as e:
        print(f"[MAIN] [ERROR] 守护进程初始化异常: {e}")
        try:
            core.publish(get_event_id('log_critical'), message=f"守护进程初始化异常: {e}")
        except:
            pass  # 如果事件总线也失败，至少保证程序不崩溃
        return False

def main():
    """
    主程序入口：启动守护进程和异步系统 (重构版本)
    
    重构后的启动流程：
    1. 初始化事件总线和配置系统
    2. 启动关键系统守护进程（硬件监控、看门狗）
    3. 启动异步任务系统（WiFi、NTP、LED、业务逻辑）
    4. 进入主循环直到系统停止
    
    设计特点：
    - 事件驱动：所有模块通过事件总线通信
    - 配置驱动：系统参数通过配置管理
    - 错误隔离：单个模块失败不影响整体系统
    - 优雅关闭：支持中断信号和异常处理
    """
    print("\n" + "="*60)
    print("         ESP32-C3 IoT系统启动 (重构版本)")
    print("="*60)
    
    # 启动关键系统守护进程
    if not start_critical_daemon():
        print("[CRITICAL] 守护进程启动失败！系统无法继续运行")
        return

    if DEBUG:
        print("[MAIN] 守护进程启动成功，开始初始化异步系统...")
    
    # 初始化日志系统
    try:
        if DEBUG:
            print("[MAIN] 初始化日志系统...")
        core.init_logger()
        core.publish(get_event_id('logger_initialized'))
        if DEBUG:
            print("[MAIN] 日志系统初始化成功")
    except Exception as e:
        print(f"[MAIN] [ERROR] 日志系统初始化失败: {e}")
        # 日志系统失败不应阻止系统启动
    
    # 初始化LED系统
    try:
        if DEBUG:
            print("[MAIN] 初始化LED系统...")
        if utils.init_leds():
            if DEBUG:
                print("[MAIN] LED系统初始化成功")
        else:
            if DEBUG:
                print("[MAIN] [WARNING] LED系统初始化失败")
    except Exception as e:
        print(f"[MAIN] [ERROR] LED系统初始化异常: {e}")
        # LED系统失败不应阻止系统启动
    
    # 发布系统启动事件
    core.publish(EV_SYSTEM_STARTING)
    core.publish(get_event_id('log_info'), message="系统启动中...")

    try:
        # 定义异步系统运行函数
        async def run_system():
            # 发布异步系统启动事件
            core.publish(EV_ASYNC_SYSTEM_STARTING)
            
            # 启动所有异步任务
            tasks = [
                asyncio.create_task(utils.start_all_tasks()),
                asyncio.create_task(main_business_loop()),
                asyncio.create_task(system_coordinator_task())
            ]
            
            # 发布任务启动完成事件
            core.publish(EV_ASYNC_TASKS_STARTED, task_count=len(tasks))
            core.publish(get_event_id('log_info'), message=f"启动了 {len(tasks)} 个异步任务")
            
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                print(f"[MAIN] [ERROR] 系统任务错误: {e}")
                core.publish(get_event_id('log_critical'), message=f"系统任务错误: {e}")
                core.publish(get_event_id('system_task_error'), error=str(e))
            finally:
                # 清理任务
                if DEBUG:
                    print("[MAIN] 正在清理异步任务...")
                core.publish(EV_ASYNC_TASKS_CLEANUP_STARTED)
                
                for i, task in enumerate(tasks):
                    if not task.done():
                        task.cancel()
                        if DEBUG:
                            print(f"[MAIN] 取消任务 {i+1}/{len(tasks)}")
                
                core.publish(EV_ASYNC_TASKS_CLEANUP_COMPLETED)
                core.publish(get_event_id('log_info'), message="异步任务清理完成")
        
        # 运行异步系统
        if DEBUG:
            print("[MAIN] 启动异步任务系统...")
        core.publish(get_event_id('log_info'), message="启动异步任务系统")
        asyncio.run(run_system())
        
    except KeyboardInterrupt:
        print("\n[MAIN] 收到中断信号，正在关闭系统...")
        core.publish(get_event_id('system_shutdown_requested'), reason="keyboard_interrupt")
        core.publish(get_event_id('log_info'), message="收到中断信号，正在关闭系统")
    except Exception as e:
        print(f"\n[MAIN] [ERROR] 系统运行错误: {e}")
        core.publish(get_event_id('system_error'), error=str(e))
        core.publish(get_event_id('log_critical'), message=f"系统运行错误: {e}")
    finally:
        # 发布系统关闭事件
        core.publish(EV_SYSTEM_SHUTTING_DOWN)
        
        # 最后处理日志队列
        try:
            core.process_log_queue()
        except Exception as e:
            print(f"[MAIN] [ERROR] 最终日志处理失败: {e}")
        
        if DEBUG:
            print("[MAIN] 系统已停止，守护进程继续运行")
        core.publish(EV_SYSTEM_STOPPED)
        
        # 执行垃圾回收
        gc.collect()
        if DEBUG:
            print("[MAIN] 最终垃圾回收完成")


if __name__ == "__main__":
    main()