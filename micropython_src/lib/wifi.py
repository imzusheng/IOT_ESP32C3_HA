# wifi.py
"""
WiFi管理模块

从utils.py中分离出来的WiFi连接管理功能，提供：
- WiFi连接状态管理
- 网络扫描和连接
- 状态机驱动的连接流程
- 事件驱动的状态通知

重构后采用依赖注入模式：
- WifiManager类接收event_bus和config作为依赖
- 避免直接导入core和config模块
- 提高模块的可测试性和独立性
"""

try:
    import network
except ImportError:
    network = None
import time
try:
    import esp32
except ImportError:
    esp32 = None
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
import gc
from .config import get_event_id, DEBUG

# WiFi状态机枚举 - MicroPython兼容版本
class WifiState:
    """WiFi连接状态机的状态定义 - 使用类常量替代Enum"""
    DISCONNECTED = 1  # 未连接状态
    SCANNING = 2      # 扫描网络状态
    CONNECTING = 3    # 正在连接状态
    CONNECTED = 4     # 已连接状态
    RETRY_WAIT = 5    # 重试等待状态

    # 状态名称映射
    _STATE_NAMES = {
        1: 'DISCONNECTED',
        2: 'SCANNING',
        3: 'CONNECTING',
        4: 'CONNECTED',
        5: 'RETRY_WAIT'
    }

    @classmethod
    def get_name(cls, state_value):
        """获取状态名称"""
        return cls._STATE_NAMES.get(state_value, f'UNKNOWN({state_value})')

