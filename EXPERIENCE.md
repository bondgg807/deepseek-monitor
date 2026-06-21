# DeepSeek Monitor — 开发经验总结

## 技术栈
Python 3.11 + customtkinter + pystray + Pillow + PyInstaller

## 踩坑记录

### Canvas 动画内存泄漏
- 问题：扫光动画每秒创建 1200 个矩形，长时间运行 Tk 内存不回收导致卡顿
- 解决：每 30 次数据更新（≈30 分钟）销毁重建整个 BarChart 画布

### PyInstaller 图标
- `--icon` 只设 exe 文件图标，不设运行时窗口任务栏图标
- 需额外用 `--add-data "icon.ico;."` 打包，代码中通过 `sys._MEIPASS` 读取
- 需在窗口创建前调用 `SetCurrentProcessExplicitAppUserModelID`

### 单实例检测
- 文件锁：进程崩溃后残留锁文件，需要手动清理
- Windows 互斥锁（CreateMutexW）：进程退出自动释放，更可靠
- 第二次启动：弹出已有窗口 + 任务栏闪烁提示

### 充值金额处理
- 问题：充值后余额上涨，session delta 变正数，消费统计被破坏
- 解决：检测到充值后调用 `add_to_session_start()` 上调消费起点，不重置历史

### Canvas 双缓冲
- `delete("all")` 再重绘会产生闪烁
- 用版本号标签法：新内容画到 `v{N}` 标签，画完删 `v{N-1}`，无闪烁

### customtkinter 布局
- `pack()` 间距难以精确控制 → 卡片内元素用 `place()` 像素定位
- CTkButton 做不到完美圆形 → 改用 PIL 渲染 + Canvas 显示

### PIL 图标抗锯齿
- 2x 渲染后 LANCZOS 缩小到 1x，边缘丝滑
- 多尺寸 ICO 需每尺寸分别渲染，不能放缩

### 动画性能
- 浮字用 Toplevel 透明窗口，不挡内容
- 扫光用渐变遮罩限制在柱边界内
- 定时器用 `after()` 链式调用，避免 `while True` 阻塞主线程

## 文件结构
```
├── deepseek_monitor.pyw    # 入口：单实例锁 + AppUserModelID + API Key 弹窗
├── ui.py                   # 主界面：DeepSeekMonitor + BalanceCard + BarChart
├── balance_tracker.py      # 数据层：记录余额、计算 delta、token 估算
├── api_client.py           # HTTP：调用 /user/balance，重试逻辑
├── config_manager.py       # 配置：多源读取 API Key，窗口位置持久化
├── tray_icon.py            # 托盘：pystray 图标 + 右键菜单
├── acrylic_effect.py       # 窗口特效：Win11 云母/亚克力/圆角
├── assets.py               # 资源：闪电图标生成（PIL 像素坐标）
├── config.example.json     # 配置模板
├── config.json             # 用户配置（gitignore）
├── balance_history.json    # 余额历史（gitignore，上限 1440 条）
├── requirements.txt        # 依赖清单
└── launch.bat              # 双击启动脚本
```
