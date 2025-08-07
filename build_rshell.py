#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MicroPython 项目构建和部署脚本 (v2.1 - 终极版)

主要功能:
1.  [优化] 更直观的命令行参数逻辑。
2.  [修复] 自动设置Windows控制台为UTF-8模式，彻底解决乱码问题。
3.  编译 .py 文件为 .mpy 字节码
4.  使用持久化 rshell 会话高速上传文件
5.  智能同步：仅上传变更过的文件
6.  上传进度条
7.  端口缓存
8.  设备监控和 REPL 交互

作者: 重构自原 build.py
日期: 2024
"""

import os
import shutil
import subprocess
import sys
import argparse
import time
import serial
import serial.tools.list_ports
import tempfile
import threading
import queue
import json
import hashlib
from pathlib import Path

# 尝试导入可选的依赖
try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# --- 配置常量 ---
SRC_DIR = "src"
DIST_DIR = "dist"
MPY_CROSS_EXECUTABLE = "mpy-cross"
RSHELL_EXECUTABLE = "rshell"
NO_COMPILE_FILES = ['boot.py', 'main.py']
DEFAULT_EXCLUDE_DIRS = ['tests']

# 缓存文件
PORT_CACHE_FILE = ".port_cache"
UPLOAD_CACHE_FILE = ".upload_cache.json"

# 排除的文件和目录
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "Thumbs.db",
    PORT_CACHE_FILE,
    UPLOAD_CACHE_FILE
]

# ESP32 设备识别模式
ESP32_VID_PID_PATTERNS = [
    (0x303A, 0x1001),  # Espressif
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # QinHeng CH340
    (0x1A86, 0x55D4),  # QinHeng CH343
    (0x0403, 0x6001),  # FTDI
]
ESP32_KEYWORDS = ['esp32', 'cp210', 'ch340', 'ch343', 'usb to uart', 'serial']

# --- 辅助函数 ---

def print_message(message, msg_type="INFO"):
    """格式化打印消息"""
    colors = {
        "INFO": "\033[94m", "SUCCESS": "\032[92m",
        "WARNING": "\033[93m", "ERROR": "\033[91m",
        "HEADER": "\033[95m", "RESET": "\033[0m"
    }
    color = colors.get(msg_type.upper(), colors["INFO"])
    reset = colors["RESET"]
    timestamp = time.strftime("%H:%M:%S")
    print(f"{color}[{timestamp}] [{msg_type.upper()}] {message}{reset}")

def safe_decode(data):
    """安全地将字节解码为字符串"""
    if not data:
        return "", b""
    try:
        return data.decode('utf-8'), b""
    except UnicodeDecodeError as e:
        valid_part = data[:e.start].decode('utf-8', 'ignore')
        remaining_part = data[e.start:]
        return valid_part, remaining_part
    except Exception:
        if CHARDET_AVAILABLE:
            try:
                detected = chardet.detect(data)
                if detected['encoding']:
                    return data.decode(detected['encoding'], 'ignore'), b""
            except Exception:
                pass
        return data.decode('latin-1', 'ignore'), b""

def get_file_md5(file_path):
    """计算文件的MD5哈希值"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def load_cache(cache_file):
    """加载JSON缓存文件"""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print_message(f"缓存文件 {cache_file} 已损坏，将重新创建。", "WARNING")
    return {}

def save_cache(cache_data, cache_file):
    """保存数据到JSON缓存文件"""
    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)
    except IOError as e:
        print_message(f"无法写入缓存文件 {cache_file}: {e}", "ERROR")

# --- 核心功能 ---

