import os
import shutil
import subprocess
import sys
import argparse
import time
import serial
import serial.tools.list_ports

# 尝试导入chardet进行智能编码检测
try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False
    print("[WARNING] chardet库未安装，将使用基础编码检测功能")

def print_message(message, msg_type="INFO", verbose=False):
    """打印消息，支持不同类型的消息前缀"""
    prefixes = {
        "INFO": "[INFO]",
        "WARNING": "[WARNING]",
        "ERROR": "[ERROR]",
        "SUCCESS": "[SUCCESS]",
        "HEADER": "[HEADER]",
        "DEBUG": "[DEBUG]"
    }
    prefix = prefixes.get(msg_type, "[INFO]")
    
    # 如果是 DEBUG 类型且不是 verbose 模式，则不显示
    if msg_type == "DEBUG" and not verbose:
        return
    
    print(f"{prefix} {message}")


def safe_decode(data, encodings=None, errors='replace', verbose=False):
    """
    安全地解码字节数据，使用chardet进行智能编码检测，特别优化中文字符支持
    支持处理不完整的UTF-8字节序列和'unexpected end of data'错误
    
    Args:
        data: 要解码的字节数据
        encodings: 要尝试的编码列表，默认包含中文常用编码
        errors: 错误处理方式，默认为 'replace'
        verbose: 是否显示调试信息
    
    Returns:
        解码后的字符串和剩余的字节数据 (decoded_str, remaining_bytes)
    """
    if not data:
        return "", b""
    
    # 如果数据已经是字符串，直接返回
    if isinstance(data, str):
        return data, b""
    
    # 如果数据不是字节数据，尝试转换为字符串
    if not isinstance(data, bytes):
        return str(data), b""
    
    # 记录原始数据的十六进制转储（仅前128字节，以避免日志过长）
    if len(data) > 0 and verbose:
        hex_dump = ' '.join(f'{b:02x}' for b in data[:128])
        print_message(f"调试: 原始数据 (前128字节): {hex_dump}", "DEBUG", verbose)
    
    # 使用chardet进行智能编码检测
    detected_encoding = None
    if CHARDET_AVAILABLE and len(data) >= 4:  # chardet需要足够的数据进行检测
        try:
            detection_result = chardet.detect(data)
            if detection_result and detection_result['confidence'] > 0.7:  # 置信度阈值
                detected_encoding = detection_result['encoding']
                if verbose:
                    print_message(f"调试: chardet检测到编码: {detected_encoding} (置信度: {detection_result['confidence']:.2f})", "DEBUG", verbose)
        except Exception as e:
            if verbose:
                print_message(f"调试: chardet检测失败: {e}", "WARNING", verbose)
    
    # 构建编码尝试列表
    if encodings is None:
        encodings = []
        # 如果chardet检测到编码，优先使用
        if detected_encoding:
            encodings.append(detected_encoding)
        
        # 添加常用编码（避免重复）
        common_encodings = [
            'utf-8',          # 标准编码，优先处理
            'gbk',            # 简体中文常用
            'gb2312',         # 简体中文标准
            'gb18030',        # 简体中文扩展
            'big5',           # 繁体中文
            'utf-16',         # UTF-16 编码
            'utf-16-le',      # UTF-16 Little Endian
            'utf-16-be',      # UTF-16 Big Endian
            'latin-1',        # 兼容编码
            'cp437',          # DOS 编码
            'cp1252',         # Windows 西欧编码
        ]
        
        for enc in common_encodings:
            if enc not in encodings:
                encodings.append(enc)
    
    # 特殊处理UTF-8编码，支持不完整字节序列和'unexpected end of data'错误
    if 'utf-8' in encodings:
        try:
            # 尝试完整解码
            decoded = data.decode('utf-8', errors='strict')
            if verbose:
                print_message(f"调试: 成功使用 utf-8 编码完整解码数据", "DEBUG", verbose)
            return decoded, b""
        except UnicodeDecodeError as e:
            if verbose:
                print_message(f"调试: UTF-8解码失败: {e}", "DEBUG", verbose)
            
            # 处理'unexpected end of data'错误 - 通常是不完整的UTF-8序列
            if "unexpected end of data" in str(e) or e.start > 0:
                # 尝试解码到错误位置之前的有效部分
                if e.start > 0:
                    valid_part = data[:e.start]
                    remaining_part = data[e.start:]
                    try:
                        decoded_valid = valid_part.decode('utf-8', errors='strict')
                        if verbose:
                            print_message(f"调试: UTF-8部分解码成功，有效字节: {e.start}, 剩余字节: {len(remaining_part)}", "DEBUG", verbose)
                        return decoded_valid, remaining_part
                    except UnicodeDecodeError:
                        if verbose:
                            print_message(f"调试: UTF-8部分解码也失败，尝试其他方法", "DEBUG", verbose)
                
                # 如果部分解码失败，尝试从末尾删除可能不完整的字节
                for trim_bytes in range(1, min(4, len(data)) + 1):  # UTF-8最多4字节
                    try:
                        trimmed_data = data[:-trim_bytes]
                        if trimmed_data:
                            decoded_trimmed = trimmed_data.decode('utf-8', errors='strict')
                            remaining_trimmed = data[-trim_bytes:]
                            if verbose:
                                print_message(f"调试: UTF-8修剪解码成功，删除了{trim_bytes}字节", "DEBUG", verbose)
                            return decoded_trimmed, remaining_trimmed
                    except UnicodeDecodeError:
                        continue
    
    # 尝试其他编码方式
    for encoding in encodings:
        if encoding == 'utf-8':  # 已经在上面特殊处理过了
            continue
        try:
            decoded = data.decode(encoding, errors=errors)
            if verbose:
                print_message(f"调试: 成功使用 {encoding} 编码解码数据", "DEBUG", verbose)
            return decoded, b""
        except (UnicodeDecodeError, LookupError) as e:
            if verbose:
                print_message(f"调试: 使用 {encoding} 编码解码失败: {e}", "WARNING", verbose)
            continue
    
    # 如果所有编码都失败，使用 latin-1 并替换错误字符
    if verbose:
        print_message(f"调试: 所有编码方式都失败，使用 latin-1 并替换错误字符", "ERROR", verbose)
    return data.decode('latin-1', errors='replace'), b""


