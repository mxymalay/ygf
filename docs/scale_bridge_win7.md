# ScaleBridge（Windows 7 SP1 x64）完整操作手册

ScaleBridge 是独立 Windows 服务，也是唯一打开物理电子秤串口的进程。物理秤端口由安装人员扫描并测试后选择，不假设为 `COM1` 或任何固定端口。官方 POS 与本 POS 分别使用自己的称重虚拟端口。

系统设置已按职责分开：

- “电子秤设置”只设置本 POS 从哪里读取重量；
- “POS 称桥接”只设置官方 POS 与本 POS 共享电子秤；
- “收钱吧插件”只设置金额发送、快捷键和可选支付串口配对。

已由现场抓包确认的电子秤为 DIBAL ACS-G315，协议参数为 `9600 / 8N1 / DTR 开 / RTS 关 / 无流控`。主机约每 200 ms 发送 ASCII `$`（十六进制 `24`），秤返回 `000.402\r` 形式的 kg 重量。

## 部署包内容

完整部署目录必须同时包含：

```text
YGF-POS\
  驱动.exe
  ScaleBridgeService.exe
  ScaleBridgeMaintenance.exe
  ThirdParty\com0com\Setup_com0com...W7_x64_signed.exe
  data\scale_bridge.example.json
  docs\scale_bridge_win7.md
  docs\scale_bridge_troubleshooting.md
```

如果部署目录还包含 `ThirdParty\hub4com\hub4com.exe`，打包脚本会一并复制它及批处理示例。hub4com 仅用于技术人员手工诊断/临时多路复用；正式运行时由 `YgfScaleBridge` 独占物理秤并完成仲裁，程序不会自动启动 hub4com，也不会把它当作必需依赖。

`build_exe.py` 会生成上述目录。不能只复制 `驱动.exe`，否则无法安装独立服务或首次安装虚拟串口驱动。

## POS 称桥接字段

| 字段 | 首次建议 | 说明 |
| --- | --- | --- |
| 物理秤端口 | 无 | 必须扫描、选择并测试，例如 `COM5` |
| 官方 POS | `COM2` | 官方 POS 实际打开的虚拟端口，可调整 |
| 服务官方对端 | 空 | 初始化时读取 `setupc list` 后自动填写 |
| 本 POS | `COM3` | 本 POS 称重模块打开的虚拟端口，可调整 |
| 服务本 POS 对端 | 空 | 初始化时自动生成，只读显示 |

程序不假设内部对端一定是某个 `CNCB` 序号。收钱吧端口不出现在此页面。

## 从一台全新收银机开始

1. 把整个 `YGF-POS` 部署目录复制到收银机的固定目录，不要只复制主 EXE。
2. 双击根目录 `双击启动系统.bat`；脚本会自动请求管理员权限。发布版 `驱动.exe` 同样带管理员权限清单。
3. 打开“系统设置 → POS 称桥接”。页面已经按 1 → 2 → 3 → 4 排列。
4. 步骤 1 点击“识别物理设备”。页面会：
   - 枚举真实串口；
   - 排除虚拟串口；
   - 显示 COM 号、设备名称、制造商、Service、PNPDeviceID、Hardware ID、VID/PID、USB 序列号和占用状态；
   - 让安装人员明确选择实际连接 DIBAL ACS-G315 的端口。
5. 点击“测试物理秤”。成功时必须看到合法重量、原始十六进制数据和实际物理端口。
6. 步骤 2 填写“官方 POS 使用”和“本 POS 使用”两个不同的空闲 COM 号。两个服务对端无需填写；也可仅保存草稿。
7. 步骤 3 点击“初始化 / 修复 POS 称桥接”并确认。程序会按顺序：
   - 再次测试物理电子秤；
   - 检查管理员权限；
   - 查找 com0com 与 `setupc.exe`；
   - 缺少驱动时运行部署包内经过验证的签名安装程序；
   - 枚举真实/虚拟串口并检查名称冲突；
   - 只维护官方 POS 和本 POS 两组称重配对；
   - 复用完全匹配的现有称重配对，只创建缺失配对；
   - 重新执行 `setupc list`，读取并保存真实内部对端；
   - 把本程序新建的配对写入 `data/scale_bridge_installation.json` 所有权清单；
   - 安装自动启动的 `YgfScaleBridge` Windows 服务；
   - 启动服务并确认 Windows 服务进入 RUNNING。
8. 步骤 4 依次执行“查看服务状态”“检查两组端口配对”“测试官方 POS 秤通道”“测试本 POS 秤通道”。四项都通过才算完成。
9. 将官方 POS 设置为页面显示的官方 POS 端口。
10. 到“电子秤设置”，把本 POS 的数据来源设为 `com`，端口填写桥接页显示的本 POS 端口并保存。不要填写实际物理秤端口。

## 可选：收钱吧支付串口配对

这部分与 POS 称桥接独立，只在“系统设置 → 收钱吧插件”操作：

