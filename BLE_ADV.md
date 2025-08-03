def _parse_device_name(self, adv_data):
    """
    解析设备名称 - 修复版本
    
    主要修复：
    1. 修正长度字段的解析逻辑
    2. 增强错误处理和边界检查
    3. 优化字符编码处理
    4. 改进调试输出
    """
    if not adv_data:
        return "未知"
    
    # 转换为bytes
    try:
        if isinstance(adv_data, memoryview):
            adv_bytes = bytes(adv_data)
        elif isinstance(adv_data, (bytes, bytearray)):
            adv_bytes = bytes(adv_data)
        else:
            return "未知"
    except:
        return "未知"
    
    if len(adv_bytes) == 0:
        return "未知"
    
    # 解析AD结构
    index = 0
    device_name = ""
    complete_name = ""  # 优先保存完整名称
    short_name = ""     # 备用短名称
    
    # 调试模式：显示解析过程
    if self.debug_mode:
        print(f"[DEBUG] 开始解析设备名称，数据长度: {len(adv_bytes)}")
        print(f"[DEBUG] 原始数据: {ubinascii.hexlify(adv_bytes).decode()}")
    
    while index < len(adv_bytes):
        try:
            # 读取长度字段 (1个字节)
            if index >= len(adv_bytes):
                break
            
            length = adv_bytes[index]
            if length == 0:
                # 长度为0，跳出循环
                break
            
            # 检查是否有足够的数据（长度字段本身不包含在长度计算中）
            if index + 1 + length > len(adv_bytes):
                if self.debug_mode:
                    print(f"[DEBUG] 数据不完整，位置: {index}, 长度: {length}, 剩余数据: {len(adv_bytes) - index}")
                break
            
            # 读取类型字段 (1个字节)
            if index + 1 >= len(adv_bytes):
                break
            
            ad_type = adv_bytes[index + 1]
            
            # 计算数据长度 (length - 1，因为length包含了类型字节)
            data_len = length - 1
            data_start = index + 2
            data_end = data_start + data_len
            
            # 调试模式：显示每个字段
            if self.debug_mode:
                print(f"[DEBUG] 字段位置: {index}, 长度字段值: {length}, 类型: 0x{ad_type:02X}, 数据长度: {data_len}")
            
            # 检查是否是设备名称类型
            if ad_type in [0x08, 0x09]:  # 0x08=短名称, 0x09=完整名称
                if data_len > 0 and data_end <= len(adv_bytes):  # 确保有名称数据且不越界
                    name_bytes = adv_bytes[data_start:data_end]
                    
                    if self.debug_mode:
                        print(f"[DEBUG] 发现名称字段，类型: 0x{ad_type:02X}, 原始数据: {ubinascii.hexlify(name_bytes).decode()}")
                    
                    # 解析名称数据
                    try:
                        # 首先尝试UTF-8编码
                        parsed_name = name_bytes.decode('utf-8').strip()
                        
                        # 过滤掉控制字符和不可打印字符
                        clean_name = ''.join(c for c in parsed_name if c.isprintable() and ord(c) >= 32)
                        
                        if clean_name and len(clean_name.strip()) > 0:
                            clean_name = clean_name.strip()
                            
                            if ad_type == 0x09:  # 完整名称
                                complete_name = clean_name
                                if self.debug_mode:
                                    print(f"[DEBUG] 成功解析完整名称: {complete_name}")
                            elif ad_type == 0x08:  # 短名称
                                short_name = clean_name
                                if self.debug_mode:
                                    print(f"[DEBUG] 成功解析短名称: {short_name}")
                                    
                    except UnicodeDecodeError:
                        # UTF-8解码失败，尝试ASCII编码
                        try:
                            parsed_name = name_bytes.decode('ascii', errors='ignore').strip()
                            clean_name = ''.join(c for c in parsed_name if c.isprintable() and ord(c) >= 32)
                            
                            if clean_name and len(clean_name.strip()) > 0:
                                clean_name = clean_name.strip()
                                
                                if ad_type == 0x09:  # 完整名称
                                    complete_name = clean_name
                                    if self.debug_mode:
                                        print(f"[DEBUG] 成功解析完整名称(ASCII): {complete_name}")
                                elif ad_type == 0x08:  # 短名称
                                    short_name = clean_name
                                    if self.debug_mode:
                                        print(f"[DEBUG] 成功解析短名称(ASCII): {short_name}")
                        except:
                            if self.debug_mode:
                                print(f"[DEBUG] 名称解析失败，原始数据: {ubinascii.hexlify(name_bytes).decode()}")
            
            # 移动到下一个AD结构
            # 关键修复：正确的偏移量计算
            index += 1 + length  # 1字节长度字段 + length字节的数据（包含类型字段）
            
        except Exception as e:
            if self.debug_mode:
                print(f"[DEBUG] 解析AD结构时出错: {e}")
            break
    
    # 确定最终的设备名称
    # 优先级：完整名称 > 短名称 > 未知
    if complete_name:
        device_name = complete_name
    elif short_name:
        device_name = short_name
    else:
        device_name = "未知"
    
    if self.debug_mode:
        print(f"[DEBUG] 最终设备名称: {device_name}")
    
    return device_name

