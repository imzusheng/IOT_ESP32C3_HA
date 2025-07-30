# deploy.py (v4.2 - ESP32-C3交互式开发环境版)
import sys
import time
import serial
import serial.tools.list_ports
import os
import shutil
import subprocess
from base64 import b64encode

# --- 配置区 ---
SOURCE_DIR = "micropython_src"
BUILD_DIR = "dist"
MPY_CROSS_CMD = "mpy-cross"  # 如果mpy-cross不在系统PATH中，请提供其完整路径
DEBUG = True  # 默认启用调试模式

# --- 核心功能实现 ---

class PyboardError(Exception):
    """自定义异常，用于表示与开发板通信时发生的错误"""
    pass

class Pyboard:
    """一个健壮的类，用于处理与MicroPython开发板的底层通信。"""
    def __init__(self, port, baudrate=115200):
        try:
            self.serial = serial.Serial(port, baudrate=baudrate, timeout=1)
            # 连接后立即发送Ctrl+C中断任何正在运行的程序
            self._interrupt_running_program()
        except serial.SerialException as e:
            raise PyboardError(f"无法打开串口 {port}: {e}")

    def _interrupt_running_program(self):
        """发送Ctrl+C中断任何正在运行的程序"""
        try:
            if DEBUG:
                print("[设备] 正在发送中断信号...")
            # 发送Ctrl+C多次确保中断
            for i in range(3):
                self.serial.write(b'\x03')  # Ctrl+C
                time.sleep(0.1)
            # 清空缓冲区
            time.sleep(0.2)
            self.serial.read_all()
            if DEBUG:
                print("[设备] 中断信号发送完成")
        except Exception as e:
            if DEBUG:
                print(f"[设备] 发送中断信号时出错: {e}")
            # 不抛出异常，因为这只是初始化的一部分

    def test_connection(self):
        """测试串口连接并显示设备信息"""
        try:
            if DEBUG:
                print("[测试] 正在测试串口连接...")
            
            # 清空缓冲区
            self.serial.read_all()
            time.sleep(0.1)
            
            # 发送简单的测试命令
            self.serial.write(b'\x03\x03')  # Ctrl+C
            time.sleep(0.1)
            self.serial.write(b'print("ESP32-C3 Connection Test")\r\n')
            time.sleep(0.5)
            
            # 读取响应
            response = self.serial.read_all()
            if DEBUG:
                print(f"[测试] 设备响应: {response}")
            
            if b"ESP32-C3 Connection Test" in response:
                print("[测试] ✅ 设备连接正常，可以通信")
                return True
            else:
                print("[测试] ⚠️ 设备已连接但未收到预期响应")
                print(f"[测试] 收到: {response}")
                return False
                
        except Exception as e:
            print(f"[测试] ❌ 连接测试失败: {e}")
            return False

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()

    def listen_output(self, duration=None, filter_text=None):
        """
        监听串口输出
        
        Args:
            duration: 监听持续时间（秒），None表示持续监听
            filter_text: 过滤文本，只显示包含该文本的行
        """
        print(f"[监听] 开始监听串口输出...")
        if DEBUG:
            print(f"[调试] 串口状态: {self.serial.is_open}")
            print(f"[调试] 串口设置: {self.serial.baudrate} baud")
        
        if filter_text:
            print(f"[监听] 过滤条件: 包含 '{filter_text}'")
        if duration:
            print(f"[监听] 监听时长: {duration} 秒")
        print("[监听] 按 Ctrl+C 停止监听")
        print("-" * 50)
        
        # 先清空缓冲区
        if DEBUG:
            print("[调试] 清空串口缓冲区...")
        self.serial.read_all()
        time.sleep(0.1)
        
        # 发送复位信号激活设备
        if DEBUG:
            print("[调试] 发送复位信号激活设备...")
        self.serial.write(b'\x03\x03')  # Ctrl+C
        time.sleep(0.1)
        self.serial.write(b'\x04')  # Ctrl+D
        time.sleep(0.5)
        
        start_time = time.time()
        buffer = ""
        last_data_time = time.time()
        data_received = False
        
        try:
            while True:
                # 检查是否超时
                if duration and (time.time() - start_time) > duration:
                    print(f"[监听] 监听时间已到 ({duration} 秒)")
                    break
                
                # 读取数据
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)
                    if DEBUG:
                        print(f"[调试] 收到数据: {len(data)} bytes")
                    
                    # 尝试解码
                    try:
                        decoded_data = data.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    
                    buffer += decoded_data
                    data_received = True
                    last_data_time = time.time()
                    
                    # 按行处理
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        
                        if line:  # 非空行
                            # 过滤处理
                            if filter_text:
                                if filter_text.lower() in line.lower():
                                    print(f"[监听] {line}")
                            else:
                                print(f"[监听] {line}")
                
                # 如果长时间没有数据，显示状态
                if not data_received and (time.time() - start_time) > 5:
                    print(f"[监听] 等待设备输出中... ({int(time.time() - start_time)} 秒)")
                    data_received = True  # 避免重复显示
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            print("\n[监听] 用户中断，停止监听")
        except Exception as e:
            print(f"\n[监听] 监听出错: {e}")
        
        print("-" * 50)
        print("[监听] 监听结束")

    def listen_with_interaction(self):
        """
        交互式监听模式，支持实时过滤和控制
        """
        print("[监听] 交互式监听模式启动")
        if DEBUG:
            print(f"[调试] 串口状态: {self.serial.is_open}")
            print(f"[调试] 串口设置: {self.serial.baudrate} baud")
        
        print("[监听] 可用命令:")
        print("  help     - 显示帮助")
        print("  filter X - 设置过滤文本")
        print("  clear    - 清除过滤")
        print("  status   - 显示状态")
        print("  exit     - 退出监听")
        print("[监听] 注意：在Windows上可能需要在新开窗口中输入命令")
        print("-" * 50)
        
        # 先清空缓冲区并激活设备
        if DEBUG:
            print("[调试] 清空串口缓冲区...")
        self.serial.read_all()
        time.sleep(0.1)
        
        # 发送复位信号激活设备
        if DEBUG:
            print("[调试] 发送复位信号激活设备...")
        self.serial.write(b'\x03\x03')  # Ctrl+C
        time.sleep(0.1)
        self.serial.write(b'\x04')  # Ctrl+D
        time.sleep(0.5)
        
        filter_text = None
        line_count = 0
        start_time = time.time()
        last_command_check = 0
        data_received = False
        
        try:
            while True:
                current_time = time.time()
                
                # 检查串口数据
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)
                    if DEBUG:
                        print(f"[调试] 收到数据: {len(data)} bytes")
                    
                    # 尝试解码
                    try:
                        decoded_data = data.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    
                    data_received = True
                    
                    # 处理每一行
                    for line in decoded_data.split('\n'):
                        line = line.strip()
                        if line:
                            # 应用过滤
                            if filter_text:
                                if filter_text.lower() in line.lower():
                                    timestamp = time.strftime("%H:%M:%S")
                                    print(f"[{timestamp}] {line}")
                                    line_count += 1
                            else:
                                timestamp = time.strftime("%H:%M:%S")
                                print(f"[{timestamp}] {line}")
                                line_count += 1
                
                # 如果长时间没有数据，显示状态
                if not data_received and (current_time - start_time) > 5:
                    print(f"[监听] 等待设备输出中... ({int(current_time - start_time)} 秒)")
                    data_received = True  # 避免重复显示
                
                # 每5秒检查一次是否有预设命令（简化版本）
                if current_time - last_command_check > 5:
                    # 这里可以添加文件或信号检测来实现命令输入
                    # 为了简化，我们只显示状态
                    elapsed = int(current_time - start_time)
                    if line_count > 0 and elapsed % 10 == 0:  # 每10秒显示一次状态
                        print(f"[监听] 状态: 运行 {elapsed} 秒, 处理 {line_count} 行")
                        if filter_text:
                            print(f"[监听] 当前过滤: '{filter_text}'")
                        else:
                            print("[监听] 当前过滤: 无")
                    
                    last_command_check = current_time
                
                time.sleep(0.01)
                
        except KeyboardInterrupt:
            print("\n[监听] 用户中断，停止监听")
        except Exception as e:
            print(f"\n[监听] 监听出错: {e}")
        
        print("-" * 50)
        print(f"[监听] 监听结束，共处理 {line_count} 行输出")

    def interactive_shell(self):
        """
        Thonny-like交互式shell，支持RST、文件上传、持续监听
        """
        print("=" * 60)
        print("=      ESP32-C3 交互式开发环境 v4.2      =")
        print("=" * 60)
        if DEBUG:
            print(f"[调试] 串口状态: {self.serial.is_open}")
            print(f"[调试] 串口设置: {self.serial.baudrate} baud")
        
        print("\n可用命令:")
        print("  help, h     - 显示帮助信息")
        print("  rst, reset  - 复位开发板")
        print("  upload      - 上传文件到开发板")
        print("  monitor, m  - 开始持续监听")
        print("  listen X    - 监听X秒")
        print("  filter X    - 设置过滤文本")
        print("  clear       - 清除过滤")
        print("  status      - 显示设备状态")
        print("  exec <code> - 执行MicroPython代码")
        print("  reboot      - 重启开发板")
        print("  exit, quit  - 退出交互模式")
        print("-" * 50)
        
        # 先清空缓冲区并激活设备
        if DEBUG:
            print("[调试] 清空串口缓冲区...")
        self.serial.read_all()
        time.sleep(0.1)
        
        # 发送复位信号激活设备
        if DEBUG:
            print("[调试] 发送复位信号激活设备...")
        self.serial.write(b'\x03\x03')  # Ctrl+C
        time.sleep(0.1)
        self.serial.write(b'\x04')  # Ctrl+D
        time.sleep(0.5)
        
        filter_text = None
        monitoring = False
        line_count = 0
        start_time = time.time()
        data_received = False
        
        try:
            while True:
                current_time = time.time()
                
                # 检查串口数据
                if self.serial.in_waiting:
                    data = self.serial.read(self.serial.in_waiting)
                    if DEBUG:
                        print(f"[调试] 收到数据: {len(data)} bytes")
                    
                    # 尝试解码
                    try:
                        decoded_data = data.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded_data = data.decode('utf-8', errors='ignore')
                    
                    data_received = True
                    
                    # 处理每一行
                    for line in decoded_data.split('\n'):
                        line = line.strip()
                        if line:
                            # 应用过滤
                            if filter_text:
                                if filter_text.lower() in line.lower():
                                    timestamp = time.strftime("%H:%M:%S")
                                    print(f"[{timestamp}] {line}")
                                    line_count += 1
                            else:
                                timestamp = time.strftime("%H:%M:%S")
                                print(f"[{timestamp}] {line}")
                                line_count += 1
                
                # 显示状态信息
                if monitoring and current_time - start_time > 10:
                    elapsed = int(current_time - start_time)
                    print(f"[监控] 运行 {elapsed} 秒, 处理 {line_count} 行")
                    start_time = current_time
                
                # 如果长时间没有数据且在监控模式，显示等待状态
                if monitoring and not data_received and (current_time - start_time) > 5:
                    print(f"[监控] 等待设备输出中... ({int(current_time - start_time)} 秒)")
                    data_received = True  # 避免重复显示
                
                # 获取用户输入
                try:
                    cmd = input("\n>>> ").strip().lower()
                    if not cmd:
                        continue
                        
                    # 处理命令
                    if cmd in ['help', 'h']:
                        self._show_help()
                    elif cmd in ['rst', 'reset']:
                        self._reset_board()
                    elif cmd == 'upload':
                        self._upload_files()
                    elif cmd in ['monitor', 'm']:
                        monitoring = True
                        print("[监控] 开始持续监听模式...")
                    elif cmd.startswith('listen '):
                        try:
                            duration = int(cmd.split()[1])
                            print(f"[监听] 监听 {duration} 秒...")
                            self.listen_output(duration=duration, filter_text=filter_text)
                        except (IndexError, ValueError):
                            print("[错误] 请指定有效的监听时间（秒）")
                    elif cmd.startswith('filter '):
                        filter_text = cmd[7:].strip()
                        print(f"[过滤] 设置过滤文本: '{filter_text}'")
                    elif cmd == 'clear':
                        filter_text = None
                        print("[过滤] 清除过滤条件")
                    elif cmd == 'status':
                        self._show_status()
                    elif cmd.startswith('exec '):
                        code = cmd[5:].strip()
                        self._execute_code(code)
                    elif cmd == 'reboot':
                        self._reboot_board()
                    elif cmd in ['exit', 'quit']:
                        print("[退出] 退出交互模式")
                        break
                    else:
                        print(f"[错误] 未知命令: {cmd}")
                        print("输入 'help' 查看可用命令")
                        
                except KeyboardInterrupt:
                    print("\n[中断] 使用 'exit' 命令退出")
                except EOFError:
                    print("\n[退出] 退出交互模式")
                    break
                    
        except Exception as e:
            print(f"\n[错误] 交互模式出错: {e}")
        
        print("=" * 60)
        print("交互模式已结束")

    def _show_help(self):
        """显示帮助信息"""
        print("\n=== 命令帮助 ===")
        print("help, h     - 显示此帮助信息")
        print("rst, reset  - 发送Ctrl+D复位开发板")
        print("upload      - 编译并上传文件到开发板")
        print("monitor, m  - 开始持续监听模式")
        print("listen X    - 监听X秒后自动停止")
        print("filter X    - 设置输出过滤条件")
        print("clear       - 清除过滤条件")
        print("status      - 显示设备状态信息")
        print("exec <code> - 执行MicroPython代码")
        print("reboot      - 完全重启开发板")
        print("exit, quit  - 退出交互模式")

    def _reset_board(self):
        """复位开发板"""
        print("[复位] 正在复位开发板...")
        try:
            # 先发送Ctrl+C中断当前程序
            for i in range(3):
                self.serial.write(b'\x03')  # Ctrl+C
                time.sleep(0.1)
            
            # 发送Ctrl+D复位
            self.serial.write(b'\x04')  # Ctrl+D
            time.sleep(0.5)
            print("[复位] 复位完成")
        except Exception as e:
            print(f"[错误] 复位失败: {e}")

    def _upload_files(self):
        """上传文件到开发板"""
        print("[上传] 开始编译和上传文件...")
        try:
            # 重新构建项目
            build_project(compile_files=True)
            
            # 进入raw repl模式
            self.enter_raw_repl()
            
            # 清空设备
            self.wipe_device()
            
            # 上传文件
            file_count = 0
            for root, dirs, files in os.walk(BUILD_DIR):
                # 过滤掉 __pycache__ 目录
                if '__pycache__' in dirs:
                    dirs.remove('__pycache__')
                
                for file in files:
                    local_path = os.path.join(root, file)
                    remote_path = "/" + os.path.relpath(local_path, BUILD_DIR).replace("\\", "/")
                    self.put_file(local_path, remote_path)
                    file_count += 1
            
            print(f"[上传] 成功上传 {file_count} 个文件")
            
            # 退出raw repl并复位
            self.exit_raw_repl()
            self.soft_reset()
            
            print("[上传] 文件上传完成，开发板已复位")
            
        except Exception as e:
            print(f"[错误] 上传失败: {e}")

    def _show_status(self):
        """显示设备状态"""
        print("[状态] 正在获取设备信息...")
        try:
            response = self.exec_raw(
                "import machine\n"
                "import sys\n"
                "import uos\n"
                "import gc\n"
                "print('=== 设备状态 ===')\n"
                "print('频率:', machine.freq(), 'Hz')\n"
                "print('平台:', sys.platform)\n"
                "print('版本:', sys.version.split()[0])\n"
                "gc.collect()\n"
                "print('内存:', gc.mem_free(), 'bytes free')\n"
                "try:\n"
                "    print('MCU温度:', machine.ADC(4).read())\n"
                "except:\n"
                "    print('MCU温度: 不可用')\n"
                "print('文件数量:', len(list(uos.ilistdir('/'))))\n"
            )
            print(response.decode('utf-8', errors='ignore'))
        except Exception as e:
            print(f"[错误] 获取状态失败: {e}")

    def _execute_code(self, code):
        """执行MicroPython代码"""
        print(f"[执行] 执行代码: {code}")
        try:
            response = self.exec_raw(code)
            if response:
                print("[结果]", response.decode('utf-8', errors='ignore'))
        except Exception as e:
            print(f"[错误] 执行失败: {e}")

    def _reboot_board(self):
        """完全重启开发板"""
        print("[重启] 正在重启开发板...")
        try:
            self.exec_raw("import machine; machine.reset()")
            time.sleep(2)
            print("[重启] 重启命令已发送")
        except Exception as e:
            print(f"[错误] 重启失败: {e}")

    def read_until(self, min_len, ending, timeout=10):
        data = self.serial.read(min_len)
        start_time = time.time()
        while time.time() - start_time < timeout:
            if data.endswith(ending):
                break
            new_data = self.serial.read(1)
            if new_data:
                data += new_data
            else:
                time.sleep(0.01)
        return data

    def exec_raw(self, command, timeout=10, quiet=False):
        # 先发送Ctrl+C确保设备就绪
        if not quiet:
            if DEBUG:
                print("[调试] 发送Ctrl+C确保设备就绪...")
        self.serial.write(b'\x03\x03')  # 发送Ctrl+C两次
        time.sleep(0.1)
        
        # 清空缓冲区
        self.serial.read_all()
        time.sleep(0.05)
        
        # 发送命令
        command_bytes = command.encode('utf-8')
        self.serial.write(command_bytes)
        self.serial.write(b'\x04') # Ctrl+D to execute
        
        response = self.read_until(2, b'>', timeout)
        if not response.endswith(b'>'):
             raise PyboardError(f"执行命令失败，未收到 '>' 提示符。收到: {response}")
        
        if b'OK' not in response:
            return response

        output, error = response.split(b'OK', 1)
        if b"Traceback" in error:
             raise PyboardError(f"远程执行出错:\n{error.decode('utf-8', 'ignore')}")
        
        return output

    def enter_raw_repl(self):
        print("[设备] 正在中断程序并进入裸 REPL 模式...")
        # 发送Ctrl+C多次确保中断任何正在运行的程序
        for i in range(3):
            self.serial.write(b'\x03')  # Ctrl+C
            time.sleep(0.1)
        
        # 发送回车和Ctrl+A进入裸 REPL
        self.serial.write(b'\r\x01')  # 回车 + Ctrl+A: 进入裸 REPL
        time.sleep(0.3)
        
        # 读取响应
        response = self.serial.read_all()
        if DEBUG:
            print(f"[调试] 进入REPL响应: {response}")
        
        if b'raw REPL' not in response:
            print(f"[警告] 可能未能正确进入裸 REPL。响应: {response}")
            # 尝试再次发送Ctrl+A
            self.serial.write(b'\x01')
            time.sleep(0.2)
            response = self.serial.read_all()
            if DEBUG:
                print(f"[调试] 第二次尝试响应: {response}")
        
        print("[设备] 成功进入裸 REPL。")

    def exit_raw_repl(self):
        print("[设备] 正在退出裸 REPL 模式...")
        self.serial.write(b'\x02') # Ctrl+B 退出
        time.sleep(0.1)

    def soft_reset(self):
        print("[设备] 正在执行软复位...")
        self.serial.write(b'import machine; machine.reset()\x04')
        time.sleep(1.5) # 给设备重启留出时间
        print("[设备] 软复位完成。")

    def wipe_device(self):
        print("[设备] 正在清空设备文件系统 (这可能需要一些时间)...")
        self.exec_raw(
            "import uos\n"
            "def rm_all(path):\n"
            "  try:\n"
            "    for item in uos.ilistdir(path):\n"
            "      full_path = path + '/' + item[0]\n"
            "      if item[1] == 0x8000: uos.remove(full_path)\n" # 文件
            "      else: rm_all(full_path); uos.rmdir(full_path)\n" # 文件夹
            "  except OSError: pass\n"
            "rm_all('/')"
        , timeout=30)
        print("[设备] 文件系统已清空。")

    def put_file(self, local_path, remote_path):
        try:
            with open(local_path, 'rb') as f:
                content = f.read()
        except FileNotFoundError:
            raise PyboardError(f"本地文件未找到: {local_path}")
        
        print(f"  传输: {local_path} -> {remote_path} ({len(content)} bytes)")
        
        remote_dir = '/'.join(remote_path.split('/')[:-1])
        if remote_dir:
            self.exec_raw(f"try: uos.mkdir('{remote_dir}')\nexcept OSError: pass", quiet=True)

        encoded_content = b64encode(content)
        self.exec_raw(f"f = open('{remote_path}', 'wb'); import ubinascii", quiet=True)
        
        chunk_size = 256
        for i in range(0, len(encoded_content), chunk_size):
            chunk = encoded_content[i:i+chunk_size]
            self.exec_raw(f"f.write(ubinascii.a2b_base64(b'{chunk.decode('ascii')}'))", quiet=True)
        
        self.exec_raw("f.close()", quiet=True)