def detect_chinese_encoding(data):
    """
    检测数据是否包含中文字符并返回可能的编码
    
    Args:
        data: 要检测的字节数据
    
    Returns:
        可能的编码名称，如果无法检测则返回 None
    """
    if not data or len(data) < 2:
        return None
    
    # 检查 UTF-8 BOM
    if data.startswith(b'\xef\xbb\xbf'):
        return 'utf-8'
    
    # 检查 UTF-16 BE BOM
    if data.startswith(b'\xfe\xff'):
        return 'utf-16-be'
    
    # 检查 UTF-16 LE BOM
    if data.startswith(b'\xff\xfe'):
        return 'utf-16-le'
    
    # 简单的中文编码检测
    # GBK/GB2312/GB18030 的特征字节范围
    gbk_patterns = [
        # 双字节第一字节范围
        lambda b: 0x81 <= b[0] <= 0xFE and len(b) > 1 and 0x40 <= b[1] <= 0xFE,
        # GBK 特殊模式
        lambda b: 0x81 <= b[0] <= 0xFE and len(b) > 1 and 0x30 <= b[1] <= 0x39,
    ]
    
    # Big5 的特征字节范围
    big5_patterns = [
        lambda b: 0xA1 <= b[0] <= 0xF9 and len(b) > 1 and 0x40 <= b[1] <= 0x7E,
        lambda b: 0xA1 <= b[0] <= 0xF9 and len(b) > 1 and 0xA1 <= b[1] <= 0xFE,
    ]
    
    # 尝试匹配中文编码模式
    for i in range(len(data) - 1):
        byte_pair = data[i:i+2]
        
        # 检查 GBK 模式
        for pattern in gbk_patterns:
            try:
                if pattern(byte_pair):
                    return 'gbk'
            except:
                continue
        
        # 检查 Big5 模式
        for pattern in big5_patterns:
            try:
                if pattern(byte_pair):
                    return 'big5'
            except:
                continue
    
    return None


def log_decode_error(error, data_context):
    """
    记录解码错误的详细信息
    
    Args:
        error: UnicodeDecodeError 异常对象
        data_context: 错误发生时的数据上下文
    """
    print_message(f"\n=== Unicode 解码错误详情 ===", "ERROR")
    print_message(f"错误类型: {type(error).__name__}", "ERROR")
    print_message(f"错误信息: {error}", "ERROR")
    
    if hasattr(error, 'start') and hasattr(error, 'end'):
        print_message(f"错误位置: 字节 {error.start} 到 {error.end}", "ERROR")
        
        # 显示错误位置附近的原始数据
        if hasattr(error, 'object') and error.object:
            start_pos = max(0, error.start - 16)
            end_pos = min(len(error.object), error.end + 16)
            context_data = error.object[start_pos:end_pos]
            
            print_message(f"错误位置附近的原始数据:", "ERROR")
            print_message(f"  十六进制: {' '.join(f'{b:02x}' for b in context_data)}", "ERROR")
            try:
                print_message(f"  尝试UTF-8解码: {context_data.decode('utf-8', errors='replace')}", "ERROR")
            except:
                print_message(f"  尝试Latin-1解码: {context_data.decode('latin-1', errors='replace')}", "ERROR")
    
    print_message(f"数据上下文: {data_context}", "ERROR")
    print_message(f"===============================\n", "ERROR")


# --- 配置 ---
SRC_DIR = "src"
DIST_DIR = "dist"
MPY_CROSS_EXECUTABLE = "mpy-cross"
MPREMOTE_EXECUTABLE = "mpremote"
NO_COMPILE_FILES = ['boot.py', 'main.py']
DEFAULT_EXCLUDE_DIRS = ['tests']
ESP32_VID_PID_PATTERNS = [
    (0x303A, 0x1001),  # Espressif
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # QinHeng CH340
    (0x1A86, 0x55D4),  # QinHeng CH343
    (0x0403, 0x6001),  # FTDI
    (0x067B, 0x2303),  # Prolific
]



