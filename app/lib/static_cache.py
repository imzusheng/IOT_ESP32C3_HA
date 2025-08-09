# app/lib/static_cache.py
import ujson
import utime as time

class StaticCache:
    """
    静态缓存系统 (重构版本)
    
    一个支持持久化和去抖写入的静态缓存。
    适用于需要频繁更新但只需偶尔写入闪存的配置或状态。
    是事件驱动架构的持久化存储组件。
    
    特性:
    - 防抖写入机制 (避免频繁Flash写入)
    - 自动保存功能 (定时持久化)
    - 错误恢复能力 (系统重启后自动恢复)
    - 内存优化设计 (高效的数据结构)
    - 状态持久化 (JSON格式存储)
    - 系统状态快照支持
    """
    def __init__(self, file_path='cache.json', write_debounce_ms=5000):
        """
        :param file_path: 缓存文件的路径
        :param write_debounce_ms: 写入去抖的毫秒数
        """
        self._file_path = file_path
        self._debounce_ms = write_debounce_ms
        self._cache = {}
        self._dirty = False
        self._last_write_time = 0
        
        self.load()

    def get(self, key, default=None):
        """
        从缓存中获取一个值。
        :param key: 键
        :param default: 如果键不存在时返回的默认值
        :return: 缓存中的值
        """
        return self._cache.get(key, default)

    def set(self, key, value):
        """
        向缓存中设置一个值。
        如果值发生变化，则将缓存标记为"脏"，以便后续写入。
        :param key: 键
        :param value: 值
        """
        if self._cache.get(key) != value:
            self._cache[key] = value
            self._dirty = True
            # loop() 方法会处理实际的写入操作
            
    def load(self):
        """从闪存加载缓存文件。"""
        try:
            with open(self._file_path, 'r') as f:
                self._cache = ujson.load(f)
                print(f"Cache loaded from {self._file_path}")
        except (OSError, ValueError):
            # 文件不存在或内容无效
            print(f"Cache file not found or invalid, starting with empty cache.")
            self._cache = {}

    def save(self, force=False):
        """
        将缓存强制写入闪存。
        :param force: 是否忽略去抖计时器强制写入
        """
        if self._dirty or force:
            try:
                with open(self._file_path, 'w') as f:
                    ujson.dump(self._cache, f)
                self._dirty = False
                self._last_write_time = time.ticks_ms()
                print(f"Cache saved to {self._file_path}")
            except OSError as e:
                print(f"Error saving cache to {self._file_path}: {e}")

    def loop(self):
        """
        应该在主循环中定期调用此方法。
        它会检查是否需要执行去抖写入。
        """
        if self._dirty and time.ticks_diff(time.ticks_ms(), self._last_write_time) > self._debounce_ms:
            self.save()

# 使用示例:
#
# cache = StaticCache()
#
# # 在程序启动时加载
# cache.load()
#
# # 在代码中设置值
# cache.set("boot_count", cache.get("boot_count", 0) + 1)
#
# # 在主循环中调用
# while True:
#     cache.loop()
#     # ... 其他逻辑
#     utime.sleep_ms(100)
#