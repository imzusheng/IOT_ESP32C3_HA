# test_logger.py - Logger 全功能测试
# 专为 MicroPython 环境设计，测试基于 ulogging 的日志系统
import sys
import utime as time

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
try:
    from lib.logger import Logger, log, get_global_logger, set_global_logger, debug, info, warning, error, critical
    from lib.event_bus import EventBus
    from event_const import EVENT
except ImportError:
    print("错误：无法导入Logger或相关模块。请确保文件在正确位置。")
    sys.exit(1)

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
        logger2 = Logger(EVENT.LOG_DEBUG)
        logger3 = Logger(EVENT.LOG_ERROR)
        
        # 验证实例是否创建成功
        has_logger_attr = hasattr(logger1, '_logger')
        has_level_map = hasattr(logger1, '_level_map')
        has_event_bus_ref = hasattr(logger1, '_event_bus')
        
        if has_logger_attr and has_level_map and has_event_bus_ref:
            log_test_result("Logger初始化", True)
            return True
        else:
            log_test_result("Logger初始化", False, "缺少必需的实例属性")
            return False
            
    except Exception as e:
        log_test_result("Logger初始化", False, f"初始化异常: {e}")
        return False

def test_event_bus_setup():
    """测试 Logger 与事件总线的集成"""
    try:
        # 创建事件总线和日志器
        event_bus = EventBus(verbose=True)
        logger = Logger(EVENT.LOG_INFO)
        
        # 设置事件总线
        logger.setup(event_bus)
        
        # 验证事件总线引用是否设置
        bus_reference_set = logger._event_bus is event_bus
        
        # 验证是否订阅了日志事件
        has_debug_subscribers = event_bus.has_subscribers(EVENT.LOG_DEBUG)
        has_info_subscribers = event_bus.has_subscribers(EVENT.LOG_INFO)
        has_warn_subscribers = event_bus.has_subscribers(EVENT.LOG_WARN)
        has_error_subscribers = event_bus.has_subscribers(EVENT.LOG_ERROR)
        
        # 等待事件订阅完成
        time.sleep(0.1)
        
        if bus_reference_set and has_info_subscribers and has_warn_subscribers and has_error_subscribers:
            log_test_result("事件总线集成", True)
            return True
        else:
            log_test_result("事件总线集成", False, 
                           f"总线引用: {bus_reference_set}, 订阅状态: DEBUG={has_debug_subscribers}, INFO={has_info_subscribers}, WARN={has_warn_subscribers}, ERROR={has_error_subscribers}")
            return False
            
    except Exception as e:
        log_test_result("事件总线集成", False, f"集成异常: {e}")
        return False

def test_log_level_setting():
    """测试日志级别设置功能"""
    try:
        logger = Logger(EVENT.LOG_INFO)
        
        # 测试设置不同级别
        test_levels = [EVENT.LOG_DEBUG, EVENT.LOG_INFO, EVENT.LOG_WARN, EVENT.LOG_ERROR]
        
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
        logger = Logger(EVENT.LOG_DEBUG)  # 设置为最低级别以捕获所有日志
        
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

def test_event_driven_logging():
    """测试通过事件总线的日志记录"""
    global event_driven_logs
    event_driven_logs = []
    
    def event_log_callback(event_name, msg, *args):
        global event_driven_logs
        try:
            formatted_msg = msg.format(*args)
        except:
            formatted_msg = msg
        event_driven_logs.append((event_name, formatted_msg))
    
    try:
        # 创建事件总线和日志器
        event_bus = EventBus(verbose=True)
        logger = Logger(EVENT.LOG_DEBUG)
        
        # 替换处理方法以捕获日志
        logger._handle_log = event_log_callback
        
        # 设置事件总线
        logger.setup(event_bus)
        
        # 通过事件总线发布日志事件
        test_events = [
            (EVENT.LOG_DEBUG, "事件调试: {}", "调试参数"),
            (EVENT.LOG_INFO, "事件信息: {}", "信息参数"),
            (EVENT.LOG_WARN, "事件警告: {}", "警告参数"),
            (EVENT.LOG_ERROR, "事件错误: {}", "错误参数")
        ]
        
        for event, msg, arg in test_events:
            event_bus.publish(event, msg, arg)
        
        # 等待异步事件处理完成
        time.sleep(0.2)
        
        # 验证是否收到了所有事件驱动的日志
        if len(event_driven_logs) >= len(test_events):
            log_test_result("事件驱动日志记录", True)
            return True
        else:
            log_test_result("事件驱动日志记录", False, 
                           f"期望 {len(test_events)} 条日志，实际收到 {len(event_driven_logs)} 条")
            return False
            
    except Exception as e:
        log_test_result("事件驱动日志记录", False, f"事件驱动记录异常: {e}")
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
        logger = Logger(EVENT.LOG_INFO)
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
        logger = Logger(EVENT.LOG_INFO)
    
        # 通过替换底层 ulogging 的方法来捕获真正通过过滤的日志调用
        def dbg(msg):
            filtered_logs.append(EVENT.LOG_DEBUG)
        def inf(msg):
            filtered_logs.append(EVENT.LOG_INFO)
        def warn(msg):
            filtered_logs.append(EVENT.LOG_WARN)
        def err(msg):
            filtered_logs.append(EVENT.LOG_ERROR)
    
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
        expected_events = [EVENT.LOG_INFO, EVENT.LOG_WARN, EVENT.LOG_ERROR]
    
        # 检查是否只包含期望的事件，且DEBUG被过滤
        has_debug = EVENT.LOG_DEBUG in filtered_logs
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
        custom_logger = Logger(EVENT.LOG_DEBUG)
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

def test_log_helper_function():
    """测试 log 辅助函数"""
    global helper_logs
    helper_logs = []
    
    def helper_callback(event_name, msg, *args):
        global helper_logs
        helper_logs.append((event_name, msg, args))
    
    try:
        # 创建事件总线
        event_bus = EventBus(verbose=True)
        
        # 替换发布方法来捕获
        event_bus.publish = helper_callback
        
        # 使用 log 辅助函数
        log(event_bus, EVENT.LOG_INFO, "辅助函数测试: {}", "参数值")
        
        # 等待处理完成
        time.sleep(0.1)
        
        # 验证是否正确调用
        if len(helper_logs) > 0:
            event_name, msg, args = helper_logs[0]
            if (event_name == EVENT.LOG_INFO and 
                "辅助函数测试" in msg and 
                args == ("参数值",)):
                log_test_result("log 辅助函数", True)
                return True
        
        log_test_result("log 辅助函数", False, f"辅助函数调用失败，捕获: {helper_logs}")
        return False
        
    except Exception as e:
        log_test_result("log 辅助函数", False, f"辅助函数异常: {e}")
        return False

def test_error_handling():
    """测试日志系统的错误处理"""
    try:
        logger = Logger(EVENT.LOG_INFO)
        
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
    test_event_bus_setup()
    test_log_level_setting()
    test_direct_logging_methods()
    test_event_driven_logging()
    test_log_message_formatting()
    test_log_level_filtering()
    test_global_logger_functions()
    test_log_helper_function()
    test_error_handling()
    
    # 打印测试摘要
    print_test_summary()

# 如果直接运行此文件，执行所有测试
if __name__ == "__main__":
    run_all_tests()
