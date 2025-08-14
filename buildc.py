#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MicroPython 高性能构建和部署脚本 (v5.2 - 串口冲突处理增强版)
专为事件驱动架构的 ESP32-C3 IoT 设备设计

新增功能:
- 强制释放被占用的串口 (Thonny, IDE等)
- 进程检测和终止功能
- 串口独占检测和恢复

项目架构:
- app/  : 源代码目录 (开发代码, 编译后直接上传到设备根目录)
- dist/ : 编译输出文件 (上传到设备根目录 /)
- app/tests/: 单元测试文件 (位于 app 目录内)
- docs/ : 项目文档

作者: ESP32-C3 开发团队 (由AI重构和增强)
版本: 5.2 (串口冲突处理增强版)
日期: 2025-08-12
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
        # 设置控制台输出为 UTF-8, 以正确显示中文字符
        os.system("chcp 65001 > nul")
        os.system("set PYTHONIOENCODING=utf-8")
    except Exception as e:
        print(f"警告: 设置Windows代码页失败: {e}")

# 尝试导入 pyserial 和进程管理库
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# ==================== 配置常量 ====================

# --- 目录和文件配置 ---
SRC_DIR = "app"                    # 源代码目录 (开发和运行代码)
DIST_DIR = "dist"                  # 编译输出目录
DOCS_DIR = "docs"                  # 文档目录
TESTS_DIR = "app/tests"            # 测试目录 (位于 app 目录内)

# --- 工具可执行文件 ---
MPY_CROSS_EXECUTABLE = "mpy-cross"  # MicroPython 编译器
MPREMOTE_EXECUTABLE = "mpremote"   # MicroPython 远程工具
RSHELL_EXECUTABLE = "rshell"       # rshell 备用连接工具

# --- 编译排除文件 ---
NO_COMPILE_FILES = ['boot.py', 'main.py']  # 不进行交叉编译的文件列表
DEFAULT_EXCLUDE_DIRS = ['__pycache__']   # 默认排除的目录 (tests, app/tests 和 docs 会被模式排除)

# --- 缓存文件 ---
UPLOAD_CACHE_FILE = ".upload_cache.json"   # 上传缓存文件