def detect_esp32_port():
    """自动检测ESP32设备端口"""
    print_message("正在扫描可用串口...", "INFO")
    try:
        ports = serial.tools.list_ports.comports()
    except Exception as e:
        print_message(f"扫描串口时出错: {e}", "ERROR")
        return None

    if not ports:
        print_message("未找到任何串口设备。", "WARNING")
        return None

    esp32_ports = []
    KEYWORDS = ['esp32', 'cp210', 'ch340', 'ch343', 'ft232', 'usb-serial', 'usb to uart', 'jtag', 'serial']

    print("找到的所有串口设备:")
    for port in ports:
        print(f"  - 端口: {port.device}, 描述: {port.description}, HWID: {port.hwid}")
        is_esp_port = False
        if port.vid and port.pid:
            if (port.vid, port.pid) in ESP32_VID_PID_PATTERNS:
                is_esp_port = True
        
        if not is_esp_port and port.description:
            desc_lower = port.description.lower()
            if any(keyword in desc_lower for keyword in KEYWORDS):
                is_esp_port = True

        if is_esp_port and port not in esp32_ports:
            esp32_ports.append(port)

    if not esp32_ports:
        print_message("\n在自动扫描中未能识别出ESP32设备。", "WARNING")
        print_message("请使用 -p 或 --port 参数手动指定端口。", "WARNING")
        return None
    
    if len(esp32_ports) == 1:
        selected_port = esp32_ports[0]
        print_message(f"\n自动选择ESP32设备: {selected_port.device} ({selected_port.description})", "SUCCESS")
        return selected_port.device
    
    print_message(f"\n找到 {len(esp32_ports)} 个可能的ESP32设备:", "INFO")
    for i, port in enumerate(esp32_ports):
        print(f"  {i+1}. {port.device} - {port.description}")
    
    while True:
        try:
            choice = input(f"请选择设备序号 (1-{len(esp32_ports)}): ")
            index = int(choice) - 1
            if 0 <= index < len(esp32_ports):
                selected_port = esp32_ports[index]
                print_message(f"已选择设备: {selected_port.device}", "SUCCESS")
                return selected_port.device
            else:
                print_message("无效的选择，请重新输入。", "WARNING")
        except (ValueError, KeyboardInterrupt):
            print("\n已取消设备选择。")
            return None


def check_tool(executable):
    """检查指定的命令行工具是否存在"""
    if not shutil.which(executable):
        print_message(f"错误: '{executable}' 命令未找到。", "ERROR")
        if executable == MPREMOTE_EXECUTABLE:
            print_message("请使用 'pip install mpremote' 命令进行安装。", "ERROR")
        elif executable == MPY_CROSS_EXECUTABLE:
            print_message("请确保 mpy-cross 已经编译并已添加到系统的 PATH 环境变量中。", "ERROR")
        return False
    return True


def monitor_device_output(port, raw_repl=False, interactive_repl=False):
    """监控设备输出"""
    
    if interactive_repl:
        print("\n[INFO] 启动完整REPL交互模式...")
        print("[INFO] 在此模式下，您可以查看所有原始输出并与设备交互")
        print("[INFO] 按 Ctrl+C 退出监控")
        return monitor_with_interactive_repl(port)
    elif raw_repl:
        print("\n[INFO] 使用原始REPL模式连接设备（可能遇到编码问题）...")
        return monitor_with_continuous_repl(port)
    else:
        print("\n[INFO] 使用实时REPL模式监控设备输出...")
        print("[INFO] 将显示设备的实时日志输出")
        print("[INFO] 按 Ctrl+C 停止监控")
        return monitor_with_continuous_repl(port)

def monitor_with_interactive_repl(port):
    """完整REPL交互模式，支持用户输入和查看所有输出"""
    import threading
    import select
    import sys
    
    # 使用更安全的连接方式，避免mpremote的Unicode问题
    try:
        # 首先尝试使用exec模式建立连接并获取基本信息
        print("\n[REPL] 正在建立安全连接...")
        test_script = '''
print("[REPL_READY] 设备连接成功")
print("[REPL_READY] 可以开始交互")
'''
        result = subprocess.run(
            ["mpremote", "connect", port, "exec", test_script],
            capture_output=True,
            text=False,
            timeout=10
        )
        
        if result.returncode != 0:
            print("[ERROR] 无法建立设备连接")
            return False
            
        print("[REPL] 连接成功！现在启动交互模式...")
        print("[REPL] 输入Python代码并按回车执行")
        print("[REPL] 输入 'exit()' 或按 Ctrl+C 退出\n")
        
    except Exception as e:
        print(f"[ERROR] 连接设备失败: {e}")
        return False
    
    # 使用exec模式进行安全的交互
    try:
        while True:
            try:
                # 读取用户输入
                user_input = input(">>> ")
                
                if user_input.strip().lower() in ['exit()', 'quit()', 'exit', 'quit']:
                    print("[REPL] 退出交互模式")
                    break
                    
                if user_input.strip():
                    # 创建安全的执行脚本
                    exec_script = f'''
try:
    {user_input}
except Exception as e:
    print(f"错误: {{e}}")
'''
                    
                    # 使用exec模式执行用户代码
                    result = subprocess.run(
                        ["mpremote", "connect", port, "exec", exec_script],
                        capture_output=True,
                        text=False,
                        timeout=30
                    )
                    
                    # 安全处理输出
                    if result.stdout:
                        stdout_text, _ = safe_decode(result.stdout)
                        if stdout_text.strip():
                            print(stdout_text)
                    
                    if result.stderr:
                        stderr_text, _ = safe_decode(result.stderr)
                        if stderr_text.strip():
                            print(f"[STDERR] {stderr_text}")
                    
                    if result.returncode != 0:
                        print(f"[WARNING] 命令执行失败，退出码: {result.returncode}")
                        
            except EOFError:
                print("\n[REPL] 输入结束，退出交互模式")
                break
            except KeyboardInterrupt:
                print("\n[REPL] 用户中断，退出交互模式")
                break
            except subprocess.TimeoutExpired:
                print("[WARNING] 命令执行超时")
            except Exception as e:
                print(f"[ERROR] 执行命令时发生错误: {e}")
                
    except Exception as e:
        print(f"\n[REPL] 交互过程中发生错误: {e}")
        return False
    
    return True

