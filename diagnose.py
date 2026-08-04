"""
远程硬件诊断脚本
─────────────────────────────────────
在店内电脑上运行此脚本，自动检测：
  1. 所有 COM 端口
  2. 所有 Windows 打印机
  3. 尝试读取称重秤原始数据
  4. 检测 Xprinter 打印机状态

运行方式: python diagnose.py
输出结果保存在 data/diagnosis_report.txt
"""
import os
import sys
import time
import json
from datetime import datetime

REPORT_LINES = []


def log(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('gbk', errors='replace').decode('gbk'))
    REPORT_LINES.append(msg)


def divider(title: str = ""):
    line = f"\n{'=' * 50}"
    if title:
        line += f"\n  {title}\n{'=' * 50}"
    log(line)


def scan_com_ports():
    """扫描所有 COM 端口"""
    divider("1. COM 端口扫描")
    try:
        import serial.tools.list_ports
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            log("  ⚠ 未发现任何 COM 端口")
            return []

        for p in ports:
            log(f"  端口: {p.device}")
            log(f"    描述: {p.description}")
            log(f"    硬件ID: {p.hwid}")
            if p.manufacturer:
                log(f"    厂商: {p.manufacturer}")
            if p.product:
                log(f"    产品: {p.product}")
            if p.serial_number:
                log(f"    序列号: {p.serial_number}")
            log("")
        return ports
    except ImportError:
        log("  ❌ pyserial 未安装，请运行: pip install pyserial")
        return []


def scan_printers():
    """扫描 Windows 打印机"""
    divider("2. Windows 打印机扫描")
    try:
        import win32print
        default = win32print.GetDefaultPrinter()
        log(f"  默认打印机: {default}")
        log("")

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = win32print.EnumPrinters(flags, None, 2)
        for printer in printers:
            name = printer['pPrinterName']
            status = printer.get('Status', 0)
            port = printer.get('pPortName', '?')
            driver = printer.get('pDriverName', '?')
            marker = " <-- [默认]" if name == default else ""
            log(f"  打印机: {name}{marker}")
            log(f"    端口: {port}")
            log(f"    驱动: {driver}")
            log(f"    状态码: {status} ({'就绪' if status == 0 else '异常'})")
            log("")
        return printers
    except ImportError:
        log("  ❌ pywin32 未安装，请运行: pip install pywin32")
        log("  尝试使用 wmic 命令获取打印机列表...")
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "printer", "get", "Name,PortName,DriverName,Default"],
                capture_output=True, text=True, timeout=10
            )
            log(result.stdout)
        except Exception as e:
            log(f"  wmic 也失败了: {e}")
        return []


def try_read_scale(port_name: str, baudrate: int = 9600, duration: int = 5):
    """尝试从指定 COM 端口读取数据"""
    divider(f"3. 尝试读取 {port_name} (波特率 {baudrate})")
    try:
        import serial
        ser = serial.Serial(
            port=port_name,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1
        )
        log(f"  ✅ 成功打开 {port_name}")
        log(f"  正在读取 {duration} 秒的数据...")
        log("")

        start = time.time()
        lines_read = 0
        while time.time() - start < duration:
            if ser.in_waiting > 0:
                raw = ser.readline()
                hex_str = raw.hex(' ')
                try:
                    ascii_str = raw.decode('ascii', errors='replace').strip()
                except Exception:
                    ascii_str = "(无法解码)"

                log(f"  [HEX] {hex_str}")
                log(f"  [ASC] {ascii_str}")
                log("")
                lines_read += 1
            else:
                time.sleep(0.1)

        if lines_read == 0:
            log("  ⚠ 未收到任何数据")
            log("  可能原因:")
            log("    - 秤未开机")
            log("    - 波特率不对 (尝试 4800)")
            log("    - 秤未设置为连续发送模式")
            log("    - 此端口不是秤的端口")
            log("    - 端口被其他程序占用")
        else:
            log(f"  共读取 {lines_read} 行数据")

        ser.close()
        return lines_read

    except serial.SerialException as e:
        if "PermissionError" in str(e) or "Access" in str(e):
            log(f"  ⚠ 端口 {port_name} 被占用！")
            log(f"    这可能就是公司收银系统正在使用的端口")
            log(f"    错误: {e}")
        else:
            log(f"  ❌ 无法打开 {port_name}: {e}")
        return -1
    except Exception as e:
        log(f"  ❌ 读取失败: {e}")
        return -1


def system_info():
    """收集系统信息"""
    divider("0. 系统信息")
    import platform
    log(f"  操作系统: {platform.platform()}")
    log(f"  Python: {platform.python_version()}")
    log(f"  架构: {platform.machine()}")
    log(f"  电脑名: {platform.node()}")
    log(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def main():
    log("╔══════════════════════════════════════╗")
    log("║  杨国福麻辣烫 · 硬件诊断工具 v1.0   ║")
    log("╚══════════════════════════════════════╝")

    system_info()
    ports = scan_com_ports()
    scan_printers()

    # 尝试读取每个 COM 端口
    if ports:
        for p in ports:
            for baud in [9600, 4800]:
                result = try_read_scale(p.device, baud, duration=3)
                if result > 0:
                    log(f"\n  >>> 发现数据! {p.device} @ {baud} bps 可能是称重秤!")
                    break
                elif result == -1 and "占用" in "\n".join(REPORT_LINES[-5:]):
                    log(f"\n  >>> {p.device} 被占用 -- 很可能是公司系统使用的称重端口!")
                    break

    # 保存报告
    divider("诊断完成")
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    report_path = os.path.join(data_dir, "diagnosis_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT_LINES))
    log(f"\n  报告已保存: {report_path}")
    log("  请将此文件发送给开发者。")

    input("\n按 Enter 键退出...")


if __name__ == "__main__":
    main()
