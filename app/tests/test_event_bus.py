# test_event_bus.py - EventBus 全功能测试
# 专为 MicroPython 环境设计
import sys
try:
    import utime as time
except ImportError:
    import time
import gc

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

# Import EventBus module
try:
    from lib.event_bus import EventBus
    from lib.event_bus.events_const import EVENTS
except ImportError:
    print("错误：无法导入EventBus。请确保event_bus包在正确位置。")
    sys.exit(1)

# 全局变量用于测试
test_results = []
test_count = 0
passed_count = 0

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

# 测试回调函数
def simple_callback(event_name):
    """简单回调函数，接收event_name"""
    global simple_callback_called
    simple_callback_called = True

def callback_with_args(event_name, arg1, arg2):
    """带位置参数的回调函数"""
    global callback_args_received
    callback_args_received = (arg1, arg2)

def callback_with_kwargs(event_name, **kwargs):
    """带关键字参数的回调函数"""
    global callback_kwargs_received
    callback_kwargs_received = kwargs

def callback_with_mixed(event_name, arg1, arg2, kwarg1=None, kwarg2=None):
    """混合参数的回调函数"""
    global callback_mixed_received
    callback_mixed_received = {
        'args': (arg1, arg2),
        'kwargs': {'kwarg1': kwarg1, 'kwarg2': kwarg2}
    }

def error_callback(event_name):
    """会抛出异常的回调函数"""
    raise ValueError("这是一个测试异常")

def system_error_callback(event_name, *args, **kwargs):
    """系统错误回调函数"""
    global system_error_received
    # EventBus 可能以不同方式传递参数，尝试多种方式获取错误上下文
    if args:
        # 如果有位置参数，第一个应该是错误上下文
        error_context = args[0]
        # 检查错误上下文的类型
        if isinstance(error_context, dict):
            # 如果是字典，检查是否已经是 EventBus 传递的标准格式
            if "source" in error_context and error_context.get("source") == "event_bus":
                # 已经是标准格式，直接使用
                system_error_received = error_context
            else:
                # 不是标准格式，包装成标准格式
                system_error_received = {
                    "source": "event_bus",
                    "error_type": "event_callback",
                    "error_message": str(error_context),
                    "raw_data": error_context
                }
        elif isinstance(error_context, str):
            # 如果是字符串，创建一个包含字符串的错误上下文字典
            system_error_received = {
                "source": "event_bus",
                "error_type": "event_callback",
                "error_message": error_context,
                "raw_data": error_context
            }
        else:
            # 其他类型，尝试转换为字典或创建包含该对象的错误上下文
            try:
                if hasattr(error_context, '__dict__'):
                    # 如果对象有 __dict__ 属性，使用它
                    system_error_received = error_context.__dict__
                else:
                    # 否则创建一个包含该对象的错误上下文
                    system_error_received = {
                        "source": "event_bus",
                        "error_type": "event_callback",
                        "raw_data": str(error_context)
                    }
            except Exception:
                # 如果转换失败，创建一个基本的错误上下文
                system_error_received = {
                    "source": "event_bus",
                    "error_type": "event_callback",
                    "error_message": "无法解析错误上下文",
                    "raw_data": str(error_context)
                }
    elif 'error_context' in kwargs:
        # 如果有关键字参数 error_context
        error_context = kwargs['error_context']
        if isinstance(error_context, dict):
            # 检查是否已经是 EventBus 传递的标准格式
            if "source" in error_context and error_context.get("source") == "event_bus":
                # 已经是标准格式，直接使用
                system_error_received = error_context
            else:
                # 不是标准格式，包装成标准格式
                system_error_received = {
                    "source": "event_bus",
                    "error_type": "event_callback",
                    "error_message": str(error_context),
                    "raw_data": error_context
                }
        else:
            system_error_received = {
                "source": "event_bus",
                "error_type": "event_callback",
                "error_message": str(error_context),
                "raw_data": str(error_context)
            }
    elif kwargs:
        # 如果有其他关键字参数，取第一个
        error_context = next(iter(kwargs.values()))
        if isinstance(error_context, dict):
            # 检查是否已经是 EventBus 传递的标准格式
            if "source" in error_context and error_context.get("source") == "event_bus":
                # 已经是标准格式，直接使用
                system_error_received = error_context
            else:
                # 不是标准格式，包装成标准格式
                system_error_received = {
                    "source": "event_bus",
                    "error_type": "event_callback",
                    "error_message": str(error_context),
                    "raw_data": error_context
                }
        else:
            system_error_received = {
                "source": "event_bus",
                "error_type": "event_callback",
                "error_message": str(error_context),
                "raw_data": str(error_context)
            }
    else:
        # 没有参数，设置为 None
        system_error_received = None