def detect_esp32_port():
    """自动检测ESP32设备端口 (带缓存功能)"""
    cached_port = load_cache(PORT_CACHE_FILE).get('port')
    if cached_port:
        print_message(f"从缓存中找到端口: {cached_port}", "INFO")
        try:
            with serial.Serial(cached_port) as ser:
                print_message(f"端口 {cached_port} 验证成功。", "SUCCESS")
                return cached_port
        except serial.SerialException:
            print_message(f"缓存的端口 {cached_port} 无效或无法访问。", "WARNING")

    print_message("正在扫描可用串口...", "INFO")
    ports = list(serial.tools.list_ports.comports())
    esp32_ports = []
    for port in ports:
        is_esp_port = False
        if port.vid and port.pid and (port.vid, port.pid) in ESP32_VID_PID_PATTERNS:
            is_esp_port = True
        if not is_esp_port and port.description and any(keyword in port.description.lower() for keyword in ESP32_KEYWORDS):
            is_esp_port = True
        if is_esp_port:
            esp32_ports.append(port)

    if not esp32_ports:
        print_message("未能自动识别出ESP32设备。", "ERROR")
        return None

    if len(esp32_ports) == 1:
        selected_port_dev = esp32_ports[0].device
        print_message(f"自动选择ESP32设备: {selected_port_dev} ({esp32_ports[0].description})", "SUCCESS")
    else:
        print_message(f"找到 {len(esp32_ports)} 个可能的ESP32设备:", "INFO")
        for i, port in enumerate(esp32_ports):
            print(f"  {i+1}. {port.device} - {port.description}")
        try:
            choice = input(f"请选择设备序号 (1-{len(esp32_ports)}): ").strip()
            index = int(choice) - 1
            selected_port_dev = esp32_ports[index].device
        except (ValueError, IndexError, KeyboardInterrupt):
            print_message("无效选择或已取消，将使用第一个设备。", "WARNING")
            selected_port_dev = esp32_ports[0].device
    
    save_cache({'port': selected_port_dev}, PORT_CACHE_FILE)
    print_message(f"已选择端口 {selected_port_dev} 并更新缓存。", "SUCCESS")
    return selected_port_dev

def check_tool(executable):
    """检查工具是否可用"""
    try:
        subprocess.run([executable, "--version"], capture_output=True, check=True, text=True, timeout=5)
        print_message(f"{executable} 可用", "SUCCESS")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print_message(f"检查 {executable} 时出错: {e}", "ERROR")
        if executable == MPY_CROSS_EXECUTABLE:
            print_message("请从 https://micropython.org/download/ 下载 mpy-cross", "ERROR")
        elif executable == RSHELL_EXECUTABLE:
            print_message("请使用 'pip install rshell' 命令进行安装。", "ERROR")
        return False