class WifiManager:
    """WiFi管理器类 - 采用依赖注入模式"""

    def __init__(self, event_bus, wifi_configs, connect_timeout_s, 
                 wifi_check_interval_s, retry_interval_s):
        """
        初始化WiFi管理器

        Args:
            event_bus: 事件总线实例，用于发布事件
            wifi_configs: WiFi配置列表
            connect_timeout_s: 连接超时时间（秒）
            wifi_check_interval_s: WiFi状态检查间隔（秒）
            retry_interval_s: 重试间隔时间（秒）
        """
        self.event_bus = event_bus
        self.wifi_configs = wifi_configs
        self.connect_timeout_s = connect_timeout_s
        self.retry_interval_s = retry_interval_s

        # 订阅配置更新事件
        self.event_bus.subscribe(get_event_id('config_update'), self._on_config_update)

        # 实例状态变量
        self._wifi_connected = False
        self._wifi_check_interval_s = wifi_check_interval_s

    def _on_config_update(self, **kwargs):
        """处理配置更新事件"""
        changed_sections = kwargs.get('changed', [])
        new_config = kwargs.get('new_config', {})
        source = kwargs.get('source', 'config_reload')

        # 检查是否有WiFi相关的配置变更
        if 'wifi' in changed_sections or source == 'temp_optimizer':
            if DEBUG:
                print("[WiFi] 收到配置更新，来源:", source)

            # 处理温度优化配置
            if source == 'temp_optimizer':
                temp_level = kwargs.get('temp_level', 'normal')
                if DEBUG:
                    print("[WiFi] 温度优化级别:", temp_level)

                # 更新WiFi检查间隔
                if 'wifi_check_interval_s' in new_config:
                    self._wifi_check_interval_s = max(30, new_config['wifi_check_interval_s'])
                    if DEBUG:
                        print("[WiFi] 更新连接检查间隔为:", self._wifi_check_interval_s, "秒")

            # 处理WiFi配置变更
            elif 'wifi' in changed_sections:
                # 更新WiFi配置
                if 'wifi' in new_config:
                    self.wifi_configs = new_config['wifi'].get('configs', [])
                if DEBUG:
                    print("[WiFi] WiFi配置已更新，将在下次连接时生效")

            # 配置更新后进行垃圾回收
            gc.collect()

    async def scan_available_networks(self):
        """扫描可用的WiFi网络 - 异步版本"""
        wlan = network.WLAN(network.STA_IF)
        if not wlan.active():
            wlan.active(True)
            await asyncio.sleep_ms(1000)

        print("[WiFi] 正在扫描可用网络...")
        try:
            networks = wlan.scan()
            if networks:
                available_ssids = []
                for net in networks:
                    try:
                        ssid = net[0].decode('utf-8')
                        available_ssids.append(ssid)
                    except:
                        continue
                print("[WiFi] 发现", len(available_ssids), "个网络")
                return available_ssids
            else:
                print("[WiFi] 扫描结果为空")
                return []
        except Exception as e:
            print("[WiFi] [ERROR] 扫描网络失败:", str(e))
            return []
        finally:
            gc.collect()

    async def scan_available_networks_for_config(self):
        """扫描并返回配置中可用的网络"""
        available_networks = await self.scan_available_networks()
        if not available_networks:
            return []

        # 返回配置中可用的网络
        available_configs = []
        for config in self.wifi_configs:
            if config["ssid"] in available_networks:
                available_configs.append(config)

        return available_configs

    async def _wait_for_connection(self, wlan, ssid):
        """内部辅助函数：等待WiFi连接完成"""
        start_time = time.time()
        blink_count = 0

        while not wlan.isconnected():
            if time.time() - start_time > self.connect_timeout_s:
                error_msg = f"连接 {ssid} 超时"
                print(f"\n[WiFi] [ERROR] {error_msg}！")
                self.event_bus.publish(get_event_id('wifi_timeout'), ssid=ssid)
                return False

            # 每2秒发布连接中事件（用于LED闪烁）
            blink_count += 1
            if blink_count % 40 == 0:  # 50ms * 40 = 2秒
                self.event_bus.publish(get_event_id('wifi_connecting_blink'))

            await asyncio.sleep_ms(50)

        return True

    async def connect_wifi_attempt(self, wifi_configs=None):
        """尝试连接WiFi网络（支持多个网络尝试）"""
        if wifi_configs is None:
            wifi_configs = self.wifi_configs

        if not wifi_configs:
            return False

        wlan = network.WLAN(network.STA_IF)
        if not wlan.active():
            wlan.active(True)

        # 尝试连接所有可用网络
        for config in wifi_configs:
            ssid = config["ssid"]
            password = config["password"]

            print(f"[WiFi] 尝试连接到: {ssid}")
            self.event_bus.publish(get_event_id('wifi_trying'), ssid=ssid)

            try:
                # 断开之前的连接
                if wlan.isconnected():
                    wlan.disconnect()
                    await asyncio.sleep_ms(500)

                # 开始连接过程
                wlan.connect(ssid, password)

                if await self._wait_for_connection(wlan, ssid):
                    # 连接成功处理
                    ip_info = wlan.ifconfig()
                    ip = ip_info[0]
                    print(f"\n[WiFi] [SUCCESS] 成功连接到: {ssid}")
                    print(f"[WiFi] IP地址: {ip}")
                    self._wifi_connected = True
                    self.event_bus.publish(get_event_id('wifi_connected'), ssid=ssid, ip=ip, reconnect=True)
                    self.event_bus.publish(get_event_id('log_info'), message=f"WiFi连接成功: {ssid} ({ip})")
                    return True
                else:
                    error_msg = f"连接 {ssid} 超时"
                    print(f"[WiFi] [WARNING] {error_msg}")
                    self.event_bus.publish(get_event_id('wifi_error'), ssid=ssid, error=error_msg)
                    continue

            except Exception as e:
                error_msg = f"连接 {ssid} 异常: {e}"
                print(f"[WiFi] [WARNING] {error_msg}")
                self.event_bus.publish(get_event_id('wifi_error'), ssid=ssid, error=error_msg)
                continue

        # 所有网络都尝试失败
        error_msg = "所有WiFi网络连接失败"
        print(f"[WiFi] [ERROR] {error_msg}")
        self._wifi_connected = False
        self.event_bus.publish(get_event_id('wifi_failed'))
        self.event_bus.publish(get_event_id('log_warning'), message=error_msg)
        return False

    async def connect_wifi(self):
        """WiFi智能连接函数 - 异步版本，单次尝试"""
        print("[WiFi] 开始智能WiFi连接...")
        self.event_bus.publish(get_event_id('wifi_connecting'))
        wlan = network.WLAN(network.STA_IF)

        if not wlan.active():
            wlan.active(True)

        # 检查是否已连接
        if wlan.isconnected():
            ssid = wlan.config('essid')
            ip = wlan.ifconfig()[0]
            print("[WiFi] 网络已连接。")
            print(f"[WiFi] IP地址: {ip}")
            if not self._wifi_connected:
                self._wifi_connected = True
                self.event_bus.publish(get_event_id('wifi_connected'), ssid=ssid, ip=ip, reconnect=False)
            return True

        # 扫描可用网络
        available_networks = await self.scan_available_networks()
        if not available_networks:
            error_msg = "未发现任何可用网络"
            print(f"[WiFi] [ERROR] {error_msg}")
            self.event_bus.publish(get_event_id('wifi_scan_failed'))
            self.event_bus.publish(get_event_id('log_warning'), message=error_msg)
            return False

        # 尝试连接配置中的第一个可用网络
        for config in self.wifi_configs:
            ssid = config["ssid"]
            password = config["password"]

            if ssid in available_networks:
                print("[WiFi] 尝试连接到:", ssid)
                self.event_bus.publish(get_event_id('wifi_trying'), ssid=ssid)

                # 开始连接过程
                wlan.connect(ssid, password)

                if await self._wait_for_connection(wlan, ssid):
                    ip_info = wlan.ifconfig()
                    ip = ip_info[0]
                    print("\n[WiFi] [SUCCESS] 成功连接到:", ssid)
                    print("[WiFi] IP地址:", ip)
                    self._wifi_connected = True
                    self.event_bus.publish(get_event_id('wifi_connected'), ssid=ssid, ip=ip, reconnect=True)
                    log_msg = "WiFi连接成功: " + ssid + " (" + ip + ")"
                    self.event_bus.publish(get_event_id('log_info'), message=log_msg)
                    return True
                else:
                    error_msg = "连接 " + ssid + " 失败"
                    print("[WiFi] [WARNING]", error_msg)
                    self.event_bus.publish(get_event_id('wifi_error'), ssid=ssid, error=error_msg)
                    break

        error_msg = "WiFi连接失败"
        print(f"[WiFi] [ERROR] {error_msg}")
        self._wifi_connected = False
        self.event_bus.publish(get_event_id('wifi_failed'))
        self.event_bus.publish(get_event_id('log_warning'), message=error_msg)
        return False

    async def wifi_task(self):
        """WiFi连接异步任务：基于状态机的重构版本"""
        print("[WiFi] 启动WiFi连接任务（状态机版本）...")

        wlan = network.WLAN(network.STA_IF)
        state = WifiState.DISCONNECTED
        available_configs = []
        error_count = 0

        while True:
            try:
                if DEBUG:
                    print("[WiFi] 当前状态:", WifiState.get_name(state))

                # 温度检查（所有状态都需要检查）
                try:
                    if esp32:
                        temp = esp32.mcu_temperature()
                        if temp and temp > 42.0:
                            print(f"[WiFi] 温度过高 ({temp:.1f}°C)，暂停WiFi操作")
                            await asyncio.sleep(60)
                            continue
                except:
                    pass

                # 状态机逻辑
                if state == WifiState.DISCONNECTED:
                    if not wlan.active():
                        wlan.active(True)
                        await asyncio.sleep_ms(1000)

                    if wlan.isconnected():
                        state = WifiState.CONNECTED
                    else:
                        self._wifi_connected = False
                        self.event_bus.publish(get_event_id('led_set_effect'), mode='slow_blink')
                        state = WifiState.SCANNING

                elif state == WifiState.SCANNING:
                    print("[WiFi] 扫描可用网络...")
                    available_configs = await self.scan_available_networks_for_config()
                    if not available_configs:
                        print("[WiFi] 未发现配置中的网络，等待重试")
                        state = WifiState.RETRY_WAIT
                    else:
                        print(f"[WiFi] 发现 {len(available_configs)} 个可连接网络")
                        state = WifiState.CONNECTING

                elif state == WifiState.CONNECTING:
                    print("[WiFi] 尝试连接网络...")
                    success = await self.connect_wifi_attempt(available_configs)
                    if success:
                        state = WifiState.CONNECTED
                    else:
                        print("[WiFi] 连接失败，进入重试等待")
                        state = WifiState.RETRY_WAIT

                elif state == WifiState.CONNECTED:
                    if not self._wifi_connected:
                        self._wifi_connected = True
                        print("[WiFi] WiFi连接状态已确认")
                        self.event_bus.publish(get_event_id('led_set_effect'), mode='single_on', led_num=1)

                    # 使用动态WiFi检查间隔（支持温度优化）
                    await asyncio.sleep(self._wifi_check_interval_s)

                    # 检查连接状态
                    if not wlan.isconnected():
                        print("[WiFi] 检测到连接丢失")
                        self._wifi_connected = False
                        state = WifiState.DISCONNECTED

                elif state == WifiState.RETRY_WAIT:
                    print(f"[WiFi] 连接失败，{self.retry_interval_s}秒后重试...")
                    await asyncio.sleep(self.retry_interval_s)
                    state = WifiState.SCANNING

                # 状态间的短暂延迟，避免过于频繁的状态切换
                if state != WifiState.CONNECTED and state != WifiState.RETRY_WAIT:
                    await asyncio.sleep_ms(500)

            except Exception as e:
                error_count += 1
                error_msg = "WiFi任务错误 (第" + str(error_count) + "次): " + str(e)
                print("[WiFi] [ERROR]", error_msg)
                self.event_bus.publish(get_event_id('log_warning'), message=error_msg)

                # 如果错误次数过多，延长等待时间
                if error_count > 5:
                    await asyncio.sleep(30)
                    error_count = 0
                else:
                    await asyncio.sleep(10)

                state = WifiState.RETRY_WAIT
                gc.collect()

    def get_wifi_status(self):
        """获取WiFi状态"""
        try:
            wlan = network.WLAN(network.STA_IF)
            status = {
                'connected': self._wifi_connected,
                'active': wlan.active(),
                'ip_address': None,
                'ssid': None
            }

            if wlan.isconnected():
                status['ip_address'] = wlan.ifconfig()[0]
                status['ssid'] = wlan.config('essid')

            return status
        except Exception as e:
            if DEBUG:
                print(f"[WiFi] 获取状态失败: {e}")
            return {'connected': False, 'active': False, 'ip_address': None, 'ssid': None}

    def is_wifi_connected(self):
        """检查WiFi是否已连接"""
        return self._wifi_connected


