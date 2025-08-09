# app/lib/lock/umqtt.py
"""
umqtt 模块的简化版本, 不可编辑

基于umqtt库的轻量级版本，专为ESP32-C3优化。
是事件驱动架构的MQTT通信基础组件。

特性:
- 轻量级MQTT客户端实现
- 内存优化设计
- 断线重连支持
- 心跳保持机制
- 错误恢复能力
"""

import socket
import time
import ustruct
import uerrno
import struct

class MQTTException(Exception):
    pass

class MQTTClient:
    def __init__(self, client_id, server, port=1883, user=None, password=None, keepalive=60,
                 ssl=False, ssl_params={}):
        self.client_id = client_id
        self.server = server
        self.port = port
        self.user = user
        self.password = password
        self.keepalive = keepalive
        self.ssl = ssl
        self.ssl_params = ssl_params
        
        self.sock = None
        self.cb = None
        self.cb_mutex = None
        self.last_ping = time.time()
        self.last_ping_resp = time.time()
        self._in_callback = False
        
    def _send_str(self, s):
        self.sock.write(ustruct.pack("!H", len(s)))
        self.sock.write(s)
    
    def _recv_len(self):
        n = 0
        sh = 0
        while 1:
            b = self.sock.read(1)[0]
            n |= (b & 0x7f) << sh
            if not b & 0x80:
                return n
            sh += 7
    
    def set_callback(self, f):
        self.cb = f
    
    def connect(self, clean_session=True):
        self.sock = socket.socket()
        
        addr = socket.getaddrinfo(self.server, self.port)[0][-1]
        self.sock.connect(addr)
        
        if self.ssl:
            import ussl
            self.sock = ussl.wrap_socket(self.sock, **self.ssl_params)
        
        premsg = bytearray(b"\x10\0\0\0\0\0")
        msg = bytearray(b"\x04MQTT\x04\x02\0\0")
        
        sz = 10 + 2 + len(self.client_id)
        msg[6] = clean_session << 1
        if self.user is not None:
            sz += 2 + len(self.user) + 2 + len(self.password)
            msg[6] |= 0xC0
        
        if self.keepalive:
            assert self.keepalive < 65536
            msg[7] |= self.keepalive >> 8
            msg[8] |= self.keepalive & 0x00FF
        sz = 10 + 2 + len(self.client_id)
        msg[6] = clean_session << 1
        if self.user is not None:
            sz += 2 + len(self.user) + 2 + len(self.password)
            msg[6] |= 0xC0
        
        if self.keepalive:
            assert self.keepalive < 65536
            msg[7] |= self.keepalive >> 8
            msg[8] |= self.keepalive & 0x00FF
        
        i = 1
        while sz > 0x7f:
            premsg[i] = (sz & 0x7f) | 0x80
            sz >>= 7
            i += 1
        premsg[i] = sz
        
        self.sock.write(premsg, i + 2)
        self.sock.write(msg)
        self._send_str(self.client_id)
        if self.user is not None:
            self._send_str(self.user)
            self._send_str(self.password)
        
        resp = self.sock.read(4)
        assert resp[0] == 0x20 and resp[1] == 0x02
        if resp[3] != 0:
            raise MQTTException(resp[3])
        return True
    
    def disconnect(self):
        if self.sock is not None:
            self.sock.write(b"\xe0\0")
            self.sock.close()
            self.sock = None
    
    def ping(self):
        self.sock.write(b"\xc0\0")
        self.last_ping = time.time()
    
    def publish(self, topic, msg, retain=False, qos=0):
        pkt = bytearray(b"\x30\0\0\0")
        pkt[0] |= qos << 1 | retain
        sz = 2 + len(topic) + len(msg)
        if qos > 0:
            sz += 2
        assert sz < 2097152
        i = 1
        while sz > 0x7f:
            pkt[i] = (sz & 0x7f) | 0x80
            sz >>= 7
            i += 1
        pkt[i] = sz
        self.sock.write(pkt, i + 1)
        self._send_str(topic)
        if qos > 0:
            self.sock.write(b"\x00\x00")
        self.sock.write(msg)
        if qos == 1:
            while 1:
                op = self.wait_msg()
                if op == 0x40:
                    sz = self.sock.read(1)
                    assert sz == b"\x02"
                    rcvid = self.sock.read(2)
                    assert rcvid == pid
                    return
    
    def subscribe(self, topic, qos=0):
        assert self.cb is not None, "Subscribe callback is not set"
        pkt = bytearray(b"\x82\0\0\0")
        self.sock.write(pkt)
        self._send_str(topic)
        self.sock.write(qos.to_bytes(1, "little"))
        
        while 1:
            op = self.wait_msg()
            if op == 0x90:
                resp = self.sock.read(4)
                assert resp[0] == 0x90
                assert resp[2] == qos & 0x01
                return
    
    def wait_msg(self):
        res = self.sock.read(1)
        self.last_ping_resp = time.time()
        if res is None:
            return None
        if res == b"":
            raise OSError(-1)
        if res == b"\xd0":  # PINGRESP
            return 0xd0
        
        op = res[0]
        if op & 0xf0 != 0x30:
            return op
        
        sz = self._recv_len()
        topic_len = self.sock.read(2)
        topic_len = (topic_len[0] << 8) | topic_len[1]
        topic = self.sock.read(topic_len)
        sz -= topic_len + 2
        if op & 6:
            pid = self.sock.read(2)
            pid = pid[0] << 8 | pid[1]
            sz -= 2
        
        msg = self.sock.read(sz)
        self.cb(topic, msg)
        if op & 6 == 2:
            pkt = bytearray(b"\x40\x02\0\0")
            struct.pack_into("!H", pkt, 2, pid)
            self.sock.write(pkt)
        elif op & 6 == 4:
            assert 0
    
    def check_msg(self):
        self.sock.setblocking(False)
        try:
            return self.wait_msg()
        except OSError as e:
            if e.args[0] == uerrno.EAGAIN:
                return None
            raise
    
    def is_connected(self):
        if self.sock is None:
            return False
        try:
            self.sock.getpeername()
            return True
        except:
            return False