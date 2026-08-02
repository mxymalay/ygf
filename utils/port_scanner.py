"""
串口与打印机扫描工具 — 用于探测店内电脑硬件
兼容 Python 3.8+
"""


def scan_ports():
    """扫描所有可用的串口，返回端口信息列表"""
    results = []
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        for p in ports:
            results.append({
                "device": p.device,
                "description": p.description,
                "hwid": p.hwid,
                "manufacturer": p.manufacturer or "",
                "product": p.product or "",
                "serial_number": p.serial_number or "",
            })
    except ImportError:
        pass
    return results


def scan_printers():
    """扫描 Windows 打印机列表 (结合 Qt API 与 Win32 API)"""
    printers = []
    try:
        from PyQt5.QtPrintSupport import QPrinterInfo
        names = QPrinterInfo.availablePrinterNames()
        if names:
            return list(names)
    except Exception:
        pass

    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printer_list = win32print.EnumPrinters(flags, None, 1)
        for _, _, name, _ in printer_list:
            if name and name not in printers:
                printers.append(name)
    except Exception:
        pass
    return printers


if __name__ == "__main__":
    print("=== 串口扫描结果 ===")
    for port in scan_ports():
        print("  %s: %s" % (port['device'], port['description']))
    print()
    print("=== 打印机扫描结果 ===")
    for name in scan_printers():
        print("  %s" % name)