# --- 排除模式 (用于编译和上传) ---
EXCLUDE_PATTERNS = [
    "__pycache__",     # Python 缓存目录
    "*.pyc",          # Python 字节码文件
    "*.pyo",          # Python 优化文件
    ".DS_Store",      # macOS 系统文件
    "Thumbs.db",      # Windows 缩略图文件
    UPLOAD_CACHE_FILE, # 脚本生成的上传缓存
    "*.md",           # Markdown 文档文件
    "*.txt",          # 文本文件
    "REFACTOR_*",     # 重构相关文件
    "*.log",          # 日志文件
    "*.tmp",          # 临时文件
    "*.bak",          # 备份文件
    ".idea",          # IDE 目录
    ".git",           # Git 目录
    "docs",           # 文档目录
    "tests",          # 测试目录 (根目录下的测试文件夹)
    "app/tests"       # 应用测试目录 (app/tests 文件夹, 除非 --test 标志启用)
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

# --- 串口占用程序检测 ---
SERIAL_BLOCKING_PROGRAMS = [
    'thonny.exe', 'thonny',           # Thonny IDE
    'mu-editor', 'mu.exe',            # Mu Editor
    'pycharm64.exe', 'pycharm.exe',   # PyCharm
    'code.exe', 'code',               # VS Code
    'arduino.exe', 'arduino',         # Arduino IDE
    'platformio.exe', 'pio.exe',      # PlatformIO
    'putty.exe', 'putty',             # PuTTY
    'teraterm.exe', 'ttermpro.exe',   # Tera Term
    'minicom', 'screen',              # Linux 串口工具
    'mpremote.exe', 'mpremote',       # 其他mpremote实例
    'rshell.exe', 'rshell',           # rshell
    'esptool.py', 'esptool.exe'       # ESP工具
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

# --- 串口释放配置 ---
PORT_RELEASE_TIMEOUT = 10        # 等待串口释放的超时时间(秒)
PROCESS_KILL_TIMEOUT = 5         # 强制终止进程的等待时间(秒)

# --- ANSI 颜色代码 ---
class Colors:
    INFO = '\033[94m'      # 蓝色
    SUCCESS = '\033[92m'   # 绿色
    WARNING = '\033[93m'   # 黄色
    ERROR = '\033[91m'     # 红色
    HEADER = '\033[95m'    # 紫色
    BOLD = '\033[1m'       # 加粗
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
    """计算文件的MD5哈希值, 用于文件变更检测"""
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
        print_message(f"缓存文件损坏, 将重新创建: {cache_file} - {e}", "WARNING")
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
    path_str = str(Path(path).as_posix())
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(Path(path).name, pattern):
            return True
    return False

# ==================== 串口冲突处理 ====================

def find_processes_using_port(port):
    """查找正在使用指定串口的 Thonny 相关进程"""
    if not PSUTIL_AVAILABLE:
        print_message("psutil 未安装, 无法检测进程占用。建议安装: pip install psutil", "WARNING")
        return []
    
    blocking_processes = []
    print_message(f"扫描可能占用串口 {port} 的 Thonny 相关进程...", "INFO")

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            proc_info = proc.info
            proc_name = proc_info['name'].lower()
            cmdline = ' '.join(proc_info['cmdline'] or []).lower()
            
            # 目标：仅查找并关闭 Thonny IDE 相关的进程
            is_thonny_process = 'thonny' in proc_name or 'thonny' in cmdline
            
            if is_thonny_process:
                print_message(f"检测到 Thonny 相关进程: {proc_info['name']} (PID: {proc_info['pid']})", "INFO")
                blocking_processes.append({
                    'pid': proc_info['pid'],
                    'name': proc_info['name'],
                    'cmdline': proc_info['cmdline']
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    return blocking_processes

def kill_processes_using_port(port, force=False, interactive=True):
    """终止占用串口的进程"""
    blocking_processes = find_processes_using_port(port)
    
    if not blocking_processes:
        print_message("未发现占用串口的进程", "INFO")
        return True
    
    print_message(f"发现 {len(blocking_processes)} 个可能占用串口 {port} 的进程:", "WARNING")
    for i, proc in enumerate(blocking_processes):
        cmdline_str = ' '.join(proc['cmdline']) if proc['cmdline'] else '(无命令行)'
        print(f"  {i+1}. PID: {proc['pid']}, 程序: {proc['name']}")
        print(f"      命令行: {cmdline_str[:80]}{'...' if len(cmdline_str) > 80 else ''}")
    
    if interactive and not force:
        confirm = input(f"\n是否终止这些进程以释放串口? (y/n/a): ").lower()
        if confirm == 'n':
            print_message("用户取消进程终止", "INFO")
            return False
        elif confirm == 'a':
            force = True
    
    killed_count = 0
    for proc in blocking_processes:
        try:
            process = psutil.Process(proc['pid'])
            process_name = proc['name']
            
            print_message(f"正在终止进程: {process_name} (PID: {proc['pid']})", "INFO")
            
            if not force:
                # 尝试友好终止
                process.terminate()
                try:
                    process.wait(timeout=PROCESS_KILL_TIMEOUT)
                    print_message(f"进程 {process_name} 已正常终止", "SUCCESS")
                    killed_count += 1
                except psutil.TimeoutExpired:
                    print_message(f"进程 {process_name} 拒绝正常终止, 将强制终止", "WARNING")
                    process.kill()
                    process.wait(timeout=PROCESS_KILL_TIMEOUT)
                    print_message(f"进程 {process_name} 已强制终止", "SUCCESS")
                    killed_count += 1
            else:
                # 直接强制终止
                process.kill()
                process.wait(timeout=PROCESS_KILL_TIMEOUT)
                print_message(f"进程 {process_name} 已强制终止", "SUCCESS")
                killed_count += 1
                
        except psutil.NoSuchProcess:
            print_message(f"进程 {proc['pid']} 已不存在", "INFO")
        except psutil.AccessDenied:
            print_message(f"权限不足, 无法终止进程 {proc['pid']} ({proc['name']})", "ERROR")
        except Exception as e:
            print_message(f"终止进程 {proc['pid']} 时出错: {e}", "ERROR")
    
    if killed_count > 0:
        print_message(f"已终止 {killed_count} 个进程, 等待串口释放...", "INFO")
        time.sleep(2)  # 等待系统释放串口资源
        return True
    else:
        print_message("未能终止任何进程", "ERROR")
        return False

def test_port_access(port, timeout=5):
    """测试串口是否可以访问"""
    if not SERIAL_AVAILABLE:
        return False
    
    try:
        with serial.Serial(port, baudrate=115200, timeout=timeout) as ser:
            return True
    except serial.SerialException:
        return False
    except Exception:
        return False

def release_port(port, force=False, interactive=True):
    """释放串口, 处理占用冲突"""
    print_message(f"检查串口 {port} 的占用状态...", "INFO")
    
    # 首先测试串口是否可用
    if test_port_access(port):
        print_message("串口可正常访问", "SUCCESS")
        return True
    
    print_message("串口被占用, 尝试释放...", "WARNING")
    
    # 查找并终止占用进程
    if not kill_processes_using_port(port, force=force, interactive=interactive):
        return False
    
    # 等待串口释放并重新测试
    print_message(f"等待串口释放 (最多 {PORT_RELEASE_TIMEOUT} 秒)...", "INFO")
    for i in range(PORT_RELEASE_TIMEOUT):
        if test_port_access(port):
            print_message("串口已成功释放", "SUCCESS")
            return True
        time.sleep(1)
    
    print_message("串口释放失败, 可能仍被其他程序占用", "ERROR")
    return False

# ==================== 设备检测 ====================

def detect_esp32_port():
    """自动检测ESP32设备端口, 每次都重新扫描"""
    if not SERIAL_AVAILABLE:
        print_message("pyserial 未安装, 无法自动检测端口。请手动指定端口。", "ERROR")
        print_message("安装命令: pip install pyserial", "INFO")
        return None

    # 扫描所有可用串口
    print_message("扫描ESP32设备...", "INFO")
    ports = serial.tools.list_ports.comports()
    esp32_ports = []
    for port in ports:
        # 检查 VID/PID 或描述关键词
        is_esp32_by_id = hasattr(port, 'vid') and hasattr(port, 'pid') and (port.vid, port.pid) in ESP32_VID_PID_PATTERNS
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
        # 多个设备, 让用户选择
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
                    print_message("无效的选择, 请重试。", "WARNING")
            except (ValueError, KeyboardInterrupt):
                print_message("操作取消。", "ERROR")
                return None

    return selected_port

# ==================== 工具检查 ====================

def check_tool(executable):
    """检查核心工具(mpy-cross, mpremote)是否在系统中可用"""
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

# ==================== 编译系统 ====================

def compile_project(verbose=False, include_tests=False):
    """编译项目文件从 app 到 dist, .py 文件编译为 .mpy"""
    if not os.path.isdir(SRC_DIR):
        print_message(f"源目录 '{SRC_DIR}' 不存在。", "ERROR")
        return False

    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)

    compiled_count, copied_count, error_count = 0, 0, 0
    
    # 动态调整排除模式
    current_exclude_patterns = EXCLUDE_PATTERNS.copy()
    if include_tests:
        if 'tests' in current_exclude_patterns:
            current_exclude_patterns.remove('tests')
        if 'app/tests' in current_exclude_patterns:
            current_exclude_patterns.remove('app/tests')

    # 首先处理 tests 目录, 如果启用测试文件
    if include_tests and os.path.exists(TESTS_DIR):
        print_message("处理 tests 目录...", "INFO")
        tests_target_dir = Path(DIST_DIR) / "tests"
        tests_target_dir.mkdir(parents=True)
        
        for root, dirs, files in os.walk(TESTS_DIR, topdown=True):
            # 过滤目录
            dirs[:] = [d for d in dirs if not should_exclude(Path(root) / d, current_exclude_patterns)]
            
            rel_path = Path(root).relative_to(TESTS_DIR)
            target_dir = tests_target_dir / rel_path
            
            if not target_dir.exists():
                target_dir.mkdir(parents=True)
            
            for file in files:
                src_file = Path(root) / file
                if should_exclude(src_file, current_exclude_patterns):
                    if verbose: print_message(f"排除文件: {src_file}", "INFO")
                    continue
                
                # tests 目录下的所有文件都直接复制, 不编译
                target_file = target_dir / file
                try:
                    shutil.copy2(src_file, target_file)
                    copied_count += 1
                    if verbose: print_message(f"复制测试文件: {src_file} -> {target_file}", "INFO")
                except IOError as e:
                    error_count += 1
                    print_message(f"复制测试文件失败: {src_file} - {e}", "ERROR")

    # 处理其他非 tests 目录
    for root, dirs, files in os.walk(SRC_DIR, topdown=True):
        # 跳过 tests 目录, 因为已经单独处理了
        dirs[:] = [d for d in dirs if d != 'tests' and not should_exclude(Path(root) / d, current_exclude_patterns)]
        
        rel_path = Path(root).relative_to(SRC_DIR)
        target_dir = Path(DIST_DIR) / rel_path

        if not target_dir.exists():
            target_dir.mkdir(parents=True)

        for file in files:
            src_file = Path(root) / file
            if should_exclude(src_file, current_exclude_patterns):
                if verbose: print_message(f"排除文件: {src_file}", "INFO")
                continue

            if file.endswith('.py') and file not in NO_COMPILE_FILES:
                target_file = target_dir / file.replace('.py', '.mpy')
                try:
                    subprocess.run(
                        [MPY_CROSS_EXECUTABLE, "-o", str(target_file), str(src_file)],
                        capture_output=True, text=True, check=True, encoding='utf-8', errors='ignore'
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

# ==================== 命令执行 ====================

def execute_mpremote_command(port, *cmd_args, timeout=60, retries=1, verbose=False, safe_mode_context=False):
    """执行 mpremote 命令并返回结果, 支持重试和详细错误分析, 针对安全模式优化"""
    command = [MPREMOTE_EXECUTABLE, 'connect', port, *cmd_args]
    
    if safe_mode_context:
        timeout = TIMEOUT_SAFE_MODE_RECOVERY if timeout == 60 else timeout
        retries = MAX_RETRIES_SAFE_MODE if retries == 1 else retries
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
            
            if result.returncode == 0 or not _is_connection_error(result.stderr):
                return result.returncode, result.stdout, result.stderr
            
            if attempt < retries - 1:
                if verbose:
                    print_message(f"连接错误, {retry_delay}秒后重试: {result.stderr.strip()[:100]}", "WARNING")
                time.sleep(retry_delay)
            else:
                return result.returncode, result.stdout, result.stderr
            
        except subprocess.TimeoutExpired:
            error_msg = f"命令超时 ({timeout}s): {' '.join(cmd_args)}"
            if attempt < retries - 1:
                if verbose: print_message(f"{error_msg}, {retry_delay}秒后重试...", "WARNING")
                time.sleep(retry_delay)
            else:
                print_message(error_msg, "ERROR")
                return -1, "", "命令执行超时"
                
        except Exception as e:
            error_msg = f"命令执行异常: {e}"
            if attempt < retries - 1:
                if verbose: print_message(f"{error_msg}, {retry_delay}秒后重试...", "WARNING")
                time.sleep(retry_delay)
            else:
                print_message(error_msg, "ERROR")
                return -1, "", str(e)
    
    return -1, "", "所有重试都失败了"

def _is_connection_error(stderr):
    """判断错误是否为连接相关错误"""
    connection_error_keywords = [
        "could not enter raw repl", "could not connect", "device not found",
        "permission denied", "access denied", "device busy",
        "no such file or directory", "connection failed", "timeout",
        "device disconnected", "it may be in use by another program"
    ]
    stderr_lower = stderr.lower()
    return any(keyword in stderr_lower for keyword in connection_error_keywords)

# ==================== 设备控制和上传 ====================

def clean_device(port, verbose=False):
    """高效且安全地清空设备上的所有文件和文件夹"""
    print_message("正在清空设备上的文件...", "INFO")
    clean_script = """
import os
def clean(path='/'):
    for item in os.listdir(path):
        item_path = f"{path}/{item}".replace('//', '/')
        try:
            is_dir = (os.stat(item_path)[0] & 0x4000) != 0
            if is_dir:
                clean(item_path)
                os.rmdir(item_path)
                print(f"删除目录: {item_path}")
            else:
                os.remove(item_path)
                print(f"删除文件: {item_path}")
        except OSError as e:
            print(f"删除失败: {item_path} - {e}")
clean()
print("清理完成")
"""
    returncode, stdout, stderr = execute_mpremote_command(
        port, "exec", clean_script, timeout=TIMEOUT_LONG, retries=2, verbose=verbose
    )
    if verbose and stdout:
        print_message("---设备端清理日志---\n" + stdout + "\n---日志结束---", "INFO")
    if returncode == 0:
        print_message("设备清理完成", "SUCCESS")
        return True
    else:
        print_message(f"设备清理失败: {stderr}", "ERROR")
        return False

def upload_directory(port, dist_dir, verbose=False, force_full_upload=False):
    """上传整个目录, 支持智能同步和缓存"""
    upload_cache = {} if force_full_upload else load_cache(UPLOAD_CACHE_FILE)
    new_cache = upload_cache.copy()
    files_to_upload, dirs_to_create = [], set()

    for root, _, files in os.walk(dist_dir):
        rel_path = Path(root).relative_to(dist_dir)
        if str(rel_path) != '.':
            dirs_to_create.add(rel_path.as_posix())

        for file in files:
            local_file = Path(root) / file
            remote_file = (rel_path / file).as_posix()
            if str(rel_path) == '.':
                remote_file = file
            
            file_md5 = get_file_md5(local_file)
            if not file_md5: continue

            cache_key = str(local_file).replace('\\', '/')
            if not force_full_upload and upload_cache.get(cache_key) == file_md5:
                if verbose: print_message(f"跳过未变更文件: {remote_file}", "INFO")
                continue
            
            files_to_upload.append((local_file, remote_file, file_md5, cache_key))

    if not files_to_upload and not dirs_to_create and not force_full_upload:
        print_message("所有文件都是最新的, 无需上传", "SUCCESS")
        return True

    # 创建目录
    if dirs_to_create:
        sorted_dirs = sorted(list(dirs_to_create))
        print_message(f"创建 {len(sorted_dirs)} 个目录...", "INFO")
        for d in sorted_dirs:
            execute_mpremote_command(port, "fs", "mkdir", d, timeout=TIMEOUT_SHORT)

    # 上传文件
    if files_to_upload:
        print_message(f"开始上传 {len(files_to_upload)} 个文件...", "INFO")
        for i, (local, remote, md5, key) in enumerate(files_to_upload):
            print_message(f"[{i+1}/{len(files_to_upload)}] 上传: {local.name} -> /{remote}", "INFO")
            ret, _, err = execute_mpremote_command(port, "fs", "cp", str(local), f":/{remote}", timeout=TIMEOUT_MEDIUM)
            if ret == 0:
                new_cache[key] = md5
            else:
                print_message(f"上传失败: {remote} - {err.strip()}", "ERROR")
                return False

    save_cache(new_cache, UPLOAD_CACHE_FILE)
    print_message("文件上传成功", "SUCCESS")
    return True

def reset_device(port, verbose=False):
    """软重置设备"""
    print_message("正在重置设备...", "INFO")
    returncode, _, stderr = execute_mpremote_command(
        port, "reset", timeout=TIMEOUT_SHORT, retries=2, verbose=verbose
    )
    if returncode == 0:
        print_message("设备重置完成", "SUCCESS")
        time.sleep(2)
        return True
    else:
        print_message(f"设备重置失败: {stderr.strip()}", "WARNING")
        return False

def start_repl(port, raw=False):
    """启动REPL连接到设备"""
    mode = "原始" if raw else "交互式"
    print_message(f"启动{mode}REPL (端口: {port})", "INFO")
    print_message("按 Ctrl+] 或 Ctrl+X 退出", "INFO")
    
    cmd = [MPREMOTE_EXECUTABLE, "connect", port, "repl"]
    if raw:
        cmd.append("--raw-paste") # A better mode for raw interaction
    
    try:
        # 在Windows上, 使用subprocess.run可能会有问题, 直接启动新进程
        if sys.platform == "win32":
            os.system(f"start {MPREMOTE_EXECUTABLE} connect {port} repl")
        else:
            subprocess.run(cmd)
    except KeyboardInterrupt:
        print_message(f"\n{mode}REPL连接已断开", "INFO")
    except Exception as e:
        print_message(f"{mode}REPL连接异常: {e}", "ERROR")

def monitor_device(port, verbose=False):
    """启动设备输出监控"""
    print_message(f"开始监控设备输出 (端口: {port})", "INFO")
    print_message("按 Ctrl+C 停止监控", "INFO")
    
    cmd = [MPREMOTE_EXECUTABLE, "connect", port, "repl"]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        while True:
            line = process.stdout.readline()
            if not line:
                break
            print(line.strip())
    except KeyboardInterrupt:
        print_message("\n监控已停止", "INFO")
    except Exception as e:
        print_message(f"监控异常: {e}", "ERROR")
    finally:
        if process and process.poll() is None:
            process.terminate()

def diagnose_device(port, verbose=False):
    """诊断设备状态, 特别是安全模式"""
    print_message("开始设备诊断...", "INFO")
    # 简单的诊断：检查设备是否能正常执行代码
    ret, out, err = execute_mpremote_command(port, "exec", "import gc; print(gc.mem_free())", retries=2)
    if ret == 0:
        print_message("设备连接正常", "SUCCESS")
        print_message(f"可用内存: {out.strip()} 字节", "INFO")
    else:
        print_message("设备连接异常或无响应", "ERROR")
        print_message(f"错误信息: {err.strip()}", "WARNING")
        print_message("建议：", "INFO")
        print_message("1. 检查USB线缆和端口连接", "INFO")
        print_message("2. 尝试手动重启设备", "INFO")
        print_message("3. 运行 'python build.py --clean --upload' 强制重新部署", "INFO")

# ==================== 设备连接管理 ====================

def connect_to_device(port, force_release=False, interactive=True, verbose=False):
    """连接到设备, 处理串口占用问题"""
    print_message(f"尝试连接到设备: {port}", "INFO")
    
    # 首先尝试直接连接
    ret, _, err = execute_mpremote_command(port, "exec", "print('连接测试')", timeout=10, retries=1, verbose=verbose)
    if ret == 0:
        print_message("设备连接成功", "SUCCESS")
        return True
    
    # 检查是否是串口占用问题
    if "it may be in use by another program" in err.lower() or "access denied" in err.lower():
        print_message("检测到串口被其他程序占用", "WARNING")
        
        if not force_release and interactive:
            confirm = input("是否尝试释放串口? (y/n): ").lower()
            if confirm != 'y':
                print_message("用户取消串口释放", "INFO")
                return False
        
        # 尝试释放串口
        if release_port(port, force=force_release, interactive=interactive):
            # 再次尝试连接
            print_message("重新尝试连接设备...", "INFO")
            ret, _, err = execute_mpremote_command(port, "exec", "print('重连测试')", timeout=10, retries=2, verbose=verbose)
            if ret == 0:
                print_message("设备连接成功", "SUCCESS")
                return True
            else:
                print_message(f"重新连接失败: {err.strip()}", "ERROR")
                return False
        else:
            print_message("串口释放失败", "ERROR")
            return False
    else:
        print_message(f"设备连接失败: {err.strip()}", "ERROR")
        return False

# ==================== 主程序 ====================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="ESP32-C3 MicroPython 构建和部署工具 (v5.2 - 串口冲突处理增强版)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python build.py                # 编译并上传 (智能同步)
  python build.py -c 或 --compile      # 仅编译 app/ 目录到 dist/
  python build.py -u 或 --upload       # 仅上传到设备 (智能同步)
  python build.py -c -u 或 --compile --upload  # 编译并上传
  python build.py -C 或 --clean        # 清理设备文件后, 再执行上传
  python build.py -f 或 --full-upload  # 强制全量上传, 忽略缓存
  python build.py -r 或 --repl         # 启动交互式REPL
  python build.py -R 或 --raw-repl     # 启动原始REPL
  python build.py -m 或 --monitor      # 监控设备输出
  python build.py -d 或 --diagnose     # 诊断设备连接状态
  python build.py -u -p COM3 或 --upload --port COM3  # 指定端口上传
  python build.py -t 或 --test         # 编译时包含 tests/ 和 app/tests/ 目录
  python build.py --clean-cache        # 清理本地缓存
  
串口冲突处理:
  python build.py --force-release      # 强制释放被占用的串口
  python build.py --kill-blocking      # 自动终止占用串口的程序
  python build.py -u --no-interactive  # 非交互模式(自动处理冲突)
  
短参数组合示例:
  python build.py -cu    # 编译并上传
  python build.py -Cv    # 清理设备并显示详细输出
  python build.py -cu -t # 编译并上传(包含测试文件)
        """
    )
    
    # 操作模式
    parser.add_argument("-c", "--compile", action="store_true", help="仅编译, 不上传")
    parser.add_argument("-u", "--upload", action="store_true", help="编译并上传 (或仅上传, 如果 dist 存在)")
    parser.add_argument("-r", "--repl", action="store_true", help="启动交互式REPL")
    parser.add_argument("-R", "--raw-repl", action="store_true", help="启动原始REPL")
    parser.add_argument("-m", "--monitor", action="store_true", help="监控设备输出")
    parser.add_argument("-d", "--diagnose", action="store_true", help="诊断设备状态")

    # 构建和上传选项
    parser.add_argument("-t", "--test", action="store_true", help="编译时包含测试文件 (app/tests/)")
    parser.add_argument("-C", "--clean", action="store_true", help="上传前清空设备")
    parser.add_argument("-f", "--full-upload", action="store_true", help="强制全量上传, 忽略缓存")
    
    # 设备选项
    parser.add_argument("-p", "--port", type=str, help="指定设备端口, 跳过自动检测")
    parser.add_argument("--no-reset", action="store_true", help="上传后不自动重置设备")
    
    # 串口冲突处理选项
    parser.add_argument("--force-release", action="store_true", help="强制释放被占用的串口")
    parser.add_argument("--kill-blocking", action="store_true", help="自动终止占用串口的程序")
    parser.add_argument("--no-interactive", action="store_true", help="非交互模式, 自动处理所有冲突")
    
    # 其他
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("--clean-cache", action="store_true", help="清理本地缓存文件")
    
    args = parser.parse_args()
    
    print_message("=== ESP32-C3 IoT 设备构建工具 (v5.2 - 串口冲突处理增强版) ===", "HEADER")
    
    # 清理缓存
    if args.clean_cache:
        print_message("清理缓存文件...", "INFO")
        if os.path.isfile(UPLOAD_CACHE_FILE):
            try:
                os.remove(UPLOAD_CACHE_FILE)
                print_message(f"已删除: {UPLOAD_CACHE_FILE}", "SUCCESS")
            except OSError as e:
                print_message(f"删除失败: {UPLOAD_CACHE_FILE} - {e}", "ERROR")
        return

    # 检查依赖库
    if not PSUTIL_AVAILABLE and (args.force_release or args.kill_blocking):
        print_message("psutil 未安装, 无法进行进程管理。", "ERROR")
        print_message("安装命令: pip install psutil", "INFO")
        sys.exit(1)

    # 检查工具
    if not check_tool(MPY_CROSS_EXECUTABLE) or not check_tool(MPREMOTE_EXECUTABLE):
        sys.exit(1)

    # 确定操作
    is_device_action = any([args.upload, args.repl, args.raw_repl, args.monitor, args.diagnose, args.clean])
    # 默认操作是编译和上传
    if not any([args.compile, is_device_action]):
        args.upload = True
        is_device_action = True

    # --- 编译 ---
    if args.compile or args.upload:
        print_message("开始编译项目...", "HEADER")
        if not compile_project(verbose=args.verbose, include_tests=args.test):
            print_message("编译失败, 操作中止", "ERROR")
            sys.exit(1)
        if args.compile and not is_device_action:
             print_message("仅编译完成", "SUCCESS")
             return

    # --- 设备相关操作 ---
    if is_device_action:
        device_port = args.port or detect_esp32_port()
        if not device_port:
            sys.exit(1)
        
        # 连接到设备, 处理串口占用问题
        interactive_mode = not args.no_interactive
        force_release = args.force_release or args.kill_blocking
        
        if not connect_to_device(device_port, force_release=force_release, 
                               interactive=interactive_mode, verbose=args.verbose):
            print_message("无法连接到设备, 操作中止", "ERROR")
            print_message("建议：", "INFO")
            print_message("1. 关闭Thonny或其他IDE", "INFO")
            print_message("2. 使用 --force-release 参数强制释放串口", "INFO")
            print_message("3. 手动重启ESP32设备", "INFO")
            sys.exit(1)
        
        if args.diagnose:
            diagnose_device(device_port, args.verbose)
            return
        
        if args.repl:
            start_repl(device_port, raw=False)
            return
            
        if args.raw_repl:
            start_repl(device_port, raw=True)
            return

        if args.monitor:
            monitor_device(device_port, args.verbose)
            return

        # --- 上传流程 ---
        if args.upload or args.clean:
            print_message("开始部署到设备...", "HEADER")
            if args.clean:
                if not clean_device(device_port, args.verbose):
                    print_message("设备清理失败, 部署中止", "ERROR")
                    sys.exit(1)
                # 清理后强制全量上传
                args.full_upload = True

            if not upload_directory(device_port, DIST_DIR, args.verbose, args.full_upload):
                print_message("文件上传失败, 部署中止", "ERROR")
                sys.exit(1)
            
            print_message("部署成功！", "SUCCESS")

            if not args.no_reset:
                reset_device(device_port, args.verbose)

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