# 全局WiFi管理器实例（向后兼容）
_wifi_manager = None

def init_wifi_manager(event_bus, wifi_configs, connect_timeout_s, wifi_check_interval_s, retry_interval_s):
    """初始化全局WiFi管理器实例"""
    global _wifi_manager
    _wifi_manager = WifiManager(event_bus, wifi_configs, connect_timeout_s, wifi_check_interval_s, retry_interval_s)
    return _wifi_manager

# 向后兼容的包装函数
def scan_available_networks():
    """扫描可用网络 - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.scan_available_networks()

def scan_available_networks_for_config():
    """扫描配置中的可用网络 - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.scan_available_networks_for_config()

def connect_wifi():
    """连接WiFi - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.connect_wifi()

def connect_wifi_attempt(wifi_configs=None):
    """WiFi连接尝试 - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.connect_wifi_attempt(wifi_configs)

def wifi_task():
    """WiFi任务 - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.wifi_task()

def get_wifi_status():
    """获取WiFi状态 - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.get_wifi_status()

def is_wifi_connected():
    """检查WiFi是否已连接 - 向后兼容包装函数"""
    if _wifi_manager is None:
        raise RuntimeError("WiFi管理器未初始化，请先调用init_wifi_manager()")
    return _wifi_manager.is_wifi_connected()