def parse_coros_data_enhanced(hex_data):
    """
    增强版COROS数据解析函数 - 集成到BLE扫描器中使用
    
    参数:
        hex_data: 十六进制字符串
    
    返回:
        解析后的列表和设备名称
    """
    result = []
    device_name = "未知设备"
    index = 0
    len_hex = len(hex_data)
    
    # 类型描述映射
    type_descriptions = {
        0x01: "标志",
        0x08: "短本地名称", 
        0x09: "完整设备名称",
        0x19: "外观",
        0x43: "设备标识",
        0x32: "设备信息",
        0xFF: "制造商特定数据"
    }
    
    print(f"[COROS] 解析数据: {hex_data}")
    
    while index < len_hex:
        # 读取长度 (2个十六进制字符 = 1字节)
        if index + 2 > len_hex:
            break
        length = int(hex_data[index:index+2], 16)
        index += 2
        
        print(f"[COROS] 位置 {index-2}: 长度字段 = {length}")
        
        # 读取类型 (2个十六进制字符 = 1字节)
        if index + 2 > len_hex:
            break
        type_val = int(hex_data[index:index+2], 16)
        index += 2
        
        print(f"[COROS] 位置 {index-2}: 类型字段 = 0x{type_val:02X}")
        
        # 关键修正：数据长度应该是 (length - 1) * 2
        data_len = (length - 1) * 2
        if index + data_len > len_hex:
            data_hex = hex_data[index:]
            index = len_hex
        else:
            data_hex = hex_data[index:index+data_len]
            index += data_len
        
        print(f"[COROS] 数据长度: {data_len//2} 字节, 数据: {data_hex}")
        
        # 解析数据
        data = ""
        description = ""
        
        # 针对0x09类型（完整设备名称）进行专门处理
        if type_val == 0x09:
            try:
                # 转换为ASCII字符串
                data = bytes.fromhex(data_hex).decode('ascii').strip()
                description = f"{type_descriptions[type_val]}: {data}"
                device_name = data
                print(f"[COROS] 成功解析设备名称: {device_name}")
            except Exception as e:
                data = data_hex
                description = f"完整设备名称 (解析失败: {str(e)})"
                print(f"[COROS] 名称解析失败: {e}")
                
        elif type_val == 0x19:  # 外观类型
            # 反转字节顺序
            bytes_list = [data_hex[i:i+2] for i in range(0, len(data_hex), 2)]
            reversed_bytes = bytes_list[::-1]
            uuid_hex = ''.join(reversed_bytes)
            data = f"0x{uuid_hex}"
            description = f"外观: {data}"
            
        else:  # 其他类型
            try:
                # 尝试解析为字符串
                str_data = bytes.fromhex(data_hex).decode('ascii').strip()
                data = str_data
                description = f"{type_descriptions.get(type_val, f'类型0x{type_val:02X}')}: {data}"
            except:
                data = data_hex
                description = f"{type_descriptions.get(type_val, f'类型0x{type_val:02X}')} (二进制数据)"
        
        # 添加到结果
        result.append((
            length, 
            f"0x{type_val:02X}", 
            type_descriptions.get(type_val, f"未知类型0x{type_val:02X}"), 
            data, 
            description
        ))
    
    return result, device_name

# 测试函数
def test_name_parsing():
    """测试名称解析功能"""
    print("=" * 80)
    print("BLE设备名称解析测试")
    print("=" * 80)
    
    # 测试数据1: COROS数据
    test_data_1 = "0319C1001409434F524F532050414345203220414232453037"
    print(f"\n测试数据1: {test_data_1}")
    parsed_data_1, device_name_1 = parse_coros_data_enhanced(test_data_1)
    print(f"解析结果: {device_name_1}")
    
    # 测试数据2: 模拟标准BLE广播数据
    # 长度=12, 类型=0x09(完整名称), 数据="Test Device"
    test_name = "Test Device"
    test_name_hex = test_name.encode('ascii').hex()
    test_data_2 = f"0C09{test_name_hex}"
    print(f"\n测试数据2: {test_data_2}")
    print(f"预期名称: {test_name}")
    
    # 手动解析测试
    adv_bytes = bytes.fromhex(test_data_2)
    length = adv_bytes[0]  # 12
    ad_type = adv_bytes[1]  # 0x09
    name_data = adv_bytes[2:2+(length-1)]  # 去掉类型字节
    parsed_name = name_data.decode('ascii')
    
    print(f"手动解析: 长度={length}, 类型=0x{ad_type:02X}, 名称={parsed_name}")
    
    print("=" * 80)

if __name__ == "__main__":
    test_name_parsing()