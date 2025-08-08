#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MicroPython 高性能构建和部署脚本 (v4.6 - mpremote)
专为 ESP32-C3 等 MicroPython 项目设计的构建和部署工具

作者: AI Assistant
版本: 4.6 (经过全面分析和修复)
日期: 2025-08-07
"""

import os
import sys
import json
import time
import shutil
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Windows 代码页设置
if sys.platform == "win32":
    try:
        # 设置控制台输出为 UTF-8，以正确显示中文字符
        os.system("chcp 65001 > nul")
        os.system("set PYTHONIOENCODING=utf-8")
    except Exception as e:
        print(f"警告: 设置Windows代码页失败: {e}")

# 尝试导入 pyserial
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# ==================== 配置常量 ====================

# --- 目录和文件配置 ---
SRC_DIR = "src"                    # 源代码目录
DIST_DIR = "dist"                  # 编译输出目录

# --- 工具可执行文件 ---
MPY_CROSS_EXECUTABLE = "mpy-cross"  # MicroPython 编译器
MPREMOTE_EXECUTABLE = "mpremote"   # MicroPython 远程工具
RSHELL_EXECUTABLE = "rshell"       # rshell 备用连接工具

# --- 编译排除文件 ---
NO_COMPILE_FILES = ['boot.py', 'main.py']  # 不进行交叉编译的文件列表
DEFAULT_EXCLUDE_DIRS = ['tests']           # 默认排除的目录

# --- 缓存文件 ---
PORT_CACHE_FILE = ".port_cache"            # 端口缓存文件
UPLOAD_CACHE_FILE = ".upload_cache.json"   # 上传缓存文件

# --- 排除模式 (用于编译和上传) ---
EXCLUDE_PATTERNS = [
    "__pycache__",     # Python 缓存目录
    "*.pyc",          # Python 字节码文件
    "*.pyo",          # Python 优化文件
    ".DS_Store",      # macOS 系统文件
    "Thumbs.db",      # Windows 缩略图文件
    PORT_CACHE_FILE,  # 脚本生成的端口缓存
    UPLOAD_CACHE_FILE # 脚本生成的上传缓存
]

# --- ESP32 设备 VID/PID 模式 ---
ESP32_VID_PID_PATTERNS = [
    (0x303A, 0x1001),  # Espressif 官方芯片 (ESP32-S2, S3, C3)
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # QinHeng CH340
    (0x1A86, 0x55D4),  # QinHeng CH343
    (0x0403, 0x6001),  # FTDI 芯片
]

# --- 设备关键词 (用于描述匹配) ---
ESP32_KEYWORDS = [
    'esp32', 'cp210', 'ch340', 'ch343',
    'usb to uart', 'serial'
]

# --- 命令超时时间 (秒) ---
TIMEOUT_SHORT = 15     # 短命令超时 (如准备设备)
TIMEOUT_MEDIUM = 60    # 中等命令超时 (如上传小文件)
TIMEOUT_LONG = 180     # 长命令超时 (如清理设备或上传大文件)

# --- 安全模式专用超时时间 (秒) ---
TIMEOUT_SAFE_MODE_DETECT = 30    # 安全模式检测超时
TIMEOUT_SAFE_MODE_EXIT = 45      # 安全模式退出超时
TIMEOUT_SAFE_MODE_RECOVERY = 60  # 安全模式恢复超时

# --- 重试配置 ---
MAX_RETRIES_NORMAL = 3           # 正常模式最大重试次数
MAX_RETRIES_SAFE_MODE = 5        # 安全模式最大重试次数
RETRY_DELAY_BASE = 2             # 重试延迟基础时间(秒)
RETRY_DELAY_SAFE_MODE = 5        # 安全模式重试延迟时间(秒)

# --- ANSI 颜色代码 ---
class Colors:
    INFO = '\033[94m'      # 蓝色
    SUCCESS = '\033[92m'   # 绿色
    WARNING = '\033[93m'   # 黄色
    ERROR = '\033[91m'     # 红色
    HEADER = '\033[95m'    # 紫色
    RESET = '\033[0m'      # 重置

# ==================== 辅助函数 ====================

def print_message(message, msg_type="INFO"):
    """格式化打印带时间戳和颜色的消息"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    color_map = {
        "INFO": Colors.INFO, "SUCCESS": Colors.SUCCESS,
        "WARNING": Colors.WARNING, "ERROR": Colors.ERROR, "HEADER": Colors.HEADER,
    }
    color = color_map.get(msg_type, Colors.INFO)
    print(f"{color}[{timestamp}] {message}{Colors.RESET}")

def get_file_md5(file_path):
    """计算文件的MD5哈希值，用于文件变更检测"""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except IOError as e:
        print_message(f"计算文件MD5失败: {file_path} - {e}", "ERROR")
        return None

def load_cache(cache_file):
    """加载JSON缓存文件"""
    if not os.path.isfile(cache_file):
        return {}
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print_message(f"缓存文件损坏，将重新创建: {cache_file} - {e}", "WARNING")
        return {}

def save_cache(cache_data, cache_file):
    """保存数据到JSON缓存文件"""
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print_message(f"保存缓存失败: {cache_file} - {e}", "WARNING")

def should_exclude(path, exclude_patterns):
    """检查路径是否应根据排除模式列表被排除"""
    import fnmatch
    path_str = str(path)
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(os.path.basename(path_str), pattern):
            return True
    return False

# ==================== 设备检测 ====================

def detect_esp32_port():
    """自动检测ESP32设备端口，支持缓存和多设备选择"""
    if not SERIAL_AVAILABLE:
        print_message("pyserial 未安装，无法自动检测端口。请手动指定端口。", "ERROR")
        print_message("安装命令: pip install pyserial", "INFO")
        return None

    # 检查端口缓存
    if os.path.isfile(PORT_CACHE_FILE):
        try:
            with open(PORT_CACHE_FILE, "r") as f:
                cached_port = f.read().strip()
            # 验证缓存的端口是否仍然有效
            with serial.Serial(cached_port, timeout=1):
                print_message(f"使用缓存的端口: {cached_port}", "INFO")
                return cached_port
        except (serial.SerialException, FileNotFoundError, IOError):
            print_message(f"缓存的端口不可用，重新扫描...", "WARNING")
            try:
                os.remove(PORT_CACHE_FILE)
            except OSError:
                pass

    # 扫描所有可用串口
    print_message("扫描ESP32设备...", "INFO")
    ports = serial.tools.list_ports.comports()
    esp32_ports = []
    for port in ports:
        # 检查 VID/PID 或描述关键词
        is_esp32_by_id = (port.vid, port.pid) in ESP32_VID_PID_PATTERNS
        is_esp32_by_desc = port.description and any(kw in port.description.lower() for kw in ESP32_KEYWORDS)
        if is_esp32_by_id or is_esp32_by_desc:
            esp32_ports.append(port)

    if not esp32_ports:
        print_message("未发现ESP32设备。请检查设备连接和驱动安装。", "ERROR")
        return None

    if len(esp32_ports) == 1:
        selected_port = esp32_ports[0].device
        print_message(f"发现ESP32设备: {selected_port} ({esp32_ports[0].description})", "SUCCESS")
    else:
        # 多个设备，让用户选择
        print_message(f"发现 {len(esp32_ports)} 个ESP32设备:", "INFO")
        for i, port in enumerate(esp32_ports, 1):
            print(f"  {i}. {port.device} - {port.description}")
        while True:
            try:
                choice = input(f"请选择设备序号 (1-{len(esp32_ports)}): ")
                choice_index = int(choice) - 1
                if 0 <= choice_index < len(esp32_ports):
                    selected_port = esp32_ports[choice_index].device
                    break
                else:
                    print_message("无效的选择，请重试。", "WARNING")
            except (ValueError, KeyboardInterrupt):
                print_message("操作取消。", "ERROR")
                return None

    # 缓存选中的端口
    try:
        with open(PORT_CACHE_FILE, "w") as f:
            f.write(selected_port)
    except IOError as e:
        print_message(f"无法保存端口缓存: {e}", "WARNING")

    return selected_port

