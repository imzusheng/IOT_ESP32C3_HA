# app/net/modules/retry_manager.py
"""重试管理模块"""

import utime as time
from lib.logger import debug, info, warning, error

class RetryManager:
    """重试管理器 - 负责连接重试逻辑和状态管理"""
    
    def __init__(self, config=None):
        """
        初始化重试管理器
        :param config: 连接配置字典
        """
        self.config = config or {}
        
        # 重试配置
        self.max_retries = self.config.get('max_retries', 3)
        self.base_retry_delay = self.config.get('base_retry_delay', 1000)
        self.max_retry_delay = 30000
        
        # 重试状态
        self.retry_count = 0
        self.last_retry_time = 0
    
    def get_retry_delay(self):
        """获取重试延迟时间"""
        if self.retry_count == 0:
            return 0
            
        # 指数退避: 2^(retry_count-1) * base_delay, 最大不超过max_retry_delay
        delay = min(self.base_retry_delay * (2 ** (self.retry_count - 1)), self.max_retry_delay)
        return delay
    
    def should_retry(self):
        """检查是否应该重试"""
        return self.retry_count < self.max_retries
    
    def is_ready_to_retry(self):
        """检查是否准备好重试"""
        if not self.should_retry():
            return False
            
        if self.retry_count == 0:
            return True
            
        next_retry_time = self.last_retry_time + self.get_retry_delay()
        return time.ticks_diff(time.ticks_ms(), next_retry_time) >= 0
    
    def record_attempt(self):
        """记录一次重试尝试"""
        self.retry_count += 1
        self.last_retry_time = time.ticks_ms()
        
        info("重试尝试 {}/{}", self.retry_count, self.max_retries, module="NET")
    
    def record_success(self):
        """记录成功"""
        old_count = self.retry_count
        self.reset()
        
        if old_count > 0:
            info("重试成功 (之前尝试{}次)", old_count, module="NET")
    
    def reset(self):
        """重置重试状态"""
        self.retry_count = 0
        self.last_retry_time = 0
    
    def get_retry_count(self):
        """获取当前重试次数"""
        return self.retry_count
    
    def get_retry_status(self):
        """获取重试状态信息"""
        return {
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'should_retry': self.should_retry(),
            'ready_to_retry': self.is_ready_to_retry(),
            'next_retry_delay': self.get_retry_delay() if self.should_retry() else 0
        }