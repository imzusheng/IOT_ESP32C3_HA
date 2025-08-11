# test_logger.py - Logger 全功能测试
# 专为 MicroPython 环境设计，测试基于 ulogging 的日志系统
import sys
try:
    import utime as time
except ImportError:
    import time

# MicroPython-compatible path handling
try:
    import os
    # Robust cross-platform parent directory insertion
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
except Exception:
    # Fallback for MicroPython or restricted environments
    if '..' not in sys.path:
        sys.path.insert(0, '..')

# 导入 logger 模块和相关依赖
# EventBus dependency removed - Logger now works independently
try:
    from lib.logger import Logger, get_global_logger, set_global_logger, debug, info, warning, error, critical
    from lib.event_bus import EVENTS
except ImportError:
    print("错误：无法导入Logger或相关模块。请确保文件在正确位置。")
    sys.exit(1)

# Define log levels locally since EVENT constants are no longer needed
class LogLevel:
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARN = 'WARN'
    ERROR = 'ERROR'

# 全局变量用于测试
test_results = []
test_count = 0
passed_count = 0
captured_logs = []

def log_test_result(test_name, passed, message=""):
    """记录测试结果"""
    global test_count, passed_count
    test_count += 1
    if passed:
        passed_count += 1
        status = "通过"
    else:
        status = "失败"
    
    print(f"[Test] {test_name}: {status}")
    if message:
        print(f"      {message}")
    
    test_results.append((test_name, passed, message))

# 模拟输出捕获器，用于捕获日志输出
class LogCapture:
    """用于捕获日志输出的模拟类"""
    def __init__(self):
        self.logs = []
    
    def write(self, msg):
        """捕获写入的日志消息"""
        if msg.strip():  # 忽略空行
            self.logs.append(msg.strip())
    
    def get_logs(self):
        """获取所有捕获的日志"""
        return self.logs.copy()
    
    def clear(self):
        """清空捕获的日志"""
        self.logs.clear()

# 全局日志捕获器
log_capture = LogCapture()

def test_logger_initialization():
    """测试 Logger 基本初始化"""
    try:
        # 测试默认级别初始化
        logger1 = Logger()
        
        # 测试指定级别初始化
        logger2 = Logger(LogLevel.DEBUG)
        logger3 = Logger(LogLevel.ERROR)
        
        # 验证实例是否创建成功 - Logger现在独立工作，不依赖EventBus
        has_logger_attr = hasattr(logger1, '_logger')
        has_level_map = hasattr(logger1, '_level_map')
        
        if has_logger_attr and has_level_map:
            log_test_result("Logger初始化", True)
            return True
        else:
            log_test_result("Logger初始化", False, "缺少必需的实例属性")
            return False
            
    except Exception as e:
        log_test_result("Logger初始化", False, f"初始化异常: {e}")
        return False

def test_logger_basic_functionality():
    """测试 Logger 基本功能"""
    try:
        # 创建日志器
        logger = Logger(LogLevel.INFO)
        
        # 验证基本属性
        has_logger_attr = hasattr(logger, '_logger')
        has_level_map = hasattr(logger, '_level_map')
        
        # 测试级别设置
        logger.set_level(LogLevel.DEBUG)
        level_set_correctly = logger._level == logger._level_map[LogLevel.DEBUG]
        
        if has_logger_attr and has_level_map and level_set_correctly:
            log_test_result("Logger基本功能", True)
            return True
        else:
            log_test_result("Logger基本功能", False, 
                           f"属性检查: logger={has_logger_attr}, level_map={has_level_map}, level_set={level_set_correctly}")
            return False
            
    except Exception as e:
        log_test_result("Logger基本功能", False, f"功能测试异常: {e}")
        return False

def test_log_level_setting():
    """测试日志级别设置功能"""
    try:
        logger = Logger(LogLevel.INFO)
        
        # 测试设置不同级别
        test_levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR]
        
        for level in test_levels:
            logger.set_level(level)
            expected_internal_level = logger._level_map[level]
            
            if logger._level != expected_internal_level:
                log_test_result("日志级别设置", False, f"级别 {level} 设置失败")
                return False
        
        log_test_result("日志级别设置", True)
        return True
        
    except Exception as e:
        log_test_result("日志级别设置", False, f"级别设置异常: {e}")
        return False