class RShellConnection:
    """RShell 持久化连接管理器"""
    def __init__(self, port, timeout=10):
        self.port = port
        self.timeout = timeout
        self.process = None
        self.output_queue = queue.Queue()
        self.reader_thread = None
        self.prompt = b'>'
        self.is_connected = False

    def __enter__(self):
        if self.connect():
            return self
        raise ConnectionError(f"无法连接到 {self.port}")

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _reader(self):
        """后台读取线程"""
        for line in iter(self.process.stdout.readline, b''):
            self.output_queue.put(line)

    def connect(self):
        """启动持久化rshell进程"""
        print_message(f"正在启动持久 rshell 会话到 {self.port}...")
        try:
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            self.process = subprocess.Popen(
                [RSHELL_EXECUTABLE, "-p", self.port, "--quiet", "--buffer-size=256"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                env=env
            )
            self.reader_thread = threading.Thread(target=self._reader, daemon=True)
            self.reader_thread.start()
            
            initial_output_bytes = b""
            start_time = time.time()
            connection_timeout = 15

            while time.time() - start_time < connection_timeout:
                try:
                    line = self.output_queue.get(timeout=0.2)
                    initial_output_bytes += line
                    if b"Welcome to rshell" in initial_output_bytes or self.prompt in initial_output_bytes:
                        self.is_connected = True
                        print_message("Rshell 持久化会话已建立。", "SUCCESS")
                        return True
                    if b"Could not enter raw repl" in initial_output_bytes or b"failed to connect" in initial_output_bytes:
                        decoded_error, _ = safe_decode(initial_output_bytes)
                        raise ConnectionError(f"Rshell连接失败: {decoded_error.strip()}")
                except queue.Empty:
                    if self.process.poll() is not None:
                        raise ConnectionError("Rshell 进程意外退出。")
                    continue
            
            decoded_output, _ = safe_decode(initial_output_bytes)
            raise ConnectionError(f"连接 rshell 超时 ({connection_timeout}s). 收到的初始输出: {decoded_output.strip()}")

        except (FileNotFoundError, ConnectionError, Exception) as e:
            print_message(f"启动 rshell 进程失败: {e}", "ERROR")
            self.is_connected = False
            return False

    def execute_command(self, command, timeout=10):
        """执行命令并获取结果"""
        if not self.process or self.process.poll() is not None:
            return 1, "", "Rshell 进程未运行"

        while not self.output_queue.empty():
            self.output_queue.get_nowait()

        self.process.stdin.write(command.encode('utf-8') + b'\n')
        self.process.stdin.flush()

        full_output_bytes = b""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                line = self.output_queue.get(timeout=0.1)
                full_output_bytes += line
                if self.prompt in line:
                    break
            except queue.Empty:
                continue
        else:
            decoded_output, _ = safe_decode(full_output_bytes)
            return 1, decoded_output, f"命令 '{command}' 执行超时"

        stdout, _ = safe_decode(full_output_bytes)
        if "Traceback" in stdout or "Error:" in stdout or "failed" in stdout:
            return 1, "", stdout
        return 0, stdout, ""

    def upload_file(self, local_path, remote_path):
        """上传单个文件"""
        local_path_norm = Path(local_path).as_posix()
        remote_path_norm = Path(remote_path).as_posix()
        remote_dir = Path(remote_path_norm).parent
        if str(remote_dir) not in ['.', '/']:
            self.execute_command(f"mkdir {remote_dir}", timeout=5)
        return self.execute_command(f'cp "{local_path_norm}" "{remote_path_norm}"', timeout=30)
    
    def reset_device(self):
        """重置设备"""
        print_message("正在重置设备...", "INFO")
        self.execute_command("repl ~ import machine; machine.reset() ~", timeout=5)
        time.sleep(3)
        print_message("设备已重置。", "SUCCESS")

    def monitor_output(self):
        """持续打印设备输出"""
        print_message("开始监控设备输出 (按 Ctrl+C 停止)...", "INFO")
        try:
            while self.process.poll() is None:
                try:
                    line_bytes = self.output_queue.get(timeout=1)
                    line_str, _ = safe_decode(line_bytes)
                    # 过滤掉rshell自身的提示符
                    if not line_str.strip().endswith(('>', '...')):
                        print(line_str, end='')
                except queue.Empty:
                    continue
        except KeyboardInterrupt:
            print_message("\n用户中断监控。", "INFO")
        except Exception as e:
            print_message(f"\n监控期间发生错误: {e}", "ERROR")

    def close(self):
        """关闭进程"""
        if self.process and self.process.poll() is None:
            print_message("正在关闭 rshell 会话...", "INFO")
            try:
                self.process.stdin.write(b'exit\n')
                self.process.stdin.flush()
                self.process.terminate()
                self.process.wait(timeout=5)
            except (IOError, subprocess.TimeoutExpired):
                self.process.kill()
            print_message("Rshell 会话已关闭。", "SUCCESS")
        self.process = None
        self.is_connected = False

def compile_project(verbose=False, exclude_dirs=None):
    """编译项目文件"""
    if not os.path.exists(SRC_DIR):
        print_message(f"源码目录 {SRC_DIR} 不存在", "ERROR")
        return False
    if exclude_dirs is None: exclude_dirs = []
    if os.path.exists(DIST_DIR): shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR, exist_ok=True)

    compiled_files, copied_files = 0, 0
    for root, dirs, files in os.walk(SRC_DIR, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and d != '__pycache__']
        rel_dir = os.path.relpath(root, SRC_DIR)
        target_dir = os.path.join(DIST_DIR, rel_dir) if rel_dir != '.' else DIST_DIR
        os.makedirs(target_dir, exist_ok=True)

        for file in files:
            if any(file.endswith(p.strip('*')) for p in EXCLUDE_PATTERNS if p.startswith('*.')) or file in EXCLUDE_PATTERNS:
                continue
            src_file = os.path.join(root, file)
            if file.endswith('.py') and file not in NO_COMPILE_FILES:
                mpy_file = file.replace('.py', '.mpy')
                target_file = os.path.join(target_dir, mpy_file)
                try:
                    subprocess.run([MPY_CROSS_EXECUTABLE, "-o", target_file, src_file], check=True, capture_output=True, text=True, timeout=30)
                    if verbose: print_message(f"编译: {src_file} -> {target_file}", "SUCCESS")
                    compiled_files += 1
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                    print_message(f"编译失败 {file}: {e.stderr if hasattr(e, 'stderr') else e}", "ERROR")
                    return False
            else:
                target_file = os.path.join(target_dir, file)
                shutil.copy2(src_file, target_file)
                if verbose: print_message(f"复制: {src_file} -> {target_file}", "SUCCESS")
                copied_files += 1
    
    print_message(f"构建完成 - 编译: {compiled_files}, 复制: {copied_files}", "SUCCESS")
    return True