def monitor_with_continuous_repl(port):
    """持续REPL模式监控（改进版，不暂停）"""
    process = start_mpremote_process(port)
    if not process:
        return False
    
    stdout_buffer = b""
    stderr_buffer = b""
    stdout_remaining = b""  # 保存stdout的不完整UTF-8字节
    stderr_remaining = b""  # 保存stderr的不完整UTF-8字节
    
    print("\n[MONITOR] 开始持续监听设备输出...")
    print("[MONITOR] 按 Ctrl+C 停止监控\n")
    
    try:
        while True:
            # 非阻塞读取stdout
            try:
                stdout_data = os.read(process.stdout.fileno(), 4096)
                if stdout_data:
                    # 将剩余字节与新数据合并
                    stdout_buffer = stdout_remaining + stdout_data
                    stdout_remaining = b""  # 清空剩余字节
                    
                    # 处理完整的行
                    while b'\n' in stdout_buffer:
                        line, stdout_buffer = stdout_buffer.split(b'\n', 1)
                        decoded_line, remaining_bytes = safe_decode(line + b'\n')
                        # 如果有剩余字节，将其添加到缓冲区开头
                        if remaining_bytes:
                            stdout_buffer = remaining_bytes + stdout_buffer
                            break  # 停止处理，等待更多数据
                        if decoded_line.strip():
                            print(decoded_line, end='')
                    
                    # 检查缓冲区中是否有不完整的UTF-8字符（没有换行符时）
                    if stdout_buffer and b'\n' not in stdout_buffer:
                        # 尝试解码缓冲区，如果有不完整的UTF-8，保存到remaining
                        decoded_partial, remaining_bytes = safe_decode(stdout_buffer)
                        if remaining_bytes:
                            # 有不完整的UTF-8字符，保存剩余字节
                            stdout_remaining = remaining_bytes
                            # 从缓冲区中移除剩余字节
                            stdout_buffer = stdout_buffer[:-len(remaining_bytes)]
            except (OSError, IOError):
                pass
            
            # 非阻塞读取stderr
            try:
                stderr_data = os.read(process.stderr.fileno(), 4096)
                if stderr_data:
                    # 将剩余字节与新数据合并
                    stderr_buffer = stderr_remaining + stderr_data
                    stderr_remaining = b""  # 清空剩余字节
                    
                    # 处理完整的行
                    while b'\n' in stderr_buffer:
                        line, stderr_buffer = stderr_buffer.split(b'\n', 1)
                        decoded_line, remaining_bytes = safe_decode(line + b'\n')
                        # 如果有剩余字节，将其添加到缓冲区开头
                        if remaining_bytes:
                            stderr_buffer = remaining_bytes + stderr_buffer
                            break  # 停止处理，等待更多数据
                        if decoded_line.strip():
                            print(f"[STDERR] {decoded_line}", end='')
                    
                    # 检查缓冲区中是否有不完整的UTF-8字符（没有换行符时）
                    if stderr_buffer and b'\n' not in stderr_buffer:
                        # 尝试解码缓冲区，如果有不完整的UTF-8，保存到remaining
                        decoded_partial, remaining_bytes = safe_decode(stderr_buffer)
                        if remaining_bytes:
                            # 有不完整的UTF-8字符，保存剩余字节
                            stderr_remaining = remaining_bytes
                            # 从缓冲区中移除剩余字节
                            stderr_buffer = stderr_buffer[:-len(remaining_bytes)]
            except (OSError, IOError):
                pass
            
            # 检查进程是否还在运行
            if process.poll() is not None:
                print(f"\n[MONITOR] mpremote 进程已退出，退出码: {process.returncode}")
                # 进程退出后继续尝试重连
                print("[MONITOR] 尝试重新连接...")
                time.sleep(2)
                process = start_mpremote_process(port)
                if not process:
                    print("[ERROR] 重连失败")
                    return False
                stdout_buffer = b""
                stderr_buffer = b""
                stdout_remaining = b""
                stderr_remaining = b""
                continue
            
            # 防止缓冲区过大，但不清空，而是保留最新的数据
            if len(stdout_buffer) > 20480:  # 20KB
                stdout_buffer = stdout_buffer[-10240:]  # 保留后10KB
            if len(stderr_buffer) > 20480:  # 20KB
                stderr_buffer = stderr_buffer[-10240:]  # 保留后10KB
            
            time.sleep(0.05)  # 减少CPU使用率
            
    except KeyboardInterrupt:
        print("\n[MONITOR] 用户中断监控")
        return True
    except Exception as e:
        print(f"\n[MONITOR] 监控过程中发生错误: {e}")
        return False
    finally:
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            try:
                process.kill()
            except:
                pass

