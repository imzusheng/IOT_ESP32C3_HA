"""
test_event_bus.py - 事件总线测试模块
"""

import unittest
from unittest.mock import Mock, patch
from app.lib.event_bus import EventBus
from app.event_const import EVENT

class TestEventBus(unittest.TestCase):
    """事件总线测试类"""
    
    def setUp(self):
        """测试前设置"""
        self.event_bus = EventBus()
        self.received_events = []
        
        # 创建一个测试回调函数
        def test_callback(event_name, *args, **kwargs):
            self.received_events.append({
                'name': event_name,
                'args': args,
                'kwargs': kwargs
            })
        
        self.test_callback = test_callback
    
    def tearDown(self):
        """测试后清理"""
        self.event_bus = None
        self.received_events = []
    
    def test_subscribe_and_publish(self):
        """测试订阅和发布事件"""
        # 订阅事件
        self.event_bus.subscribe("test_event", self.test_callback)
        
        # 发布事件
        test_data = {"key": "value"}
        self.event_bus.publish("test_event", test_data, extra="param")
        
        # 验证事件被接收
        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(self.received_events[0]['name'], "test_event")
        self.assertEqual(self.received_events[0]['args'][0], test_data)
        self.assertEqual(self.received_events[0]['kwargs']['extra'], "param")
    
    def test_multiple_subscribers(self):
        """测试多个订阅者"""
        # 创建第二个回调函数
        received_events_2 = []
        def test_callback_2(event_name, *args, **kwargs):
            received_events_2.append({
                'name': event_name,
                'args': args,
                'kwargs': kwargs
            })
        
        # 两个订阅者订阅同一个事件
        self.event_bus.subscribe("test_event", self.test_callback)
        self.event_bus.subscribe("test_event", test_callback_2)
        
        # 发布事件
        self.event_bus.publish("test_event", "data")
        
        # 验证两个订阅者都收到了事件
        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(len(received_events_2), 1)
    
    def test_unsubscribe(self):
        """测试取消订阅"""
        # 订阅事件
        self.event_bus.subscribe("test_event", self.test_callback)
        
        # 发布事件
        self.event_bus.publish("test_event", "data1")
        
        # 取消订阅
        self.event_bus.unsubscribe("test_event", self.test_callback)
        
        # 再次发布事件
        self.event_bus.publish("test_event", "data2")
        
        # 验证只收到第一个事件
        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(self.received_events[0]['args'][0], "data1")
    
    def test_publish_with_no_subscribers(self):
        """测试发布没有订阅者的事件"""
        # 发布没有订阅者的事件
        self.event_bus.publish("no_subscribers_event", "data")
        
        # 验证没有错误发生，且没有接收到事件
        self.assertEqual(len(self.received_events), 0)
    
    def test_event_with_constants(self):
        """测试使用事件常量"""
        # 使用事件常量订阅
        self.event_bus.subscribe(EVENT.SYSTEM_READY, self.test_callback)
        
        # 使用事件常量发布
        self.event_bus.publish(EVENT.SYSTEM_READY, "system is ready")
        
        # 验证事件被接收
        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(self.received_events[0]['name'], EVENT.SYSTEM_READY)
        self.assertEqual(self.received_events[0]['args'][0], "system is ready")
    
    def test_callback_exception_handling(self):
        """测试回调函数异常处理"""
        # 创建一个会抛出异常的回调函数
        def error_callback(event_name, *args, **kwargs):
            raise Exception("Callback error")
        
        # 订阅事件
        self.event_bus.subscribe("test_event", error_callback)
        self.event_bus.subscribe("test_event", self.test_callback)
        
        # 发布事件，应该不会因为一个回调出错而影响其他回调
        try:
            self.event_bus.publish("test_event", "data")
        except Exception:
            self.fail("EventBus.publish() raised an exception!")
        
        # 验证正常的回调仍然被调用
        self.assertEqual(len(self.received_events), 1)
    
    def test_publish_pooled(self):
        """测试发布带对象池的事件"""
        # 订阅事件
        self.event_bus.subscribe("test_event", self.test_callback)
        
        # 发布带对象池的事件
        pool_idx = 0
        pool_ref = {"data": "pooled_data"}
        self.event_bus.publish_pooled("test_event", pool_idx, pool_ref)
        
        # 验证事件被接收
        self.assertEqual(len(self.received_events), 1)
        self.assertEqual(self.received_events[0]['name'], "test_event")
        # 验证对象池参数被正确传递
        self.assertEqual(self.received_events[0]['args'][0], pool_idx)
        self.assertEqual(self.received_events[0]['args'][1], pool_ref)

if __name__ == "__main__":
    unittest.main()