def upload_directory(conn, dist_dir, verbose=False):
    """上传目录，支持智能同步和进度条"""
    print_message("正在分析文件变更...", "INFO")
    upload_cache = load_cache(UPLOAD_CACHE_FILE)
    new_cache = {}
    files_to_upload = []

    for root, _, files in os.walk(dist_dir):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, dist_dir)
            current_md5 = get_file_md5(local_path)
            if current_md5 != upload_cache.get(rel_path):
                files_to_upload.append((local_path, rel_path))
            new_cache[rel_path] = current_md5

    if not files_to_upload:
        print_message("所有文件均为最新，无需上传。", "SUCCESS")
        return True

    print_message(f"发现 {len(files_to_upload)} 个文件需要上传。", "INFO")
    failed_uploads = []
    
    iterator = files_to_upload
    if TQDM_AVAILABLE:
        iterator = tqdm(files_to_upload, desc="Uploading", unit="file", ncols=100, bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
    else:
        print_message("tqdm 未安装，将不显示进度条。建议: pip install tqdm", "WARNING")

    for local_path, rel_path in iterator:
        remote_path = Path("/") / Path(rel_path).as_posix()
        if not TQDM_AVAILABLE: print_message(f"正在上传: {rel_path}", "INFO")
        returncode, _, stderr = conn.upload_file(local_path, str(remote_path))
        if returncode != 0:
            failed_uploads.append((rel_path, stderr))
            if TQDM_AVAILABLE: tqdm.write(f"\033[91m上传失败 {rel_path}: {stderr}\033[0m")
            else: print_message(f"上传失败 {rel_path}: {stderr}", "ERROR")

    if failed_uploads:
        print_message(f"上传完成，但有 {len(failed_uploads)} 个文件失败。", "ERROR")
        for file, err in failed_uploads: print(f"  - {file}: {err}")
        return False
    else:
        print_message(f"成功上传 {len(files_to_upload)} 个文件。", "SUCCESS")
        save_cache(new_cache, UPLOAD_CACHE_FILE)
        print_message("上传缓存已更新。", "INFO")
        return True

def start_interactive_repl(port):
    """启动独立的交互式REPL会话"""
    print_message("启动交互式 REPL (输入 Ctrl+] 退出)...", "INFO")
    try:
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        subprocess.run([RSHELL_EXECUTABLE, "-p", port, "repl"], env=env)
    except KeyboardInterrupt:
        print_message("REPL 会话结束。", "INFO")
    except Exception as e:
        print_message(f"启动 REPL 失败: {e}", "ERROR")

# --- 主函数 ---

def main():
    parser = argparse.ArgumentParser(
        description="MicroPython 高性能构建和部署脚本 (v2.1)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
使用示例:
  python %(prog)s                # 默认: 编译, 上传, 然后监控设备
  python %(prog)s -c             # 仅编译
  python %(prog)s -u             # 仅上传 (智能同步)
  python %(prog)s -r             # 仅连接并进入交互式REPL
  python %(prog)s -m             # 仅连接并监控设备输出
  python %(prog)s -u --full-upload # 强制全量上传，忽略缓存
  python %(prog)s -p COM3        # 指定端口
"""
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--compile", action="store_true", help="仅编译 src 目录到 dist")
    group.add_argument("-u", "--upload", action="store_true", help="仅上传 dist 目录到设备 (智能同步)")
    group.add_argument("-r", "--repl", action="store_true", help="仅连接并进入交互式REPL")
    group.add_argument("-m", "--monitor", action="store_true", help="仅连接并监控设备输出")
    
    parser.add_argument("-p", "--port", type=str, help="指定设备端口 (不指定则自动检测)")
    parser.add_argument("-v", "--verbose", action="store_true", help="显示详细的调试输出")
    parser.add_argument("--no-reset", action="store_true", help="上传后不重置设备")
    parser.add_argument("--full-upload", action="store_true", help="强制全量上传，忽略缓存 (需与-u或默认模式一同使用)")
    
    args = parser.parse_args()

    # --- 编译操作 ---
    if args.compile:
        print_message("--- 开始编译 ---", "HEADER")
        if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
        if not compile_project(args.verbose): sys.exit(1)
        print_message("编译完成。", "SUCCESS")
        return

    # --- 设备相关操作 ---
    is_device_action = args.upload or args.repl or args.monitor or (not args.compile and not args.upload and not args.repl and not args.monitor)
    if not is_device_action:
        return

    print_message("--- 连接设备 ---", "HEADER")
    if not check_tool(RSHELL_EXECUTABLE): sys.exit(1)
    device_port = args.port or detect_esp32_port()
    if not device_port: sys.exit(1)

    # 仅进入REPL
    if args.repl:
        start_interactive_repl(device_port)
        return

    # 仅监控
    if args.monitor:
        try:
            with RShellConnection(device_port) as conn:
                conn.monitor_output()
        except (ConnectionError, Exception) as e:
            print_message(f"监控过程中发生错误: {e}", "ERROR")
            sys.exit(1)
        return

    # 上传或默认流程
    if args.upload or (not args.compile and not args.upload and not args.repl and not args.monitor):
        # 默认流程需要先编译
        if not args.upload:
             print_message("--- 开始编译 ---", "HEADER")
             if not check_tool(MPY_CROSS_EXECUTABLE): sys.exit(1)
             if not compile_project(args.verbose): sys.exit(1)

        print_message("--- 开始上传 ---", "HEADER")
        if not os.path.isdir(DIST_DIR) or not os.listdir(DIST_DIR):
            print_message(f"'{DIST_DIR}' 目录不存在或为空。请先运行编译。", "ERROR")
            sys.exit(1)
        if args.full_upload:
            print_message("强制全量上传模式已启用，将忽略并覆盖现有缓存。", "WARNING")
            if os.path.exists(UPLOAD_CACHE_FILE): os.remove(UPLOAD_CACHE_FILE)
        
        try:
            with RShellConnection(device_port) as conn:
                if not upload_directory(conn, DIST_DIR, args.verbose):
                    print_message("部署因文件上传失败而中止。", "ERROR")
                    sys.exit(1)
                if not args.no_reset:
                    conn.reset_device()
                
                # 默认流程上传后进入监控模式
                if not args.upload:
                    conn.monitor_output()

        except (ConnectionError, Exception) as e:
            print_message(f"部署过程中发生严重错误: {e}", "ERROR")
            sys.exit(1)

    print_message("所有任务已成功完成！", "SUCCESS")

if __name__ == "__main__":
    # [FIX] 强制Windows控制台使用UTF-8代码页
    if sys.platform == "win32":
        try:
            # 使用 'nul' 来抑制 "Active code page: 65001" 的输出
            os.system("chcp 65001 > nul")
        except Exception as e:
            print_message(f"尝试设置Windows代码页失败: {e}", "WARNING")

    if not TQDM_AVAILABLE:
        print("[提示] tqdm 库未安装，将无法显示进度条。建议运行: pip install tqdm")
    if not CHARDET_AVAILABLE:
        print("[提示] chardet 库未安装，编码自动检测功能受限。建议运行: pip install chardet")
    
    try:
        main()
    except KeyboardInterrupt:
        print_message("\n用户中断操作。", "WARNING")
        sys.exit(1)
    except Exception as e:
        import traceback
        print_message(f"脚本执行时发生未捕获的异常: {e}", "ERROR")
        traceback.print_exc()
        sys.exit(1)