1. 在上方设置收钱吧发送端口、波特率、格式和快捷键，点击“保存收钱吧设置”。发送端不是固定 `COM10`。
2. 若收钱吧插件监听另一个串口，在“可选：收钱吧金额虚拟串口配对”填写插件接收端。
3. 点击“创建 / 修复支付配对”。它只维护支付用途配对，不创建、停止或删除称桥接服务。
4. 关闭占用两个支付端口的软件，点击“双向测试支付配对”。
5. 不再需要时点击“删除支付配对”。它只删除本产品清单中精确匹配的支付配对，收钱吧参数仍保留。

## 初始化后的验收

依次执行，不能只测试一种状态：

1. 仅启动官方 POS：官方端能获得重量。
2. 仅启动本 POS：本 POS 每 200 ms 查询并获得重量。
3. 两者同时运行：状态显示 `OFFICIAL_ACTIVE`；本 POS 查询被抑制，但仍收到官方查询产生的原始秤回包。
4. 关闭官方 POS：超过默认 1000 ms 后切换为 `PRIVATE_ACTIVE`，本 POS 查询自动恢复。
5. 再启动官方 POS：第一条官方 `$` 立即转发并恢复官方优先。
6. 分别关闭占用对应端口的 POS，运行“测试官方 POS 秤通道”和“测试本 POS 秤通道”，验证两条端到端回包。
7. 重启 Windows：虚拟配对保持存在，服务自动启动；无需再次初始化。
8. USB 转串口重新分配 COM 号时：服务只有在保存的硬件身份唯一匹配时才自动更新；多个相同设备时拒绝猜测并报告错误。

## 日常操作

- “查看桥接服务状态”：只读命名管道，不打开串口。
- “检查虚拟端口配对”：只执行 `setupc list`，不创建或删除。
- “启动服务”：服务已安装但停止时使用。
- “停止服务”：维护、重新测试物理秤或准备删除时使用。
- “生成诊断”：写入 `data/scale_bridge_diagnosis.json`，包含配置、设备身份、所有串口、配对、服务状态和所有权清单。
- “初始化 / 修复”：幂等操作；不会重复创建已有正确配对。
- 修改任一称重虚拟端口后不要只保存草稿，应直接点“初始化 / 修复”。程序只清理所有权清单中仍精确匹配的旧称重配对，不碰支付配对。

## 删除桥接功能

1. 在“POS 称桥接”页点击“删除 POS 称桥接”。
2. 确认后，程序会停止并删除本产品记录的服务，只删除所有权清单中精确匹配的两组称重配对，再删除 `data/scale_bridge.json`。
3. 若配对的序号或两端名称已被外部工具改动，程序会停止并拒绝删除，不会猜测。
4. 页面不会卸载 com0com，也不会删除支付配对、收钱吧参数、真实串口驱动或其他业务设置。

## 命令行维修

在部署目录的维护终端中可执行：

```text
ScaleBridgeMaintenance.exe --config data\scale_bridge.json diagnose
ScaleBridgeMaintenance.exe --config data\scale_bridge.json test-physical
ScaleBridgeMaintenance.exe test-pair COM10 COM11
ScaleBridgeMaintenance.exe service query
ScaleBridgeMaintenance.exe service start
ScaleBridgeMaintenance.exe service stop
ScaleBridgeMaintenance.exe --config data\scale_bridge.json initialize --yes
ScaleBridgeMaintenance.exe --config data\scale_bridge.json remove --yes
```

初始化与删除必须显式提供 `--yes`。日常 POS 启动不会执行安装、建对或删除命令。

## com0com / hub4com 边界

`com0com` 负责持久化创建 `COMx ↔ CNCBx` 虚拟配对，POS 称桥接页面通过 `setupc.exe list/install/remove` 检查、创建和安全删除；支付配对使用同一驱动，但由独立的收钱吧页面维护。`hub4com` 的典型手工命令（例如 `hub4com --route=All:All \\.\CNCB0 \\.\CNCB1 \\.\CNCB2`）只适合停服务后的诊断，不能与 `YgfScaleBridge` 同时打开同一个物理 COM 口，否则会产生端口占用和重复转发。

## Windows 7 x64 安全边界

- Python 固定为 3.8 兼容环境；PyQt5、pyserial、pywin32 与 PyInstaller 都使用 Win7 可运行版本构建。
- 只使用已核验的 Win7 x64 签名 com0com 安装包。
- 禁止 SPSniff、Ports 类 UpperFilters、测试签名模式、`nointegritychecks`、批量删除 OEM INF 或真实串口驱动。
- 队列有容量上限，断线重连会丢弃旧查询，不向重连后的电子秤重放历史命令。
- 服务配置、所有权清单和诊断报告与现有 POS 业务配置完全分离。

## 尚需在目标收银机执行的实机验收

代码测试可以验证协议、仲裁、配对规划、冲突保护、服务命令状态机和安全删除逻辑，但驱动安装、Windows SCM、真实 COM 设备和 DIBAL 硬件必须在目标 Windows 7 x64 收银机按“初始化后的验收”逐项实测。开发机不会自动执行这些系统级操作。
