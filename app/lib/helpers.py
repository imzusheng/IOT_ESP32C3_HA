# lib/utils/helpers.py
"""
辅助工具类
"""

import time

class Throttle:
    """节流器类，用于限制事件触发频率"""
    
    def __init__(self, interval_ms):
        """
        初始化节流器
        
        Args:
            interval_ms: 节流间隔时间（毫秒）
        """
        self.interval = interval_ms / 1000.0  # 转换为秒
        self.last_trigger_time = 0
    
    def should_trigger(self):
        """
        检查是否应该触发事件
        
        Returns:
            bool: True表示应该触发，False表示被节流
        """
        current_time = time.time()
        if current_time - self.last_trigger_time >= self.interval:
            self.last_trigger_time = current_time
            return True
        return False
    
    def is_throttled(self):
        """
        检查是否被节流（与should_trigger相反的逻辑）
        
        Returns:
            bool: True表示被节流，False表示可以触发
        """
        return not self.should_trigger()
    
    def reset(self):
        """
        重置节流器状态
        """
        self.last_trigger_time = 0