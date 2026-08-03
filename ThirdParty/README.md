# Local Windows deployment dependencies

Most files in this directory are intentionally excluded from Git for executable
archives and driver installers. The store-approved Shouqianba PC assistant is
the exception: it is bundled and exposed from the POS settings page as a
verified, operator-initiated download. The POS never installs it silently.

Current local files copied from the deployment desktop:

| Component | Local path | Purpose |
| --- | --- | --- |
| com0com 3.0.0.0 Win7 x64 signed | `com0com/Setup_com0com_v3.0.0.0_W7_x64_signed.exe` | Creates persistent virtual COM pairs. |
| hub4com 2.1.0.0 | `hub4com/hub4com.exe` | Diagnostic/manual multiplexer only. It is **not** used for ScaleBridge arbitration. |
| 收钱吧 PC 助手 v4.0.4 | `shouqianba/PC收款安装包v4.0.4.exe` | 从“系统设置 → 收钱吧插件”复制到桌面后，由门店人员手动安装。 |

The copied com0com installer has SHA-256
`26486B28604B49A9008C54FEB11B9ECE0008A8287EE5CAF0BCF2A62F4317128F`.

Do not install a driver automatically from the POS application. Installation,
repair and removal require an elevated maintenance action and an explicit
operator confirmation.

The bundled Shouqianba installer has SHA-256
`666EFBA745C7D20D33C22B65E765B027D431E32B7C8CAA4BF8B65A86AD6F15AC`.
