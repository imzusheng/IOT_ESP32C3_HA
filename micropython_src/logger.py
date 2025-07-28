# logger.py
import os
import daemon

LOG_FILE = 'error.log'
MAX_LOG_SIZE = 10 * 1024  # 日志文件最大为 10 KB

def _rotate_log():
    """如果日志文件过大，则进行滚动备份。"""
    try:
        # os.stat() 用于获取文件状态，第6个元素是文件大小
        size = os.stat(LOG_FILE)[6]
        if size > MAX_LOG_SIZE:
            # 删除旧的备份文件（如果存在）
            if 'error.log.bak' in os.listdir():
                os.remove('error.log.bak')
            # 将当前日志文件重命名为备份文件
            os.rename(LOG_FILE, 'error.log.bak')
    except OSError:
        # 如果 error.log 文件不存在，则什么都不做
        pass

def process_log_queue():
    """
    处理守护进程的日志队列，将消息写入文件。
    这个函数应该在主循环中被调用。
    """
    log_queue = daemon.get_log_queue()
    if not log_queue:
        return # 队列为空，直接返回

    # 先检查是否需要滚动日志
    _rotate_log()
    
    try:
        # a+ 模式：如果文件不存在则创建，如果存在则在末尾追加
        with open(LOG_FILE, 'a+') as f:
            while log_queue:
                # 从队列头部取出一个条目并写入文件
                f.write(log_queue.pop(0))
    except Exception as e:
        print(f"[Logger] 写入日志失败: {e}")