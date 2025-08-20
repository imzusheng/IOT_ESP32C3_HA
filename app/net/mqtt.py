# app/net/mqtt.py
"""
MQTT 控制器
职责：
- 封装 MQTTClient 的连接/断开/发布/订阅/消息处理
- 通过事件总线上报收到的消息，供系统其他模块使用

设计边界：
- 不包含指数退避重连与复杂会话保持策略（由上层 NetworkManager/FSM 统一治理）
- 仅做轻量的连接状态管理，避免在资源受限环境中过度占用内存

扩展建议：
- 可引入心跳/遗嘱/自动重连等策略，但需统一设计避免与FSM职责重叠
- 可通过主题前缀/设备ID规范化上报主题
"""
from lib.lock.umqtt import MQTTClient
import machine
import utime as time
from lib.logger import error, warning, debug, set_info_hook
from lib.lock.event_bus import EventBus, EVENTS
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio

# 为了在错误日志中输出更明确的原因，提供一个简单的errno解释函数
def _errno_reason(err_no):
    try:
        code = int(err_no)
    except Exception:
        return "unknown"
    reasons = {
        103: "ECONNABORTED",
        104: "ECONNRESET",
        110: "ETIMEDOUT",
        111: "ECONNREFUSED",
        113: "EHOSTUNREACH",
        128: "ENETUNREACH",
        -1:  "UNKNOWN(-1): 驱动/底层返回-1，常见于连接中断或未知错误"
    }
    return reasons.get(code, "unknown")


