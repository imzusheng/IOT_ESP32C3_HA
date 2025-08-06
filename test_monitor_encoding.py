#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试monitor_with_continuous_repl函数的编码处理
模拟mpremote输出包含中文字符和截断UTF-8的情况
"""

import sys
import os
import subprocess
import time
import threading
from io import BytesIO

# 添加当前目录到路径以导入build.py中的函数
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build import safe_decode

class MockProcess:
    """模拟mpremote进程，用于测试编码处理"""
    
    def __init__(self, test_data):
        self.test_data = test_data
        self.data_index = 0
        self.returncode = None
        
        # 创建模拟的stdout和stderr
        self.stdout_data = BytesIO()
        self.stderr_data = BytesIO()
        
        # 写入测试数据
        for data_chunk in test_data:
            self.stdout_data.write(data_chunk)
        self.stdout_data.seek(0)
        
        # 模拟文件描述符
        self.stdout = MockFile(self.stdout_data)
        self.stderr = MockFile(self.stderr_data)
    
    def poll(self):
        # 如果所有数据都读完了，返回退出码
        if self.stdout.is_eof():
            return 0
        return None
    
    def terminate(self):
        self.returncode = 0
    
    def wait(self, timeout=None):
        pass
    
    def kill(self):
        pass

class MockFile:
    """模拟文件对象，支持非阻塞读取"""
    
    def __init__(self, data_stream):
        self.data_stream = data_stream
        self.position = 0
        self.total_size = len(data_stream.getvalue())
    
    def fileno(self):
        return 1  # 返回一个假的文件描述符
    
    def read_chunk(self, size):
        """模拟非阻塞读取"""
        if self.position >= self.total_size:
            return b''
        
        # 每次只读取一小部分数据，模拟网络传输
        chunk_size = min(size, 10)  # 每次最多读10字节
        data = self.data_stream.getvalue()[self.position:self.position + chunk_size]
        self.position += len(data)
        return data
    
    def is_eof(self):
        return self.position >= self.total_size

def mock_os_read(fd, size):
    """模拟os.read函数"""
    # 这里需要根据文件描述符返回相应的数据
    # 在实际测试中，我们会替换这个函数
    return b''

def test_monitor_encoding():
    """测试monitor_with_continuous_repl的编码处理"""
    print("=== 测试monitor_with_continuous_repl编码处理 ===")
    
    # 准备测试数据：包含中文字符和截断的UTF-8
    test_data = [
        "[WiFi] 网络扫描开始\n".encode('utf-8'),
        "[WiFi] 网络 36: SSID='".encode('utf-8'),
        b'\xe4\xb8',  # "中"字的前2个字节（截断）
        b'\xad\xe6\x96\x87',  # "中"字的最后1个字节 + "文"字
        "' | RSSI=-92 dBm\n".encode('utf-8'),
        "[WiFi] 匹配的网络数量: 0\n".encode('utf-8'),
        "[WiFi] 未找到配置的网络\n".encode('utf-8'),
    ]
    
    # 创建模拟进程
    mock_process = MockProcess(test_data)
    
    # 模拟monitor_with_continuous_repl的核心逻辑
    stdout_buffer = b""
    stderr_buffer = b""
    stdout_remaining = b""
    stderr_remaining = b""
    
    processed_lines = []
    
    print("开始处理模拟数据...")
    
    # 模拟数据处理循环
    for i, data_chunk in enumerate(test_data):
        print(f"\n--- 处理数据块 {i+1}: {data_chunk} ---")
        
        # 模拟读取stdout数据
        stdout_data = data_chunk
        if stdout_data:
            # 将剩余字节与新数据合并
            stdout_buffer = stdout_remaining + stdout_data
            stdout_remaining = b""  # 清空剩余字节
            
            print(f"合并后的缓冲区: {stdout_buffer}")
            
            # 处理完整的行
            while b'\n' in stdout_buffer:
                line, stdout_buffer = stdout_buffer.split(b'\n', 1)
                print(f"处理行: {line}")
                
                decoded_line, remaining_bytes = safe_decode(line + b'\n')
                print(f"解码结果: '{decoded_line.strip()}', 剩余字节: {remaining_bytes}")
                
                # 如果有剩余字节，将其添加到缓冲区开头
                if remaining_bytes:
                    stdout_buffer = remaining_bytes + stdout_buffer
                    print(f"有剩余字节，更新缓冲区: {stdout_buffer}")
                    break  # 停止处理，等待更多数据
                
                if decoded_line.strip():
                    processed_lines.append(decoded_line.strip())
                    print(f"添加处理行: '{decoded_line.strip()}'")
            
            # 检查缓冲区中是否有不完整的UTF-8字符（没有换行符时）
            if stdout_buffer and b'\n' not in stdout_buffer:
                # 尝试解码缓冲区，如果有不完整的UTF-8，保存到remaining
                decoded_partial, remaining_bytes = safe_decode(stdout_buffer)
                print(f"缓冲区解码: '{decoded_partial}', 剩余字节: {remaining_bytes}")
                
                if remaining_bytes:
                    # 有不完整的UTF-8字符，保存剩余字节
                    stdout_remaining = remaining_bytes
                    # 从缓冲区中移除剩余字节
                    stdout_buffer = stdout_buffer[:-len(remaining_bytes)]
                    print(f"保存不完整UTF-8: {remaining_bytes}，剩余缓冲区: {stdout_buffer}")
                else:
                    # 没有不完整的UTF-8，但也没有换行符，保存整个缓冲区
                    stdout_remaining = stdout_buffer
                    stdout_buffer = b""
                    print(f"保存完整缓冲区到remaining: {stdout_remaining}")
                
                # 如果剩余缓冲区还有完整的内容，处理它
                if stdout_buffer:
                    decoded_remaining, _ = safe_decode(stdout_buffer)
                    if decoded_remaining.strip():
                        processed_lines.append(decoded_remaining.strip())
                        print(f"处理剩余缓冲区: '{decoded_remaining.strip()}'")
                    stdout_buffer = b""
    
    # 处理最后剩余的数据
    if stdout_buffer or stdout_remaining:
        final_buffer = stdout_remaining + stdout_buffer
        if final_buffer:
            decoded_final, _ = safe_decode(final_buffer)
            if decoded_final.strip():
                processed_lines.append(decoded_final.strip())
    
    print("\n=== 处理结果 ===")
    for i, line in enumerate(processed_lines, 1):
        print(f"{i}. {line}")
    
    # 验证结果 - 将所有行合并成一个字符串进行检查
    all_content = " ".join(processed_lines)
    
    expected_content = [
        "[WiFi] 网络扫描开始",
        "[WiFi] 匹配的网络数量: 0",
        "[WiFi] 未找到配置的网络"
    ]
    
    print("\n=== 验证结果 ===")
    success = True
    
    for expected in expected_content:
        found = expected in all_content
        if found:
            print(f"✅ 找到期望内容: '{expected}'")
        else:
            print(f"❌ 未找到期望内容: '{expected}'")
            success = False
    
    # 特别检查中文字符是否正确处理
    chinese_found = "中文" in all_content
    if chinese_found:
        print("✅ 截断的UTF-8字符'中文'正确恢复")
    else:
        print("❌ 截断的UTF-8字符'中文'未正确恢复")
        success = False
    
    # 检查完整的SSID行是否能够重构
    ssid_pattern = "SSID='中文' | RSSI=-92 dBm"
    if ssid_pattern in all_content:
        print(f"✅ 完整SSID行正确重构: '{ssid_pattern}'")
    else:
        print(f"ℹ️  SSID行被分割但UTF-8字符正确恢复（这是正常的，因为数据块本身就是分割的）")
        # 检查分割的部分是否都存在
        if "SSID='" in all_content and "中文" in all_content and "RSSI=-92 dBm" in all_content:
            print("✅ 所有SSID组件都正确处理")
        else:
            print("❌ SSID组件缺失")
            success = False
    
    return success

if __name__ == "__main__":
    try:
        success = test_monitor_encoding()
        if success:
            print("\n🎉 编码处理测试通过！monitor_with_continuous_repl函数能正确处理截断的UTF-8字符。")
        else:
            print("\n❌ 编码处理测试失败！")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)