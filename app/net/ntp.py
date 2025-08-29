# app/net/ntp.py
"""
NTP 时间同步管理器
职责:
- 执行一次性 NTP 时间同步并缓存同步状态
- 提供 is_synced()

设计边界:
- 不做内部重试与退避, 由 NetworkManager 统一处理
- 当固件不支持设置 ntptime.host 时优雅降级
"""

try:
    import ntptime
except ImportError:
    ntptime = None


class NtpManager:
    """提供最小可用的 NTP 同步能力与状态查询"""

    def __init__(self, config=None):
        self.config = config or {}
        self._ntp_synced = False

    def sync_time(self):
        """
        执行一次 NTP 时间同步
        Returns:
            bool: 成功 True, 失败 False
        Notes:
        - 仅尝试一次, 不在此处实现重试与退避
        - 实际重试与时序控制在 NetworkManager 中完成
        """
        if ntptime is None:
            return False

        # 支持新旧两种配置键: 优先 server, 其次 ntp_server, 最后默认池
        ntp_server = (
            self.config.get("server")
            or "pool.ntp.org"
        )

        # 尝试设置 NTP 服务器(部分端口可能不支持)
        try:
            if hasattr(ntptime, "host"):
                ntptime.host = ntp_server
        except Exception:
            # 不支持设置或设置失败时忽略
            pass

        # 设置时间(可能抛出异常)
        try:
            ntptime.settime()
            self._ntp_synced = True
            return True
        except Exception:
            return False

    def is_synced(self):
        """返回是否已完成 NTP 同步"""
        return self._ntp_synced