def test_direct_logging_methods():
    """测试直接日志记录方法"""
    global captured_logs
    captured_logs = []
    
    # 创建一个简单的日志记录回调来捕获日志
    def capture_callback(event_name, msg, *args):
        global captured_logs
        try:
            formatted_msg = msg.format(*args)
        except:
            formatted_msg = msg
        captured_logs.append((event_name, formatted_msg))
    
    try:
        logger = Logger(LogLevel.DEBUG)  # 设置为最低级别以捕获所有日志
        
        # 手动设置捕获回调
        logger._handle_log = capture_callback
        
        # 测试各种直接记录方法
        test_messages = [
            ("debug", "调试消息: {}", "参数1"),
            ("info", "信息消息: {}", "参数2"),
            ("warning", "警告消息: {}", "参数3"),
            ("error", "错误消息: {}", "参数4"),
            ("critical", "严重错误消息: {}", "参数5")
        ]
        
        for method_name, msg, arg in test_messages:
            method = getattr(logger, method_name)
            method(msg, arg)
        
        # 等待处理完成
        time.sleep(0.1)
        
        # 验证是否捕获了所有日志（除了critical特殊处理）
        expected_count = 4  # debug, info, warning, error (critical 特殊处理)
        
        if len(captured_logs) >= expected_count:
            log_test_result("直接日志记录方法", True)
            return True
        else:
            log_test_result("直接日志记录方法", False, 
                           f"期望至少 {expected_count} 条日志，实际捕获 {len(captured_logs)} 条")
            return False
            
    except Exception as e:
        log_test_result("直接日志记录方法", False, f"直接记录异常: {e}")
        return False

def test_logger_output_capture():
    """测试 Logger 输出捕获"""
    global captured_output
    captured_output = []
    
    def capture_print(*args, **kwargs):
        global captured_output
        if args:
            captured_output.append(str(args[0]))
    
    try:
        # 创建日志器
        logger = Logger(EVENTS.LOG_DEBUG)
        
        # 临时替换 print 函数来捕获输出
        import builtins
        original_print = builtins.print
        builtins.print = capture_print
        
        try:
            # 测试各种日志级别
            logger.debug("调试消息: {}", "调试参数")
            logger.info("信息消息: {}", "信息参数")
            logger.warning("警告消息: {}", "警告参数")
            logger.error("错误消息: {}", "错误参数")
            
            # 等待处理完成
            time.sleep(0.1)
            
            # 验证是否捕获了输出
            if len(captured_output) >= 4:
                log_test_result("Logger输出捕获", True)
                return True
            else:
                log_test_result("Logger输出捕获", False, 
                               f"期望至少4条输出，实际捕获 {len(captured_output)} 条")
                return False
        finally:
            # 恢复原始 print 函数
            builtins.print = original_print
            
    except Exception as e:
        log_test_result("Logger输出捕获", False, f"输出捕获异常: {e}")
        return False