# ==================== 工具检查 ====================

def check_tool(executable):
    """检查核心工具（mpy-cross, mpremote）是否在系统中可用"""
    try:
        cmd = [executable, "--version"] if executable == MPY_CROSS_EXECUTABLE else [executable, "version"]
        subprocess.run(cmd, capture_output=True, check=True, text=True, timeout=5)
        return True
    except FileNotFoundError:
        print_message(f"命令未找到: {executable}", "ERROR")
        if executable == MPREMOTE_EXECUTABLE:
            print_message("请安装 mpremote 工具: pip install mpremote", "INFO")
        else:
            print_message("请确保 MicroPython 或相关构建工具已安装在系统路径中。", "INFO")
        return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print_message(f"命令 {executable} 执行失败: {e}", "ERROR")
        return False

def check_rshell_available():
    """检查rshell工具是否可用，处理兼容性问题"""
    try:
        # 尝试直接运行rshell命令
        result = subprocess.run([RSHELL_EXECUTABLE, "--version"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True, "direct"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except subprocess.CalledProcessError as e:
        # 检查是否是兼容性问题
        if "collections.Callable" in str(e.stderr) or "AttributeError" in str(e.stderr):
            print_message("检测到rshell兼容性问题，但工具已安装", "WARNING")
            return True, "compatibility_issue"
    
    # 尝试通过python模块方式运行
    try:
        result = subprocess.run(["python", "-c", "import rshell; print('rshell available')"], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True, "python_module"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    
    return False, "not_available"

def rshell_connect_and_reset(port, verbose=False):
    """使用rshell连接设备并执行硬重启"""
    rshell_available, rshell_mode = check_rshell_available()
    
    if not rshell_available:
        if verbose: print_message("rshell工具不可用，跳过rshell重启", "WARNING")
        return False
    
    if verbose: print_message(f"尝试使用rshell ({rshell_mode}模式) 连接设备...", "INFO")
    
    try:
        # 根据不同的rshell模式构建命令
        if rshell_mode == "direct":
            # 直接运行rshell命令
            rshell_cmd = [RSHELL_EXECUTABLE, '-p', port, '--quiet']
        elif rshell_mode == "python_module":
            # 通过python模块运行
            rshell_cmd = ['python', '-c', f'import rshell.main; rshell.main.main(["-p", "{port}", "--quiet"])']
        else:  # compatibility_issue
            # 兼容性问题时尝试简单的连接测试
            if verbose: print_message("rshell存在兼容性问题，尝试基本连接测试", "WARNING")
            return False
        
        # 创建重启脚本
        reset_script = "import machine; machine.reset()"
        
        if verbose: print_message(f"执行rshell重启命令...", "INFO")
        
        # 使用rshell执行重启命令
        if rshell_mode == "direct":
            # 直接模式：使用rshell的repl功能
            full_cmd = rshell_cmd + ['repl', '~', reset_script, '~', '.']
            result = subprocess.run(full_cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=15,
                                  input='\n')
        else:
            # Python模块模式：直接执行导入和重启
            python_script = f"""
import sys
sys.path.insert(0, '.')
try:
    import rshell.main
    import io
    from contextlib import redirect_stdout, redirect_stderr
    
    # 重定向输出以避免干扰
    f = io.StringIO()
    with redirect_stdout(f), redirect_stderr(f):
        # 模拟rshell连接和执行重启命令
        rshell.main.main(["-p", "{port}", "--quiet", "repl", "~", "{reset_script}", "~", "."])
    print("rshell_reset_sent")
except Exception as e:
    print(f"rshell_error:{{e}}")
"""
            result = subprocess.run(['python', '-c', python_script], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=15)
        
        if verbose:
            if result.stdout:
                print_message(f"rshell输出: {result.stdout.strip()}", "INFO")
            if result.stderr:
                print_message(f"rshell错误: {result.stderr.strip()}", "WARNING")
        
        # 检查是否成功发送重启命令
        success_indicators = ["rshell_reset_sent", "machine.reset"]
        error_indicators = ["error", "failed", "timeout", "connection refused"]
        
        output_text = (result.stdout + result.stderr).lower()
        
        # 检查成功指示器
        has_success = any(indicator in output_text for indicator in success_indicators)
        has_error = any(indicator in output_text for indicator in error_indicators)
        
        if has_success or (result.returncode == 0 and not has_error):
            if verbose: print_message("rshell重启命令已发送", "SUCCESS")
            return True
        else:
            if verbose: print_message(f"rshell重启可能失败: {result.stderr.strip()}", "WARNING")
            return False
            
    except subprocess.TimeoutExpired:
        if verbose: print_message("rshell连接超时", "WARNING")
        return False
    except Exception as e:
        if verbose: print_message(f"rshell连接异常: {e}", "WARNING")
        return False

def rshell_hard_reset_fallback(port, verbose=False):
    """rshell备用硬重启方案，当mpremote连接完全失败时使用
    
    包含详细的等待和状态检测逻辑：
    1. 渐进式等待时间，确保设备完全重启
    2. 多阶段状态验证，包括基础连接和功能测试
    3. 详细的诊断信息和错误处理
    """
    if verbose: print_message("尝试rshell备用硬重启方案...", "INFO")
    
    # 尝试rshell连接和重启
    if rshell_connect_and_reset(port, verbose):
        if verbose: print_message("rshell重启成功，开始设备重启等待和状态检测...", "SUCCESS")
        
        # 阶段1: 初始等待，让设备完全断电重启
        initial_wait = 3
        if verbose: print_message(f"阶段1: 等待设备断电重启 ({initial_wait}秒)...", "INFO")
        time.sleep(initial_wait)
        
        # 阶段2: 渐进式状态检测，最多尝试5次
        max_attempts = 5
        wait_intervals = [2, 3, 4, 5, 6]  # 渐进式增加等待时间
        
        for i in range(max_attempts):
            if verbose: print_message(f"阶段2: 设备状态检测 (第{i+1}/{max_attempts}次)...", "INFO")
            
            # 基础连接测试
            if check_device_status(port, verbose=False):  # 关闭详细输出避免干扰
                if verbose: print_message("基础连接测试通过", "SUCCESS")
                
                # 阶段3: 功能验证测试
                if verbose: print_message("阶段3: 执行功能验证测试...", "INFO")
                
                # 简单的Python执行测试
                returncode, stdout, stderr = execute_mpremote_command(
                    port, "exec", "print('RSHELL_RESET_TEST_OK')", 
                    timeout=5, retries=1, verbose=False
                )
                
                if returncode == 0 and "RSHELL_RESET_TEST_OK" in stdout:
                    if verbose: print_message("功能验证测试通过，rshell重启完全成功", "SUCCESS")
                    return True
                else:
                    if verbose: print_message(f"功能验证失败 (返回码: {returncode})，继续等待...", "WARNING")
            else:
                if verbose: print_message("基础连接测试失败，继续等待...", "WARNING")
            
            # 如果不是最后一次尝试，等待后继续
            if i < max_attempts - 1:
                wait_time = wait_intervals[i]
                if verbose: print_message(f"等待 {wait_time} 秒后继续检测...", "INFO")
                time.sleep(wait_time)
        
        # 所有验证都失败
        if verbose: 
            print_message("设备重启后所有状态验证都失败", "WARNING")
            print_message("可能的原因：", "INFO")
            print_message("  1. 设备重启时间超出预期", "INFO")
            print_message("  2. rshell重启未完全生效", "INFO")
            print_message("  3. 设备固件或硬件问题", "INFO")
        return False
    else:
        if verbose: print_message("rshell重启失败，可能的原因：", "WARNING")
        if verbose: 
            print_message("  1. rshell工具版本兼容性问题", "INFO")
            print_message("  2. 设备端口被占用或无响应", "INFO")
            print_message("  3. 设备硬件连接问题", "INFO")
        return False

# ==================== 命令执行 ====================

def execute_mpremote_command(port, *cmd_args, timeout=60, retries=1, verbose=False, safe_mode_context=False):
    """执行 mpremote 命令并返回结果，支持重试和详细错误分析，针对安全模式优化"""
    command = [MPREMOTE_EXECUTABLE, 'connect', port, *cmd_args]
    
    # 根据安全模式上下文调整参数
    if safe_mode_context:
        # 安全模式下使用更长的超时和更多重试
        if timeout == 60:  # 如果使用默认超时，则调整为安全模式超时
            timeout = TIMEOUT_SAFE_MODE_RECOVERY
        if retries == 1:  # 如果使用默认重试次数，则调整为安全模式重试次数
            retries = MAX_RETRIES_SAFE_MODE
        retry_delay = RETRY_DELAY_SAFE_MODE
    else:
        retry_delay = RETRY_DELAY_BASE
    
    for attempt in range(retries):
        if attempt > 0 and verbose:
            print_message(f"命令重试 {attempt + 1}/{retries}: {' '.join(cmd_args)}", "INFO")
        
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=timeout
            )
            
            # 成功执行或非连接相关错误直接返回
            if result.returncode == 0 or not _is_connection_error(result.stderr):
                return result.returncode, result.stdout, result.stderr
            
            # 连接错误且还有重试机会
            if attempt < retries - 1:
                if verbose:
                    print_message(f"连接错误，{retry_delay}秒后重试: {result.stderr.strip()[:100]}", "WARNING")
                time.sleep(retry_delay)
                continue
            
            return result.returncode, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            error_msg = f"命令超时 ({timeout}s): {' '.join(cmd_args)}"
            if attempt < retries - 1:
                if verbose: print_message(f"{error_msg}，{retry_delay}秒后重试...", "WARNING")
                time.sleep(retry_delay)
                continue
            else:
                print_message(error_msg, "ERROR")
                return -1, "", "命令执行超时"
                
        except Exception as e:
            error_msg = f"命令执行异常: {e}"
            if attempt < retries - 1:
                if verbose: print_message(f"{error_msg}，{retry_delay}秒后重试...", "WARNING")
                time.sleep(retry_delay)
                continue
            else:
                print_message(error_msg, "ERROR")
                return -1, "", str(e)
    
    return -1, "", "所有重试都失败了"

def _is_connection_error(stderr):
    """判断错误是否为连接相关错误"""
    connection_error_keywords = [
        "could not enter raw repl",
        "could not connect",
        "device not found",
        "permission denied",
        "access denied",
        "device busy",
        "no such file or directory",
        "connection failed",
        "timeout",
        "device disconnected"
    ]
    
    stderr_lower = stderr.lower()
    return any(keyword in stderr_lower for keyword in connection_error_keywords)

# ==================== 编译系统 ====================

def compile_project(verbose=False, exclude_dirs=None):
    """编译项目文件从 src 到 dist，.py 文件编译为 .mpy"""
    if exclude_dirs is None:
        exclude_dirs = DEFAULT_EXCLUDE_DIRS.copy()

    if not os.path.isdir(SRC_DIR):
        print_message(f"源目录 '{SRC_DIR}' 不存在。", "ERROR")
        return False

    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)

    compiled_count, copied_count, error_count = 0, 0, 0

    for root, dirs, files in os.walk(SRC_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        rel_path = Path(root).relative_to(SRC_DIR)
        target_dir = Path(DIST_DIR) / rel_path

        if not target_dir.exists():
            target_dir.mkdir(parents=True)

        for file in files:
            src_file = Path(root) / file
            if should_exclude(src_file, EXCLUDE_PATTERNS):
                if verbose: print_message(f"排除文件: {src_file}", "INFO")
                continue

            if file.endswith('.py') and file not in NO_COMPILE_FILES:
                target_file = target_dir / file.replace('.py', '.mpy')
                try:
                    subprocess.run(
                        [MPY_CROSS_EXECUTABLE, "-o", str(target_file), str(src_file)],
                        capture_output=True, text=True, check=True
                    )
                    compiled_count += 1
                    if verbose: print_message(f"编译: {src_file} -> {target_file}", "INFO")
                except subprocess.CalledProcessError as e:
                    error_count += 1
                    print_message(f"编译失败: {src_file}\n{e.stderr}", "ERROR")
            else:
                target_file = target_dir / file
                try:
                    shutil.copy2(src_file, target_file)
                    copied_count += 1
                    if verbose: print_message(f"复制: {src_file} -> {target_file}", "INFO")
                except IOError as e:
                    error_count += 1
                    print_message(f"复制失败: {src_file} - {e}", "ERROR")

    print_message(f"编译完成: {compiled_count} 个文件已编译, {copied_count} 个文件已复制", "SUCCESS")
    if error_count > 0:
        print_message(f"编译过程中出现 {error_count} 个错误", "WARNING")
        return False
    return True

# ==================== 安全模式检测和处理 ====================

def detect_safe_mode(port, verbose=False):
    """检测设备是否处于安全模式"""
    if verbose: print_message("检测设备安全模式状态...", "INFO")
    
    # 尝试检查安全模式状态的脚本
    safe_mode_check_script = """
try:
    import sys_daemon
    if hasattr(sys_daemon, 'is_safe_mode'):
        safe_mode = sys_daemon.is_safe_mode()
        print(f"SAFE_MODE_STATUS:{safe_mode}")
    else:
        print("SAFE_MODE_STATUS:unknown")
except ImportError:
    print("SAFE_MODE_STATUS:no_daemon")
except Exception as e:
    print(f"SAFE_MODE_STATUS:error:{e}")
"""
    
    returncode, stdout, stderr = execute_mpremote_command(
        port, "exec", safe_mode_check_script, 
        timeout=5, retries=1, verbose=verbose, safe_mode_context=True
    )
    
    if returncode == 0 and "SAFE_MODE_STATUS:" in stdout:
        status_line = [line for line in stdout.split('\n') if "SAFE_MODE_STATUS:" in line]
        if status_line:
            status = status_line[0].split(":", 1)[1].strip()
            if status == "True":
                if verbose: print_message("设备处于安全模式", "WARNING")
                return True
            elif status == "False":
                if verbose: print_message("设备处于正常模式", "SUCCESS")
                return False
            elif status == "unknown":
                if verbose: print_message("无法确定安全模式状态（守护进程函数不可用）", "WARNING")
                return None
            elif status == "no_daemon":
                if verbose: print_message("设备未运行守护进程", "INFO")
                return False
            elif status.startswith("error:"):
                if verbose: print_message(f"检测安全模式时出错: {status[6:]}", "WARNING")
                return None
    
    if verbose: print_message("无法检测安全模式状态", "WARNING")
    return None

def force_exit_safe_mode(port, verbose=False):
    """强制设备退出安全模式
    
    Returns:
        bool: True - 成功退出安全模式或执行重启命令
              False - 操作失败
    """
    if verbose:
        print_message("正在尝试强制退出安全模式...", "INFO")
    
    # 尝试软件重启
    restart_script = """
try:
    import machine
    print("RESTART_INITIATED")
    machine.reset()
except Exception as e:
    print(f"RESTART_ERROR:{e}")
"""
    
    try:
        # 执行重启脚本，使用安全模式上下文
        returncode, stdout, stderr = execute_mpremote_command(
            port, 'exec', restart_script,
            timeout=TIMEOUT_SAFE_MODE_EXIT,
            retries=1,
            verbose=verbose,
            safe_mode_context=True
        )
        
        # 检查是否成功发送重启命令
        if 'RESTART_INITIATED' in stdout:
            if verbose:
                print_message("已发送软件重启命令，设备将重新启动", "SUCCESS")
            return True
        elif 'RESTART_ERROR' in stdout:
            if verbose:
                print_message("软件重启失败，建议手动断电重启", "WARNING")
            return False
        else:
            if verbose:
                print_message("重启命令执行状态不明，建议手动检查设备", "WARNING")
            return False
            
    except Exception as e:
        if verbose:
            print_message(f"强制退出安全模式异常: {e}", "ERROR")
            print_message("建议手动断电重启设备", "WARNING")
        return False


def diagnose_safe_mode_issue(port, verbose=False):
    """诊断安全模式问题并提供详细的解决方案
    
    Returns:
        dict: 包含诊断结果和建议的字典
    """
    diagnosis = {
        'safe_mode_status': 'unknown',
        'system_health': {},
        'recommendations': [],
        'severity': 'unknown',
        'rshell_info': {}  # 添加rshell相关信息
    }
    
    if verbose:
        print_message("开始安全模式问题诊断...", "INFO")
    
    # 检查rshell工具可用性
    rshell_available, rshell_mode = check_rshell_available()
    diagnosis['rshell_info']['available'] = rshell_available
    diagnosis['rshell_info']['mode'] = rshell_mode if rshell_available else 'unavailable'
    
    if rshell_available:
        diagnosis['rshell_info']['status'] = 'ready'
        diagnosis['rshell_info']['note'] = 'rshell工具可用，可作为备用连接方案'
    else:
        diagnosis['rshell_info']['status'] = 'unavailable'
        diagnosis['rshell_info']['note'] = 'rshell工具不可用或存在兼容性问题'
    
    # 1. 检测安全模式状态
    safe_mode_status = detect_safe_mode(port, verbose=verbose)
    diagnosis['safe_mode_status'] = safe_mode_status
    
    if safe_mode_status == True:  # 布尔值True，设备处于安全模式
        diagnosis['severity'] = 'high'
        if verbose:
            print_message("设备确认处于安全模式，正在收集系统信息...", "WARNING")
        
        # 2. 收集系统健康信息
        health_script = """
try:
    import sys_daemon
    import gc
    import machine
    
    # 获取系统状态
    status = sys_daemon.get_daemon_status()
    print(f"DAEMON_STATUS:{status}")
    
    # 获取内存信息
    gc.collect()
    free_mem = gc.mem_free()
    alloc_mem = gc.mem_alloc()
    print(f"MEMORY_INFO:free={free_mem},alloc={alloc_mem}")
    
    # 获取温度信息（如果可用）
    try:
        temp = machine.temperature()
        print(f"TEMPERATURE:{temp}")
    except:
        print("TEMPERATURE:unavailable")
        
except Exception as e:
    print(f"HEALTH_CHECK_ERROR:{e}")
"""
        
        try:
            returncode, stdout, stderr = execute_mpremote_command(
                port, 'exec', health_script,
                timeout=5,  # 减少超时时间
                retries=1,  # 减少重试次数
                verbose=verbose,
                safe_mode_context=True
            )
            
            # 解析系统健康信息
            for line in stdout.strip().split('\n'):
                if line.startswith('DAEMON_STATUS:'):
                    diagnosis['system_health']['daemon_status'] = line.split(':', 1)[1]
                elif line.startswith('MEMORY_INFO:'):
                    mem_info = line.split(':', 1)[1]
                    diagnosis['system_health']['memory'] = mem_info
                elif line.startswith('TEMPERATURE:'):
                    temp_info = line.split(':', 1)[1]
                    diagnosis['system_health']['temperature'] = temp_info
                elif line.startswith('HEALTH_CHECK_ERROR:'):
                    diagnosis['system_health']['error'] = line.split(':', 1)[1]
        
        except Exception as e:
            diagnosis['system_health']['collection_error'] = str(e)
        
        # 3. 生成针对性建议
        recommendations = [
            "设备已进入安全模式，这通常是由于系统检测到严重问题",
            "安全模式下自动恢复已被禁用，需要手动干预",
            "立即解决方案：",
            "  1. 断开设备电源，等待10秒后重新上电",
            "  2. 如果问题持续，检查设备温度是否过高",
            "  3. 检查内存使用情况，清理不必要的文件",
            "  4. 检查最近的代码更改是否导致内存泄漏或死循环"
        ]
        
        # 添加rshell相关建议
        if rshell_available:
            recommendations.extend([
                "备用连接方案：",
                "  5. 如果mpremote连接失败，系统会自动尝试使用rshell进行硬重启",
                "  6. rshell工具已检测可用，可提供额外的设备恢复选项"
            ])
        else:
            recommendations.extend([
                "备用连接方案：",
                "  5. 建议安装rshell工具作为备用连接方案：pip install rshell",
                "  6. rshell可在mpremote连接失败时提供额外的设备恢复选项"
            ])
        
        recommendations.extend([
            "预防措施：",
            "  1. 定期监控设备温度和内存使用",
            "  2. 避免在代码中使用大量内存的操作",
            "  3. 实现适当的错误处理和资源清理",
            "  4. 考虑调整sys_daemon的监控参数"
        ])
        
        diagnosis['recommendations'] = recommendations
        
    elif safe_mode_status == False:  # 布尔值False，设备处于正常模式
        diagnosis['severity'] = 'low'
        recommendations = [
            "设备当前处于正常模式",
            "如果之前遇到连接问题，可能是临时的网络或通信问题",
            "建议检查：",
            "  1. USB连接是否稳定",
            "  2. 串口驱动是否正确安装",
            "  3. 设备是否被其他程序占用"
        ]
        
        # 添加rshell状态信息
        if rshell_available:
            recommendations.append("  4. rshell工具已就绪，可在需要时提供备用连接")
        else:
            recommendations.append("  4. 建议安装rshell工具以增强连接稳定性：pip install rshell")
        
        diagnosis['recommendations'] = recommendations
        
    elif safe_mode_status is None:  # None值，无法检测或守护进程不可用
        diagnosis['severity'] = 'medium'
        recommendations = [
            "无法检测到sys_daemon守护进程",
            "这可能表示：",
            "  1. 守护进程未正确启动",
            "  2. 设备固件版本不兼容",
            "  3. 系统文件损坏",
            "建议解决方案：",
            "  1. 重新上传完整的项目代码",
            "  2. 检查sys_daemon.py文件是否存在",
            "  3. 手动重启设备",
            "  4. 如果问题持续，考虑重新刷写固件"
        ]
        
        # 添加rshell备用方案建议
        if rshell_available:
            recommendations.extend([
                "备用连接方案：",
                "  5. 可尝试使用rshell工具进行设备连接和重启",
                "  6. rshell可能在某些情况下比mpremote更稳定"
            ])
        else:
            recommendations.extend([
                "备用连接方案：",
                "  5. 建议安装rshell工具：pip install rshell",
                "  6. rshell可提供与mpremote不同的连接机制"
            ])
        
        diagnosis['recommendations'] = recommendations
        
    elif isinstance(safe_mode_status, str) and 'error' in safe_mode_status.lower():
        diagnosis['severity'] = 'high'
        recommendations = [
            "检测安全模式时发生错误",
            "这通常表示设备通信存在严重问题",
            "紧急处理步骤：",
            "  1. 立即断开设备电源",
            "  2. 检查USB连接线是否损坏",
            "  3. 更换USB端口重试",
            "  4. 如果问题持续，设备可能需要维修"
        ]
        
        # 添加rshell紧急恢复建议
        if rshell_available:
            recommendations.extend([
                "紧急恢复方案：",
                "  5. 在设备通信异常时，rshell可能提供不同的连接路径",
                "  6. 系统会自动尝试rshell硬重启作为最后手段"
            ])
        else:
            recommendations.extend([
                "紧急恢复方案：",
                "  5. 强烈建议安装rshell工具：pip install rshell",
                "  6. rshell可在严重通信故障时提供备用恢复选项"
            ])
        
        diagnosis['recommendations'] = recommendations
        
    else:  # 其他未知状态或超时
        diagnosis['severity'] = 'medium'
        recommendations = [
            "无法确定设备的安全模式状态",
            "这可能是由于：",
            "  1. 设备响应超时",
            "  2. 通信协议不匹配",
            "  3. 设备固件异常",
            "排查步骤：",
            "  1. 检查设备是否正确连接",
            "  2. 尝试重新启动设备",
            "  3. 检查串口设置是否正确"
        ]
        
        # 添加rshell作为其他工具选项
        if rshell_available:
            recommendations.extend([
                "  4. rshell工具已就绪，可尝试使用rshell连接设备",
                "  5. 系统会在mpremote失败时自动尝试rshell备用方案"
            ])
        else:
            recommendations.extend([
                "  4. 建议安装rshell工具作为备用连接方案：pip install rshell",
                "  5. rshell可提供与mpremote不同的设备连接机制"
            ])
        
        diagnosis['recommendations'] = recommendations
    
    return diagnosis


def print_diagnosis_report(diagnosis, verbose=True):
    """打印详细的诊断报告"""
    if not verbose:
        return
    
    print_message("\n" + "="*60, "INFO")
    print_message("ESP32-C3 安全模式诊断报告", "INFO")
    print_message("="*60, "INFO")
    
    # 状态信息
    status_color = {
        'True': 'ERROR',
        'False': 'SUCCESS', 
        'no_daemon': 'WARNING',
        'unknown': 'WARNING',
        'error': 'ERROR'
    }.get(diagnosis['safe_mode_status'], 'INFO')
    
    print_message(f"安全模式状态: {diagnosis['safe_mode_status']}", status_color)
    print_message(f"问题严重程度: {diagnosis['severity']}", "INFO")
    
    # rshell工具状态信息
    if 'rshell_info' in diagnosis and diagnosis['rshell_info']:
        rshell_info = diagnosis['rshell_info']
        rshell_available = rshell_info.get('available', False)
        rshell_mode = rshell_info.get('mode', 'unknown')
        rshell_color = 'SUCCESS' if rshell_available else 'WARNING'
        
        status_text = '可用' if rshell_available else '不可用'
        if rshell_available and rshell_mode != 'unavailable':
            status_text += f' ({rshell_mode}模式)'
        
        print_message(f"\nrshell工具状态: {status_text}", rshell_color)
        if 'note' in rshell_info:
            print_message(f"  说明: {rshell_info['note']}", "INFO")
    
    # 系统健康信息
    if diagnosis['system_health']:
        print_message("\n系统健康信息:", "INFO")
        for key, value in diagnosis['system_health'].items():
            print_message(f"  {key}: {value}", "INFO")
    
    # 建议和解决方案
    print_message("\n诊断建议:", "INFO")
    for i, recommendation in enumerate(diagnosis['recommendations'], 1):
        if recommendation.startswith('  '):
            print_message(f"    {recommendation.strip()}", "INFO")
        else:
            print_message(f"  {recommendation}", "INFO")
    
    print_message("\n" + "="*60 + "\n", "INFO")

# ==================== 设备控制 ====================

def hardware_reset_device(port, verbose=False):
    """通过DTR/RTS信号对ESP32设备进行硬重置"""
    if not SERIAL_AVAILABLE:
        if verbose: print_message("pyserial不可用，跳过硬重置", "WARNING")
        return False
    
    try:
        if verbose: print_message(f"正在对端口 {port} 执行硬重置...", "INFO")
        with serial.Serial(port, 115200, timeout=1) as ser:
            # ESP32硬重置序列：拉低DTR和RTS
            ser.dtr = False
            ser.rts = False
            time.sleep(0.1)
            
            # 释放DTR，保持RTS低电平进入下载模式
            ser.dtr = True
            time.sleep(0.1)
            
            # 释放RTS，让设备正常启动
            ser.rts = True
            time.sleep(0.5)  # 等待设备启动
            
        if verbose: print_message("硬重置完成", "SUCCESS")
        return True
    except Exception as e:
        if verbose: print_message(f"硬重置失败: {e}", "WARNING")
        return False

def check_device_status(port, verbose=False):
    """检查设备状态和连接性"""
    if verbose: print_message("检查设备状态...", "INFO")
    
    # 尝试简单的ping命令
    test_script = "print('DEVICE_OK')"
    returncode, stdout, stderr = execute_mpremote_command(
        port, "exec", test_script, timeout=5, retries=2, verbose=verbose
    )
    
    if returncode == 0 and "DEVICE_OK" in stdout:
        if verbose: print_message("设备状态正常", "SUCCESS")
        return True
    else:
        if verbose: print_message(f"设备状态异常: {stderr.strip()}", "WARNING")
        return False

def prepare_device(port, verbose=False, max_retries=3):
    """多阶段设备准备策略，包含安全模式检测、硬重置、软重置和重试机制"""
    print_message("正在准备设备...", "INFO")
    
    for attempt in range(max_retries):
        if attempt > 0:
            print_message(f"第 {attempt + 1} 次尝试连接设备...", "INFO")
        
        # 阶段0: 快速安全模式检测和处理（优化版）
        if verbose: print_message("快速检测设备安全模式状态...", "INFO")
        
        try:
            # 使用更短的超时时间进行快速检测
            safe_mode_status = detect_safe_mode(port, verbose=False)  # 关闭详细输出以加快检测
            
            if safe_mode_status == True:  # 明确检测到安全模式
                print_message("检测到设备处于安全模式，尝试强制退出...", "WARNING")
                if force_exit_safe_mode(port, verbose):
                    print_message("成功退出安全模式，等待设备重启...", "SUCCESS")
                    time.sleep(3)  # 减少等待时间
                    # 重新检查设备状态
                    if check_device_status(port, verbose):
                        print_message("设备准备成功 (安全模式恢复)", "SUCCESS")
                        return True
                # 如果强制退出失败，直接跳到硬重置
                print_message("安全模式退出失败，直接进行硬重置...", "WARNING")
                if hardware_reset_device(port, verbose):
                    time.sleep(3)  # 等待设备完全启动
                    if check_device_status(port, verbose):
                        print_message("设备准备成功 (安全模式硬重置)", "SUCCESS")
                        return True
            elif safe_mode_status == False:  # 明确检测到正常模式
                if verbose: print_message("设备处于正常模式，继续标准流程", "INFO")
            else:  # 检测失败、超时或未知状态
                if verbose: print_message("安全模式检测超时或失败，跳过检测直接尝试硬重置", "WARNING")
                # 直接进行硬重置，不再尝试其他方法
                if hardware_reset_device(port, verbose):
                    time.sleep(3)  # 等待设备完全启动
                    if check_device_status(port, verbose):
                        print_message("设备准备成功 (检测超时后硬重置)", "SUCCESS")
                        return True
                    
        except Exception as e:
            if verbose: print_message(f"安全模式检测异常: {e}，直接进行硬重置", "WARNING")
            # 检测异常时直接硬重置
            if hardware_reset_device(port, verbose):
                time.sleep(3)
                if check_device_status(port, verbose):
                    print_message("设备准备成功 (检测异常后硬重置)", "SUCCESS")
                    return True
        
        # 阶段1: 发送中断信号，停止当前运行的程序
        if verbose: print_message("发送中断信号...", "INFO")
        try:
            subprocess.run([MPREMOTE_EXECUTABLE, 'connect', port, 'exec', '\x03'], 
                          capture_output=True, timeout=2, text=True)
        except subprocess.TimeoutExpired:
            pass  # 中断信号不需要等待响应
        time.sleep(3)  # 等待设备完全停止
        
        # 阶段2: 尝试exec命令
        if verbose: print_message("尝试exec命令...", "INFO")
        returncode, _, stderr = execute_mpremote_command(port, "exec", "pass", timeout=TIMEOUT_SHORT, retries=2, verbose=verbose)
        if returncode == 0:
            if check_device_status(port, verbose):
                if verbose: print_message("设备准备成功 (exec)", "SUCCESS")
                return True
        
        # 阶段3: 尝试软重置
        if verbose: print_message("尝试软重置...", "INFO")
        returncode, _, stderr = execute_mpremote_command(port, "reset", timeout=TIMEOUT_SHORT, retries=2, verbose=verbose)
        if returncode == 0:
            time.sleep(2)  # 等待设备重启
            if check_device_status(port, verbose):
                if verbose: print_message("设备准备成功 (软重置)", "SUCCESS")
                return True
        
        # 阶段4: 硬重置（最后手段）
        if attempt < max_retries - 1:  # 不在最后一次尝试硬重置
            if verbose: print_message("尝试硬重置...", "INFO")
            if hardware_reset_device(port, verbose):
                time.sleep(3)  # 等待设备完全启动
                if check_device_status(port, verbose):
                    if verbose: print_message("设备准备成功 (硬重置)", "SUCCESS")
                    return True
        
        # 如果不是最后一次尝试，等待一段时间再重试
        if attempt < max_retries - 1:
            wait_time = 2 * (attempt + 1)  # 递增等待时间
            if verbose: print_message(f"等待 {wait_time} 秒后重试...", "INFO")
            time.sleep(wait_time)
    
    # 所有mpremote尝试都失败了，尝试rshell备用方案
    print_message("所有mpremote尝试都失败，尝试使用rshell备用方案...", "WARNING")
    
    # 检查rshell是否可用
    rshell_available, _ = check_rshell_available()
    if rshell_available:
        print_message("检测到rshell工具，尝试使用rshell进行硬重启...", "INFO")
        
        # 尝试使用rshell进行硬重启
        if rshell_hard_reset_fallback(port, verbose):
            print_message("rshell硬重启成功，设备已准备就绪", "SUCCESS")
            return True
        else:
            print_message("rshell硬重启失败", "WARNING")
    else:
        print_message("rshell工具不可用，跳过rshell备用方案", "WARNING")
    
    # 所有尝试都失败了
    print_message("设备准备失败，已尝试所有方法（包括rshell备用方案）", "ERROR")
    
    # 最后一次安全模式检测和详细诊断
    if verbose:
        print_message("所有尝试都失败了，正在进行详细诊断...", "WARNING")
    
    # 执行完整的安全模式诊断
    diagnosis = diagnose_safe_mode_issue(port, verbose=verbose)
    
    # 打印详细的诊断报告
    print_diagnosis_report(diagnosis, verbose=True)
    
    # 根据诊断结果提供额外的操作建议
    if diagnosis['safe_mode_status'] == 'True' and diagnosis['severity'] == 'high':
        print_message("\n紧急操作建议：", "ERROR")
        print_message("  由于设备处于安全模式，建议立即采取以下行动：", "ERROR")
        print_message("  1. 立即断开设备电源（拔掉USB线）", "ERROR")
        print_message("  2. 等待至少10秒让设备完全断电", "ERROR")
        print_message("  3. 检查设备是否过热，如是请等待冷却", "ERROR")
        print_message("  4. 重新连接设备并重试", "ERROR")
        
        # 询问用户是否尝试强制重启
        try:
            user_input = input("\n是否尝试通过软件强制重启设备？(y/N): ").strip().lower()
            if user_input in ['y', 'yes']:
                print_message("正在尝试强制重启...", "INFO")
                if force_exit_safe_mode(port, verbose=True):
                    print_message("强制重启命令已发送，请等待设备重启后重试", "SUCCESS")
                else:
                    print_message("强制重启失败，请手动断电重启设备", "ERROR")
        except (KeyboardInterrupt, EOFError):
            print_message("\n用户取消操作", "INFO")
    
    return False

def clean_device(port, verbose=False):
    """高效且安全地清空设备上的所有文件和文件夹"""
    print_message("正在清空设备上的文件...", "INFO")
    # 优化的MicroPython清理脚本
    clean_script = """
import os
def clean(path='/'):
    files_in_dir = []
    dirs_in_dir = []
    # 先列出所有条目
    for item in os.listdir(path):
        # 排除 boot.py 和 main.py，最后处理
        if item in ('boot.py', 'main.py') and path == '/':
            continue
        item_path = path + '/' + item if path != '/' else '/' + item
        try:
            is_dir = os.stat(item_path)[0] & 0x4000
            if is_dir:
                dirs_in_dir.append(item_path)
            else:
                files_in_dir.append(item_path)
        except OSError:
            print(f"无法访问: {item_path}")
    
    # 先删除所有文件
    for f in files_in_dir:
        try:
            os.remove(f)
            print(f"删除文件: {f}")
        except OSError as e:
            print(f"删除文件失败: {f} - {e}")
            
    # 递归清理子目录
    for d in dirs_in_dir:
        clean(d)
        try:
            os.rmdir(d)
            print(f"删除目录: {d}")
        except OSError as e:
            print(f"删除目录失败: {d} - {e}")

# 执行清理
clean('/')
# 最后尝试删除核心文件
for f in ('/boot.py', '/main.py'):
    try:
        os.remove(f)
        print(f"删除文件: {f}")
    except OSError:
        pass
print("清理完成")
"""
    returncode, stdout, stderr = execute_mpremote_command(
        port, "exec", clean_script, 
        timeout=TIMEOUT_LONG, 
        retries=2, 
        verbose=verbose
    )
    
    if verbose:
        print_message("--- 设备端清理日志 ---", "INFO")
        print(stdout)
        print_message("--- 日志结束 ---", "INFO")

    if returncode == 0:
        print_message("设备清理完成", "SUCCESS")
        return True
    else:
        print_message(f"设备清理失败: {stderr}", "ERROR")
        return False

def reset_device(port, verbose=False):
    """软重置设备"""
    print_message("正在重置设备...", "INFO")
    returncode, _, stderr = execute_mpremote_command(
        port, "reset", 
        timeout=TIMEOUT_SHORT, 
        retries=2, 
        verbose=verbose
    )
    
    if returncode == 0:
        print_message("设备重置完成", "SUCCESS")
        time.sleep(2)  # 等待设备重启
        return True
    else:
        print_message(f"设备重置失败: {stderr.strip()}", "WARNING")
        return False

def start_interactive_repl(port):
    """启动交互式REPL会话，自动绕过编码错误"""
    print_message(f"启动交互式REPL会话 (端口: {port})", "INFO")
    print_message("按 Ctrl+] 或 Ctrl+X 退出REPL", "INFO")
    print_message("提示: 已启用编码错误自动处理，不会因UTF-8错误而崩溃", "INFO")
    
    try:
        # 方法1: 使用环境变量和错误处理
        import os
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8:replace'  # 设置Python的编码错误处理
        
        # 尝试直接运行mpremote
        process = subprocess.Popen(
            [MPREMOTE_EXECUTABLE, 'connect', port, 'repl'],
            env=env,
            encoding='utf-8',
            errors='replace',  # 关键：替换无法解码的字符
            text=True,
            # 不重定向stdin/stdout/stderr，让系统直接处理交互
        )
        
        # 等待进程结束
        process.wait()
        print_message("REPL会话已结束", "INFO")
        
    except UnicodeDecodeError as e:
        print_message("检测到UTF-8编码错误，尝试备用方案...", "WARNING")
        # 方法2: 使用原始字节处理
        try:
            print_message("启动备用REPL模式 (原始字节处理)", "INFO")
            process = subprocess.Popen(
                [MPREMOTE_EXECUTABLE, 'connect', port, 'repl'],
                env=env,
                # 不设置encoding，使用原始字节
                # 但仍然设置环境变量
            )
            process.wait()
            print_message("备用REPL会话已结束", "INFO")
        except Exception as e2:
            print_message(f"备用REPL模式也失败: {e2}", "ERROR")
            print_message("建议使用原始REPL模式: python build_m.py --raw-repl", "INFO")
        
    except subprocess.TimeoutExpired:
        print_message("REPL会话超时", "WARNING")
        
    except KeyboardInterrupt:
        print_message("\nREPL会话已由用户中断", "INFO")
        
    except Exception as e:
        print_message(f"REPL启动失败: {e}", "ERROR")
        print_message("建议尝试以下解决方案:", "INFO")
        print_message("  1. 检查设备连接是否正常", "INFO")
        print_message("  2. 重启设备后重试", "INFO")
        print_message("  3. 检查mpremote工具是否正确安装", "INFO")
        print_message("  4. 尝试使用原始REPL模式: python build_m.py --raw-repl", "INFO")


def start_raw_repl(port):
    """启动原始REPL会话，显示所有原始输出"""
    print_message(f"启动原始REPL会话 (端口: {port})", "INFO")
    print_message("按 Ctrl+] 或 Ctrl+X 退出REPL", "INFO")
    print_message("警告: 原始模式可能显示编码错误，但可以看到所有输出", "WARNING")
    
    try:
        # 直接运行mpremote，不进行任何编码处理
        process = subprocess.Popen(
            [MPREMOTE_EXECUTABLE, 'connect', port, 'repl'],
            # 不设置encoding和errors，使用原始字节
        )
        
        # 等待进程结束
        process.wait()
        print_message("原始REPL会话已结束", "INFO")
        
    except subprocess.TimeoutExpired:
        print_message("REPL会话超时", "WARNING")
        
    except KeyboardInterrupt:
        print_message("\nREPL会话已由用户中断", "INFO")
        
    except Exception as e:
        print_message(f"原始REPL启动失败: {e}", "ERROR")


def monitor_device(port):
    """启动设备输出监控"""
    print_message(f"开始监控设备输出 (端口: {port})", "INFO")
    print_message("按 Ctrl+C 停止监控", "INFO")
    try:
        subprocess.run([MPREMOTE_EXECUTABLE, 'connect', port, 'monitor'], check=True)
    except KeyboardInterrupt:
        print_message("\n监控已停止", "INFO")
    except Exception as e:
        print_message(f"监控启动失败: {e}", "ERROR")

# ==================== 文件上传 ====================

def upload_file(port, local_path, remote_path, verbose=False):
    """上传单个文件并使用MicroPython兼容的方式进行验证"""
    # 执行上传命令（带重试）
    returncode, _, stderr = execute_mpremote_command(
        port, "fs", "cp", str(local_path), f":{remote_path}", 
        timeout=TIMEOUT_MEDIUM, 
        retries=2, 
        verbose=verbose
    )
    if returncode != 0:
        if verbose: print_message(f"上传命令失败: {remote_path} - {stderr.strip()}", "ERROR")
        return False

    # *** 关键修复 ***
    # 使用 os.stat() 进行验证，因为它在标准 MicroPython 中可用
    verify_script = f"""
import os
try:
    os.stat('{remote_path}')
    print('EXISTS')
except OSError:
    print('NOT_EXISTS')
"""
    returncode, stdout, stderr = execute_mpremote_command(
        port, "exec", verify_script, 
        timeout=TIMEOUT_SHORT, 
        retries=2, 
        verbose=verbose
    )

    if returncode == 0 and "EXISTS" in stdout:
        return True
    else:
        if verbose:
            print_message(f"文件验证失败: {remote_path}", "ERROR")
            print_message(f"  - stdout: {stdout.strip()}", "ERROR")
            print_message(f"  - stderr: {stderr.strip()}", "ERROR")
        return False

def upload_directory(port, dist_dir, verbose=False, force_full_upload=False):
    """上传整个目录，支持智能同步和缓存"""
    upload_cache = {} if force_full_upload else load_cache(UPLOAD_CACHE_FILE)
    new_cache = upload_cache.copy()
    files_to_upload, dirs_to_create = [], set()

    # 收集需要上传的文件和创建的目录
    for root, _, files in os.walk(dist_dir):
        rel_path = Path(root).relative_to(dist_dir)
        if rel_path.name != '.': # 确保不把根目录 '.' 加入
            dirs_to_create.add(rel_path)

        for file in files:
            local_file = Path(root) / file
            if should_exclude(local_file, EXCLUDE_PATTERNS):
                continue

            # 使用 as_posix() 确保远程路径使用 '/'
            remote_file = (rel_path / file).as_posix()
            if remote_file.startswith('./'):
                remote_file = remote_file[2:]

            file_md5 = get_file_md5(local_file)
            if not file_md5: continue

            # 使用本地文件的相对路径作为缓存键值，确保路径一致性
            cache_key = str(local_file).replace('\\', '/')
            if not force_full_upload and upload_cache.get(cache_key) == file_md5:
                if verbose: print_message(f"跳过未变更文件: {remote_file}", "INFO")
                continue

            files_to_upload.append((local_file, remote_file, file_md5, cache_key))

    if not files_to_upload and not force_full_upload:
        print_message("所有文件都是最新的，无需上传", "SUCCESS")
        return True

    # 创建目录结构
    if dirs_to_create:
        # 过滤掉根目录 '.'
        valid_dirs = {d for d in dirs_to_create if d.name != '.'}
        if valid_dirs:
            print_message(f"创建 {len(valid_dirs)} 个目录...", "INFO")
            sorted_dirs = sorted(list(valid_dirs), key=lambda p: len(p.parts))
            for d in sorted_dirs:
                remote_dir_target = d.as_posix()
                returncode, _, stderr = execute_mpremote_command(
                    port, "fs", "mkdir", remote_dir_target, timeout=TIMEOUT_SHORT
                )
                # 忽略 "File exists" 错误
                if returncode != 0 and "exists" not in stderr.lower():
                    print_message(f"创建目录失败: {remote_dir_target} - {stderr.strip()}", "WARNING")

    # 上传文件
    upload_count = len(files_to_upload)
    if upload_count > 0:
        print_message(f"开始上传 {upload_count} 个文件...", "INFO")
        for i, (local_file, remote_file, file_md5, cache_key) in enumerate(files_to_upload):
            print_message(f"[{i+1}/{upload_count}] 上传: {local_file.name} -> {remote_file}", "INFO")
            if upload_file(port, local_file, remote_file, verbose):
                new_cache[cache_key] = file_md5
            else:
                print_message(f"上传失败: {remote_file}", "ERROR")
                print_message(f"  本地文件: {local_file}", "INFO")
                print_message(f"  文件大小: {os.path.getsize(local_file)} bytes", "INFO")
                # 上传失败后不保存缓存，以便下次重试
                return False

    # 保存新的上传缓存
    save_cache(new_cache, UPLOAD_CACHE_FILE)
    skip_count = len(upload_cache) - (len(new_cache) - upload_count)
    print_message(f"上传完成: {upload_count} 个文件已上传, {skip_count} 个文件已跳过", "SUCCESS")
    return True

# ==================== 主程序 ====================

def main():
    """主程序入口，解析命令行参数并执行相应操作"""
    parser = argparse.ArgumentParser(
        description="MicroPython 高性能构建和部署脚本 (v4.6)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""使用示例:
  python %(prog)s                # 默认: 编译, 上传, 然后监控设备
  python %(prog)s -c             # 仅编译
  python %(prog)s -u             # 仅上传 (智能同步)
  python %(prog)s -u --clean     # 清理设备后，再进行智能同步上传
  python %(prog)s --clean --full-upload # 清理设备后，再进行强制全量上传
  python %(prog)s -r             # 仅连接并进入交互式REPL (自动处理编码错误)
  python %(prog)s -m             # 仅连接并监控设备输出
  python %(prog)s --diagnose     # 诊断设备安全模式状态
  python %(prog)s --clean-cache  # 清理本地缓存
  python %(prog)s -p COM3        # 手动指定端口
  
编码错误处理:
  - REPL模式 (-r) 已内置编码错误自动处理，遇到UTF-8错误时会自动替换字符
  - 原始REPL模式 (--raw-repl) 显示所有原始输出，可能看到编码错误但信息最完整
  - 两种模式都不会因编码问题而崩溃，可根据需要选择使用
"""
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--compile", action="store_true", help="仅编译 src 目录到 dist")
    group.add_argument("-u", "--upload", action="store_true", help="仅上传 dist 目录到设备 (智能同步)")
    group.add_argument("-r", "--repl", action="store_true", help="仅连接并进入交互式REPL (自动处理编码错误)")
    group.add_argument("--raw-repl", action="store_true", help="仅连接并进入原始REPL模式 (显示所有原始输出)")
    group.add_argument("-m", "--monitor", action="store_true", help="仅连接并监控设备输出")
    group.add_argument("--diagnose", action="store_true", help="诊断设备安全模式状态并提供解决方案")
    group.add_argument("--clean-cache", action="store_true", help="清理本地端口和上传缓存文件")

    parser.add_argument("-p", "--port", type=str, help="指定设备端口，跳过自动检测")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细的调试输出")
    parser.add_argument("--no-reset", action="store_true", help="上传后不自动重置设备")
    parser.add_argument("--clean", action="store_true", help="上传前清空设备上的所有文件")
    parser.add_argument("--full-upload", action="store_true", help="强制全量上传，忽略本地缓存")
    args = parser.parse_args()

    print_message("=== MicroPython 构建和部署工具 v4.6 ===", "HEADER")

    if args.clean_cache:
        for cache_file in [PORT_CACHE_FILE, UPLOAD_CACHE_FILE]:
            if os.path.exists(cache_file):
                os.remove(cache_file)
                print_message(f"已删除缓存文件: {cache_file}", "SUCCESS")
        return

    if args.compile:
        print_message("--- 开始编译 ---", "HEADER")
        if check_tool(MPY_CROSS_EXECUTABLE):
            compile_project(args.verbose)
        return

    # 需要与设备交互的操作
    is_device_action = args.upload or args.repl or args.raw_repl or args.monitor or args.clean or args.diagnose or \
                       not any([args.compile, args.repl, args.raw_repl, args.monitor, args.clean_cache, args.diagnose])

    if not is_device_action:
        parser.print_help()
        return

    if not check_tool(MPREMOTE_EXECUTABLE): sys.exit(1)

    device_port = args.port or detect_esp32_port()
    if not device_port:
        print_message("无法找到设备端口。请使用 -p 参数手动指定。", "ERROR")
        sys.exit(1)
    if not args.port:
        print_message(f"自动选择端口: {device_port}", "INFO")

    if args.repl:
        start_interactive_repl(device_port)
        return
    if args.raw_repl:
        start_raw_repl(device_port)
        return
    if args.monitor:
        monitor_device(device_port)
        return
    if args.diagnose:
        print_message("--- 开始安全模式诊断 ---", "HEADER")
        diagnosis = diagnose_safe_mode_issue(device_port, args.verbose)
        print_diagnosis_report(diagnosis)
        return

    # 默认流程或上传流程
    if not args.upload: # 默认流程需要先编译
        print_message("--- 开始编译 ---", "HEADER")
        if not check_tool(MPY_CROSS_EXECUTABLE) or not compile_project(args.verbose):
            sys.exit(1)

    print_message("--- 开始部署 ---", "HEADER")
    if not os.path.isdir(DIST_DIR) or not os.listdir(DIST_DIR):
        print_message(f"'{DIST_DIR}' 目录不存在或为空。请先运行编译。", "ERROR")
        sys.exit(1)

    if not prepare_device(device_port, args.verbose):
        print_message("无法准备设备，部署中止。", "ERROR")
        sys.exit(1)

    if args.clean:
        if not clean_device(device_port, args.verbose):
            print_message("设备清理失败，部署中止。", "ERROR")
            sys.exit(1)
        # 清理设备后，强制进行全量上传，因为设备是空的
        args.full_upload = True
        print_message("设备已清理，将进行全量上传。", "INFO")

    if not upload_directory(device_port, DIST_DIR, args.verbose, args.full_upload):
        print_message("部署因文件上传失败而中止。", "ERROR")
        sys.exit(1)

    print_message("部署完成！", "SUCCESS")

    if not args.no_reset:
        reset_device(device_port)

    # 默认流程(无-u, -c, -r, -m等独立指令时)上传后进入监控模式
    if not any([args.upload, args.compile, args.repl, args.raw_repl, args.monitor, args.clean, args.clean_cache]):
        print_message("--- 开始监控设备输出 ---", "HEADER")
        monitor_device(device_port)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print_message("\n操作已由用户取消", "WARNING")
        sys.exit(0)
    except Exception as e:
        print_message(f"程序执行期间发生意外错误: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
