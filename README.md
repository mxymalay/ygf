# 杨国福麻辣烫 · 独立称重打印系统 (YGF POS)

本系统是一套为杨国福麻辣烫加盟店量身定制的**独立称重与自定义小票打印系统**。旨在绕过公司统一收银系统，实现特定营业数据的本地化独立存储与统计，同时保证原有系统与硬件完全兼容并存。

---

## 🛠️ 技术栈与环境

- **运行环境**: Python 3.8.10+ (完全兼容 Windows 7 / Windows 10 / Windows 11)
- **GUI 框架**: PyQt5 (深色触控界面)
- **数据库**: SQLite 3 (内置 WAL 高并发模式)
- **硬件通信**: `pyserial` (串口通信) / `pywin32` (Windows 原生打印驱动)
- **指令集**: ESC/POS 80mm 热敏切纸指令

---

## 🔌 硬件适配情况

| 硬件 | 设备型号 | 通信方式 | 端口/驱动名称 | 说明 |
|------|----------|----------|---------------|------|
| **电子计价秤** | DIBAL ACS-G315 | RS-232 串口 | 现场识别、不固定 COM 号（9600 bps） | 支持 DIBAL 多协议格式解析 + 原始数据日志 |
| **小票打印机** | Xprinter XP-A160M / XP-80C | USB 驱动 | `shouyin` | 支持 Windows 驱动无冲突共享打印 |

双 POS 电子秤桥接的完整安装、测试、修复与安全删除步骤见 [ScaleBridge Windows 7 操作手册](docs/scale_bridge_win7.md)，故障处理见 [ScaleBridge 故障排查](docs/scale_bridge_troubleshooting.md)。

官方 POS 打印中继安装、测试、停用与删除步骤见 [打印机中继 Windows 7 操作手册](docs/printer_relay_win7.md)。

官方 POS 窗口首次选择、启动检测与切换规则见 [官方 POS 窗口识别](docs/official_window_setup.md)。

---

## 📂 项目结构

```
ygf/
├── main.py               # 主程序入口
├── build_exe.py          # PyInstaller 一键 EXE 打包编译工具
├── build.bat             # Windows 鼠标双击打包批处理文件
├── config.py             # 全局配置管理 (JSON 持久化)
├── diagnose.py           # 硬件诊断工具 (一键扫描 COM 口和打印机)
├── install_env.bat       # Win7 一键环境安装脚本
├── requirements.txt      # 依赖列表 (PyQt5, pyserial, pywin32)
├── core/                 # 核心模块
│   ├── call_number_manager.py # 智能避重叫号引擎 (上午/下午/晚上自动段划分)
│   ├── scale_reader.py   # DIBAL ACS-G315 电子秤串口读取与稳定检测
│   ├── printer.py        # ESC/POS 小票生成与 Win32 打印驱动
│   ├── database.py       # SQLite 销售数据 CRUD 与每日汇总
│   └── calculator.py     # 重量与金额计算器 (按斤/公斤)
├── ui/                   # GUI 界面
│   ├── sidebar.py        # 杨国福原生火焰红竖向导航侧边栏
│   ├── main_window.py    # 主框架与 QStackedWidget 堆栈导航
│   ├── sale_widget.py    # 称重收银界面
│   ├── history_widget.py # 历史记录查询与数据卡片
│   ├── queue_widget.py   # 叫号避重设置独立菜单
│   ├── settings_widget.py# 串口/打印机/单价参数设置
│   └── styles.py         # 现代化触控 QSS 样式表
├── utils/                # 诊断与扫描工具
│   └── port_scanner.py   # 硬件端口检测
└── data/                 # 本地数据目录
    ├── db/               # SQLite 销售数据库（旧 data/sales.db 会自动移入）
    ├── settings/         # 分模块配置
    └── backups/          # 配置迁移/重置备份
```

首次发现旧版 `data/settings.json` 时，系统会显示触屏迁移向导：可以重建配置、勾选保留项目，或全部自动迁移。三种选择都不会删除或重建销售数据库。

---

## 📦 一键打包为独立软件 (.EXE)

系统内置了 PyInstaller 一键打包工具，并生成带安装、更新、卸载功能的独立安装包；店面电脑无需安装 Python：

### 打包步骤：
1. **直接双击运行 `build.bat`** (或者在终端运行 `python build_exe.py`)。
2. 脚本将自动安装打包依赖并完成高压编译。
3. 编译完成后，项目 `dist/` 目录只生成一个 `YGF-POS-Setup.exe` 安装包。
4. **推荐使用**：双击 `dist/YGF-POS-Setup.exe`，选择安装目录。安装包会在安装目录释放 `启动.exe`、桥接服务、维修工具，并创建快捷方式和“卸载.exe”。
5. 再次运行新的安装包时会覆盖更新程序文件，并保留安装目录下 `data/` 中的数据库、配置和日志；卸载时可选择是否保留这些数据。

安装向导还可以选择应用显示名称：`私有 POS 系统`、`门店称重助手`、`称重桥接管理器`，或选择“用户自定”输入名称。该名称用于桌面/开始菜单快捷方式和 Windows“应用和功能”显示；实际 EXE 与桥接服务文件名保持固定，确保更新、服务注册和卸载稳定。

---

## ⚡ 快速开始 (开发调试)

### 1. 克隆代码
```bash
git clone https://github.com/mxymalay/ygf.git
cd ygf
```

### 2. 安装依赖
#### Windows 7 (店内电脑):
直接双击运行 `install_env.bat`。

#### Windows 10/11:
```bash
pip install -r requirements.txt
```

### 3. 运行程序
```bash
python main.py
```