def test_log_message_formatting():
    """测试日志消息格式化功能"""
    global formatting_logs
    formatting_logs = []
    
    def formatting_callback(event_name, msg, *args):
        global formatting_logs
        try:
            formatted_msg = msg.format(*args)
        except:
            formatted_msg = msg
        formatting_logs.append(formatted_msg)
    
    try:
        logger = Logger(LogLevel.INFO)
        logger._handle_log = formatting_callback
        
        # 测试不同类型的格式化
        test_cases = [
            ("简单字符串", []),
            ("单个参数: {}", ["值1"]),
            ("多个参数: {} 和 {}", ["值2", "值3"]),
            ("命名参数: {name} 年龄 {age}", []),  # 这个会失败，因为使用位置参数
            ("混合内容: 数字{} 字符串{}", [42, "测试"])
        ]
        
        for msg, args in test_cases:
            if args:
                logger.info(msg, *args)
            else:
                logger.info(msg)
        
        # 等待处理完成
        time.sleep(0.1)
        
        # 验证是否处理了所有格式化
        expected_results = [
            "简单字符串",
            "单个参数: 值1",
            "多个参数: 值2 和 值3",
            "命名参数: {name} 年龄 {age}",  # 无参数时保持原样
            "混合内容: 数字42 字符串测试"
        ]
        
        success_count = 0
        for i, expected in enumerate(expected_results):
            if i < len(formatting_logs):
                if expected in formatting_logs[i] or formatting_logs[i] == expected:
                    success_count += 1
        
        if success_count >= 4:  # 至少4个成功
            log_test_result("日志消息格式化", True)
            return True
        else:
            log_test_result("日志消息格式化", False, 
                           f"格式化成功 {success_count}/{len(expected_results)} 个测试")
            return False
            
    except Exception as e:
        log_test_result("日志消息格式化", False, f"格式化异常: {e}")
        return False

def test_log_level_filtering():
    """测试日志级别过滤功能"""
    global filtered_logs
    filtered_logs = []
    
    try:
        # 创建INFO级别的日志器
        logger = Logger(LogLevel.INFO)
    
        # 通过替换底层 ulogging 的方法来捕获真正通过过滤的日志调用
        def dbg(msg):
            filtered_logs.append(LogLevel.DEBUG)
        def inf(msg):
            filtered_logs.append(LogLevel.INFO)
        def warn(msg):
            filtered_logs.append(LogLevel.WARN)
        def err(msg):
            filtered_logs.append(LogLevel.ERROR)
    
        # 替换底层记录器的方法（不替换 _handle_log，保留其级别过滤逻辑）
        logger._logger.debug = dbg
        logger._logger.info = inf
        logger._logger.warning = warn
        logger._logger.error = err
    
        # 测试不同级别的日志是否被正确过滤
        logger.debug("这是DEBUG日志")    # 应该被过滤（不会触发 dbg）
        logger.info("这是INFO日志")      # 应该通过（触发 inf）
        logger.warning("这是WARNING日志") # 应该通过（触发 warn）
        logger.error("这是ERROR日志")    # 应该通过（触发 err）
    
        # 等待处理完成
        time.sleep(0.1)
    
        # 验证过滤结果：只有INFO、WARNING、ERROR应该通过
        expected_events = [LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR]
    
        # 检查是否只包含期望的事件，且DEBUG被过滤
        has_debug = LogLevel.DEBUG in filtered_logs
        has_expected = all(event in filtered_logs for event in expected_events)
    
        if not has_debug and has_expected:
            log_test_result("日志级别过滤", True)
            return True
        else:
            log_test_result("日志级别过滤", False, 
                           f"过滤失败: DEBUG存在={has_debug}, 期望事件完整={has_expected}, 实际事件={filtered_logs}")
            return False
    
    except Exception as e:
        log_test_result("日志级别过滤", False, f"级别过滤异常: {e}")
        return False

def test_global_logger_functions():
    """测试全局日志函数"""
    try:
        # 测试获取全局日志器
        global_logger1 = get_global_logger()
        global_logger2 = get_global_logger()
        
        # 应该返回相同的实例
        is_same_instance = global_logger1 is global_logger2
        
        # 测试设置全局日志器
        custom_logger = Logger(LogLevel.DEBUG)
        set_global_logger(custom_logger)
        
        global_logger3 = get_global_logger()
        is_custom_logger = global_logger3 is custom_logger
        
        # 测试全局便捷函数是否能执行（不抛出异常）
        try:
            debug("全局调试消息")
            info("全局信息消息")
            warning("全局警告消息")
            error("全局错误消息")
            critical("全局严重错误消息")
            functions_work = True
        except Exception as e:
            functions_work = False
            function_error = str(e)
        
        if is_same_instance and is_custom_logger and functions_work:
            log_test_result("全局日志函数", True)
            return True
        else:
            error_msg = f"单例模式: {is_same_instance}, 自定义设置: {is_custom_logger}, 函数工作: {functions_work}"
            if not functions_work:
                error_msg += f", 函数错误: {function_error}"
            log_test_result("全局日志函数", False, error_msg)
            return False
            
    except Exception as e:
        log_test_result("全局日志函数", False, f"全局函数异常: {e}")
        return False