def build_project(compile_files=True):
    title = "步骤 1: 构建和编译项目" if compile_files else "步骤 1: 构建项目 (跳过编译)"
    print(f"--- {title} ---")

    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR)
    os.makedirs(BUILD_DIR)

    stats = []
    total_before, total_after = 0, 0

    for root, dirs, files in os.walk(SOURCE_DIR):
        # 过滤掉 __pycache__ 目录
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
        
        rel_path = os.path.relpath(root, SOURCE_DIR)
        dist_path = os.path.join(BUILD_DIR, rel_path) if rel_path != '.' else BUILD_DIR

        if not os.path.exists(dist_path):
            os.makedirs(dist_path)

        for file in files:
            local_file_path = os.path.join(root, file)
            
            if compile_files and file.endswith('.py'):
                mpy_file = file.replace('.py', '.mpy')
                dist_file_path = os.path.join(dist_path, mpy_file)
                try:
                    result = subprocess.run(
                        [MPY_CROSS_CMD, local_file_path, "-o", dist_file_path],
                        check=True, capture_output=True, text=True, encoding='utf-8'
                    )
                    
                    original_size = os.path.getsize(local_file_path)
                    compiled_size = os.path.getsize(dist_file_path)
                    reduction = (original_size - compiled_size) / original_size * 100 if original_size > 0 else 0
                    total_before += original_size
                    total_after += compiled_size
                    stats.append((file, original_size, compiled_size, reduction))

                except FileNotFoundError:
                    print(f"\n[致命错误] 找不到 mpy-cross 命令。请确保它已正确安装并位于系统 PATH 环境变量中。")
                    sys.exit(1)
                except subprocess.CalledProcessError as e:
                    print(f"\n[致命错误] 编译文件 '{local_file_path}' 失败。")
                    print("="*15 + " mpy-cross 编译器错误信息 " + "="*15)
                    print(e.stderr)
                    print("="*58)
                    print("错误原因可能是：\n  1. mpy-cross 版本与设备固件不兼容。\n  2. Python 代码中存在语法错误。")
                    print("\n[建议] 您可以尝试使用 '--no-compile' 选项跳过编译，直接部署 .py 源文件。")
                    sys.exit(1)
            else:
                shutil.copy(local_file_path, os.path.join(dist_path, file))

    if compile_files and stats:
        print("\n[编译报告]")
        print("-" * 60)
        print(f"{'文件名':<25} | {'原始大小':>10} | {'编译后大小':>12} | {'压缩率':>7}")
        print("-" * 60)
        for name, orig, comp, red in sorted(stats, key=lambda x: x[3], reverse=True):
            print(f"{name:<25} | {orig:>8} B | {comp:>10} B | {red:>6.1f}%")
        print("-" * 60)
        total_reduction = (total_before - total_after) / total_before * 100 if total_before > 0 else 0
        print(f"{'总计':<25} | {total_before:>8} B | {total_after:>10} B | {total_reduction:>6.1f}%")
        print("-" * 60)
    
    print(f"构建产物已输出到 '{BUILD_DIR}/' 目录。\n")