def test_basic_subscribe_publish():
    """测试基本订阅和发布功能"""
    global simple_callback_called
    simple_callback_called = False
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 订阅事件
    event_bus.subscribe("test.event", simple_callback)
    
    # 发布事件
    event_bus.publish("test.event")
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证回调是否被调用
    if simple_callback_called:
        log_test_result("基本订阅和发布", True)
        return True
    else:
        log_test_result("基本订阅和发布", False, "回调函数未被调用")
        return False

def test_multiple_subscribers():
    """测试多个订阅者订阅同一事件"""
    global callback1_called, callback2_called, callback3_called
    callback1_called = False
    callback2_called = False
    callback3_called = False
    
    def callback1(event_name):
        global callback1_called
        callback1_called = True
    
    def callback2(event_name):
        global callback2_called
        callback2_called = True
    
    def callback3(event_name):
        global callback3_called
        callback3_called = True
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 多个订阅者订阅同一事件
    event_bus.subscribe("multi.event", callback1)
    event_bus.subscribe("multi.event", callback2)
    event_bus.subscribe("multi.event", callback3)
    
    # 发布事件
    event_bus.publish("multi.event")
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证所有回调是否被调用
    if callback1_called and callback2_called and callback3_called:
        log_test_result("多个订阅者", True)
        return True
    else:
        log_test_result("多个订阅者", False, 
                       f"回调调用状态: callback1={callback1_called}, callback2={callback2_called}, callback3={callback3_called}")
        return False

def test_unsubscribe():
    """测试取消订阅功能"""
    global callback_called_after_unsubscribe
    callback_called_after_unsubscribe = False
    
    def callback(event_name):
        global callback_called_after_unsubscribe
        callback_called_after_unsubscribe = True
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 订阅事件
    event_bus.subscribe("unsubscribe.event", callback)
    
    # 取消订阅
    event_bus.unsubscribe("unsubscribe.event", callback)
    
    # 发布事件
    event_bus.publish("unsubscribe.event")
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证回调是否未被调用
    if not callback_called_after_unsubscribe:
        log_test_result("取消订阅", True)
        return True
    else:
        log_test_result("取消订阅", False, "取消订阅后回调仍被调用")
        return False

def test_args_passing():
    """测试事件参数传递（位置参数）"""
    global callback_args_received
    callback_args_received = None
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 订阅事件
    event_bus.subscribe("args.event", callback_with_args)
    
    # 发布带参数的事件
    test_arg1 = "测试参数1"
    test_arg2 = 42
    event_bus.publish("args.event", test_arg1, test_arg2)
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证参数是否正确传递
    if callback_args_received == (test_arg1, test_arg2):
        log_test_result("位置参数传递", True)
        return True
    else:
        log_test_result("位置参数传递", False, 
                       f"期望: {(test_arg1, test_arg2)}, 实际: {callback_args_received}")
        return False

def test_kwargs_passing():
    """测试事件参数传递（关键字参数）"""
    global callback_kwargs_received
    callback_kwargs_received = None
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 订阅事件
    event_bus.subscribe("kwargs.event", callback_with_kwargs)
    
    # 发布带关键字参数的事件
    test_kwargs = {"key1": "值1", "key2": 123}
    event_bus.publish("kwargs.event", **test_kwargs)
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证参数是否正确传递
    if callback_kwargs_received == test_kwargs:
        log_test_result("关键字参数传递", True)
        return True
    else:
        log_test_result("关键字参数传递", False, 
                       f"期望: {test_kwargs}, 实际: {callback_kwargs_received}")
        return False

