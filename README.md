# 中文语音识别系统

一个基于Web Speech API的中文语音识别应用，支持长按录音和实时识别。

## 功能特点

✅ **中文精准识别** - 专为中文语音优化，识别准确率高
✅ **长按录音** - 人性化交互设计，长按开始录音，松开自动识别
✅ **实时反馈** - 录音状态实时显示，识别结果即时呈现
✅ **响应式设计** - 完美适配桌面和移动设备
✅ **无需后端** - 纯前端实现，无需服务器配置
✅ **开箱即用** - 下载后直接运行，无需额外配置

## 浏览器兼容性

- ✅ Chrome (推荐)
- ✅ Edge
- ✅ Safari
- ❌ Firefox (不支持Web Speech API)

## 快速开始

### 方法一：直接打开HTML文件

1. 下载项目文件
2. 使用Chrome/Edge浏览器直接打开 `index.html`
3. 允许麦克风权限即可使用

### 方法二：使用本地服务器（推荐）

使用本地服务器可以避免跨域问题和麦克风权限问题：

#### Python方式：
```bash
# Python 3
python -m http.server 8000

# 然后在浏览器访问 http://localhost:8000
```

#### Node.js方式：
```bash
# 安装http-server
npm install -g http-server

# 启动服务器
http-server -p 8000

# 然后在浏览器访问 http://localhost:8000
```

#### 使用提供的启动脚本：

Windows用户双击运行 `start-server.bat`

## 使用方法

1. **打开页面**：在支持的浏览器中打开应用
2. **授权麦克风**：首次使用时允许麦克风访问权限
3. **长按录音**：长按录音按钮开始说话
4. **松开识别**：松开按钮后自动进行语音识别
5. **查看结果**：识别结果会显示在下方文本框中

## 技术实现

- **Web Speech API**：浏览器原生的语音识别接口
- **长按检测**：JavaScript实现长按手势识别
- **中文优化**：设置`lang: 'zh-CN'`确保中文识别精准
- **动画效果**：CSS动画增强用户体验

## 注意事项

⚠️ **首次使用需要授权麦克风权限**
- Chrome：点击地址栏左侧的锁图标，允许麦克风
- Edge：同上
- Safari：在系统偏好设置 > 安全性与隐私中授权

⚠️ **网络连接**
- Web Speech API需要联网才能工作
- 确保设备已连接到互联网

⚠️ **识别精度优化建议**
- 在安静环境下使用
- 说话清晰、语速适中
- 避免方言口音过重

## 自定义配置

如需调整识别参数，可在 `main.js` 中修改：

```javascript
this.recognition.lang = 'zh-CN';  // 识别语言
this.longPressDelay = 300;          // 长按触发时间（毫秒）
```

## 项目结构

```
├── index.html      # 主页面
├── main.js         # 核心逻辑
├── style.css       # 样式文件
├── start-server.bat # Windows启动脚本
└── README.md       # 说明文档
```

## 浏览器控制台说明

### 支持的API：
- `webkitSpeechRecognition` (Chrome, Safari)
- `SpeechRecognition` (Edge)

### 常见问题：
- `NotAllowedError`：用户拒绝了麦克风权限
- `NotFoundError`：没有找到麦克风设备
- `NetworkError`：网络连接问题

## 后续优化方向

- [ ] 支持多语言切换
- [ ] 添加录音时长限制
- [ ] 支持连续语音识别
- [ ] 添加置信度显示
- [ ] 支持结果导出
- [ ] 集成第三方语音识别API（讯飞、百度等）

## 许可证

MIT License

## 技术交流群

如有问题或建议，欢迎通过GitHub Issues反馈。