def find_serial_port():
    print("--- 步骤 2: 查找设备 ---")
    ports = serial.tools.list_ports.comports()
    
    # ESP32-C3 智能检测关键词（按优先级排序）
    esp32c3_keywords = [
        # 优先级1：ESP32-C3 特定标识
        'esp32-c3', 'esp32c3', 'esp32-c3s2', 'esp32s3',
        
        # 优先级2：ESP32 通用标识
        'esp32', 'espressif', 'usb jtag/serial', 'jtag/serial',
        
        # 优先级3：常用USB转串口芯片
        'ch340', 'ch341', 'cp210x', 'cp2102', 'cp2104', 'cp2105', 'cp2108', 'cp2109',
        'cp2110', 'cp2112', 'cp2114', 'cp2116', 'cp2118', 'cp2119',
        'ftdi', 'ft232', 'ft231', 'ft230', 'ft2232', 'ft4232',
        'pl2303', 'pl2303x', 'pl2303hx', 'pl2303ta', 'pl2303ea',
        'usb to serial', 'usb serial', 'uart bridge', 'serial port',
        'usb uart', 'uart controller', 'serial controller',
        
        # 优先级4：通用串口设备
        'uart', 'serial', 'com port', 'communication port',
        
        # 优先级5：可能的VID/PID匹配（ESP32-C3常见）
        '303a', '10c4', '1a86', '0403'  # Espressif, Silicon Labs, WCH, FTDI
    ]
    
    # 为每个端口计算匹配分数
    scored_ports = []
    for port in ports:
        score = 0
        matched_keywords = []
        
        # 检查设备描述
        desc = port.description.lower()
        hwid = port.hwid.lower()
        
        # 根据关键词优先级计算分数
        for i, keyword in enumerate(esp32c3_keywords):
            if keyword in desc or keyword in hwid:
                # 根据优先级给予不同分数
                if i < 4:  # ESP32-C3 特定标识
                    score += 100 - i * 10  # 100, 90, 80, 70
                elif i < 8:  # ESP32 通用标识
                    score += 60 - (i - 4) * 10  # 60, 50, 40, 30
                elif i < 20:  # USB转串口芯片
                    score += 25 - (i - 8) * 2  # 25, 23, 21, ...
                elif i < 25:  # 通用串口设备
                    score += 10 - (i - 20) * 2  # 10, 8, 6, 4, 2
                else:  # VID/PID匹配
                    score += 5
                
                matched_keywords.append(keyword)
        
        # 额外检查：ESP32-C3的典型VID/PID
        if '303a' in hwid:  # Espressif VID
            score += 50
        if '1001' in hwid:  # ESP32-C3常见PID
            score += 30
        
        # 如果找到任何匹配，添加到列表
        if score > 0:
            scored_ports.append({
                'port': port,
                'score': score,
                'keywords': matched_keywords
            })
    
    # 按分数排序
    scored_ports.sort(key=lambda x: x['score'], reverse=True)
    
    if not scored_ports:
        # 如果没有找到匹配的设备，显示所有可用串口
        print("[警告] 未找到可能的ESP32-C3设备。显示所有可用串口：")
        if not ports:
            raise PyboardError("未找到任何串口设备。请检查连接和驱动程序。")
        
        for i, p in enumerate(ports):
            print(f"  [{i+1}]: {p.device} - {p.description}")
            print(f"         HWID: {p.hwid}")
        
        try:
            choice = int(input("请选择串口 (输入编号，或按Enter跳过): ") or "0") - 1
            if not (0 <= choice < len(ports)):
                raise ValueError
            return ports[choice].device
        except (ValueError, IndexError, KeyboardInterrupt):
            print("\n选择无效或操作取消，脚本退出。")
            sys.exit(1)
    
    # 显示检测到的设备
    print(f"检测到 {len(scored_ports)} 个可能的ESP32-C3设备：")
    for i, item in enumerate(scored_ports):
        p = item['port']
        print(f"  [{i+1}]: {p.device} - {p.description}")
        print(f"         匹配分数: {item['score']}")
        print(f"         匹配关键词: {', '.join(item['keywords'])}")
        print(f"         HWID: {p.hwid}")
        print()
    
    # 如果只有一个设备，自动选择
    if len(scored_ports) == 1:
        selected = scored_ports[0]['port']
        print(f"自动选择唯一设备: {selected.device} - {selected.description}")
        return selected.device
    
    # 如果有多个设备，让用户选择
    print("检测到多个设备，请选择一个:")
    try:
        choice = int(input("请输入端口编号 (推荐选择分数最高的): ") or "1") - 1
        if not (0 <= choice < len(scored_ports)):
            raise ValueError
        selected = scored_ports[choice]['port']
        print(f"已选择: {selected.device} - {selected.description}")
        return selected.device
    except (ValueError, IndexError, KeyboardInterrupt):
        print("\n选择无效或操作取消，脚本退出。")
        sys.exit(1)

