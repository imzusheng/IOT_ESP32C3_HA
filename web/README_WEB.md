# ESP32C3 Web 配置界面

## 📋 概述

这是一个专为 ESP32C3 物联网设备设计的 Web 配置界面，采用 Apple 设计风格，提供简洁、优雅的用户体验。通过蓝牙连接设备，支持 WiFi、MQTT 和设备配置的完整管理。

## ✨ 主要特性

### 🔧 核心功能
- **蓝牙设备连接**：自动检测和连接 ESP32C3 设备
- **WiFi 配置**：扫描、添加、删除 WiFi 网络
- **MQTT 配置**：配置 MQTT 服务器、端口、主题等参数
- **设备配置**：设置设备名称、位置、日志级别等
- **系统操作**：重启设备、恢复出厂设置

### 📱 用户体验优化
- **防止双击放大**：完全禁用页面缩放，确保移动端体验流畅
- **Apple 设计风格**：采用 Apple 官方设计语言和配色方案
- **响应式设计**：完美适配移动端和桌面端设备
- **实时状态反馈**：固定状态指示器显示连接状态
- **智能错误处理**：友好的错误提示和状态反馈

### 🛡️ 技术特性
- **Web Bluetooth API**：使用现代 Web 蓝牙技术
- **实时通信**：支持双向数据交换和状态更新
- **安全连接**：加密的蓝牙通信
- **自动重连**：蓝牙状态变化时的自动处理

## 🚀 快速开始

### 浏览器要求

此 Web 应用需要支持 Web Bluetooth API 的现代浏览器：

- ✅ **Google Chrome**（推荐）
- ✅ **Microsoft Edge**
- ✅ **Opera**
- ❌ **Firefox**（不支持 Web Bluetooth API）
- ❌ **Safari**（iOS 版不支持 Web Bluetooth API）

### 使用步骤

1. **打开页面**
   ```bash
   # 在支持 Web Bluetooth API 的浏览器中打开
   # file:///path/to/your/project/web/index.html
   # 或通过 Web 服务器访问
   ```

2. **蓝牙检测**
   - 页面加载时自动检测设备蓝牙支持情况
   - 如果蓝牙不可用，会显示相应的提示信息

3. **连接设备**
   - 点击"连接设备"按钮
   - 在弹出的蓝牙设备选择对话框中选择 ESP32C3 设备
   - 等待连接完成

4. **配置设备**
   - **WiFi 配置**：扫描网络，选择并添加 WiFi 凭据
   - **MQTT 配置**：设置 MQTT 服务器连接参数
   - **设备配置**：配置设备基本信息和系统参数

5. **系统操作**
   - 重启设备：应用新配置后重启设备
   - 恢复出厂设置：清除所有配置并重启

## 📖 详细功能说明

### 1. 蓝牙连接管理

#### 自动检测功能
```javascript
// 页面加载时自动检测蓝牙支持
document.addEventListener('DOMContentLoaded', () => {
    initBluetooth();
});
```

#### 实时状态监控
- 监听蓝牙可用性变化
- 自动更新连接状态
- 智能重连机制

#### 连接状态显示
- **固定状态指示器**：右上角显示连接状态
- **状态颜色编码**：
  - 🟢 绿色：已连接
  - 🔴 红色：未连接
  - 🟠 橙色：扫描中

### 2. WiFi 配置

#### 网络扫描
```javascript
// 扫描可用 WiFi 网络
await wifiScanCharacteristic.writeValue(new TextEncoder().encode('scan'));
```

#### 网络信息显示
- 网络名称 (SSID)
- 加密类型 (开放/WEP/WPA/WPA2)
- 信号强度 (强/中/弱)
- 信道信息
- 保存状态

#### 网络管理
- **添加网络**：输入 SSID 和密码添加新网络
- **删除网络**：删除已保存的网络配置
- **选择网络**：快速选择扫描到的网络

### 3. MQTT 配置

#### 配置参数
- **服务器地址**：MQTT broker 的 IP 地址或域名
- **端口**：MQTT 服务端口（默认 1883）
- **主题**：设备发布和订阅的主题
- **心跳间隔**：MQTT 连接保活时间（默认 60 秒）

#### 配置验证
- 自动验证必填字段
- 实时反馈配置状态
- 错误提示和修正建议

### 4. 设备配置

#### 基本信息
- **设备名称**：自定义设备显示名称
- **设备位置**：设备安装位置描述

