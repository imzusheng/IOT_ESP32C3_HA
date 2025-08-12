# app/net/ntp.py
# 简化版NTP时间同步管理器，只提供基本的NTP操作功能
import utime as time
from lib.logger import get_global_logger

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
        self.logger = get_global_logger()
        self._ntp_synced = False
    
    def sync_time(self):
        """
        执行NTP时间同步
        
        Returns:
            bool: 同步成功返回True, 失败返回False
        """
        if ntptime is None:
            self.logger.warning("NTP模块不可用，跳过时间同步", module="NTP")
            return False
        
        # 通过配置允许自定义NTP服务器，默认使用阿里云NTP池
        ntp_server = self.config.get('ntp_server', 'ntp1.aliyun.com')
        max_attempts = int(self.config.get('ntp_max_attempts', 3))
        retry_interval = int(self.config.get('ntp_retry_interval', 2))  # 秒
        
        try:
            if hasattr(ntptime, 'host'):
                ntptime.host = ntp_server  # 设置NTP服务器
        except Exception:
            # 某些端口的ntptime不支持设置host，忽略
            pass
        
        self.logger.info("NTP同步开始 - 服务器={}", ntp_server, module="NTP")
        
        try:
            for i in range(max_attempts):
                try:
                    # ntptime.settime() 是一个阻塞操作
                    ntptime.settime()
                    # 成功
                    self._ntp_synced = True
                    timestamp = time.time()
                    
                    self.logger.info("NTP同步成功 - 服务器={}, 时间戳={}",
                                   ntp_server, timestamp, module="NTP")
                    return True
                    
                except Exception as e:
                    self.logger.warning("NTP同步失败, 尝试 {}/{}: {}", i + 1, max_attempts, str(e), module="NTP")
                    if i < max_attempts - 1:
                        time.sleep(retry_interval)
            
            # 所有尝试都失败
            return False
            
        except Exception as e:
            self.logger.error("NTP同步异常: {}", e, module="NTP")
            return False
    
    def is_synced(self):
        """
        检查NTP是否已同步
        
        Returns:
            bool: 已同步返回True
        """
        return self._ntp_synced
    
  