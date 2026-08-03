# ScaleBridge（Windows 7 SP1 x64）完整操作手册

ScaleBridge 是独立 Windows 服务，也是唯一打开物理电子秤串口的进程。物理秤端口由安装人员扫描并测试后选择，不假设为 `COM1` 或任何固定端口。官方 POS、私有 POS 和支付插件只使用各自配置的虚拟端口。

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

`build_exe.py` 会生成上述目录。不能只复制 `驱动.exe`，否则无法安装独立服务或首次安装虚拟串口驱动。

## 设置字段

| 字段 | 首次建议 | 说明 |
| --- | --- | --- |
| 物理秤端口 | 无 | 必须扫描、选择并测试，例如 `COM5` |
| 官方 POS | `COM2` | 官方 POS 实际打开的虚拟端口，可调整 |
| 服务官方对端 | 空 | 初始化时读取 `setupc list` 后自动填写 |
| 私有 POS | `COM3` | 私有 POS 称重模块打开的虚拟端口，可调整 |
| 服务私有对端 | 空 | 初始化时读取 `setupc list` 后自动填写 |
| 收钱吧发送端 | 当前收钱吧设置，通常 `COM10` | 私有 POS 发送金额使用，可调整 |
| 支付插件对端 | 通常 `COM11` | 收钱吧插件打开，可调整；不需要支付配对时两项都留空 |

所有字段都可配置。程序不假设内部对端一定是某个 `CNCB` 序号。

## 从一台全新收银机开始

1. 把整个 `YGF-POS` 部署目录复制到收银机的固定目录，不要只复制主 EXE。
2. 启动 `驱动.exe`。发布版带管理员权限清单，Windows 会显示 UAC 确认。
3. 打开“系统设置 → 电子秤设置 → ScaleBridge 双 POS 串口服务（安装与维护）”。
4. 点击“识别物理设备”。页面会：
   - 枚举真实串口；
   - 排除虚拟串口；
   - 显示 COM 号、设备名称、制造商、Service、PNPDeviceID、Hardware ID、VID/PID、USB 序列号和占用状态；
   - 让安装人员明确选择实际连接 DIBAL ACS-G315 的端口。
5. 点击“测试物理秤”。成功时必须看到合法重量、原始十六进制数据和实际物理端口。测试只发送已确认的 `$` 查询，不发送其他探测命令。
6. 检查官方、私有和支付应用端口。应用端口可调整；首次安装时官方/私有“服务对端”保持空白，让程序自动分配。
7. 可先点“保存桥接配置”。它只写 `data/scale_bridge.json`，不会安装驱动、创建端口、启动服务或修改现有 POS 设置。
8. 点击“初始化 / 修复”并确认。程序会按顺序：
   - 再次测试物理电子秤；
   - 检查管理员权限；
   - 查找 com0com 与 `setupc.exe`；
   - 缺少驱动时运行部署包内经过验证的签名安装程序；
   - 枚举真实/虚拟串口并检查名称冲突；
   - 复用完全匹配的现有配对，只创建缺失配对；
   - 重新执行 `setupc list`，读取并保存真实内部对端；
   - 把本程序新建的配对写入 `data/scale_bridge_installation.json` 所有权清单；
   - 安装自动启动的 `YgfScaleBridge` Windows 服务；
   - 启动服务并确认 Windows 服务进入 RUNNING。
9. 点击“查看桥接服务状态”。确认物理端口、官方/私有应用端和服务对端、当前模式、最近重量、最近查询/回包、重连次数和错误信息均合理。
10. 点击“检查虚拟端口配对”，确认三组配对。支付配对未启用时可将支付两项都留空。
11. 关闭占用支付端口的程序后点击“测试支付配对”。程序会在两个端口间双向发送随机测试字节并逐字节校验。
12. 保持桥接服务运行，分别关闭占用对应端口的软件，再点击“测试官方秤通道”和“测试私有秤通道”。两项都必须显示合法重量；这会验证 `POS 虚拟端口 → ScaleBridge → 物理秤 → 回包` 的完整链路。
13. 将官方 POS 设置为页面显示的“官方 POS”端口。官方 POS 本身不需要任何代码修改。
14. 在本私有 POS 上把称来源设为 `com`，称端口设置为页面显示的“私有 POS”端口并保存。不要填写实际物理秤端口。
15. 收钱吧发送端仍在“收钱吧插件”页调整；它不是固定 `COM10`。插件另一端使用桥接区配置的支付对端。