def monitor_with_continuous_exec(port):
    """持续exec模式监控，定期检查设备状态"""
    print("\n[MONITOR] 开始持续监听模式...")
    print("[MONITOR] 将定期检查设备状态和输出")
    print("[MONITOR] 按 Ctrl+C 停止监控\n")
    
    # 简化的持续监控脚本
    monitor_script = '''
import time
import gc
import network
import ubinascii
import sys

def safe_print(msg):
    """安全打印，避免编码问题"""
    try:
        print(msg)
    except:
        # 如果直接打印失败，使用base64编码
        encoded = ubinascii.b2a_base64(msg.encode('utf-8')).decode('ascii').strip()
        print(f"[B64]{encoded}")

# 持续监控循环
loop_count = 0
while True:
    try:
        loop_count += 1
        safe_print(f"[MONITOR] 循环 {loop_count} - 时间: {time.ticks_ms()}")
        safe_print(f"[MONITOR] 可用内存: {gc.mem_free()} bytes")
        
        # 检查WiFi状态
        try:
            wlan = network.WLAN(network.STA_IF)
            if wlan.active() and wlan.isconnected():
                config = wlan.ifconfig()
                safe_print(f"[MONITOR] WiFi: 已连接 IP={config[0]}")
            else:
                safe_print("[MONITOR] WiFi: 未连接")
        except Exception as e:
            safe_print(f"[MONITOR] WiFi检查失败: {e}")
        
        # 等待一段时间再继续
        time.sleep(10)
        
    except KeyboardInterrupt:
        safe_print("[MONITOR] 监控被中断")
        break
    except Exception as e:
        safe_print(f"[MONITOR] 监控循环错误: {e}")
        time.sleep(5)
'''
    
    try:
        while True:
            try:
                print("[MONITOR] 执行设备监控脚本...")
                result = subprocess.run(
                    ["mpremote", "connect", port, "exec", monitor_script],
                    capture_output=True,
                    text=False,  # 使用bytes模式避免自动解码
                    timeout=120,  # 增加超时时间
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
                )
                
                if result.stdout:
                    # 使用safe_decode处理bytes输出
                    stdout_text, _ = safe_decode(result.stdout)
                    lines = stdout_text.strip().split('\n')
                    for line in lines:
                        if line.startswith('[B64]'):
                            try:
                                import base64
                                decoded = base64.b64decode(line[5:]).decode('utf-8')
                                print(decoded)
                            except:
                                print(line)
                        else:
                            print(line)
                
                if result.stderr:
                    stderr_text, _ = safe_decode(result.stderr)
                    stderr_lines = stderr_text.strip().split('\n')
                    for line in stderr_lines:
                        if line.strip():
                            print(f"[WARNING] {line}")
                
                if result.returncode != 0:
                    print(f"[WARNING] 监控脚本退出码: {result.returncode}")
                    print("[MONITOR] 等待5秒后重试...")
                    time.sleep(5)
                    continue
                
            except subprocess.TimeoutExpired:
                print("[MONITOR] 监控脚本超时，重新启动...")
                continue
            except Exception as e:
                print(f"[MONITOR] 监控脚本执行失败: {e}")
                print("[MONITOR] 等待5秒后重试...")
                time.sleep(5)
                continue
                
    except KeyboardInterrupt:
        print("\n[MONITOR] 用户中断监控")
        return True
    except Exception as e:
        print(f"\n[MONITOR] 持续监控过程中发生错误: {e}")
        return False

