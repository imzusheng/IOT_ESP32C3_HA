# app/net/mqtt.py
"""
MQTT 控制器
职责:
- 封装 MQTTClient 的连接、断开、发布、订阅、消息处理

设计边界:
- 不包含指数退避或复杂会话保持策略, 由上层 NetworkManager/FSM 统一治理
- 仅做轻量的连接状态管理, 避免在资源受限环境中过度占用内存

扩展建议:
- 可引入心跳/遗嘱/自动重连等策略, 但需统一设计避免与 FSM 职责重叠
- 可通过主题前缀/设备 ID 规范化上报主题
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
        -1:  "UNKNOWN(-1): 驱动或底层返回-1, 常见于连接中断或未知错误",
        None: "unknown",
    }
    return err_no, reasons.get(err_no, "unknown")


class MqttController:
    """
    MQTT 控制器

    仅提供基本的 MQTT 操作能力:
    - 连接、断开连接
    - 发布、订阅消息
    - 基本的连接状态检查
    - 设置消息回调
    - 配置 LWT(若底层实现支持)
    """

    def __init__(self, config=None):
        """
        初始化 MQTT 控制器
        Args:
            config: MQTT 配置字典
        """
        self.config = config or {}
        self.client = None
        self._is_connected = False

        # 并发控制: 防止并发连接重入
        self._connecting = False

        # 订阅恢复: 记录订阅的主题与 qos, 以便重连后恢复
        self._subscriptions = {}

        # LWT 配置(控制器层面的抽象, 底层不支持则降级)
        self._lwt = None  # dict: {topic, payload, qos, retain}

        # 根据配置初始化 MQTT 客户端
        try:
            # 检查必需的配置项
            if not self.config.get("broker"):
                warning("MQTT配置缺少broker地址, MQTT功能将不可用", module="MQTT")
                return

            # 生成稳健的 client_id: 使用 hex(uid) 的可打印 ASCII, 避免非法字符
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
            # 缓存 client_id 供上层构造主题使用
            self._client_id = _client_id  # bytes, 可解码为 ascii

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
            error("创建MQTT客户端失败: {}", e, module="MQTT")

    # ------------------ 基础能力: 回调、连接、心跳 ------------------
    def set_callback(self, cb):
        """设置消息回调, 与底层 MQTTClient.set_callback 等价"""
        try:
            if self.client:
                self.client.set_callback(cb)
                return True
            return False
        except Exception as e:
            err_no, reason = _errno_info(e)
            error("设置MQTT回调失败 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            return False

    def set_last_will(self, topic, payload="offline", qos=0, retain=True):
        """配置 LWT(遗嘱). 若底层客户端支持 set_last_will, 将在下次连接时设置; 否则降级为仅在正常断开时发布 offline。
        Args:
            topic: LWT 主题
            payload: LWT 消息
            qos: QoS 等级
            retain: 是否保留
        """
        try:
            if not topic:
                return False
            self._lwt = {
                "topic": topic,
                "payload": payload if isinstance(payload, (bytes, bytearray, str)) else str(payload),
                "qos": int(qos) if qos in (0, 1, 2) else 0,
                "retain": bool(retain),
            }
            debug("已设置LWT @{}", topic, module="MQTT")
            return True
        except Exception as e:
            warning("设置LWT失败: {}", e, module="MQTT")
            return False

    def get_client_id(self):
        """获取用于 MQTT 连接的 client_id 字符串
        优先从底层客户端读取, 退回到初始化缓存
        Returns:
            str 或 None
        """
        try:
            cid = None
            if self.client and hasattr(self.client, "client_id"):
                cid = getattr(self.client, "client_id", None)
            if cid is None:
                cid = getattr(self, "_client_id", None)
            if isinstance(cid, (bytes, bytearray)):
                try:
                    return cid.decode("ascii")
                except Exception:
                    # 无法 ascii 解码时转 hex 表达
                    return _binascii.hexlify(bytes(cid)).decode("ascii")
            if isinstance(cid, str):
                return cid
        except Exception:
            pass
        return None

    def _on_disconnected(self):
        """统一断链处理
        - 标记内部连接状态为 False
        - 尝试关闭底层 socket, 避免残留半开连接
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
        """异步连接到 MQTT Broker
        Returns:
            bool: 连接成功返回 True, 失败返回 False
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
            err_no, reason = _errno_info(e)
            error("MQTT连接异常 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            self._on_disconnected()
            return False
        finally:
            self._connecting = False

    async def _async_connect_with_timeout(self):
        """内部: 带超时的连接流程, 避免长阻塞"""
        try:
            import uasyncio as asyncio

            async def _phase_connect():
                try:
                    # 若底层支持 LWT, 在连接前设置
                    if self._lwt and hasattr(self.client, "set_last_will"):
                        try:
                            self.client.set_last_will(
                                self._lwt["topic"],
                                self._lwt["payload"],
                                self._lwt.get("retain", True),
                                self._lwt.get("qos", 0),
                            )
                            debug("已在底层客户端设置LWT", module="MQTT")
                        except Exception as _e:
                            warning("底层LWT设置失败(将降级): {}", _e, module="MQTT")
                    elif self._lwt:
                        debug("底层客户端不支持LWT, 将通过正常断开发布offline进行降级", module="MQTT")
                    self.client.connect()
                    return True
                except Exception:
                    return False

            async def _phase_settle():
                await asyncio.sleep_ms(50)
                return True

            async def _run_with_timeout(ms=3000):
                try:
                    tk = asyncio.create_task(_phase_connect())
                    try:
                        await asyncio.wait_for(tk, ms/1000)
                    except Exception:
                        try:
                            tk.cancel()
                        except Exception:
                            pass
                        return False
                    await _phase_settle()
                    return True
                except Exception:
                    return False

            return await _run_with_timeout()
        except Exception:
            return False

    async def _async_verify_connection(self):
        """内部: 通过一次最小交互验证连接可用性"""
        try:
            import uasyncio as asyncio
            await asyncio.sleep_ms(10)
            return True
        except Exception:
            return False

    def is_connected(self):
        """返回当前 MQTT 连接状态"""
        return bool(self._is_connected)

    def publish(self, topic, payload, retain=False, qos=0):
        """发布消息(对底层 publish 的薄封装)"""
        try:
            if not self.client:
                return False
            self.client.publish(topic, payload, retain, qos)
            return True
        except Exception as e:
            err_no, reason = _errno_info(e)
            error("MQTT发布失败 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            self._on_disconnected()
            return False

    def subscribe(self, topic, qos=0):
        """订阅指定主题, 记录以便重连后恢复"""
        try:
            if not self.client:
                return False
            self.client.subscribe(topic, qos)
            # 记录订阅以便重连后恢复
            self._subscriptions[topic] = qos
            return True
        except Exception as e:
            err_no, reason = _errno_info(e)
            error("MQTT订阅失败 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            self._on_disconnected()
            return False

    async def process_once(self):
        """处理一次消息(非阻塞)"""
        try:
            if not self.client:
                return False
            self.client.check_msg()
            return True
        except Exception as e:
            err_no, reason = _errno_info(e)
            warning("MQTT消息处理异常 [errno={} reason={}]: {}", err_no, reason, e, module="MQTT")
            return False

    def disconnect(self):
        """断开 MQTT 连接"""
        try:
            if self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
        finally:
            self._on_disconnected()

    def _restore_subscriptions(self):
        """在重连后恢复之前的所有订阅"""
        try:
            for topic, qos in self._subscriptions.items():
                try:
                    self.client.subscribe(topic, qos)
                except Exception:
                    pass
        except Exception:
            pass