def verify_esp32c3_device(board):
    """
    验证设备是否为ESP32-C3
    """
    print("[验证] 正在验证设备类型...")
    try:
        # 尝试获取设备信息
        response = board.exec_raw(
            "import machine\n"
            "import sys\n"
            "print('Device Info:')\n"
            "print('Machine:', machine.freq())\n"
            "print('Platform:', sys.platform)\n"
            "print('Version:', sys.version)\n"
            "try:\n"
            "    print('MCU Temp:', machine.ADC(4).read())\n"
            "except:\n"
            "    print('MCU Temp: N/A')\n"
        )
        
        response_str = response.decode('utf-8', errors='ignore').lower()
        
        # 检查是否为ESP32设备
        esp32_indicators = ['esp32', 'espressif', 'esp32c3', 'esp32-c3']
        is_esp32 = any(indicator in response_str for indicator in esp32_indicators)
        
        if is_esp32:
            print("[验证] 确认为ESP32设备")
            return True
        else:
            print("[验证] 设备可能不是ESP32系列，但继续部署...")
            print(f"[验证] 设备响应: {response_str[:200]}...")
            return True
            
    except Exception as e:
        print(f"[验证] 验证失败，但继续部署: {e}")
        return True

def deploy(no_compile_flag, port=None, debug=True):
    global DEBUG
    DEBUG = debug
    
    if port:
        print(f"使用指定串口: {port}")
    else:
        port = find_serial_port()
    
    print("\n--- 步骤 3: 部署到设备 ---")
    board = None
    try:
        board = Pyboard(port)
        board.enter_raw_repl()
        
        # 验证设备类型
        if not verify_esp32c3_device(board):
            print("[警告] 设备验证失败，但继续部署...")
        
        board.wipe_device()

        print("[部署] 开始上传文件...")
        # 上传 `dist` 目录的所有内容
        file_count = 0
        for root, dirs, files in os.walk(BUILD_DIR):
            # 过滤掉 __pycache__ 目录
            if '__pycache__' in dirs:
                dirs.remove('__pycache__')
            
            for file in files:
                local_path = os.path.join(root, file)
                # 计算远程路径时，去掉 'dist/' 前缀
                remote_path = "/" + os.path.relpath(local_path, BUILD_DIR).replace("\\", "/")
                board.put_file(local_path, remote_path)
                file_count += 1
        
        print(f"[部署] 所有文件上传成功！共上传 {file_count} 个文件")
        
        board.exit_raw_repl()
        board.soft_reset()

    except PyboardError as e:
        print(f"\n[致命错误] 部署过程中发生错误: {e}")
        print("[建议] 请检查：")
        print("  1. 设备是否正确连接")
        print("  2. 串口驱动是否正常")
        print("  3. 设备是否处于可被访问的状态")
        print("  4. 尝试重新插拔设备")
        sys.exit(1)
    finally:
        if board:
            board.close()