def monitor_with_exec(port):
    """使用exec模式安全监控设备"""
    # 创建一个安全的监控脚本，使用base64编码传输可能包含特殊字符的数据
    monitor_script = '''
import time
import gc
import network
import ubinascii
import sys

def safe_print(msg):
    """安全打印，避免编码问题"""
    try:
        print(msg)
    except:
        # 如果直接打印失败，使用base64编码
        encoded = ubinascii.b2a_base64(msg.encode('utf-8')).decode('ascii').strip()
        print(f"[B64]{encoded}")

safe_print("[MONITOR] 设备监控已启动")
safe_print(f"[MONITOR] 可用内存: {gc.mem_free()} bytes")
safe_print(f"[MONITOR] Python版本: {sys.version}")

# 检查WiFi状态
try:
    wlan = network.WLAN(network.STA_IF)
    if wlan.active():
        if wlan.isconnected():
            config = wlan.ifconfig()
            safe_print(f"[MONITOR] WiFi状态: 已连接")
            safe_print(f"[MONITOR] IP地址: {config[0]}")
            safe_print(f"[MONITOR] 网关: {config[2]}")
        else:
            safe_print("[MONITOR] WiFi状态: 已激活但未连接")
    else:
        safe_print("[MONITOR] WiFi状态: 未激活")
        
    # 安全地扫描WiFi网络
    safe_print("[MONITOR] 开始WiFi扫描...")
    if not wlan.active():
        wlan.active(True)
        time.sleep(1)
    
    networks = wlan.scan()
    safe_print(f"[MONITOR] 发现 {len(networks)} 个WiFi网络")
    
    for i, net in enumerate(networks[:5]):  # 只显示前5个网络
        ssid = net[0].decode('utf-8', 'ignore')  # 忽略无法解码的字符
        rssi = net[3]
        channel = net[2]
        # 使用base64编码SSID以避免特殊字符问题
        ssid_b64 = ubinascii.b2a_base64(ssid.encode('utf-8')).decode('ascii').strip()
        safe_print(f"[MONITOR] 网络{i+1}: [B64SSID]{ssid_b64} | RSSI={rssi} | CH={channel}")
        
except Exception as e:
    safe_print(f"[MONITOR] WiFi检查失败: {e}")

safe_print("[MONITOR] 监控完成，设备运行正常")
'''
    
    try:
        print("[INFO] 执行设备监控脚本...")
        result = subprocess.run(
            ["mpremote", "connect", port, "exec", monitor_script],
            capture_output=True,
            text=False,  # 使用bytes模式避免自动解码
            timeout=60,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        
        if result.stdout:
            # 使用safe_decode处理bytes输出
            stdout_text, _ = safe_decode(result.stdout)  # safe_decode返回(text, remaining_bytes)
            lines = stdout_text.strip().split('\n')
            for line in lines:
                if line.startswith('[B64]'):
                    try:
                        import base64
                        decoded = base64.b64decode(line[5:]).decode('utf-8')
                        print(decoded)
                    except:
                        print(line)  # 如果解码失败，显示原始内容
                elif line.startswith('[B64SSID]'):
                    try:
                        import base64
                        ssid = base64.b64decode(line[9:]).decode('utf-8')
                        # 重新格式化WiFi信息
                        parts = line.split(' | ')
                        if len(parts) >= 3:
                            rssi_part = parts[1] if len(parts) > 1 else ""
                            ch_part = parts[2] if len(parts) > 2 else ""
                            print(f"[MONITOR] WiFi网络: SSID='{ssid}' | {rssi_part} | {ch_part}")
                        else:
                            print(f"[MONITOR] WiFi网络: SSID='{ssid}'")
                    except:
                        print(line)
                else:
                    print(line)
        
        if result.stderr:
            # 使用safe_decode处理bytes错误输出
            stderr_text, _ = safe_decode(result.stderr)  # safe_decode返回(text, remaining_bytes)
            stderr_lines = stderr_text.strip().split('\n')
            for line in stderr_lines:
                if line.strip():
                    print(f"[WARNING] {line}")
        
        if result.returncode != 0:
            print(f"[WARNING] 监控脚本退出码: {result.returncode}")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        print("[WARNING] 监控脚本执行超时")
        return False
    except Exception as e:
        print(f"[ERROR] 监控脚本执行失败: {e}")
        return False

def monitor_with_repl(port):
    """使用原始REPL模式监控（可能遇到编码问题）"""
    process = start_mpremote_process(port)
    if not process:
        return False
    
    stdout_buffer = b""
    stderr_buffer = b""
    
    try:
        while True:
            # 非阻塞读取stdout
            try:
                stdout_data = os.read(process.stdout.fileno(), 4096)
                if stdout_data:
                    stdout_buffer += stdout_data
                    # 处理完整的行
                    while b'\n' in stdout_buffer:
                        line, stdout_buffer = stdout_buffer.split(b'\n', 1)
                        decoded_line = safe_decode(line + b'\n')
                        if decoded_line.strip():
                            print(decoded_line, end='')
            except (OSError, IOError):
                pass
            
            # 非阻塞读取stderr
            try:
                stderr_data = os.read(process.stderr.fileno(), 4096)
                if stderr_data:
                    stderr_buffer += stderr_data
                    # 处理完整的行
                    while b'\n' in stderr_buffer:
                        line, stderr_buffer = stderr_buffer.split(b'\n', 1)
                        decoded_line = safe_decode(line + b'\n')
                        if decoded_line.strip():
                            print(f"[STDERR] {decoded_line}", end='')
            except (OSError, IOError):
                pass
            
            # 检查进程是否还在运行
            if process.poll() is not None:
                print(f"\n[WARNING] mpremote 进程已退出，退出码: {process.returncode}")
                return process.returncode == 0
            
            # 防止缓冲区过大
            if len(stdout_buffer) > 10240:  # 10KB
                print("[WARNING] stdout缓冲区过大，强制清空")
                stdout_buffer = b""
            if len(stderr_buffer) > 10240:  # 10KB
                print("[WARNING] stderr缓冲区过大，强制清空")
                stderr_buffer = b""
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断监控")
        return True
    except Exception as e:
        print(f"\n[ERROR] 监控过程中发生错误: {e}")
        return False
    finally:
        try:
            process.terminate()
            process.wait(timeout=5)
        except:
            try:
                process.kill()
            except:
                pass

def start_mpremote_process(port):
    """启动mpremote REPL进程"""
    try:
        cmd = ["mpremote", "connect", port, "repl"]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            bufsize=0
        )
        
        # 设置非阻塞读取
        if hasattr(os, 'set_blocking'):
            try:
                os.set_blocking(process.stdout.fileno(), False)
                os.set_blocking(process.stderr.fileno(), False)
            except (OSError, AttributeError):
                pass
        
        return process
    except Exception as e:
        print(f"[ERROR] 启动mpremote进程失败: {e}")
        return None