def test_direct_logger_methods():
    """测试直接调用 Logger 方法"""
    global helper_logs
    helper_logs = []
    
    def capture_output(msg):
        global helper_logs
        helper_logs.append(msg)
    
    try:
        # 创建 Logger 实例
        logger = Logger(LogLevel.INFO)
        
        # 重定向输出来捕获日志
        import sys
        original_print = print
        
        def mock_print(*args, **kwargs):
            if args:
                capture_output(str(args[0]))
        
        # 临时替换 print 函数
        import builtins
        builtins.print = mock_print
        
        try:
            # 直接调用 logger 方法
            logger.info("直接调用测试: {}", "参数值")
            
            # 等待处理完成
            time.sleep(0.1)
            
            # 验证是否正确输出
            if len(helper_logs) > 0:
                output = helper_logs[0]
                if "直接调用测试: 参数值" in output:
                    log_test_result("直接 Logger 方法调用", True)
                    return True
            
            log_test_result("直接 Logger 方法调用", False, f"输出失败，捕获: {helper_logs}")
            return False
        finally:
            # 恢复原始 print 函数
            builtins.print = original_print
        
    except Exception as e:
        log_test_result("直接 Logger 方法调用", False, f"调用异常: {e}")
        return False

def test_error_handling():
    """测试日志系统的错误处理"""
    try:
        logger = Logger(LogLevel.INFO)
        
        # 测试格式化错误的处理
        error_count = 0
        
        try:
            # 这应该不会抛出异常，而是使用原始消息
            logger.info("格式化错误: {invalid}", "多余参数", "另一个多余参数")
        except:
            error_count += 1
        
        try:
            # 测试None参数
            logger.info("包含None: {}", None)
        except:
            error_count += 1
        
        try:
            # 测试空参数
            logger.info("空消息", )
        except:
            error_count += 1
        
        # 如果没有抛出异常，说明错误处理工作正常
        if error_count == 0:
            log_test_result("错误处理机制", True)
            return True
        else:
            log_test_result("错误处理机制", False, f"有 {error_count} 个操作抛出了异常")
            return False
            
    except Exception as e:
        log_test_result("错误处理机制", False, f"错误处理测试异常: {e}")
        return False

def reset_test_results():
    """重置测试结果"""
    global test_results, test_count, passed_count
    test_results = []
    test_count = 0
    passed_count = 0

def print_test_summary():
    """打印测试结果摘要"""
    print("\n" + "=" * 50)
    print("Logger测试结果摘要")
    print("=" * 50)
    print(f"总测试数: {test_count}")
    print(f"通过: {passed_count}")
    print(f"失败: {test_count - passed_count}")
    if test_count > 0:
        print(f"成功率: {passed_count / test_count * 100:.1f}%")
    
    if passed_count == test_count:
        print("\n所有测试通过！Logger功能正常工作。")
    else:
        print("\n部分测试失败。请查看上方的详细测试结果。")
        
    print("\n详细测试结果：")
    for test_name, passed, message in test_results:
        status = "✓" if passed else "✗"
        print(f"  {status} {test_name}")
        if message:
            print(f"    {message}")

def run_all_tests():
    """运行所有测试"""
    reset_test_results()
    print("=" * 50)
    print("运行所有Logger功能测试")
    print("=" * 50)
    
    # 运行所有测试
    test_logger_initialization()
    test_logger_basic_functionality()
    test_log_level_setting()
    test_direct_logging_methods()
    test_logger_output_capture()
    test_log_message_formatting()
    test_log_level_filtering()
    test_global_logger_functions()
    test_direct_logger_methods()
    test_error_handling()
    
    # 打印测试摘要
    print_test_summary()

# 如果直接运行此文件，执行所有测试
if __name__ == "__main__":
    run_all_tests()
