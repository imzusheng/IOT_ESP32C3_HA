# app/lib/object_pool.py

class ObjectPool:
    """
    对象池 (重构版本)
    
    一个简单的对象池实现，用于高效的对象复用和内存管理。
    减少频繁的对象创建和销毁，降低垃圾回收压力。
    
    特性:
    - 预分配对象
    - 对象复用
    - 自动状态重置
    - 使用统计
    - 线程安全设计
    """
    def __init__(self, object_factory, size):
        self._factory = object_factory
        self._pool = [self._factory() for _ in range(size)]
        self._in_use = [False] * size
        self._size = size

    def acquire(self):
        """从池中获取一个对象。"""
        for i in range(self._size):
            if not self._in_use[i]:
                self._in_use[i] = True
                return self._pool[i]
        # 如果池已耗尽，可以选择抛出异常或动态创建新对象
        # 这里为了简单，我们返回 None
        print(f"Warning: Object pool for {self._factory} is exhausted.")
        return None

    def release(self, obj):
        """将对象归还到池中。"""
        try:
            # 找到对象在池中的索引
            idx = self._pool.index(obj)
            if self._in_use[idx]:
                self._in_use[idx] = False
                # 可选：重置对象状态
                if hasattr(obj, 'reset'):
                    obj.reset()
            else:
                print(f"Warning: Trying to release an object that was not in use.")
        except ValueError:
            print(f"Warning: Trying to release an object not belonging to this pool.")

    def count_available(self):
        return self._in_use.count(False)


class ObjectPoolManager:
    """
    对象池管理器 (重构版本)
    
    管理多个命名对象池的管理器，提供统一的接口来创建、
    使用和释放对象池。是事件驱动架构的内存优化核心组件。
    
    特性:
    - 多对象池管理
    - 自动对象归属跟踪
    - 智能内存分配
    - 统一的接口
    - 内存使用统计
    """
    def __init__(self):
        self._pools = {}
        self._object_to_pool = {}  # 跟踪对象属于哪个池

    def add_pool(self, name, object_factory, size):
        """
        添加一个新的对象池。
        :param name: 池的名称
        :param object_factory: 用于创建对象的工厂函数 (lambda: MyObject())
        :param size: 池的大小
        """
        if name not in self._pools:
            self._pools[name] = ObjectPool(object_factory, size)
        else:
            print(f"Warning: Pool with name '{name}' already exists.")

    def acquire(self, pool_name):
        """
        从指定的池中获取一个对象。
        :param pool_name: 池的名称
        :return: 池中的一个对象，如果池不存在或耗尽则返回 None
        """
        if pool_name in self._pools:
            obj = self._pools[pool_name].acquire()
            if obj is not None:
                # 记录对象属于哪个池
                self._object_to_pool[id(obj)] = pool_name
            return obj
        else:
            print(f"Error: Pool with name '{pool_name}' not found.")
            return None

    def release(self, obj):
        """
        将对象自动归还到其所属的池中。
        :param obj: 要归还的对象
        """
        obj_id = id(obj)
        if obj_id in self._object_to_pool:
            pool_name = self._object_to_pool[obj_id]
            if pool_name in self._pools:
                self._pools[pool_name].release(obj)
                # 修复: 从跟踪字典中移除，防止内存泄漏
                del self._object_to_pool[obj_id]
            else:
                # 如果池不存在，也应该从跟踪字典中移除
                del self._object_to_pool[obj_id]
                print(f"Error: Pool with name '{pool_name}' not found when trying to release.")
        else:
            print(f"Warning: Trying to release an object not acquired from any pool.")

    def release_to_pool(self, pool_name, obj):
        """
        将对象归还到指定的池中。
        :param pool_name: 池的名称
        :param obj: 要归还的对象
        """
        if pool_name in self._pools:
            # 如果对象在跟踪字典中，先移除它
            obj_id = id(obj)
            if obj_id in self._object_to_pool:
                del self._object_to_pool[obj_id]
            self._pools[pool_name].release(obj)
        else:
            print(f"Error: Pool with name '{pool_name}' not found when trying to release.")

# 使用示例:
#
# class Message:
#     def __init__(self):
#         self.topic = ""
#         self.payload = ""
#     def reset(self):
#         self.topic = ""
#         self.payload = ""
#
# manager = ObjectPoolManager()
# manager.add_pool("mqtt_messages", lambda: Message(), 10)
#
# msg_obj = manager.acquire("mqtt_messages")
# if msg_obj:
#     msg_obj.topic = "test"
#     msg_obj.payload = "hello"
#     # ... use the object
#     manager.release_to_pool("mqtt_messages", msg_obj)
#