def test_mixed_args_passing():
    """测试事件参数传递（混合参数）"""
    global callback_mixed_received
    callback_mixed_received = None
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 订阅事件
    event_bus.subscribe("mixed.event", callback_with_mixed)
    
    # 发布带混合参数的事件
    test_arg1 = "位置参数1"
    test_arg2 = "位置参数2"
    test_kwarg1 = "关键字参数1"
    test_kwarg2 = "关键字参数2"
    
    event_bus.publish("mixed.event", test_arg1, test_arg2, 
                      kwarg1=test_kwarg1, kwarg2=test_kwarg2)
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证参数是否正确传递
    expected = {
        'args': (test_arg1, test_arg2),
        'kwargs': {'kwarg1': test_kwarg1, 'kwarg2': test_kwarg2}
    }
    
    if callback_mixed_received == expected:
        log_test_result("混合参数传递", True)
        return True
    else:
        log_test_result("混合参数传递", False, 
                       f"期望: {expected}, 实际: {callback_mixed_received}")
        return False

def test_introspection_tools():
    """测试内省与调试工具"""
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 记录测试开始前的事件列表
    events_before_test = set(event_bus.list_events())
    
    # 定义几个测试回调
    def test_callback1(event_name):
        pass
    
    def test_callback2(event_name):
        pass
    
    # 订阅几个事件
    event_bus.subscribe("introspect.event1", test_callback1)
    event_bus.subscribe("introspect.event1", test_callback2)
    event_bus.subscribe("introspect.event2", test_callback1)
    
    # 等待订阅完成
    time.sleep(0.1)
    
    # 测试 list_events
    events = event_bus.list_events()
    expected_events = ["introspect.event1", "introspect.event2"]
    
    # 只检查当前测试添加的事件，过滤掉之前测试中已经存在的事件
    current_test_events = [event for event in events if event not in events_before_test]
    events_correct = set(current_test_events) == set(expected_events)
    
    # 测试 list_subscribers
    subscribers1 = event_bus.list_subscribers("introspect.event1")
    subscribers2 = event_bus.list_subscribers("introspect.event2")
    
    # 订阅者数量应该正确
    subscribers1_correct = len(subscribers1) == 2
    subscribers2_correct = len(subscribers2) == 1
    
    # 测试 has_subscribers
    has_sub1 = event_bus.has_subscribers("introspect.event1")
    has_sub2 = event_bus.has_subscribers("introspect.event2")
    has_sub3 = event_bus.has_subscribers("nonexistent.event")
    
    has_subscribers_correct = has_sub1 and has_sub2 and not has_sub3
    
    # 详细调试信息
    debug_info = f"测试前事件: {events_before_test}\n"
    debug_info += f"当前事件列表: {events}, 当前测试事件: {current_test_events}, 期望: {expected_events}, 匹配: {events_correct}\n"
    debug_info += f"订阅者1: {subscribers1}, 数量: {len(subscribers1)}, 正确: {subscribers1_correct}\n"
    debug_info += f"订阅者2: {subscribers2}, 数量: {len(subscribers2)}, 正确: {subscribers2_correct}\n"
    debug_info += f"has_subscribers: {has_sub1}, {has_sub2}, {not has_sub3}, 全部正确: {has_subscribers_correct}"
    
    if events_correct and subscribers1_correct and subscribers2_correct and has_subscribers_correct:
        log_test_result("内省与调试工具", True)
        return True
    else:
        log_test_result("内省与调试工具", False, debug_info)
        return False

