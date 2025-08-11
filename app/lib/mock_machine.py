# mock_machine.py - 模拟MicroPython的machine模块用于测试
"""
模拟MicroPython的machine模块，用于在标准Python环境中测试
"""

import threading
import time

class Timer:
    """模拟MicroPython的Timer类"""
    
    PERIODIC = 1
    ONE_SHOT = 0
    
    def __init__(self, timer_id):
        self.timer_id = timer_id
        self.callback = None
        self.period = 0
        self.mode = self.ONE_SHOT
        self._thread = None
        self._running = False
    
    def init(self, period, mode, callback):
        """初始化定时器"""
        self.period = period / 1000.0  # 转换为秒
        self.mode = mode
        self.callback = callback
        self._start_timer()
    
    def _start_timer(self):
        """启动定时器线程"""
        if self._thread and self._thread.is_alive():
            self._running = False
            self._thread.join()
        
        self._running = True
        if self.mode == self.PERIODIC:
            self._thread = threading.Thread(target=self._periodic_callback)
        else:
            self._thread = threading.Thread(target=self._oneshot_callback)
        
        self._thread.daemon = True
        self._thread.start()
    
    def _periodic_callback(self):
        """周期性回调"""
        while self._running:
            time.sleep(self.period)
            if self._running and self.callback:
                try:
                    self.callback(None)
                except Exception as e:
                    print(f"Timer callback error: {e}")
    
    def _oneshot_callback(self):
        """单次回调"""
        time.sleep(self.period)
        if self._running and self.callback:
            try:
                self.callback(None)
            except Exception as e:
                print(f"Timer callback error: {e}")
    
    def deinit(self):
        """停止定时器"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()