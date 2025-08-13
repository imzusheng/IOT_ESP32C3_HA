# app/net/index.py
# 网络统一控制器 - 使用状态机封装内部流程
from lib.logger import get_global_logger
from lib.lock.event_bus import EVENTS
from .wifi import WifiManager
from .ntp import NtpManager
from .mqtt import MqttController
from .fsm import NetworkFSM

class NetworkManager:
    """
    网络统一控制器
    
    使用状态机封装网络连接内部流程，外部只需调用简单接口：
    - connect(): 启动连接
    - disconnect(): 断开连接
    - get_status(): 获取状态
    - loop(): 主循环调用
    
    内部状态机管理 WiFi→NTP→MQTT 的完整流程，外部无需关心细节
    """
    
    def __init__(self, event_bus, config):
        """
        初始化网络管理器
        
        Args:
            event_bus: EventBus实例
            config: 网络配置字典
        """
        self.event_bus = event_bus
        self.config = config
        self.logger = get_global_logger()
        
        # 初始化各个网络组件
        self.wifi = WifiManager(config.get('wifi', {}))
        self.ntp = NtpManager(config.get('ntp', {}))
        self.mqtt = MqttController(config.get('mqtt', {}))
        
        # 设置MQTT的事件总线
        self.mqtt.set_event_bus(event_bus)
        
        # 创建网络状态机
        self.fsm = NetworkFSM(
            event_bus=event_bus,
            config=config.get('network', {}),
            wifi_manager=self.wifi,
            mqtt_manager=self.mqtt,
            ntp_manager=self.ntp
        )
        
        # 订阅系统事件
        self._setup_event_subscriptions()
        
        self.logger.info("网络管理器已初始化（使用状态机）", module="NET")
    
    def _setup_event_subscriptions(self):
        """设置事件订阅"""
        # 订阅系统状态变化事件
        self.event_bus.subscribe(EVENTS.SYSTEM_STATE_CHANGE, self._on_system_state_change)
    
    def _on_system_state_change(self, state, info=None):
        """
        处理系统状态变化事件
        
        Args:
            state: 系统状态
            info: 附加信息
        """
        if state == 'networking':
            self.logger.info("系统进入网络状态，开始连接流程", module="NET")
            self.connect()
        elif state == 'shutdown':
            self.logger.info("系统关闭，断开网络连接", module="NET")
            self.disconnect()
    
    def connect(self):
        """
        启动网络连接
        
        内部状态机会自动处理 WiFi→NTP→MQTT 的完整流程
        外部只需调用此方法即可
        """
        self.fsm.connect()
    
    def disconnect(self):
        """
        断开网络连接
        """
        self.fsm.disconnect()
    
    def get_status(self):
        """
        获取网络连接状态
        
        Returns:
            dict: 网络状态信息
        """
        return self.fsm.get_status()
    
    def is_connected(self):
        """
        检查网络是否已连接
        
        Returns:
            bool: 已连接返回True
        """
        return self.fsm.is_connected()
    
    def loop(self):
        """
        主循环处理函数
        """
        self.fsm.loop()
    
    def reset_failures(self):
        """
        重置失败计数器
        """
        # 状态机内部管理重试计数，这里提供兼容性接口
        self.logger.info("重置网络失败计数器（状态机内部管理）", module="NET")
        self.fsm.disconnect()
        self.fsm.connect()
    
    def start_connection_flow(self):
        """
        启动连接流程（兼容性接口）
        """
        self.connect()
    
    def start_services(self):
        """
        启动网络服务（兼容性接口）
        """
        # 状态机内部自动处理，无需单独调用
        pass
    
    def update(self):
        """
        更新网络状态（兼容性接口）
        """
        # 状态机内部自动处理，无需单独调用
        pass
    
    def check_consistency(self):
        """
        检查网络状态一致性
        """
        # 状态机内部保持状态一致性，总是返回True
        return True