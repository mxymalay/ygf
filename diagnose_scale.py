"""
杨国福麻辣烫 · 电子秤串口诊断工具 (含 DTR/RTS 硬件握手)
运行方法: python diagnose_scale.py
"""
import sys
import time

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("[X] 缺少 pyserial 库，请运行: pip install pyserial")
    sys.exit(1)


def test_scale():
    print("=" * 65)
    print("      杨国福麻辣烫 · 电子秤全串口硬件诊断工具 v3.0 (含 DTR/RTS 握手)")
    print("=" * 65)

    ports = list(serial.tools.list_ports.comports())
    print("\n[1] 正在扫描电脑全部可用 COM 串口...")
    if not ports:
        print("    [!] 未检测到任何可用 COM 串口！请检查电子秤数据线或 VSPE 设置。")
        return

    available_devices = [p.device for p in ports]
    for p in ports:
        print("    -> [%s] %s (%s)" % (p.device, p.description, p.hwid))

    print("\n[2] 开始逐个测试串口 (激活 RTS/DTR 光耦供电脚)...")
    baudrates = [9600, 4800, 2400, 19200]
    init_cmds = [b"\x05", b"\x0201\x03", b"W\r\n", b"\x0200\x03", b"Q\r\n"]

    found_port = None

    for port_name in available_devices:
        print("\n" + "=" * 50)
        print(" 🔍 正在测试端口: %s" % port_name)
        print("=" * 50)

        for baud in baudrates:
            try:
                ser = serial.Serial(port_name, baudrate=baud, timeout=0.3)
                # 关键：使能 DTR/RTS 给串口放大芯片/光耦器件供电
                try:
                    ser.dtr = True
                    ser.rts = True
                except Exception:
                    pass

                print("  -> 尝试 %s (%d bps) [RTS/DTR 已拉高]..." % (port_name, baud))

                received_any = False
                start_t = time.time()

                # 发送握手探针
                for cmd in init_cmds:
                    try:
                        ser.write(cmd)
                        time.sleep(0.15)
                        if ser.in_waiting > 0:
                            raw = ser.read(ser.in_waiting)
                            received_any = True
                            hex_str = raw.hex(' ')
                            asc_str = raw.decode("ascii", errors="ignore").strip()
                            print("  [🎉 握手响应 %r] HEX: %s | ASCII: %s" % (cmd, hex_str, asc_str))
                            break
                    except Exception:
                        pass

                # 监听后续数据
                if not received_any:
                    start_t = time.time()
                    while time.time() - start_t < 1.0:
                        if ser.in_waiting > 0:
                            raw = ser.read(ser.in_waiting)
                            received_any = True
                            hex_str = raw.hex(' ')
                            asc_str = raw.decode("ascii", errors="ignore").strip()
                            print("  [🎉 收到数据] HEX: %s | ASCII: %s" % (hex_str, asc_str))
                        time.sleep(0.1)

                ser.close()
                if received_any:
                    found_port = (port_name, baud)
                    print("\n" + "★" * 50)
                    print("  【匹配成功！】电子秤硬件位于 %s (波特率 %d bps)" % (port_name, baud))
                    print("★" * 50)
                    break

            except Exception as e:
                print("  [!] %s (%d bps) 打开失败: %s" % (port_name, baud, str(e)))

        if found_port:
            break

    print("\n" * 2)
    print("=" * 65)
    print("【诊断结果汇总】")
    if found_port:
        print(" 找到正确串口: %s (波特率 %d bps)" % (found_port[0], found_port[1]))
        print(" 请在软件【系统设置】中将串口选为 %s 并保存！" % found_port[0])
    else:
        print(" 任何串口均未收到响应。排查关键原因：")
        print(" 1. 【原 POS 软件占用】：如果杨国福专用软件正打开运行，它会独占锁死串口！")
        print("    请先关闭杨国福专用软件后，再测试本软件或诊断工具。")
        print(" 2. 【VSPE 软件】：如果两个软件要同时开，请确保 VSPE 在后台运行并分流串口。")
    print("=" * 65)


if __name__ == "__main__":
    test_scale()
    input("\n按回车键退出诊断...")
