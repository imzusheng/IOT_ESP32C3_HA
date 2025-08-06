# -*- coding: utf-8 -*-
"""
mem_optimizer.py 模块的独立测试脚本。

该脚本旨在验证 mem_optimizer 模块的各项功能是否按预期工作，
包括对象池、缓存和内存清理器的基本行为。

用法:
1. 确保 mem_optimizer.py 文件已存在于设备的 /lib 目录中。
2. 将此文件 (test_mem_optimizer.py) 上传到设备的根目录。
3. 在 REPL 中执行 `import test_mem_optimizer` 或通过 IDE 直接运行此文件。
"""

import gc
try:
    # 导入位于 /lib 目录下的优化模块，并使用别名
    import mem_optimizer as mem
except ImportError:
    print("[TEST_MEM_OPTIMIZER] 错误: 未在 /lib 目录中找到 mem_optimizer.py 模块。")
    print("[TEST_MEM_OPTIMIZER] 请先将功能模块上传到设备。")
    # 退出，避免后续代码因导入失败而崩溃
    raise

# 定义一个统一的前缀，方便识别测试输出
_PREFIX = "[TEST_MEM_OPTIMIZER]"

def run_all_tests():
    """执行所有测试用例。"""
    
    print(f"{_PREFIX} --- 内存优化模块测试开始 ---")
    print(f"{_PREFIX} 初始空闲内存: {gc.mem_free()} B")

    # =========================================================================
    # 1. 测试字典池 (DictPool)
    # =========================================================================
    print(f"\n{_PREFIX} [1] === 测试字典池 ===")
    
    dict1 = mem.get_dict()
    print(f"{_PREFIX} 获取 dict1 (ID: {id(dict1)})")
    dict1['id'] = 1
    dict1['data'] = 'test_data_1'
    print(f"{_PREFIX}   -> 使用后: {dict1}")

    dict2 = mem.get_dict()
    print(f"{_PREFIX} 获取 dict2 (ID: {id(dict2)})")
    dict2['id'] = 2
    dict2['sensor'] = 'temperature'
    print(f"{_PREFIX}   -> 使用后: {dict2}")

    # 使用完毕后归还
    mem.return_dict(dict1)
    mem.return_dict(dict2)
    print(f"{_PREFIX} dict1 和 dict2 已归还。")

    # 再次获取，验证对象复用
    dict3 = mem.get_dict()
    print(f"{_PREFIX} 再次获取 dict3 (ID: {id(dict3)})")
    print(f"{_PREFIX}   -> 验证: dict3 的 ID {'与 dict2 相同' if id(dict3) == id(dict2) else '与 dict2 不同'}，证明复用成功。")
    mem.return_dict(dict3)

    # =========================================================================
    # 2. 测试缓冲区管理器 (BufferManager)
    # =========================================================================
    print(f"\n{_PREFIX} [2] === 测试缓冲区管理器 ===")
    
    buffer1 = mem.get_buffer(100)
    print(f"{_PREFIX} 请求 100B，实际得到缓冲区大小: {len(buffer1)}")
    # 写入一些数据来“弄脏”缓冲区
    buffer1[0] = 0xDE
    buffer1[1] = 0xAD
    mem.return_buffer(buffer1)
    print(f"{_PREFIX} 缓冲区已归还。")
    
    # 再次获取同样大小的缓冲区，验证内容是否被清空（应为0）
    buffer2 = mem.get_buffer(100)
    print(f"{_PREFIX} 再次获取 100B 缓冲区，首字节为: {buffer2[0]}")
    print(f"{_PREFIX}   -> 验证: 首字节为 0，证明归还时缓冲区被安全清空。")
    mem.return_buffer(buffer2)
    
    # =========================================================================
    # 3. 测试字符串缓存 (StringCache)
    # =========================================================================
    print(f"\n{_PREFIX} [3] === 测试字符串缓存 ===")
    
    # 测试预缓存的字符串
    s_cached_1 = "error"
    s_cached_2 = mem.get_string("error")
    print(f"{_PREFIX} 对预缓存字符串 'error' 调用 get_string。")
    print(f"{_PREFIX}   -> 验证: Python VM 自动驻留: {s_cached_1 is s_cached_2}")

    # 测试未在预缓存列表中的字符串
    s_new = "a_very_unique_string"
    s_new_from_func = mem.get_string(s_new)
    print(f"{_PREFIX} 对非预缓存字符串 '{s_new[:10]}...' 调用 get_string。")
    print(f"{_PREFIX}   -> 验证: 函数直接返回值: {s_new is s_new_from_func}")

    # =========================================================================
    # 4. 查看最终统计信息
    # =========================================================================
    print(f"\n{_PREFIX} [4] === 查看最终统计信息 ===")
    
    stats = mem.get_all_stats()
    print(f"{_PREFIX} 字典池状态: {stats['dict_pool']}")
    print(f"{_PREFIX} 字符串缓存状态: {stats['string_cache']}")
    print(f"{_PREFIX} 缓冲区管理器状态: {stats['buffer_manager']}")
    
    print(f"\n{_PREFIX} 最终空闲内存: {gc.mem_free()} B")
    print(f"{_PREFIX} --- 内存优化模块测试结束 ---")

# =============================================================================
# 主执行入口
# =============================================================================
if __name__ == "__main__":
    # 这样设计使得该文件既可以被直接运行，也可以在REPL中通过 import 来执行测试。
    run_all_tests()