def upload_and_run_with_mpremote(port, dist_dir, verbose=False, use_safe_monitor=True, interactive_repl=False):
    """使用 mpremote 上传文件、重置并监控输出（覆盖上传，排除__pycache__）"""
    
    base_cmd = [MPREMOTE_EXECUTABLE, "connect", port]

    def should_exclude_path(path):
        """检查路径是否应该被排除"""
        path_parts = path.replace(os.sep, '/').split('/')
        
        # 排除__pycache__目录及其内容
        if '__pycache__' in path_parts:
            return True
        
        # 排除编译缓存文件
        if path.endswith(('.pyc', '.pyo')):
            return True
            
        return False

    # --- 1. 上传文件（覆盖模式，排除__pycache__） ---
    print_message("\n--- [1/3] 正在上传文件（覆盖模式） ---", "HEADER")
    uploaded_files_count = 0
    try:
        if not os.path.isdir(dist_dir) or not os.listdir(dist_dir):
            print_message(f"警告: '{dist_dir}' 目录为空，没有文件可上传。", "WARNING")
        else:
            # 遍历 dist 目录下的所有文件和子目录
            for root, dirs, files in os.walk(dist_dir):
                # 过滤目录，排除__pycache__
                dirs[:] = [d for d in dirs if not should_exclude_path(os.path.join(root, d))]
                
                # 创建远程目录
                for d in dirs:
                    local_path = os.path.join(root, d)
                    # 构造远程路径时，始终使用 / 作为分隔符
                    relative_path = os.path.relpath(local_path, dist_dir).replace(os.sep, '/')
                    remote_path = f":{relative_path}"
                    print(f"  创建目录: {remote_path}")
                    mkdir_cmd = base_cmd + ["fs", "mkdir", remote_path]
                    # 忽略目录已存在的错误
                    subprocess.run(mkdir_cmd, capture_output=True)

                # 上传文件
                for f in files:
                    local_path = os.path.join(root, f)
                    
                    # 检查是否应该排除此文件
                    if should_exclude_path(local_path):
                        if verbose:
                            print(f"  跳过: {os.path.relpath(local_path, dist_dir)} (已排除)")
                        continue
                    
                    relative_path = os.path.relpath(local_path, dist_dir).replace(os.sep, '/')
                    remote_path = f":{relative_path}"
                    
                    # 添加上传功能的调试日志
                    if verbose:
                        print(f"调试: 上传文件 - 本地路径: {repr(local_path)}")
                        print(f"调试: 上传文件 - 相对路径: {repr(relative_path)}")
                        print(f"调试: 上传文件 - 远程路径: {repr(remote_path)}")
                    
                    # 验证路径有效性
                    if not local_path or not os.path.exists(local_path):
                        print_message(f"  错误: 本地文件不存在: {local_path}", "ERROR")
                        continue
                    
                    if not relative_path or relative_path.startswith('/') or relative_path.startswith('\\'):
                        print_message(f"  错误: 无效的相对路径: {relative_path}", "ERROR")
                        continue
                    
                    print(f"  上传文件: {local_path} -> {remote_path}")
                    cp_cmd = base_cmd + ["fs", "cp", local_path, remote_path]
                    if verbose:
                        print(f"调试: 上传命令: {' '.join(cp_cmd)}")
                    
                    try:
                        result = subprocess.run(cp_cmd, check=True, capture_output=True, text=True)
                        if verbose:
                            print(f"调试: 上传命令成功，返回码: {result.returncode}")
                            if result.stdout:
                                print(f"调试: 上传命令标准输出: {repr(result.stdout)}")
                            if result.stderr:
                                print(f"调试: 上传命令错误输出: {repr(result.stderr)}")
                        uploaded_files_count += 1
                    except subprocess.CalledProcessError as e:
                        error_msg = e.stderr.strip() or e.stdout.strip()
                        print_message(f"  错误: 上传 {local_path} 失败: {error_msg}", "ERROR", verbose)
                        if verbose:
                            print(f"调试: 上传命令失败，返回码: {e.returncode}")
                            print(f"调试: 失败命令: {' '.join(e.cmd)}")
                            print(f"调试: 失败标准输出: {repr(e.stdout)}")
                            print(f"调试: 失败错误输出: {repr(e.stderr)}")
            
            if uploaded_files_count > 0:
                print_message(f"\n成功上传了 {uploaded_files_count} 个文件。", "SUCCESS")
            else:
                 print_message("没有文件被上传。", "WARNING")
            print_message("文件上传完成。", "SUCCESS")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() or e.stdout.strip()
        print_message(f"错误: 上传文件时失败: {error_msg}", "ERROR")
        return False
    except Exception as e:
        print_message(f"错误: 上传文件时发生未预期的异常: {e}", "ERROR")
        return False

    # --- 2. 重置设备 ---
    print_message("\n--- [2/3] 正在重置设备 (软重启) ---", "HEADER")
    try:
        reset_cmd = base_cmd + ["reset"]
        subprocess.run(reset_cmd, check=True, capture_output=True, timeout=10)
        print("设备重置命令已发送。等待设备重启...")
        time.sleep(2)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print_message("设备重置可能未成功或超时，但仍将尝试连接 REPL。", "WARNING")
        if hasattr(e, 'stderr') and (e.stderr or e.stdout):
            error_msg = e.stderr.strip() or e.stdout.strip()
            print_message(f"mpremote 输出: {error_msg}", "WARNING")

    # --- 3. 运行并监控 (REPL) ---
    print_message("\n--- [3/3] 连接到 REPL 并监控输出 ---", "HEADER")
    print_message("设备正在运行... (按 Ctrl+C 停止监控)", "INFO")
    
    # 监控设备输出
    success = monitor_device_output(port, not use_safe_monitor, interactive_repl)
    if not success:
        print("\n[ERROR] 设备监控失败")
        if use_safe_monitor and not interactive_repl:
            print("[INFO] 提示：如果需要查看原始输出，可以使用 --raw-repl 参数")
            print("[INFO] 或使用 -r/--repl 参数启用完整交互模式")
            print("[INFO] 但请注意，原始REPL模式可能因特殊字符而崩溃")
        return False
    
    return True


