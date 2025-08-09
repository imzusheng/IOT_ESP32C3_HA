"""
boot.py
"""

import sys
import gc

# 添加 lib 目录到 Python 搜索路径
# 这样就可以使用 from lib.module import Class 的导入方式
sys.path.append('/lib')

# 初始化垃圾回收
gc.collect()