# app/net/ntp.py
# 简化版NTP时间同步管理器, 只提供基本的NTP操作功能
import utime as time
from lib.logger import debug, info, warning, error

try:
    import ntptime
except ImportError:
    ntptime = None

class NtpManager:
    """
    NTP时间同步管理器
    
    只提供基本的NTP时间同步功能:
    - 执行NTP时间同步
    - 检查同步状态
    """
    
    def __init__(self, config=None):
        """
        初始化NTP管理器
        :param config: NTP配置字典-可选
        """
        self.config = config or {}
        # 移除logger实例, 直接使用全局日志函数
        self._ntp_synced = False
        self._last_sync_time = 0
        self._sync_duration = 0
    
    def sync_time(self):
        """
        执行NTP时间同步
        
        Returns:
            bool: 同步成功返回True, 失败返回False
        """
        if ntptime is None:
            warning("NTP模块不可用", module="NET")
            return False
        
        # 通过配置允许自定义NTP服务器, 默认使用阿里云NTP池
        ntp_server = self.config.get('ntp_server', 'ntp1.aliyun.com')
        max_attempts = int(self.config.get('ntp_max_attempts', 3))
        retry_interval = int(self.config.get('ntp_retry_interval', 2))  # 秒
        
        try:
            if hasattr(ntptime, 'host'):
                ntptime.host = ntp_server  # 设置NTP服务器
        except Exception:
            # 某些端口的ntptime不支持设置host, 忽略
            pass
        
        start_time = time.ticks_ms()
        
        try:
            # 只尝试一次, 让外部的NetworkManager处理重试和退避
            ntptime.settime()
            # 成功
            self._ntp_synced = True
            self._last_sync_time = time.ticks_ms()
            self._sync_duration = time.ticks_diff(time.ticks_ms(), start_time)
            
            info("NTP时间同步成功，耗时: {}ms", self._sync_duration, module="NET")
            return True
            
        except Exception as e:
            debug("NTP时间同步失败: {}", e, module="NET")
            # 直接返回失败, 让外部的NetworkManager处理重试
            return False
    
    def is_synced(self):
        """
        检查NTP是否已同步
        
        Returns:
            bool: 已同步返回True
        """
        return self._ntp_synced
    
  