def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(
        description="MicroPython 项目构建和部署脚本 (使用 mpremote)",
        epilog="""使用示例:
  python build.py -c              # 仅编译 src 到 dist 目录
  python build.py -u              # 仅上传 dist 目录并监听
  python build.py                 # 默认：上传并监听（需要预先编译）
  python build.py -c -t           # 编译时包含 tests 目录
  python build.py -u -p COM3      # 指定端口上传
  python build.py -u -r           # 启用完整REPL交互模式
  python build.py -u --raw-repl   # 使用原始REPL模式（调试用）""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-c', '--compile', action='store_true', help="编译 src 目录到 dist 目录，编译完成后退出。")
    parser.add_argument('-t', '--test', action='store_true', help="包含 'tests' 目录进行构建 (默认排除)。")
    parser.add_argument('-u', '--upload', action='store_true', help="上传 dist 目录文件到ESP32设备并监听输出。")
    parser.add_argument('-p', '--port', type=str, help="指定ESP32设备端口（如不指定将自动检测）。")
    parser.add_argument('-v', '--verbose', action='store_true', help="显示详细的调试输出。")
    parser.add_argument('-r', '--repl', action='store_true', help='启用完整REPL交互模式，可查看所有原始输出并与设备交互')
    parser.add_argument('--raw-repl', action='store_true', help='使用原始REPL模式（可能遇到编码问题，仅用于调试）')
    args = parser.parse_args()

    exclude_dirs = [] if args.test else [os.path.join(SRC_DIR, d) for d in DEFAULT_EXCLUDE_DIRS]

    print_message("--- MicroPython Build & Deploy Script ---", "HEADER")
    
    # 显示当前模式
    if args.compile:
        print("模式: 编译模式 (--compile) - 编译完成后退出。")
    elif args.upload:
        print("模式: 上传模式 (--upload) - 上传并监听设备输出。")
    else:
        print("模式: 默认模式 - 上传并监听设备输出。")
    
    if args.test:
        print("选项: 包含 tests 目录进行构建 (--test)。")
    else:
        print(f"选项: 排除目录 {DEFAULT_EXCLUDE_DIRS}。")

    # --- 1. 检查工具 ---
    # 仅编译模式需要检查编译工具
    if args.compile:
        if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
    # 上传模式或默认模式需要检查 mpremote 工具
    if args.upload or not args.compile:
        if not check_tool(MPREMOTE_EXECUTABLE): sys.exit(1)
    
    # --- 2. 编译处理 ---
    # 只有在编译模式时才执行编译
    if args.compile:
        # 清理并创建输出目录
        print_message(f"\n--- 清理输出目录: {DIST_DIR} ---", "HEADER")
        if os.path.exists(DIST_DIR): shutil.rmtree(DIST_DIR)
        os.makedirs(DIST_DIR)

        # 遍历源目录并处理文件
        print_message(f"\n--- 开始处理源目录: {SRC_DIR} ---", "HEADER")
        if not os.path.isdir(SRC_DIR):
            print_message(f"错误: 源目录 '{SRC_DIR}' 不存在。", "ERROR")
            sys.exit(1)

        total_files, compiled_files, copied_files = 0, 0, 0

        for root, dirs, files in os.walk(SRC_DIR, topdown=True):
            # 过滤排除的目录和__pycache__目录
            dirs[:] = [d for d in dirs if os.path.join(root, d) not in exclude_dirs and d != '__pycache__']
            relative_path = os.path.relpath(root, SRC_DIR)
            dist_root = os.path.join(DIST_DIR, relative_path) if relative_path != '.' else DIST_DIR
            if not os.path.exists(dist_root): os.makedirs(dist_root)

            for file in files:
                # 跳过编译缓存文件
                if file.endswith(('.pyc', '.pyo')):
                    if args.verbose:
                        print(f"  跳过: {os.path.join(root, file)} (编译缓存文件)")
                    continue
                    
                total_files += 1
                src_path = os.path.join(root, file)
                dist_path = os.path.join(dist_root, file)

                if file.endswith('.py'):
                    if file in NO_COMPILE_FILES:
                        print(f"  复制: {src_path} -> {dist_path}")
                        shutil.copy2(src_path, dist_path)
                        copied_files += 1
                    else:
                        dist_path_mpy = os.path.splitext(dist_path)[0] + '.mpy'
                        print(f"  编译: {src_path} -> {dist_path_mpy}")
                        try:
                            command = [MPY_CROSS_EXECUTABLE, "-o", dist_path_mpy, src_path]
                            subprocess.run(command, check=True, capture_output=True, text=True)
                            compiled_files += 1
                        except subprocess.CalledProcessError as e:
                            print_message(f"\n!!! 编译失败: {src_path}\n{e.stderr}", "ERROR")
                            sys.exit(1)
                else:
                    print(f"  复制: {src_path} -> {dist_path}")
                    shutil.copy2(src_path, dist_path)
                    copied_files += 1

        print_message("\n--- 构建完成 ---", "HEADER")
        print(f"总共处理文件: {total_files}, 编译: {compiled_files}, 复制: {copied_files}")
        print_message(f"输出目录 '{DIST_DIR}' 已准备好。", "SUCCESS")
        
        # 如果是纯编译模式，编译完成后退出
        if args.compile:
            print_message("\n编译模式完成，程序退出。", "INFO")
            return

    # --- 3. 上传与运行 ---
    # 上传模式或默认模式执行上传
    if args.upload or (not args.compile and not args.upload):
        # 检查 dist 目录是否存在
        if not os.path.isdir(DIST_DIR) or not os.listdir(DIST_DIR):
            print_message(f"\n错误: '{DIST_DIR}' 目录不存在或为空。", "ERROR")
            print_message("请先使用 --compile 或 -c 参数编译代码，或确保 dist 目录中有文件。", "INFO")
            sys.exit(1)
        
        print_message("\n--- 开始部署到设备 ---", "HEADER")
        device_port = args.port or detect_esp32_port()
        
        if not device_port:
            print_message("错误: 无法确定设备端口。上传中止。", "ERROR")
            sys.exit(1)
        
        print_message(f"使用端口: {device_port}", "INFO")
        
        if upload_and_run_with_mpremote(device_port, DIST_DIR, args.verbose, not args.raw_repl, args.repl):
            print_message("\n--- 任务成功 ---", "HEADER")
            print_message("所有操作已成功完成！", "SUCCESS")
        else:
            print_message("\n--- 任务失败 ---", "HEADER")
            print_message("部署过程中发生错误。", "ERROR")
            sys.exit(1)

if __name__ == "__main__":
    main()
