"""
杨国福麻辣烫 · 电子秤串口诊断工具
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
    print("      杨国福麻辣烫 · 电子秤全串口硬件诊断工具 v2.0")
    print("=" * 65)

    # 1. 扫描串口
    ports = list(serial.tools.list_ports.comports())
    print("\n[1] 正在扫描电脑全部可用 COM 串口...")
    if not ports:
        print("    [!] 未检测到任何可用 COM 串口！请检查电子秤数据线或 VSPE 设置。")
        return

    available_devices = [p.device for p in ports]
    for p in ports:
        print("    -> [%s] %s (%s)" % (p.device, p.description, p.hwid))

    print("\n[2] 开始逐个轮询扫描所有串口数据...")
    baudrates = [9600, 4800, 2400, 19200]
    query_cmds = [b"\x05", b"W\r\n", b"Q\r\n", b"S\r\n", b"P\r\n"]

    found_port = None

    for port_name in available_devices:
        print("\n" + "=" * 50)
        print(" 🔍 正在测试端口: %s" % port_name)
        print("=" * 50)

        for baud in baudrates:
            try:
                ser = serial.Serial(port_name, baudrate=baud, timeout=0.3)
                print("  -> 尝试 %s (%d bps)... 打开成功，监听中..." % (port_name, baud))

                received_any = False
                start_t = time.time()

                # 被动监听 1.5 秒
                while time.time() - start_t < 1.5:
                    if ser.in_waiting > 0:
                        raw = ser.read(ser.in_waiting)
                        received_any = True
                        hex_str = raw.hex(' ')
                        asc_str = raw.decode("ascii", errors="ignore").strip()
                        print("  [🎉 收到数据] HEX: %s | ASCII: %s" % (hex_str, asc_str))
                    time.sleep(0.1)

                # 主动发送命令探针
                if not received_any:
                    for cmd in query_cmds:
                        try:
                            ser.write(cmd)
                            time.sleep(0.2)
                            if ser.in_waiting > 0:
                                raw = ser.read(ser.in_waiting)
                                received_any = True
                                hex_str = raw.hex(' ')
                                asc_str = raw.decode("ascii", errors="ignore").strip()
                                print("  [🎉 命令 %r 响应] HEX: %s | ASCII: %s" % (cmd, hex_str, asc_str))
                                break
                        except Exception:
                            pass

                ser.close()
                if received_any:
                    found_port = (port_name, baud)
                    print("\n" + "★" * 50)
                    print("  【匹配成功！】硬件位于 %s (波特率 %d bps)" % (port_name, baud))
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
        print(" 没有任何串口接收到数据。排查建议：")
        print(" 1. 【按键测试】：请放上食材后，按一下电子秤面板上的【小票】/【打印】或【确认】按键！")
        print(" 2. 【VSPE 分流】：如果公司旧软件正在运行，旧软件会独占物理 COM1。")
        print("    请查看 VSPE 里分流出来的虚拟串口名称（如 COM3），并在软件【系统设置】里选择该虚拟串口！")
    print("=" * 65)


if __name__ == "__main__":
    test_scale()
    input("\n按回车键退出诊断...")