def parse_arguments():
    """解析命令行参数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='ESP32/MicroPython 交互式开发环境 v4.2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python deploy.py                    # 默认部署模式
  python deploy.py --no-compile       # 跳过编译，直接部署源文件
  python deploy.py --listen          # 监听模式（默认30秒）
  python deploy.py --listen 60       # 监听60秒
  python deploy.py --listen-interactive  # 交互式监听模式
  python deploy.py --listen --filter "DEBUG"  # 监听并过滤包含DEBUG的行
  python deploy.py --port COM7        # 指定串口
  python deploy.py --debug            # 启用调试模式（默认启用）
  python deploy.py --interactive      # 启动Thonny-like交互式开发环境
  python deploy.py --auto-monitor     # 部署后自动进入监听模式
  python deploy.py --test             # 测试设备连接
        """
    )
    
    parser.add_argument(
        '--no-compile', 
        action='store_true',
        help='跳过编译步骤，直接部署源文件'
    )
    
    parser.add_argument(
        '--listen', 
        nargs='?', 
        const=30, 
        type=int, 
        metavar='秒数',
        help='监听串口输出（默认30秒）'
    )
    
    parser.add_argument(
        '--listen-interactive', 
        action='store_true',
        help='交互式监听模式，支持实时过滤和控制'
    )
    
    parser.add_argument(
        '--filter', 
        type=str, 
        metavar='文本',
        help='过滤监听输出，只显示包含指定文本的行'
    )
    
    parser.add_argument(
        '--port', 
        type=str, 
        metavar='串口',
        help='指定串口（如 COM7，/dev/ttyUSB0）'
    )
    
    parser.add_argument(
        '--debug', 
        action='store_true', 
        default=True,
        help='启用调试模式（默认启用）'
    )
    
    parser.add_argument(
        '--no-debug', 
        action='store_true',
        help='禁用调试模式'
    )
    
    parser.add_argument(
        '--interactive', 
        '--shell', 
        action='store_true',
        help='启动Thonny-like交互式开发环境'
    )
    
    parser.add_argument(
        '--auto-monitor', 
        action='store_true',
        help='部署后自动进入监听模式'
    )
    
    parser.add_argument(
        '--test', 
        action='store_true',
        help='测试设备连接并显示基本信息'
    )
    
    return parser.parse_args()

