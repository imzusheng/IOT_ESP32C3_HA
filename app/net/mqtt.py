# app/net/mqtt.py
"""
MQTT 控制器
职责: 
- 封装 MQTTClient 的连接/断开/发布/订阅/消息处理

设计边界: 
- 不包含指数退避重连与复杂会话保持策略(由上层 NetworkManager/FSM 统一治理)
- 仅做轻量的连接状态管理, 避免在资源受限环境中过度占用内存

扩展建议: 
- 可引入心跳/遗嘱/自动重连等策略, 但需统一设计避免与FSM职责重叠
- 可通过主题前缀/设备ID规范化上报主题
"""
from lib.umqtt_lock import MQTTClient
import machine
from lib.logger import error, warning, debug
import binascii as _binascii

# 统一 errno 提取与语义映射
# 返回 (errno, reason); errno 可能为 None, reason 为字符串
def _errno_info(exc):
    try:
        err_no = getattr(exc, "errno", None)
        if err_no is None and getattr(exc, "args", None):
            v0 = exc.args[0]
            if isinstance(v0, int):
                err_no = v0
    except Exception:
        err_no = None
    reasons = {
        103: "ECONNABORTED: 连接被中止",
        104: "ECONNRESET: 连接被重置",
        110: "ETIMEDOUT: 连接超时",
        111: "ECONNREFUSED: 连接被拒绝",
        113: "EHOSTUNREACH: 目标主机不可达",
        128: "ENETUNREACH: 网络不可达",
        -1:  "UNKNOWN(-1): 驱动/底层返回-1, 常见于连接中断或未知错误",
        None: "unknown",
    }
    return err_no, reasons.get(err_no, "unknown")


