import os
import subprocess
import time
import serial
import glob

# --- 配置区 ---

# 源文件目录 (存放 .py 文件的位置)
SRC_DIR = 'micropython_src'

# 编译后文件存放目录
DIST_DIR = 'dist'

# 设备的串口号 (请根据您的系统修改)
# Windows: 'COM3', 'COM4' 等
# Linux: '/dev/ttyUSB0', '/dev/ttyACM0' 等
# macOS: '/dev/cu.usbserial-xxxx' 等
SERIAL_PORT = 'COM6' # <--- 修改这里

# 串口波特率
BAUD_RATE = 115200

# mpy-cross 的路径 (如果已经添加到系统环境变量，可以保持 'mpy-cross')
MPY_CROSS_EXECUTABLE = 'mpy-cross'

# --- 脚本核心逻辑 ---

def compile_files():
    """
    使用 mpy-cross 编译源文件到 dist 目录。
    """
    print("="*50)
    print("🚀 步骤 1: 开始交叉编译源文件...")
    print("="*50)

    if not os.path.exists(SRC_DIR):
        print(f"❌ 错误: 源文件目录 '{SRC_DIR}' 不存在！")
        return False

    if not os.path.exists(DIST_DIR):
        print(f"✨ 信息: 创建输出目录 '{DIST_DIR}'")
        os.makedirs(DIST_DIR)

    source_files = glob.glob(os.path.join(SRC_DIR, '*.py'))
    if not source_files:
        print("🟡 警告: 没有在源目录中找到任何 .py 文件。")
        return True

    for py_file in source_files:
        file_name = os.path.basename(py_file)
        mpy_file = os.path.join(DIST_DIR, file_name.replace('.py', '.mpy'))
        
        command = [MPY_CROSS_EXECUTABLE, py_file, '-o', mpy_file]
        
        try:
            print(f"  - 编译中: {file_name} -> {os.path.basename(mpy_file)}")
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            print(f"❌ 错误: '{MPY_CROSS_EXECUTABLE}' 未找到。")
            print("  请确保 mpy-cross 已经安装并配置在系统 PATH 中。")
            return False
        except subprocess.CalledProcessError as e:
            print(f"❌ 错误: 编译 {file_name} 失败。")
            print(f"  错误信息: {e.stderr}")
            return False
            
    print("\n✅ 编译成功完成！\n")
    return True


def send_command(ser, command, delay=0.1, show_output=True):
    """
    向设备发送一个命令并等待响应。
    """
    ser.write(command.encode('utf-8'))
    time.sleep(delay)
    response = ser.read_all().decode('utf-8', errors='ignore')
    if show_output and response:
        print(response, end="")
    return response


def upload_files():
    """
    上传 dist 目录中的文件到设备。
    """
    print("="*50)
    print("🚀 步骤 2: 开始上传文件到设备...")
    print("="*50)
    
    files_to_upload = glob.glob(os.path.join(DIST_DIR, '*'))
    if not files_to_upload:
        print("🟡 警告: dist 目录为空，没有文件需要上传。")
        return True

    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
            print(f"✅ 成功连接到设备: {SERIAL_PORT}")
            
            # --- 核心：发送停止命令，类似 Thonny ---
            print("\n interrupting device (Ctrl+C)...")
            ser.write(b'\x03') # 发送 Ctrl+C
            time.sleep(0.5)
            ser.write(b'\x03') # 再次发送以确保停止
            response = ser.read_until(b'>').decode('utf-8', errors='ignore')
            print("✅ 设备已准备好接收文件。\n")

            # 进入 Raw REPL 模式，用于文件传输
            send_command(ser, '\r\x01', show_output=False) # Ctrl+A

            for file_path in files_to_upload:
                file_name = os.path.basename(file_path)
                print(f"  - 上传中: {file_name}")
                
                with open(file_path, 'rb') as f:
                    content = f.read()

                # 发送 'put' 命令
                put_command = f"f = open('{file_name}', 'wb'); w = f.write\r\n"
                send_command(ser, put_command, show_output=False)
                
                # 分块写入文件内容
                chunk_size = 256
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i+chunk_size]
                    ser.write(f"w({repr(chunk)})\r\n".encode('utf-8'))
                    time.sleep(0.05) # 短暂延时，防止串口缓冲区溢出
                
                # 关闭文件并确认
                send_command(ser, "f.close()\r\n", show_output=False)

            # 退出 Raw REPL 模式
            send_command(ser, '\x04', show_output=False) # Ctrl+D

            # 软重启设备以加载新代码
            print("\n🔄 正在软重启设备...")
            send_command(ser, '\x04', show_output=False) # Ctrl+D
            time.sleep(1)
            print("✨ 设备已重启。")

            print("\n✅ 所有文件上传成功！")
            return True

    except serial.SerialException as e:
        print(f"❌ 错误: 无法打开或读写串口 {SERIAL_PORT}。")
        print(f"  请检查设备是否连接，或串口号是否正确。错误详情: {e}")
        return False
    except Exception as e:
        print(f"❌ 上传过程中发生未知错误: {e}")
        return False


if __name__ == "__main__":
    if compile_files():
        upload_files()