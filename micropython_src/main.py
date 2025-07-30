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
from lib import config, core, daemon, ntp, temp_optimizer, wifi
from lib.config import (
    DEBUG,
    EV_ASYNC_SYSTEM_STARTING,
    EV_ASYNC_TASKS_CLEANUP_COMPLETED,
    EV_ASYNC_TASKS_CLEANUP_STARTED,
    EV_ASYNC_TASKS_STARTED,
    EV_LOW_MEMORY_WARNING,
    EV_PERFORMANCE_REPORT,
    EV_SYSTEM_HEARTBEAT,
    EV_SYSTEM_SHUTTING_DOWN,
    EV_SYSTEM_STARTING,
    EV_SYSTEM_STOPPED,
    get_event_id,
)
from lib.led import deinit_led, init_led, start_led_task, stop_led_task
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

# 导入项目模块


async def main_business_loop():
    """
    主业务循环 - 精简版本
    
    简化后的主要功能：
    - 发布系统心跳事件
    - 定期垃圾回收
    - 基本状态监控
    """
    if DEBUG:
        print("\n[MAIN] 启动主业务循环...")
    
    # 从配置获取循环参数
    general_config = config.get_general_config()
    loop_interval = general_config.get('main_loop_interval', 5)
    gc_interval = general_config.get('gc_interval_loops', 20)
    
    loop_count = 0
    core.publish(get_event_id('main_loop_started'))
    
    try:
        while True:
            loop_count += 1
            
            # 发布系统心跳
            if loop_count % 12 == 0:  # 每12个循环发布一次心跳
                core.publish(EV_SYSTEM_HEARTBEAT, loop_count=loop_count)
                if DEBUG:
                    print(f"[MAIN] 系统心跳，循环计数: {loop_count}")
            
            # 定期垃圾回收
            if loop_count % gc_interval == 0:
                try:
                    gc.collect()
                    mem_info = core.get_memory_info()
                    if DEBUG:
                        print(f"[MAIN] 垃圾回收完成，可用内存: {mem_info['free']} bytes")
                    
                    # 内存不足检查
                    if mem_info['free'] < 10000:
                        core.publish(EV_LOW_MEMORY_WARNING, free_bytes=mem_info['free'])
                        
                except Exception as e:
                    print(f"[MAIN] [ERROR] 垃圾回收失败: {e}")
            
            await asyncio.sleep(loop_interval)
            
            # 防止循环计数器溢出
            if loop_count >= 1000000:
                loop_count = 0
            
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
            # 使用温度优化器模块进行优化
            temp_optimizer.optimize_by_temperature(temp)
    
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
        # 事件总线自动初始化
        
        if DEBUG:
            print("[MAIN] 加载系统配置...")
        try:
            config.load_all_configs()
        except config.ConfigFileNotFoundError as e:
            print(f"[MAIN] [CRITICAL] {e}")
            print("[MAIN] [CRITICAL] 请确保 config.json 文件存在并包含所有必要的配置项")
            print("[MAIN] [CRITICAL] 参考现有的 config.json 文件格式创建配置")
            return False
        except (config.ConfigLoadError, KeyError) as e:
            print(f"[MAIN] [CRITICAL] 配置加载失败: {e}")
            print("[MAIN] [CRITICAL] 请检查 config.json 文件格式是否正确")
            return False
        
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

def clear_restart_counter():
    """
    清除重启计数器（系统正常启动后调用）
    """
    try:
        import os
        restart_count_file = '/restart_count.txt'
        if restart_count_file in os.listdir('/'):
            os.remove(restart_count_file)
            if DEBUG:
                print("[MAIN] 重启计数器已清除")
            core.publish(get_event_id('log_info'), message="重启计数器已清除")
    except Exception as e:
        if DEBUG:
            print(f"[MAIN] [WARNING] 清除重启计数器失败: {e}")
        core.publish(get_event_id('log_warning'), message=f"清除重启计数器失败: {e}")

def main():
    """
    主程序入口：启动守护进程和异步系统 (重构版本)
    
    重构后的启动流程：
    1. 初始化事件总线和配置系统
    2. 启动关键系统守护进程（硬件监控、看门狗）
    3. 清除重启计数器（防止无限重启循环）
    4. 启动异步任务系统（WiFi、NTP、LED、业务逻辑）
    5. 进入主循环直到系统停止
    
    设计特点：
    - 事件驱动：所有模块通过事件总线通信
    - 配置驱动：系统参数通过配置管理
    - 错误隔离：单个模块失败不影响整体系统
    - 优雅关闭：支持中断信号和异常处理
    - 重启保护：防止无限重启循环
    """
    print("\n" + "="*60)
    print("         ESP32-C3 IoT系统启动 (重构版本)")
    print("="*60)
    
    # 启动关键系统守护进程
    if not start_critical_daemon():
        print("[CRITICAL] 守护进程启动失败！系统无法继续运行")
        return
    
    # 清除重启计数器（系统正常启动后）
    clear_restart_counter()

    if DEBUG:
        print("[MAIN] 守护进程启动成功，开始初始化异步系统...")
    
    # 日志系统通过事件总线自动初始化
    if DEBUG:
        print("[MAIN] 日志系统已就绪")
    core.publish(get_event_id('logger_initialized'))
    
    # 初始化LED系统
    try:
        if DEBUG:
            print("[MAIN] 初始化LED系统...")
        if init_led():
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
            
            # 启动LED异步任务
            start_led_task()
            
            # 启动所有异步任务
            tasks = [
                asyncio.create_task(wifi.wifi_task()),
                asyncio.create_task(ntp.ntp_task()),
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
                
                # 停止LED任务
                stop_led_task()
                deinit_led()
                
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
        
        # 日志由事件系统自动处理
        if DEBUG:
            print("[MAIN] 日志系统自动处理中...")
        
        if DEBUG:
            print("[MAIN] 系统已停止，守护进程继续运行")
        core.publish(EV_SYSTEM_STOPPED)
        
        # 执行垃圾回收
        gc.collect()
        if DEBUG:
            print("[MAIN] 最终垃圾回收完成")


if __name__ == "__main__":
    main()