def listen_mode(args):
    """监听模式"""
    print("=================================================")
    print("=      ESP32/MicroPython 串口监听工具 v4.2      =")
    print("=================================================\n")
    
    try:
        # 获取串口
        if args.port:
            port = args.port
            print(f"使用指定串口: {port}")
        else:
            port = find_serial_port()
        
        # 连接设备
        board = Pyboard(port)
        
        try:
            # 测试连接
            if DEBUG:
                print("[调试] 测试设备连接...")
            board.test_connection()
            
            if args.listen_interactive:
                # 交互式监听模式
                board.listen_with_interaction()
            else:
                # 简单监听模式
                duration = args.listen if args.listen else None
                filter_text = args.filter
                board.listen_output(duration=duration, filter_text=filter_text)
        
        finally:
            board.close()
            
    except PyboardError as e:
        print(f"\n[致命错误] 监听过程中发生错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n用户中断操作")
    except Exception as e:
        print(f"\n发生未知错误: {e}")

def deploy_mode(args):
    """部署模式"""
    print("=================================================")
    print("=      ESP32/MicroPython 交互式开发环境 v4.2    =")
    print("=              (Thonny-like模式)               =")
    print("=================================================\n")
    
    # 设置调试模式
    global DEBUG
    DEBUG = args.debug and not args.no_debug
    
    if DEBUG:
        print("[调试] 调试模式已启用")
    
    should_compile = not args.no_compile
    
    build_project(compile_files=should_compile)
    deploy(no_compile_flag=(not should_compile), port=args.port, debug=DEBUG)
    
    print("\n🎉 部署成功完成！")
    
    # 如果启用自动监听，进入监听模式
    if args.auto_monitor:
        print("\n[自动监听] 部署完成，自动进入监听模式...")
        try:
            # 重新连接设备
            board = Pyboard(args.port if args.port else find_serial_port())
            try:
                print("[监听] 监听设备输出（按Ctrl+C停止）...")
                board.listen_output(duration=None, filter_text=None)
            finally:
                board.close()
        except Exception as e:
            print(f"[错误] 自动监听启动失败: {e}")

