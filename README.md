# DeepSeek Monitor

DeepSeek API 用量桌面挂件 — 实时监控 DeepSeek 余额和 token 消耗。

## 功能

- 余额实时显示 + 涨绿跌红闪烁
- 近一小时 token 消耗条形图（5 分钟粒度）
- 消耗/充值浮动动画
- 系统托盘（最小化到托盘）
- 新任务：重置计数器，存档旧消耗
- 低余额闪烁提醒 + 弹窗
- 窗口置顶切换
- 单实例运行

## 环境要求

- Windows 10/11
- Python 3.10+

## 安装

```bash
pip install -r requirements.txt
```

## 配置

1. 复制 `config.example.json` 为 `config.json`
2. 填入你的 DeepSeek API Key：
```json
{"api_key": "sk-your-api-key-here"}
```
也可从 Claude Code 的 `settings.json` 或环境变量 `DEEPSEEK_API_KEY` 自动读取。

## 运行

**源码运行：**
```bash
pythonw deepseek_monitor.pyw
```
或双击 `launch.bat`

**打包成 exe：**
```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." --collect-all customtkinter --name "DeepSeek Monitor" deepseek_monitor.pyw
```

## 定价

基于 DeepSeek v4-pro token 价格估算

## 许可证

MIT