class MqttController:
    """
    MQTT控制器

    只提供基本的MQTT操作功能:
    - 连接/断开连接
    - 发布/订阅消息
    - 基本的连接状态检查
    """

    def __init__(self, config=None, event_bus=None):
        """
        初始化MQTT控制器
        :param config: MQTT配置字典
        :param event_bus: 事件总线实例
        """
        self.config = config or {}
        self.client = None
        self._is_connected = False
        self.event_bus = event_bus  # 使用传入的EventBus，不创建新的
        
        # 并发控制：防止并发连接重入
        self._connecting = False

        # 日志转发相关
        self._log_topic = None  # INFO 日志转发主题（MQTT连接成功后设定）

        # 根据配置初始化MQTT客户端
        try:
            # 检查必需的配置项
            if not self.config.get("broker"):
                warning("MQTT配置缺少broker地址, MQTT功能将不可用", module="MQTT")
                return

            self.client = MQTTClient(
                client_id=(
                    "esp32c3_" + str(machine.unique_id())[-6:]
                    if hasattr(machine, "unique_id")
                    else "esp32c3_device"
                ),
                server=self.config["broker"],
                port=self.config.get("port", 1883),
                user=self.config.get("user"),
                password=self.config.get("password"),
                keepalive=self.config.get("keepalive", 60),
            )
            self.client.set_callback(self._mqtt_callback)
        except Exception as e:
            error(f"创建MQTT客户端失败: {e}", module="MQTT")

    def _mqtt_callback(self, topic, msg):
        """MQTT消息回调函数"""
        try:
            topic_str = topic.decode("utf-8")
            msg_str = msg.decode("utf-8")
            debug(f"收到MQTT消息: 主题={topic_str}, 消息={msg_str}", module="MQTT")

            if self.event_bus:
                self.event_bus.publish(
                    EVENTS["MQTT_MESSAGE"],
                    {
                        "topic": topic_str,
                        "message": msg_str,
                        "timestamp": time.ticks_ms(),
                    },
                )
        except Exception as e:
            error("处理MQTT消息失败: {}", e, module="MQTT")

    # ------------------ 日志与心跳辅助 ------------------
    def _resolve_client_id(self):
        """获取客户端ID（字符串），用于构造默认日志主题"""
        try:
            cid = getattr(self.client, "client_id", None)
            if cid is None:
                return "device"
            if isinstance(cid, bytes):
                try:
                    return cid.decode("utf-8")
                except Exception:
                    return str(cid)
            return str(cid)
        except Exception:
            return "device"

    def _install_info_log_hook(self):
        """
        安装 INFO 级日志转发钩子：将日志转发到 MQTT
        说明：
        - 仅在 MQTT 连接成功后调用
        - 采用 QoS0、非保留消息
        - 失败时静默，不影响主流程
        """
        try:
            # 计算日志主题：优先使用配置项，其次使用 client_id
            if not self._log_topic:
                conf_topic = (self.config or {}).get("log_topic")
                if conf_topic:
                    self._log_topic = conf_topic
                else:
                    cid = self._resolve_client_id()
                    self._log_topic = f"log/{cid}"

            def _hook(line):
                # 仅在已连接状态下转发，避免启动阶段或断链时异常
                if self._is_connected and self.client:
                    try:
                        # 使用控制器的 publish，内部自带最小保护
                        self.publish(self._log_topic, line, retain=False, qos=0)
                    except Exception:
                        # 静默失败
                        pass

            set_info_hook(_hook)
        except Exception:
            # 安装钩子失败不应影响连接流程
            pass

    def _remove_info_log_hook(self):
        """移除 INFO 级日志转发钩子"""
        try:
            set_info_hook(None)
        except Exception:
            pass

    def _maybe_send_ping(self):
        """
        根据 keepalive 调度心跳：当距离上次收到数据超过 keepalive 的安全边际时，发送 PINGREQ。
        说明：
        - 使用底层 MQTTClient 的 last_ping 与 last_ping_resp（单位：秒）
        - 边际：取 min(5, max(1, keepalive//3)) 秒，避免临界超时
        - 仅在连接状态下执行
        """
        try:
            if not (self._is_connected and self.client and getattr(self.client, "keepalive", 0)):
                return
            ka = int(self.client.keepalive) if self.client.keepalive else 0
            if ka <= 0:
                return
            # 采用 utime.time() 秒
            now_s = time.time() if hasattr(time, "time") else (time.ticks_ms() // 1000)
            last_resp = getattr(self.client, "last_ping_resp", 0) or 0
            last_ping = getattr(self.client, "last_ping", 0) or 0
            margin = 5 if ka > 15 else max(1, ka // 3)
            # 若长时间未收到任何数据，则发送心跳；并避免在刚发送过心跳后立刻重复发送
            if (now_s - last_resp) >= (ka - margin) and (now_s - last_ping) >= margin:
                try:
                    self.client.ping()
                except Exception as _:
                    # 交由上层异常路径处理
                    raise
        except Exception as _:
            # 在上层 check_msg(_async) 中统一处理异常与断链标记
            raise

    # ------------------ 连接与断开 ------------------
    def connect(self):
        """
        连接到MQTT Broker

        Returns:
            bool: 连接成功返回True, 失败返回False
        """
        if self._is_connected:
            return True

        if not self.client:
            warning("MQTT客户端未初始化或配置不完整", module="MQTT")
            return False

        try:
            debug(
                "尝试连接MQTT服务器: {}:{}",
                self.config["broker"],
                self.config.get("port", 1883),
                module="MQTT",
            )
            # 设置连接超时为10秒
            try:
                import socket as _sock
                _timeout_sec = 10
                # 如果底层客户端尚未创建socket, 通过全局默认超时影响后续socket创建
                if hasattr(_sock, "socket") and hasattr(_sock, "setdefaulttimeout"):
                    _sock.setdefaulttimeout(_timeout_sec)
            except Exception:
                pass

            self.client.connect()

            # 验证连接是否建立
            if hasattr(self.client, "is_connected") and self.client.is_connected():
                self._is_connected = True
                # 安装 INFO 日志转发钩子
                self._install_info_log_hook()
                debug("MQTT连接成功", module="MQTT")
                return True
            else:
                # 对于某些MQTT库,连接成功后没有is_connected方法
                # 尝试发送ping来验证连接
                try:
                    self.client.ping()
                    self._is_connected = True
                    # 安装 INFO 日志转发钩子
                    self._install_info_log_hook()
                    debug("MQTT连接成功 (通过ping验证)", module="MQTT")
                    return True
                except:
                    self._is_connected = False
                    warning("MQTT连接状态验证失败", module="MQTT")
                    return False

        except OSError as e:
            if e.errno == 113:  # ECONNABORTED
                error(
                    "MQTT连接被拒绝: 服务器{}:{}不可达或拒绝连接",
                    self.config["broker"],
                    self.config.get("port", 1883),
                    module="MQTT",
                )
            elif e.errno == 110:  # ETIMEDOUT
                error(
                    "MQTT连接超时: 服务器{}:{}无响应",
                    self.config["broker"],
                    self.config.get("port", 1883),
                    module="MQTT",
                )
            else:
                error("MQTT连接网络错误 [{}]: {}", e.errno, e, module="MQTT")
            self._is_connected = False
            return False
        except Exception as e:
            error("MQTT连接异常: {}", e, module="MQTT")
            self._is_connected = False
            return False

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
            
            # 异步连接，分步骤进行以避免长时间阻塞
            success = await self._async_connect_with_timeout()
            
            if success:
                # 验证连接是否建立
                if await self._async_verify_connection():
                    self._is_connected = True
                    # 安装 INFO 日志转发钩子
                    self._install_info_log_hook()
                    debug("MQTT异步连接成功", module="MQTT")
                    return True
                else:
                    self._is_connected = False
                    warning("MQTT连接状态验证失败", module="MQTT")
                    return False
            else:
                self._is_connected = False
                warning("MQTT连接失败", module="MQTT")
                return False
        except OSError as e:
            if e.errno == 113:  # ECONNABORTED
                error(
                    "MQTT连接被拒绝: 服务器{}:{}不可达或拒绝连接",
                    self.config["broker"],
                    self.config.get("port", 1883),
                    module="MQTT",
                )
            elif e.errno == 110:  # ETIMEDOUT
                error(
                    "MQTT连接超时: 服务器{}:{}无响应",
                    self.config["broker"],
                    self.config.get("port", 1883),
                    module="MQTT",
                )
            else:
                error("MQTT连接网络错误 [{}]: {}", e.errno, e, module="MQTT")
            self._is_connected = False
            return False
        except Exception as e:
            error("MQTT异步连接异常: {}", e, module="MQTT")
            self._is_connected = False
            return False
        finally:
            # 重置连接中标志，确保后续可再次尝试
            self._connecting = False
            
    async def _async_connect_with_timeout(self):
        """异步连接，带超时控制
        
        说明：
        - 仅设置全局 socket 默认超时为 10 秒，避免长时间阻塞
        - 直接复用 __init__ 中已创建并设置回调的 self.client，不在此处重复创建客户端
        - 保持最小改动，避免引入新的配置键名差异
        """
        try:
            # 设置 socket 超时（统一为 10 秒）
            try:
                import socket as _sock
                _timeout_sec = 10
                if hasattr(_sock, "setdefaulttimeout"):
                    _sock.setdefaulttimeout(_timeout_sec)
            except Exception:
                # 在部分运行时环境下，可能不支持 setdefaulttimeout，这里容错处理
                pass
            
            # 执行连接：复用已初始化的 MQTTClient 实例
            # self.client 已在 __init__ 中创建并设置了回调为 self._mqtt_callback
            self.client.connect()
            self._is_connected = True
            debug("MQTT连接成功", module="MQTT")
            return True
        except Exception as e:
            self._is_connected = False
            error("MQTT连接失败: {}", e, module="MQTT")
            return False
            
    async def _async_verify_connection(self):
        """异步验证连接状态"""
        try:
            # 检查连接状态
            if hasattr(self.client, "is_connected") and self.client.is_connected():
                return True
            else:
                # 尝试ping验证
                await asyncio.sleep_ms(10)  # 让出控制权
                try:
                    self.client.ping()
                    await asyncio.sleep_ms(50)  # 等待ping响应
                    return True
                except:
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
                error("MQTT断开失败: {}", e, module="MQTT")
                return False

        # 断开后移除 INFO 日志钩子
        self._remove_info_log_hook()

        self._is_connected = False
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
            # 确保以 UTF-8 bytes 发送，避免中文等多字节字符导致长度不一致
            topic_b = topic if isinstance(topic, (bytes, bytearray)) else str(topic).encode("utf-8")
            msg_b = msg if isinstance(msg, (bytes, bytearray)) else str(msg).encode("utf-8")
            self.client.publish(topic_b, msg_b, retain, qos)
            return True
        except Exception as e:
            error("MQTT发布失败: {}", e, module="MQTT")
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
        if not self._is_connected or not self.client:
            warning("MQTT未连接, 无法订阅主题", module="MQTT")
            return False

        try:
            # 统一编码为 bytes，保证协议报文正确
            topic_b = topic if isinstance(topic, (bytes, bytearray)) else str(topic).encode("utf-8")
            self.client.subscribe(topic_b, qos)
            return True
        except Exception as e:
            error("MQTT订阅失败: {}", e, module="MQTT")
            return False

    def check_msg(self):
        """检查是否有新消息"""
        if self._is_connected and self.client:
            try:
                # 心跳调度（同步路径）
                self._maybe_send_ping()
                self.client.check_msg()
            except Exception as e:
                # 加强错误上下文：类型、errno(若有)、repr细节
                err_no = getattr(e, "errno", None)
                if err_no is None and getattr(e, "args", None):
                    try:
                        err_no = e.args[0] if isinstance(e.args[0], int) else None
                    except Exception:
                        err_no = None
                error("检查MQTT消息失败: type={}, errno={}, reason={}, detail={}",
                      type(e).__name__, err_no, _errno_reason(err_no), repr(e), module="MQTT")
                # 标记连接已断开，交由上层进行事件与重连处理
                self._is_connected = False
                # 移除 INFO 日志钩子，避免无连接情况下继续转发
                self._remove_info_log_hook()
                
    async def check_msg_async(self):
        """异步检查是否有新消息"""
        if self._is_connected and self.client:
            try:
                # 让出控制权，避免阻塞
                await asyncio.sleep_ms(1)
                # 心跳调度（异步路径）
                self._maybe_send_ping()
                self.client.check_msg()
                await asyncio.sleep_ms(1)  # 处理完消息后让出控制权
            except Exception as e:
                # 加强错误上下文：类型、errno(若有)、repr细节
                err_no = getattr(e, "errno", None)
                if err_no is None and getattr(e, "args", None):
                    try:
                        err_no = e.args[0] if isinstance(e.args[0], int) else None
                    except Exception:
                        err_no = None
                error("异步检查MQTT消息失败: type={}, errno={}, reason={}, detail={}",
                      type(e).__name__, err_no, _errno_reason(err_no), repr(e), module="MQTT")
                # 标记连接已断开，交由上层进行事件与重连处理
                self._is_connected = False
                # 移除 INFO 日志钩子，避免无连接情况下继续转发
                self._remove_info_log_hook()