#### 系统设置
- **日志级别**：DEBUG/INFO/WARNING/ERROR/CRITICAL
- **调试模式**：开启/关闭调试功能

#### 配置同步
- 配置保存后自动同步到设备
- 实时更新设备信息显示

### 5. 系统操作

#### 重启设备
```javascript
// 发送重启命令
const command = JSON.stringify({ cmd: 'device_restart' });
await configCharacteristic.writeValue(new TextEncoder().encode(command));
```

#### 恢复出厂设置
```javascript
// 发送恢复出厂设置命令
const command = JSON.stringify({ cmd: 'factory_reset' });
await configCharacteristic.writeValue(new TextEncoder().encode(command));
```

#### 安全确认
- 两次确认机制防止误操作
- 清晰的操作后果提示

## 🎨 界面设计

### Apple 设计风格
- **字体系统**：使用 `-apple-system, BlinkMacSystemFont` 等系统字体
- **配色方案**：采用 Apple 官方配色
  - 主色调：#007aff (蓝色)
  - 成功色：#34c759 (绿色)
  - 警告色：#ff9500 (橙色)
  - 错误色：#ff3b30 (红色)
- **圆角设计**：统一的 8px 圆角
- **阴影效果**：柔和的阴影增强层次感

### 响应式布局
- **最大宽度**：480px 确保移动端友好
- **紧凑表单**：网格布局优化空间利用
- **触摸优化**：按钮和表单元素适合触摸操作

### 状态反馈
- **加载动画**：扫描和连接过程的视觉反馈
- **通知系统**：操作结果的即时反馈
- **状态指示器**：实时显示系统状态

## 🔧 技术实现

### 核心技术栈
- **HTML5**：语义化标记结构
- **CSS3**：现代样式和动画
- **JavaScript ES6+**：现代 JavaScript 特性
- **Web Bluetooth API**：蓝牙设备通信
- **Web APIs**：各种现代 Web API

### 关键函数

#### 蓝牙检测
```javascript
async function initBluetooth() {
    // 检查浏览器支持
    if (!navigator.bluetooth) {
        // 显示不支持提示
        return;
    }
    
    // 检查蓝牙可用性
    const availability = await navigator.bluetooth.getAvailability();
    
    // 监听状态变化
    bluetooth.addEventListener('availabilitychanged', (event) => {
        // 更新状态
    });
}
```

#### 设备连接
```javascript
async function connectBluetoothDevice() {
    // 请求蓝牙设备
    const device = await navigator.bluetooth.requestDevice({
        filters: [{ services: [SERVICE_UUID] }]
    });
    
    // 连接 GATT 服务器
    const server = await device.gatt.connect();
    
    // 获取服务和特征值
    const service = await server.getPrimaryService(SERVICE_UUID);
    const characteristic = await service.getCharacteristic(CHAR_CONFIG_UUID);
    
    // 启用通知
    await characteristic.startNotifications();
}
```

#### 配置管理
```javascript
async function saveConfig(path, value) {
    const command = JSON.stringify({ cmd: 'update_config', path: path, value: value });
    await configCharacteristic.writeValue(new TextEncoder().encode(command));
}
```

### 蓝牙服务配置
```javascript
// 蓝牙服务 UUID
const SERVICE_UUID = '00001234-0000-1000-8000-00805f9b34fb';

// 特征值 UUID
const CHAR_CONFIG_UUID = '00001235-0000-1000-8000-00805f9b34fb';    // 配置读写
const CHAR_STATUS_UUID = '00001236-0000-1000-8000-00805f9b34fb';     // 状态通知
const CHAR_WIFI_SCAN_UUID = '00001237-0000-1000-8000-00805f9b34fb';  // WiFi 扫描
const CHAR_WIFI_LIST_UUID = '00001238-0000-1000-8000-00805f9b34fb'; // WiFi 列表
const CHAR_DEVICE_INFO_UUID = '00001239-0000-1000-8000-00805f9b34fb'; // 设备信息
```

## 🛡️ 安全特性

