"""
串口扫描工具 — 用于远程探测店内电脑的硬件端口
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
        # pyserial 未安装时模拟
        results.append({
            "device": "COM3",
            "description": "USB-SERIAL CH340 (COM3) [模拟]",
            "hwid": "USB VID:PID=1A86:7523",
            "manufacturer": "wch.cn",
            "product": "",
            "serial_number": "",
        })
        results.append({
            "device": "COM4",
            "description": "USB Printing Support (COM4) [模拟]",
            "hwid": "USB VID:PID=0483:5740",
            "manufacturer": "",
            "product": "",
            "serial_number": "",
        })
    return results


def scan_printers():
    """扫描 Windows 打印机列表"""
    printers = []
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printer_list = win32print.EnumPrinters(flags, None, 1)
        for _, _, name, _ in printer_list:
            printers.append(name)
    except ImportError:
        printers = ["POS-58 [模拟]", "GP-L80160 [模拟]"]
    return printers


if __name__ == "__main__":
    print("=== 串口扫描结果 ===")
    for port in scan_ports():
        print("  %s: %s" % (port['device'], port['description']))
        print("    HWID: %s" % port['hwid'])
        if port['manufacturer']:
            print("    厂商: %s" % port['manufacturer'])
    print()
    print("=== 打印机扫描结果 ===")
    for name in scan_printers():
        print("  %s" % name)
