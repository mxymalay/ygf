# ScaleBridge（Windows 7 x64）部署与维护

ScaleBridge 是独立的 Windows 服务：它是**唯一**打开物理电子秤串口的进程。官方 POS 和私有 POS 仅打开自己对应的虚拟端口，因此两边不会争抢 `COM1`。

已由现场抓包确认的 DIBAL ACS-G315 参数是 `9600 / 8N1 / DTR=开 / RTS=关`。查询报文为 ASCII `$`（`24`），秤回 `000.402\r` 这类以 kg 表示的原始回包。服务不改写回包，原样广播给两个 POS。

## 推荐端口拓扑

| 用途 | POS/插件打开的端口 | 服务/对端 |
| --- | --- | --- |
| 物理秤 | 无 | 现场识别到的物理端口（当前为 `COM1`） |
| 官方 POS | `COM2` | `CNCB0` |
| 私有 POS | `COM3` | `CNCB1` |
| 收钱吧 / 私有支付插件 | 在“收钱吧插件”页配置（示例 `COM10`） | 可配置对端（示例 `COM11`） |

`COM2 ↔ CNCB0`、`COM3 ↔ CNCB1` 的建对形式来自随附 hub4com 2.1.0.0 的说明。服务打开的是 `CNCB0/CNCB1`，官方和私有 POS 分别打开 `COM2/COM3`。

## 一次性维护步骤（必须管理员权限）

1. 验证现场驱动包哈希，并人工安装 `ThirdParty/com0com/Setup_com0com_v3.0.0.0_W7_x64_signed.exe`。应用程序不会自动安装驱动。
2. 在 com0com 的 Setup Command Prompt 中创建并核对配对。例如：

   ```text
   install 0 PortName=COM2,EmuBR=yes -
   install 1 PortName=COM3,EmuBR=yes -
   ```

   然后使用 `list` 核对另一端确实是 `CNCB0`、`CNCB1`。若使用支付插件对接，支付对必须按“收钱吧插件”页当前配置的端口建立；`COM10 ↔ COM11` 只是示例，不是固定要求。
3. 复制 `data/scale_bridge.example.json` 为 `data/scale_bridge.json`，填入经核对后的物理秤端口与配对端口。设备身份字段应在部署诊断时保存；设备更换/COM 号变化时只有唯一匹配才会自动重绑，多个匹配会拒绝猜测。
4. 把官方 POS 配为 `COM2`，私有 POS 配为 `COM3`。私有 POS 的 `scale_source` 必须为 `com`；它不应再读取官方日志作为依赖。
   收钱吧端口继续在“收钱吧插件”页调整；桥接区的支付端口只用于核对可选的支付虚拟端口配对，不会覆盖该设置。
5. 以管理员身份将服务注册一次：

   ```text
   python -m scale_bridge.service install --startup auto
   python -m scale_bridge.service start
   ```

   日常开机由 Windows 服务启动，**不**重复运行安装程序或创建端口。

## 验收与诊断

在维护终端中运行：

```text
python -m scale_bridge.cli check-pairs
python -m scale_bridge.cli status
```

`status` 仅读取本机命名管道 `\\.\pipe\YgfScaleBridgeStatus`，不会打开物理串口。维护时可在两个 POS 都关闭的情况下使用：

```text
python -m scale_bridge.cli probe --port COM3
```

它只会从虚拟端口发送一次 `$`，回显原始 hex/ASCII；不允许直接探测物理串口。若官方 POS 在最近 1 秒内仍发送 `$`，服务将让官方通道优先，抑制私有端的 `$`，但仍向双方广播秤的原始回包。

## 安全与回退

- 串口只由服务打开一次；POS 与调试工具不能直接打开物理秤口。
- 队列是有界的，服务重连会丢弃旧查询而非向新连接重放。
- 重连采用 1 秒到 10 秒退避；状态中会显示模式、最近重量、抑制次数、异常帧和最后错误。
- 禁止用 SPSniff、UpperFilters 或禁用驱动签名等方式解决串口问题。
- 移除服务前先停止服务；桥接配置与现有 POS 设置相互独立。