def test_error_handling():
    """测试错误处理机制"""
    global system_error_received
    system_error_received = None
    
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 订阅系统错误事件
    event_bus.subscribe(EVENTS.SYSTEM_ERROR, system_error_callback)
    
    # 订阅一个会抛出异常的事件
    event_bus.subscribe("error.event", error_callback)
    
    # 发布会触发异常的事件
    event_bus.publish("error.event")
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 验证系统错误是否被正确捕获和处理
    if system_error_received is not None:
        error_context = system_error_received
        
        # 检查错误上下文是否为字典
        if isinstance(error_context, dict):
            # 如果是字典，检查标准字段
            source_ok = error_context.get("source") == "event_bus"
            event_ok = error_context.get("event") == "error.event"
            error_type_ok = error_context.get("error_type") == "callback_error"
            error_message_ok = "测试异常" in error_context.get("error_message", "")
            
            if source_ok and event_ok and error_type_ok and error_message_ok:
                log_test_result("错误处理机制", True)
                return True
            else:
                # 如果标准字段检查失败，检查是否有原始数据
                raw_data = error_context.get("raw_data", "")
                if isinstance(raw_data, dict) and "测试异常" in raw_data.get("error_message", ""):
                    log_test_result("错误处理机制", True)
                    return True
                elif isinstance(raw_data, str) and "测试异常" in raw_data:
                    log_test_result("错误处理机制", True)
                    return True
        else:
            # 如果不是字典，检查是否包含错误信息
            error_str = str(error_context)
            if "测试异常" in error_str:
                log_test_result("错误处理机制", True)
                return True
    
    log_test_result("错误处理机制", False,
                   f"系统错误未正确处理，接收到的错误上下文: {system_error_received}")
    return False

def test_singleton_pattern():
    """测试单例模式验证"""
    # 创建两个事件总线实例
    event_bus1 = EventBus()
    event_bus2 = EventBus()
    
    # 它们应该是同一个对象
    is_same_instance = event_bus1 is event_bus2
    
    # 在一个实例上订阅事件
    def test_callback():
        pass
    
    event_bus1.subscribe("singleton.event", test_callback)
    
    # 另一个实例应该也有相同的订阅
    has_subscribers_in_instance2 = event_bus2.has_subscribers("singleton.event")
    
    if is_same_instance and has_subscribers_in_instance2:
        log_test_result("单例模式", True)
        return True
    else:
        log_test_result("单例模式", False, 
                       f"相同实例: {is_same_instance}, 实例2中有订阅者: {has_subscribers_in_instance2}")
        return False

def test_no_subscribers():
    """测试发布没有订阅者的事件"""
    # 创建事件总线实例
    event_bus = EventBus()
    
    # 发布一个没有订阅者的事件
    # 这不应该引发错误
    try:
        event_bus.publish("no.subscribers.event")
        log_test_result("无订阅者事件", True)
        return True
    except Exception as e:
        log_test_result("无订阅者事件", False, f"发布无订阅者事件时出错: {e}")
        return False

def test_duplicate_subscription():
    """测试重复订阅同一事件"""
    # 创建事件总线实例
    event_bus = EventBus()
    
    def test_callback(event_name):
        global duplicate_callback_call_count
        duplicate_callback_call_count += 1
    
    global duplicate_callback_call_count
    duplicate_callback_call_count = 0
    
    # 多次订阅同一回调
    event_bus.subscribe("duplicate.event", test_callback)
    event_bus.subscribe("duplicate.event", test_callback)
    
    # 发布事件
    event_bus.publish("duplicate.event")
    
    # 等待异步执行
    time.sleep(0.1)
    
    # 回调应该只被调用一次
    if duplicate_callback_call_count == 1:
        log_test_result("重复订阅处理", True)
        return True
    else:
        log_test_result("重复订阅处理", False, 
                       f"回调被调用了 {duplicate_callback_call_count} 次，期望 1 次")
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
    print("测试结果摘要")
    print("=" * 50)
    print(f"总测试数: {test_count}")
    print(f"通过: {passed_count}")
    print(f"失败: {test_count - passed_count}")
    if test_count > 0:
        print(f"成功率: {passed_count / test_count * 100:.1f}%")
    
    if passed_count == test_count:
        print("\n所有测试通过！EventBus功能正常工作。")
    else:
        print("\n部分测试失败。请查看上方的详细测试结果。")

def run_all_tests():
    """运行所有测试"""
    reset_test_results()
    print("=" * 50)
    print("运行所有EventBus功能测试")
    print("=" * 50)
    
    # 运行所有测试
    test_basic_subscribe_publish()
    test_multiple_subscribers()
    test_unsubscribe()
    test_args_passing()
    test_kwargs_passing()
    test_mixed_args_passing()
    test_introspection_tools()
    test_error_handling()
    test_singleton_pattern()
    test_no_subscribers()
    test_duplicate_subscription()
    
    print_test_summary()
    return passed_count == test_count

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)