def interactive_mode(args):
    """交互式开发环境模式"""
    print("=================================================")
    print("=      ESP32/MicroPython 交互式开发环境 v4.2    =")
    print("=              (Thonny-like模式)               =")
    print("=================================================\n")
    
    try:
        # 获取串口
        if args.port:
            port = args.port
            print(f"使用指定串口: {port}")
        else:
            port = find_serial_port()
        
        # 连接设备
        board = Pyboard(port)
        
        try:
            # 测试连接
            if DEBUG:
                print("[调试] 测试设备连接...")
            board.test_connection()
            
            # 启动交互式shell
            board.interactive_shell()
        
        finally:
            board.close()
            
    except PyboardError as e:
        print(f"\n[致命错误] 交互模式启动失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n用户中断操作")
    except Exception as e:
        print(f"\n发生未知错误: {e}")

def test_mode(args):
    """测试设备连接模式"""
    print("=================================================")
    print("=      ESP32/MicroPython 设备连接测试 v4.2      =")
    print("=================================================\n")
    
    try:
        # 获取串口
        if args.port:
            port = args.port
            print(f"使用指定串口: {port}")
        else:
            port = find_serial_port()
        
        # 连接设备
        board = Pyboard(port)
        
        try:
            # 测试连接
            print("[测试] 开始设备连接测试...")
            success = board.test_connection()
            
            if success:
                print("\n[测试] ✅ 设备连接正常，可以正常通信")
                print("[测试] 可以使用监听模式或交互式模式")
            else:
                print("\n[测试] ⚠️ 设备连接可能有问题")
                print("[测试] 请检查：")
                print("  1. 设备是否正确连接")
                print("  2. 串口驱动是否正常")
                print("  3. 设备是否正在运行MicroPython固件")
                print("  4. 尝试重新插拔设备")
        
        finally:
            board.close()
            
    except PyboardError as e:
        print(f"\n[致命错误] 连接测试失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n用户中断操作")
    except Exception as e:
        print(f"\n发生未知错误: {e}")

def main():
    args = parse_arguments()
    
    # 检查是否为测试模式
    if args.test:
        test_mode(args)
    # 检查是否为交互式模式
    elif args.interactive:
        interactive_mode(args)
    # 检查是否为监听模式
    elif args.listen is not None or args.listen_interactive:
        listen_mode(args)
    else:
        deploy_mode(args)

if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code != 0:
             print(f"\n脚本因错误退出 (代码: {e.code})")
        else:
             print("\n\n用户中断了操作。")
    except Exception as e:
        print(f"\n发生未知错误: {e}")