## 初始化后的验收

依次执行，不能只测试一种状态：

1. 仅启动官方 POS：官方端能获得重量。
2. 仅启动私有 POS：私有端每 200 ms 查询并获得重量。
3. 两者同时运行：状态显示 `OFFICIAL_ACTIVE`；私有查询被抑制，但私有端仍收到官方查询产生的原始秤回包。
4. 关闭官方 POS：超过默认 1000 ms 后切换为 `PRIVATE_ACTIVE`，私有查询自动恢复。
5. 再启动官方 POS：第一条官方 `$` 立即转发并恢复官方优先。
6. 分别关闭占用对应端口的 POS，运行“测试官方秤通道”和“测试私有秤通道”，验证两条端到端回包。
7. 重启 Windows：虚拟配对保持存在，服务自动启动；无需再次初始化。
8. USB 转串口重新分配 COM 号时：服务只有在保存的硬件身份唯一匹配时才自动更新；多个相同设备时拒绝猜测并报告错误。

## 日常操作

- “查看桥接服务状态”：只读命名管道，不打开串口。
- “检查虚拟端口配对”：只执行 `setupc list`，不创建或删除。
- “启动服务”：服务已安装但停止时使用。
- “停止服务”：维护、重新测试物理秤或准备删除时使用。
- “生成诊断”：写入 `data/scale_bridge_diagnosis.json`，包含配置、设备身份、所有串口、配对、服务状态和所有权清单。
- “初始化 / 修复”：幂等操作；不会重复创建已有正确配对。
- 修改任一虚拟端口后不要只点“保存桥接配置”，应直接点“初始化 / 修复”。程序会创建新的所需配对并只清理本产品所有权清单中仍精确匹配的旧配对；把支付两端同时清空也会安全移除原来由本产品创建的支付配对。

## 删除桥接功能

1. 点击“删除桥接功能”。
2. 第一次确认后，程序会停止并删除本产品记录的服务，只删除所有权清单中精确匹配的配对，再删除 `data/scale_bridge.json`。
3. 若配对的序号或两端名称已被外部工具改动，程序会停止并拒绝删除，不会猜测。
4. 第二次对话框可选择是否同时卸载 com0com：
   - 只有驱动由本产品安装；
   - 且系统中已没有任何 com0com 配对；
   - 且能找到系统登记的精确卸载命令；
   - 三项同时满足才会卸载。
5. 删除过程不会修改私有 POS、官方 POS、收钱吧或其他业务设置，不会删除真实串口、CH340/CH341/WCH 驱动，也不会批量操作 Windows Ports 设备类。

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

## Windows 7 x64 安全边界

- Python 固定为 3.8 兼容环境；PyQt5、pyserial、pywin32 与 PyInstaller 都使用 Win7 可运行版本构建。
- 只使用已核验的 Win7 x64 签名 com0com 安装包。
- 禁止 SPSniff、Ports 类 UpperFilters、测试签名模式、`nointegritychecks`、批量删除 OEM INF 或真实串口驱动。
- 队列有容量上限，断线重连会丢弃旧查询，不向重连后的电子秤重放历史命令。
- 服务配置、所有权清单和诊断报告与现有 POS 业务配置完全分离。

## 尚需在目标收银机执行的实机验收

代码测试可以验证协议、仲裁、配对规划、冲突保护、服务命令状态机和安全删除逻辑，但驱动安装、Windows SCM、真实 COM 设备和 DIBAL 硬件必须在目标 Windows 7 x64 收银机按“初始化后的验收”逐项实测。开发机不会自动执行这些系统级操作。
