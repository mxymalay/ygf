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
| **电子计价秤** | DIBAL ACS-G315 | RS-232 串口 | `COM1` (9600 bps) | 支持 DIBAL 多协议格式解析 + 原始数据日志 |
| **小票打印机** | Xprinter XP-A160M / XP-80C | USB 驱动 | `shouyin` | 支持 Windows 驱动无冲突共享打印 |

---

## 📂 项目结构

```
ygf/
├── main.py               # 主程序入口
├── config.py             # 全局配置管理 (JSON 持久化)
├── diagnose.py           # 硬件诊断工具 (一键扫描 COM 口和打印机)
├── install_env.bat       # Win7 一键环境安装脚本
├── requirements.txt      # 依赖列表 (PyQt5, pyserial, pywin32)
├── core/                 # 核心模块
│   ├── scale_reader.py   # DIBAL ACS-G315 电子秤串口读取与稳定检测
│   ├── printer.py        # ESC/POS 小票生成与 Win32 打印驱动
│   ├── database.py       # SQLite 销售数据 CRUD 与每日汇总
│   └── calculator.py     # 重量与金额计算器 (按斤/公斤)
├── ui/                   # GUI 界面
│   ├── main_window.py    # 主框架与标签页导航
│   ├── sale_widget.py    # 称重收银界面
│   ├── history_widget.py # 历史记录查询与数据卡片
│   ├── settings_widget.py# 串口/打印机/单价参数设置
│   └── styles.py         # 现代化触控 QSS 样式表
├── utils/                # 诊断与扫描工具
│   └── port_scanner.py   # 硬件端口检测
└── data/                 # 本地数据目录 (数据库、配置文件、日志)
```

---

## ⚡ 快速开始

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

---

## 🔒 端口冲突解决方案 (VSPE)

由于公司收银软件占用 `COM1` 串口，推荐使用 **VSPE (Virtual Serial Port Emulator)** 建立 `Splitter`（串口分流器）：
1. 将物理端口 `COM1` 映射为虚拟端口 `COM2`
2. 公司收银软件与本系统同时读取 `COM2`，实现两套系统实时并行工作。
