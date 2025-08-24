# app/lib/async_runtime.py
"""
异步运行时管理器
职责: 
- 管理 uasyncio 事件循环的创建、运行和清理
- 提供任务注册、取消和监控接口
- 统一异步任务的错误处理和日志记录

设计边界: 
- 仅负责异步任务编排, 不包含具体业务逻辑
- 确保异步任务异常不会影响主事件循环
"""

import uasyncio as asyncio
from lib.logger import error, debug, warning


class AsyncRuntime:
    """异步运行时管理器"""
    
    def __init__(self):
        """初始化异步运行时"""
        self.loop = None
        self.tasks = {}  # 任务名称 -> Task 映射
        self.running = False
        
    def create_task(self, coro, name=None):
        """
        创建并注册异步任务
        
        Args:
            coro: 协程对象
            name: 任务名称, 用于标识和管理
            
        Returns:
            Task: asyncio.Task 对象
        """
        try:
            # 同名任务幂等: 若存在同名任务且未结束, 先取消旧任务, 避免并发重复执行
            if name and name in self.tasks:
                try:
                    old_task = self.tasks.get(name)
                    if old_task and not old_task.done():
                        old_task.cancel()
                        debug("取消已存在的同名异步任务以进行替换: {}", name, module="ASYNC")
                except Exception as _e:
                    # 取消失败不应阻断后续创建, 记录告警继续
                    warning("取消同名任务时发生异常, 将继续创建新任务: {} -> {}", name, _e, module="ASYNC")
            
            task = asyncio.create_task(coro)
            
            if name:
                self.tasks[name] = task
                debug("创建异步任务: {}", name, module="ASYNC")
                
            return task
            
        except Exception as e:
            error("创建异步任务失败 {}: {}", name or "unnamed", e, module="ASYNC")
            return None
            
    def cancel_task(self, name):
        """
        取消指定名称的任务
        
        Args:
            name: 任务名称
            
        Returns:
            bool: 取消成功返回 True
        """
        try:
            if name in self.tasks:
                task = self.tasks[name]
                if not task.done():
                    task.cancel()
                    debug("取消异步任务: {}", name, module="ASYNC")
                del self.tasks[name]
                return True
            return False
            
        except Exception as e:
            error("取消异步任务失败 {}: {}", name, e, module="ASYNC")
            return False
            
    def cancel_all_tasks(self):
        """取消所有注册的任务"""
        try:
            task_names = list(self.tasks.keys())
            for name in task_names:
                self.cancel_task(name)
            debug("已取消所有异步任务", module="ASYNC")
            
        except Exception as e:
            error("取消所有异步任务失败: {}", e, module="ASYNC")
            
    def get_task_status(self):
        """
        获取所有任务状态
        
        Returns:
            dict: 任务名称 -> 状态信息
        """
        status = {}
        try:
            for name, task in self.tasks.items():
                status[name] = {
                    "done": task.done(),
                    "cancelled": task.cancelled() if hasattr(task, 'cancelled') else False
                }
        except Exception as e:
            error("获取任务状态失败: {}", e, module="ASYNC")
            
        return status

    async def _cleanup(self):
        """清理异步运行时资源"""
        try:
            self.running = False
            
            # 取消所有任务
            self.cancel_all_tasks()
            
            # 等待短暂时间让任务清理
            await asyncio.sleep_ms(100)
            
            debug("异步运行时清理完成", module="ASYNC")
            
        except Exception as e:
            error("异步运行时清理失败: {}", e, module="ASYNC")


# 全局异步运行时实例
_async_runtime = None


def get_async_runtime():
    """获取全局异步运行时实例"""
    global _async_runtime
    if _async_runtime is None:
        _async_runtime = AsyncRuntime()
    return _async_runtime


def create_task(coro, name=None):
    """便捷函数: 创建异步任务"""
    runtime = get_async_runtime()
    return runtime.create_task(coro, name)


def cancel_task(name):
    """便捷函数: 取消异步任务"""
    runtime = get_async_runtime()
    return runtime.cancel_task(name)