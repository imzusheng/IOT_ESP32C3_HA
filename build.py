import os
import shutil
import subprocess
import sys
import argparse
import time
import serial
import serial.tools.list_ports
import signal

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
    安全地解码字节数据，尝试多种编码方式，特别优化中文字符支持
    
    Args:
        data: 要解码的字节数据
        encodings: 要尝试的编码列表，默认包含中文常用编码
        errors: 错误处理方式，默认为 'replace'
        verbose: 是否显示调试信息
    
    Returns:
        解码后的字符串
    """
    if not data:
        return ""
    
    if encodings is None:
        # 优先尝试 GBK，然后是中文常用编码，最后是备用编码
        encodings = [
            'gbk',            # 简体中文常用
            'utf-8',          # 标准编码
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
    
    # 如果数据已经是字符串，直接返回
    if isinstance(data, str):
        return data
    
    # 如果数据不是字节数据，尝试转换为字符串
    if not isinstance(data, bytes):
        return str(data)
    
    # 记录原始数据的十六进制转储（仅前128字节，以避免日志过长）
    if len(data) > 0 and verbose:
        hex_dump = ' '.join(f'{b:02x}' for b in data[:128])
        print_message(f"调试: 原始数据 (前128字节): {hex_dump}", "DEBUG", verbose)
    
    # 尝试各种编码方式
    for encoding in encodings:
        try:
            decoded = data.decode(encoding, errors=errors)
            if verbose:
                print_message(f"调试: 成功使用 {encoding} 编码解码数据", "DEBUG", verbose)
            return decoded
        except UnicodeDecodeError as e:
            if verbose:
                print_message(f"调试: 使用 {encoding} 编码解码失败: {e}", "WARNING", verbose)
            continue
    
    # 如果所有编码都失败，使用 latin-1 并替换错误字符
    if verbose:
        print_message(f"调试: 所有编码方式都失败，使用 latin-1 并替换错误字符", "ERROR", verbose)
    return data.decode('latin-1', errors='replace')


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


def upload_and_run_with_mpremote(port, dist_dir, verbose=False):
    """使用 mpremote 清理设备、上传文件、重置并监控输出"""
    
    base_cmd = [MPREMOTE_EXECUTABLE, "connect", port]

    # --- 1. 清空设备文件系统 (健壮版) ---
    print_message("\n--- [1/4] 正在清空设备 ---", "HEADER")
    try:
        list_cmd = base_cmd + ["fs", "ls", ":"]
        result = subprocess.run(list_cmd, capture_output=True, text=True, encoding='utf-8')
        
        # 添加调试日志：显示 ls 命令的原始输出
        print(f"调试: ls 命令返回码: {result.returncode}")
        if result.stdout:
            print(f"调试: ls 命令标准输出:\n{repr(result.stdout)}")
        if result.stderr:
            print(f"调试: ls 命令错误输出:\n{repr(result.stderr)}")

        # 如果命令失败但错误是"no such file"，说明目录为空，是正常情况
        if result.returncode != 0 and "no such file or directory" in result.stderr.lower():
             print("设备文件系统为空，无需清空。")
             items_to_delete = []
        elif result.returncode != 0:
            # 对于其他错误，则报告失败
            raise subprocess.CalledProcessError(result.returncode, list_cmd, output=result.stdout, stderr=result.stderr)
        else:
            # 智能解析ls的输出，取最后一列作为文件名
            lines = result.stdout.strip().splitlines()
            print(f"调试: 解析前的行数: {len(lines)}")
            print(f"调试: 原始行内容: {lines}")
            
            # 更安全的文件名解析逻辑
            parsed_items = []
            for line in lines:
                if not line.strip():
                    continue
                print(f"调试: 处理行: {repr(line)}")
                # 尝试多种解析方式
                parts = line.strip().split()
                if parts:
                    filename = parts[-1]
                    print(f"调试: 解析出的文件名: {repr(filename)}")
                    if filename and filename not in ['.', '..', ':/', '/']:
                        parsed_items.append(filename)
            
            items_to_delete = parsed_items
            print(f"调试: 最终要删除的项目: {items_to_delete}")


        if not items_to_delete:
            print("设备文件系统为空或已清空。")
        else:
            print(f"找到 {len(items_to_delete)} 个项目需要删除。")
            deleted_count = 0
            for item in items_to_delete:
                # 更严格的空值检查
                if not item or not isinstance(item, str) or item.strip() == '':
                    print(f"调试: 跳过无效项目: {repr(item)}")
                    continue
                
                # 清理文件名，移除可能的特殊字符
                clean_item = item.strip()
                if clean_item.startswith(':'):
                    clean_item = clean_item[1:]
                
                # 再次检查清理后的文件名
                if not clean_item or clean_item in ['.', '..', '/']:
                    print(f"调试: 跳过清理后的无效项目: {repr(clean_item)}")
                    continue
                
                remote_path = f":{clean_item}"
                print(f"调试: 准备删除项目 - 原始: {repr(item)}, 清理后: {repr(clean_item)}, 远程路径: {repr(remote_path)}")
                print(f"  删除: {remote_path}")
                
                # 使用 rm -r 可以同时删除文件和目录
                rm_cmd = base_cmd + ["fs", "rm", "-r", remote_path]
                print(f"调试: 删除命令: {' '.join(rm_cmd)}")
                
                try:
                    result = subprocess.run(rm_cmd, check=True, capture_output=True, text=True)
                    print(f"调试: 删除命令成功，返回码: {result.returncode}")
                    if result.stdout:
                        print(f"调试: 删除命令标准输出: {repr(result.stdout)}")
                    if result.stderr:
                        print(f"调试: 删除命令错误输出: {repr(result.stderr)}")
                    deleted_count += 1
                except subprocess.CalledProcessError as e:
                    # 打印更清晰的错误信息并继续
                    error_msg = e.stderr.strip() or e.stdout.strip()
                    print_message(f"  错误: 删除 {remote_path} 失败: {error_msg}", "ERROR")
                    print(f"调试: 删除命令失败，返回码: {e.returncode}")
                    print(f"调试: 失败命令: {' '.join(e.cmd)}")
                    print(f"调试: 失败标准输出: {repr(e.stdout)}")
                    print(f"调试: 失败错误输出: {repr(e.stderr)}")
            print(f"成功删除 {deleted_count}/{len(items_to_delete)} 个项目。")
        print_message("设备清空完成。", "SUCCESS")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() or e.stdout.strip()
        print_message(f"错误: 清空设备时命令执行失败: {error_msg}", "ERROR")
        return False
    except Exception as e:
        print_message(f"错误: 清空设备时发生未预期的异常: {e}", "ERROR")
        return False
    
    # --- 2. 上传文件 ---
    print_message("\n--- [2/4] 正在上传文件 ---", "HEADER")
    uploaded_files_count = 0
    try:
        if not os.path.isdir(dist_dir) or not os.listdir(dist_dir):
            print_message(f"警告: '{dist_dir}' 目录为空，没有文件可上传。", "WARNING")
        else:
            # 遍历 dist 目录下的所有文件和子目录
            for root, dirs, files in os.walk(dist_dir):
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
                    relative_path = os.path.relpath(local_path, dist_dir).replace(os.sep, '/')
                    remote_path = f":{relative_path}"
                    
                    # 添加上传功能的调试日志
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
                    print(f"调试: 上传命令: {' '.join(cp_cmd)}")
                    
                    try:
                        result = subprocess.run(cp_cmd, check=True, capture_output=True, text=True)
                        print(f"调试: 上传命令成功，返回码: {result.returncode}")
                        if result.stdout:
                            print(f"调试: 上传命令标准输出: {repr(result.stdout)}")
                        if result.stderr:
                            print(f"调试: 上传命令错误输出: {repr(result.stderr)}")
                        uploaded_files_count += 1
                    except subprocess.CalledProcessError as e:
                        error_msg = e.stderr.strip() or e.stdout.strip()
                        print_message(f"  错误: 上传 {local_path} 失败: {error_msg}", "ERROR")
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

    # --- 3. 重置设备 ---
    print_message("\n--- [3/4] 正在重置设备 (软重启) ---", "HEADER")
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

    # --- 4. 运行并监控 (REPL) ---
    print_message("\n--- [4/4] 连接到 REPL 并监控输出 ---", "HEADER")
    print_message("设备正在运行... (按 Ctrl+C 停止监控)", "INFO")
    
    # 使用简单的 mpremote repl 命令
    repl_cmd = base_cmd + ["repl"]
    process = None
    was_interrupted = False
    restart_attempts = 0
    max_restart_attempts = 5
    
    def start_mpremote_process():
        """启动 mpremote 进程并返回进程对象"""
        try:
            # 使用 PIPE 捕获输出，而不是直接连接到终端
            # 添加 startupinfo 以在 Windows 上隐藏控制台窗口
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                repl_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                startupinfo=startupinfo
            )
            print_message(f"mpremote 进程已启动 (PID: {process.pid})", "DEBUG")
            return process
        except Exception as e:
            print_message(f"启动 mpremote 进程失败: {e}", "ERROR")
            return None
    
    try:
        # 启动 mpremote 进程
        process = start_mpremote_process()
        if not process:
            return False
        
        # 实时处理输出
        while True:
            # 检查进程是否仍在运行
            if process.poll() is not None:
                print_message(f"mpremote 进程已退出，退出码: {process.returncode}", "WARNING")
                
                # 如果进程意外退出且不是用户中断，尝试重启
                if not was_interrupted and process.returncode != 0 and restart_attempts < max_restart_attempts:
                    restart_attempts += 1
                    print_message(f"尝试重启 mpremote 进程 (第 {restart_attempts}/{max_restart_attempts} 次)", "WARNING")
                    time.sleep(2)  # 等待一段时间再重启
                    process = start_mpremote_process()
                    if process:
                        continue
                    else:
                        break
                else:
                    break
            
            # 读取标准输出 - 简单处理
            try:
                output = process.stdout.read(1024)
                if output:
                    # 直接使用安全解码函数处理输出并打印
                    decoded_output = safe_decode(output)
                    print(decoded_output, end='', flush=True)
            except Exception as e:
                print_message(f"读取标准输出时出错: {e}", "ERROR")
            
            # 读取标准错误 - 简单处理
            try:
                error_output = process.stderr.read(1024)
                if error_output:
                    # 直接使用安全解码函数处理错误输出并打印
                    decoded_error = safe_decode(error_output)
                    print(decoded_error, end='', flush=True)
            except Exception as e:
                print_message(f"读取标准错误时出错: {e}", "ERROR")
            
            # 短暂休眠以避免过度占用 CPU
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        was_interrupted = True
        print_message("\n用户中断，监控已停止。正在终止 mpremote...", "SUCCESS")
        if process and process.poll() is None: # 如果进程仍在运行
            process.terminate()
            try:
                process.wait(timeout=5) # 确保进程已终止，添加超时
            except subprocess.TimeoutExpired:
                print_message("进程终止超时，强制结束...", "WARNING")
                process.kill()
        print_message("mpremote 已终止。", "SUCCESS")
    except Exception as e:
        print_message(f"\n错误: 启动监控时出错: {e}", "ERROR")
        if process and process.poll() is None:
            process.terminate()
        return False

    # 检查进程退出码，只有在不是用户中断的情况下
    if not was_interrupted and process and process.returncode != 0:
        if restart_attempts >= max_restart_attempts:
            print_message(f"\n错误: mpremote REPL 意外退出，已达到最大重启次数 ({max_restart_attempts})。", "ERROR")
            print_message(f"最后退出码: {process.returncode}", "ERROR")
        else:
            print_message(f"\n错误: mpremote REPL 意外退出 (退出码: {process.returncode})。", "ERROR")
        return False
        
    return True


def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(description="MicroPython 项目构建和部署脚本 (使用 mpremote)")
    parser.add_argument('-t', '--test', action='store_true', help="包含 'tests' 目录进行构建 (默认排除)。")
    parser.add_argument('-u', '--upload', action='store_true', help="构建完成后自动上传到ESP32设备并运行。")
    parser.add_argument('-p', '--port', type=str, help="指定ESP32设备端口（如不指定将自动检测）。")
    parser.add_argument('-v', '--verbose', action='store_true', help="显示详细的调试输出。")
    args = parser.parse_args()

    exclude_dirs = [] if args.test else [os.path.join(SRC_DIR, d) for d in DEFAULT_EXCLUDE_DIRS]

    print_message("--- MicroPython Build & Deploy Script ---", "HEADER")
    if args.test:
        print("模式: 包含 tests 目录进行构建 (--test)。")
    else:
        print(f"模式: 排除目录 {DEFAULT_EXCLUDE_DIRS}。")

    if args.upload:
        print("模式: 构建后将自动上传并运行 (--upload)。")

    # --- 1. 检查工具 ---
    if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
    if args.upload and not check_tool(MPREMOTE_EXECUTABLE): sys.exit(1)
    
    # --- 2. 清理并创建输出目录 ---
    print_message(f"\n--- 清理输出目录: {DIST_DIR} ---", "HEADER")
    if os.path.exists(DIST_DIR): shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)

    # --- 3. 遍历源目录并处理文件 ---
    print_message(f"\n--- 开始处理源目录: {SRC_DIR} ---", "HEADER")
    if not os.path.isdir(SRC_DIR):
        print_message(f"错误: 源目录 '{SRC_DIR}' 不存在。", "ERROR")
        sys.exit(1)

    total_files, compiled_files, copied_files = 0, 0, 0

    for root, dirs, files in os.walk(SRC_DIR, topdown=True):
        dirs[:] = [d for d in dirs if os.path.join(root, d) not in exclude_dirs]
        relative_path = os.path.relpath(root, SRC_DIR)
        dist_root = os.path.join(DIST_DIR, relative_path) if relative_path != '.' else DIST_DIR
        if not os.path.exists(dist_root): os.makedirs(dist_root)

        for file in files:
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

    # --- 4. 上传与运行 ---
    if args.upload:
        print_message("\n--- 开始部署到设备 ---", "HEADER")
        device_port = args.port or detect_esp32_port()
        
        if not device_port:
            print_message("错误: 无法确定设备端口。上传中止。", "ERROR")
            sys.exit(1)
        
        print_message(f"使用端口: {device_port}", "INFO")
        
        if upload_and_run_with_mpremote(device_port, DIST_DIR):
            print_message("\n--- 任务成功 ---", "HEADER")
            print_message("所有操作已成功完成！", "SUCCESS")
        else:
            print_message("\n--- 任务失败 ---", "HEADER")
            print_message("部署过程中发生错误。", "ERROR")
            sys.exit(1)
    else:
        print("\n提示: 使用 --upload 或 -u 参数可以自动编译、上传并运行代码。")

if __name__ == "__main__":
    main()
