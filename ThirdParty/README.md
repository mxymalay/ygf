# Local Windows deployment dependencies

This directory is intentionally excluded from Git for executable archives and
driver installers. The installer must obtain the exact, verified files from the
deployment package rather than downloading or replacing drivers at runtime.

Current local files copied from the deployment desktop:

| Component | Local path | Purpose |
| --- | --- | --- |
| com0com 3.0.0.0 Win7 x64 signed | `com0com/Setup_com0com_v3.0.0.0_W7_x64_signed.exe` | Creates persistent virtual COM pairs. |
| hub4com 2.1.0.0 | `hub4com/hub4com.exe` | Diagnostic/manual multiplexer only. It is **not** used for ScaleBridge arbitration. |

The copied com0com installer has SHA-256
`26486B28604B49A9008C54FEB11B9ECE0008A8287EE5CAF0BCF2A62F4317128F`.

Do not install a driver automatically from the POS application. Installation,
repair and removal require an elevated maintenance action and an explicit
operator confirmation.