### 防止双击放大
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
```
```css
* {
    touch-action: manipulation;
    -webkit-touch-callout: none;
    -webkit-user-select: none;
    user-select: none;
}
```

### 输入安全
- 表单验证和清理
- XSS 防护
- CSRF 保护

### 通信安全
- 蓝牙加密通信
- 数据完整性验证
- 安全的错误处理

## 🔍 故障排除

### 常见问题

#### 1. 蓝牙连接失败
**问题**：点击连接设备后没有反应或连接失败
**解决方案**：
- 确保浏览器支持 Web Bluetooth API
- 检查设备蓝牙是否开启
- 确保设备在范围内且可被发现
- 尝试刷新页面重新连接

#### 2. 页面无法加载
**问题**：页面显示空白或样式错误
**解决方案**：
- 确保使用支持的浏览器
- 检查浏览器控制台错误信息
- 确认文件路径正确
- 尝试清除浏览器缓存

#### 3. 配置保存失败
**问题**：配置保存后提示失败
**解决方案**：
- 检查蓝牙连接是否稳定
- 确认设备固件版本兼容
- 验证配置参数格式正确
- 尝试重新连接设备

#### 4. WiFi 扫描无结果
**问题**：扫描 WiFi 网络时没有显示任何网络
**解决方案**：
- 确保设备已连接且在线
- 检查设备 WiFi 模块是否正常工作
- 尝试重启设备
- 确认周围有可用的 WiFi 网络

### 调试技巧

#### 浏览器开发者工具
1. 打开开发者工具 (F12)
2. 查看 Console 标签页的错误信息
3. 使用 Network 标签页监控蓝牙通信
4. 检查 Application 标签页的本地存储

#### 蓝牙调试
```javascript
// 启用详细日志
console.log('蓝牙状态:', bluetoothSupported);
console.log('设备信息:', device);
console.log('连接状态:', server?.connected);
```

#### 设备端调试
- 检查设备串口日志
- 验证蓝牙服务是否正确广播
- 确认特征值读写权限设置正确

## 📱 移动端优化

### 触摸优化
- **按钮大小**：最小 44x44px 符合触摸标准
- **间距设计**：足够的点击间距防止误操作
- **视觉反馈**：按钮按下状态的即时反馈

### 性能优化
- **资源压缩**：CSS 和 JavaScript 文件压缩
- **缓存策略**：合理的浏览器缓存设置
- **懒加载**：按需加载资源减少初始加载时间

### 电池优化
- **低功耗模式**：减少不必要的后台操作
- **连接管理**：智能的蓝牙连接管理
- **动画优化**：减少复杂动画节省电量

## 🔄 更新日志

### v1.0.0 (2024-01-01)
- ✨ 初始版本发布
- 🔧 基础蓝牙连接功能
- 📡 WiFi 配置功能
- 📊 MQTT 配置功能
- 🎨 Apple 设计风格界面
- 📱 移动端优化
- 🛡️ 防止双击放大

### v1.1.0 (2024-01-15)
- 🔧 修复 JavaScript 错误
- 📊 改进状态显示
- 🎨 优化界面响应速度
- 📱 增强移动端体验
- 🔍 添加详细错误提示

## 📄 许可证

本项目采用 MIT 许可证。详情请参阅 [LICENSE](../LICENSE) 文件。

## 🤝 贡献

欢迎贡献代码、报告问题或提出改进建议！

### 贡献方式
1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

### 开发环境设置
```bash
# 克隆项目
git clone https://github.com/your-username/IOT_ESP32C3_HA.git

# 进入项目目录
cd IOT_ESP32C3_HA

# 安装依赖（如果有）
npm install

# 启动开发服务器
python -m http.server 8000
```

## 📞 支持

如果您在使用过程中遇到任何问题，请通过以下方式获取支持：

- 📧 **邮件支持**：[your-email@example.com](mailto:your-email@example.com)
- 🐛 **问题报告**：[GitHub Issues](https://github.com/your-username/IOT_ESP32C3_HA/issues)
- 📖 **文档**：[项目 Wiki](https://github.com/your-username/IOT_ESP32C3_HA/wiki)
- 💬 **讨论**：[GitHub Discussions](https://github.com/your-username/IOT_ESP32C3_HA/discussions)

## 🙏 致谢

感谢以下开源项目和贡献者：

- [Web Bluetooth API](https://webbluetoothcg.github.io/web-bluetooth/) - 蓝牙通信技术
- [Apple Design Resources](https://developer.apple.com/design/resources/) - 设计灵感
- [Material Design](https://material.io/design) - 设计规范参考
- 所有贡献代码和提出建议的开发者

---

**最后更新**：2024-01-15  
**版本**：v1.1.0  
**维护者**：ESP32C3 开发团队
