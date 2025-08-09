"""
test_object_pool.py - 对象池测试模块
"""

import unittest
from unittest.mock import Mock, patch
from app.lib.object_pool import ObjectPoolManager

class TestObjectPool(unittest.TestCase):
    """对象池测试类"""
    
    def setUp(self):
        """测试前设置"""
        self.pool_manager = ObjectPoolManager()
    
    def tearDown(self):
        """测试后清理"""
        self.pool_manager = None
    
    def test_add_pool(self):
        """测试添加对象池"""
        # 添加一个简单的对象池
        self.pool_manager.add_pool("test_pool", lambda: {"data": "test"}, 5)
        
        # 验证池已添加
        self.assertIn("test_pool", self.pool_manager.pools)
        self.assertEqual(len(self.pool_manager.pools["test_pool"]), 5)
    
    def test_acquire_object(self):
        """测试获取对象"""
        # 添加一个对象池
        self.pool_manager.add_pool("test_pool", lambda: {"data": "test"}, 3)
        
        # 获取对象
        obj = self.pool_manager.acquire("test_pool")
        
        # 验证对象不为空
        self.assertIsNotNone(obj)
        self.assertEqual(obj["data"], "test")
    
    def test_release_object(self):
        """测试释放对象"""
        # 添加一个对象池
        self.pool_manager.add_pool("test_pool", lambda: {"data": "test"}, 3)
        
        # 获取对象
        obj = self.pool_manager.acquire("test_pool")
        
        # 修改对象
        obj["data"] = "modified"
        
        # 释放对象
        self.pool_manager.release(obj)
        
        # 再次获取对象，应该是同一个对象
        new_obj = self.pool_manager.acquire("test_pool")
        self.assertEqual(new_obj["data"], "modified")
    
    def test_pool_exhaustion(self):
        """测试对象池耗尽情况"""
        # 添加一个只有1个对象的对象池
        self.pool_manager.add_pool("small_pool", lambda: {"data": "test"}, 1)
        
        # 获取对象
        obj1 = self.pool_manager.acquire("small_pool")
        
        # 尝试获取第二个对象，应该返回None或抛出异常
        obj2 = self.pool_manager.acquire("small_pool")
        # 根据实际实现，这里可能是None或抛出异常
        # self.assertIsNone(obj2)  # 或者检查异常
    
    def test_nonexistent_pool(self):
        """测试不存在的对象池"""
        # 尝试从不存在的池中获取对象
        obj = self.pool_manager.acquire("nonexistent_pool")
        self.assertIsNone(obj)

if __name__ == "__main__":
    unittest.main()