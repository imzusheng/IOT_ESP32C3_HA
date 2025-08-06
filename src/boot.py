import gc
import sys

# 添加lib目录到模块搜索路径
sys.path.append('./lib')

# gc.threshold(50000)
gc.collect()