class MqttController:
    """
    MQTT控制器

    只提供基本的MQTT操作功能:
    - 连接/断开连接
    - 发布/订阅消息
    - 基本的连接状态检查
    - 设置消息回调
    """

    def __init__(self, config=None):
        """
        初始化MQTT控制器
        :param config: MQTT配置字典
        """
        self.config = config or {}
        self.client = None
        self._is_connected = False
        
        # 并发控制: 防止并发连接重入
        self._connecting = False
        
        # 订阅恢复: 记录订阅的主题与qos, 以便重连后恢复
        self._subscriptions = {}

        # 根据配置初始化MQTT客户端
        try:
            # 检查必需的配置项
            if not self.config.get("broker"):
                warning("MQTT配置缺少broker地址, MQTT功能将不可用", module="MQTT")
                return

            # 生成稳健的 client_id: 使用 hex(uid) 的可打印ASCII, 避免非法字符
            def _gen_client_id_bytes():
                try:
                    if hasattr(machine, "unique_id"):
                        uid = machine.unique_id()
                        if isinstance(uid, (bytes, bytearray)):
                            tail = _binascii.hexlify(uid).decode("ascii")[-8:]
                            return ("esp32c3_" + tail).encode("ascii")
                except Exception:
                    pass
                # 回退
                return b"esp32c3_device"

            _client_id = _gen_client_id_bytes()

            self.client = MQTTClient(
                client_id=_client_id,
                server=self.config["broker"],
                port=self.config.get("port", 1883),
                user=self.config.get("user"),
                password=self.config.get("password"),
                keepalive=self.config.get("keepalive", 60),
            )
            # 不在此处设置默认回调; 由上层通过 set_callback 明确指定
        except Exception as e:
            error(f"创建MQTT客户端失败: {e}", module="MQTT")

    # ------------------ 基础能力: 回调、连接、心跳 ------------------
    def set_callback(self, cb):
        """设置消息回调: 与底层 MQTTClient.set_callback 等价"""
        try:
            if self.client:
                self.client.set_callback(cb)
                return True
            return False
        except Exception as e:
            err_no, reason = _errno_info(e)
            error("设置MQTT回调失败 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            return False

    def _on_disconnected(self):
        """统一的断链处理
        
        - 标记内部连接状态为 False(幂等)
        - 最佳努力关闭底层 socket, 避免残留半开连接(不发送协议层 DISCONNECT, 避免重复)
        """
        self._is_connected = False
        try:
            if self.client and hasattr(self.client, "sock") and getattr(self.client, "sock", None):
                try:
                    self.client.sock.close()
                except Exception:
                    pass
                # 确保句柄置空, 避免后续误判连接状态
                try:
                    self.client.sock = None
                except Exception:
                    pass
        except Exception:
            pass


    # ------------------ 连接与断开 ------------------

    async def connect_async(self):
        """异步连接到MQTT Broker
        
        Returns:
            bool: 连接成功返回True, 失败返回False
        """
        if self._is_connected:
            return True

        if not self.client:
            warning("MQTT客户端未初始化或配置不完整", module="MQTT")
            return False
        
        # 避免并发重入导致重复连接与重复日志
        if self._connecting:
            return False

        self._connecting = True
        try:
            debug(
                "异步尝试连接MQTT服务器: {}:{}",
                self.config["broker"],
                self.config.get("port", 1883),
                module="MQTT",
            )
            
            # 异步连接, 分步骤进行以避免长时间阻塞
            success = await self._async_connect_with_timeout()
            
            if success:
                # 验证连接是否建立
                if await self._async_verify_connection():
                    self._is_connected = True
                    # 重连后恢复订阅
                    self._restore_subscriptions()
                    debug("MQTT异步连接成功", module="MQTT")
                    return True
                else:
                    self._on_disconnected()
                    warning("MQTT连接状态验证失败", module="MQTT")
                    return False
            else:
                self._on_disconnected()
                warning("MQTT连接失败", module="MQTT")
                return False
        except OSError as e:
            # 统一错误码语义并增强可观测性
            err_no, reason = _errno_info(e)
            error(
                "MQTT连接失败: {}:{} [errno={} reason={}] {}",
                self.config["broker"],
                self.config.get("port", 1883),
                err_no,
                reason,
                e,
                module="MQTT",
            )
            self._on_disconnected()
            return False
        except Exception as e:
            error("MQTT异步连接异常: {}", e, module="MQTT")
            self._on_disconnected()
            return False
        finally:
            # 重置连接中标志, 确保后续可再次尝试
            self._connecting = False
            
    async def _async_connect_with_timeout(self):
        """异步连接, 带超时控制
        
        说明: 
        - 仅设置全局 socket 默认超时为 10 秒, 避免长时间阻塞
        - 直接复用 __init__ 中已创建并设置回调的 self.client, 不在此处重复创建客户端
        - 保持最小改动, 避免引入新的配置键名差异
        - 不在本函数内修改连接状态, 由验证步骤统一设置, 避免瞬态抖动
        """
        try:
            # 设置 socket 超时(统一为 10 秒), 并在结束后恢复, 降低对全局的副作用
            _set_default = False
            try:
                import socket as _sock
                _timeout_sec = 10
                if hasattr(_sock, "setdefaulttimeout"):
                    _sock.setdefaulttimeout(_timeout_sec)
                    _set_default = True
            except Exception:
                # 在部分运行时环境下, 可能不支持 setdefaulttimeout, 这里容错处理
                _sock = None
                pass
            try:
                # 执行连接: 复用已初始化的 MQTTClient 实例
                self.client.connect()
                return True
            except Exception:
                # 交由上层统一处理日志与语义
                raise
            finally:
                # 恢复默认超时, 避免影响其他网络操作
                try:
                    if _set_default and _sock and hasattr(_sock, "setdefaulttimeout"):
                        _sock.setdefaulttimeout(None)
                except Exception:
                    pass
        except Exception as e:
            error("MQTT连接异常: {}", e, module="MQTT")
            return False

    async def _async_verify_connection(self):
        """异步验证连接状态(瘦身版)"""
        try:
            if self.client and self.client.is_connected():
                return True
            # 简单探活: 若 ping 失败则视为未连接
            try:
                self.client.ping()
                return True
            except Exception:
                return False
        except Exception as e:
            error("异步验证MQTT连接失败: {}", e, module="MQTT")
            return False

    def is_connected(self):
        """检查MQTT是否已连接"""
        return self._is_connected

    def disconnect(self):
        """
        断开与MQTT Broker的连接

        Returns:
            bool: 断开成功返回True
        """
        if self._is_connected and self.client:
            try:
                self.client.disconnect()
            except Exception as e:
                err_no, reason = _errno_info(e)
                error("MQTT断开失败 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
                # 即使断开异常, 也统一进入断链状态
                self._on_disconnected()
                return False

        # 统一断链处理(幂等)
        self._on_disconnected()
        return True

    def publish(self, topic, msg, retain=False, qos=0):
        """
        发布消息

        Args:
            topic (str): 主题
            msg (str): 消息内容
            retain (bool): 是否保留消息
            qos (int): 服务质量等级

        Returns:
            bool: 发布成功返回True
        """
        if not self._is_connected or not self.client:
            return False

        try:
            # 确保以 UTF-8 bytes 发送, 避免中文等多字节字符导致长度不一致
            topic_b = topic if isinstance(topic, (bytes, bytearray)) else str(topic).encode("utf-8")
            msg_b = msg if isinstance(msg, (bytes, bytearray)) else str(msg).encode("utf-8")
            self.client.publish(topic_b, msg_b, retain, qos)
            return True
        except Exception as e:
            err_no, reason = _errno_info(e)
            error("MQTT发布失败 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            return False

    def subscribe(self, topic, qos=0):
        """
        订阅主题

        Args:
            topic (str): 主题
            qos (int): 服务质量等级

        Returns:
            bool: 订阅成功返回True
        """
        # 统一编码为 bytes, 保证协议报文正确; 并记录订阅以便重连恢复
        topic_b = topic if isinstance(topic, (bytes, bytearray)) else str(topic).encode("utf-8")
        try:
            self._subscriptions[topic_b] = int(qos) if isinstance(qos, int) else 0
        except Exception:
            pass

        if not self._is_connected or not self.client:
            warning("MQTT未连接, 无法订阅主题", module="MQTT")
            return False

        try:
            self.client.subscribe(topic_b, qos)
            return True
        except Exception as e:
            # 加强错误上下文: 类型、errno(若有)、repr细节
            err_no, reason = _errno_info(e)
            error(
                "MQTT消息检查失败 [type={} errno={} reason={}]",
                type(e).__name__, err_no, reason, module="MQTT")
            # 标记连接已断开, 交由上层进行事件与重连处理
            self._on_disconnected()
            return False

    async def process_once(self):
        """
        执行一次 MQTT 非阻塞消息处理周期
        - 已连接则尝试拉取一条消息并处理
        - 异常时标记断链并返回 False
        Returns:
            bool: True 表示执行成功, False 表示未连接或异常
        """
        if not self._is_connected or not self.client:
            # 未连接时直接返回 False
            return False
        try:
            # 尝试拉取并处理一条消息(非阻塞)
            self.client.check_msg()
            return True
        except Exception as e:
            # 收敛错误日志并进入断链流程
            err_no, reason = _errno_info(e)
            error("MQTT消息检查失败 [type={} errno={} reason={}]", type(e).__name__, err_no, reason, module="MQTT")
            self._on_disconnected()
            return False

    def _restore_subscriptions(self):
        """重连后恢复订阅(静默失败, 不影响主流程)"""
        if not (self._is_connected and self.client):
            return
        try:
            for t, qos in (self._subscriptions or {}).items():
                try:
                    self.client.subscribe(t, qos)
                    debug("恢复订阅: {} qos={}", t, qos, module="MQTT")
                except Exception as e:
                    warning("恢复订阅失败: {} err={}", t, e, module="MQTT")
        except Exception:
            pass
