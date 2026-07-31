"""
杨国福麻辣烫 · 电子秤串口串口诊断工具
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
    print("=" * 60)
    print("      杨国福麻辣烫 · 电子秤串口诊断与检测工具 v1.0")
    print("=" * 60)

    # 1. 扫描串口
    ports = list(serial.tools.list_ports.comports())
    print("\n[1] 正在扫描电脑可用串口...")
    if not ports:
        print("    [!] 未检测到任何可用 COM 串口！请检查串口线或 VSPE 分流设置。")
        return

    for p in ports:
        print("    -> 找到串口: %s (%s)" % (p.device, p.description))

    target_port = "COM1"
    available_devices = [p.device for p in ports]
    if target_port not in available_devices:
        target_port = available_devices[0]

    print("\n[2] 开始测试目标串口: %s" % target_port)
    baudrates = [9600, 4800, 2400, 19200]
    query_cmds = [b"\x05", b"W\r\n", b"Q\r\n", b"S\r\n", b"P\r\n"]

    for baud in baudrates:
        print("\n--------------------------------------------------")
        print("  正在尝试波特率: %d bps..." % baud)
        print("--------------------------------------------------")
        try:
            ser = serial.Serial(target_port, baudrate=baud, timeout=0.5)
            print("  [OK] 串口 %s (%d) 打开成功！正在监听 3 秒..." % (target_port, baud))

            received_any = False
            start_t = time.time()

            # 先被动监听
            while time.time() - start_t < 2.5:
                if ser.in_waiting > 0:
                    raw = ser.read(ser.in_waiting)
                    received_any = True
                    hex_str = raw.hex(' ')
                    asc_str = raw.decode("ascii", errors="ignore").strip()
                    print("  [★ 被动收到数据] HEX: %s  | ASCII: %s" % (hex_str, asc_str))
                time.sleep(0.1)

            # 再主动发送查询指令测试
            if not received_any:
                print("  [i] 被动未收到数据，尝试主动发送查询指令 (ENQ / W\\r)...")
                for cmd in query_cmds:
                    ser.write(cmd)
                    time.sleep(0.3)
                    if ser.in_waiting > 0:
                        raw = ser.read(ser.in_waiting)
                        received_any = True
                        hex_str = raw.hex(' ')
                        asc_str = raw.decode("ascii", errors="ignore").strip()
                        print("  [★ 指令 %r 响应] HEX: %s | ASCII: %s" % (cmd, hex_str, asc_str))
                        break

            ser.close()
            if received_any:
                print("\n  [🎉 成功] 在 %d bps 波特率下成功接收到了电子秤数据！" % baud)
                return

        except Exception as e:
            print("  [X] 打开 %s (%d bps) 失败: %s" % (target_port, baud, str(e)))

    print("\n" * 2)
    print("=" * 60)
    print("【诊断排查结论与建议】")
    print("1. 如果程序提示 'Access is denied' (拒绝访问)：")
    print("   说明公司原 POS 系统正独占 COM1。请打开 VSPE (Virtual Serial Port Emulator)")
    print("   将物理 COM1 分流出一个虚拟端口 (如 COM3)，然后在软件里设置选择 COM3。")
    print("2. 如果串口打开成功但收不到数据：")
    print("   请按一下电子秤面板上的【小票】/【打印】/【确认】键，看数据是否发送！")
    print("=" * 60)


if __name__ == "__main__":
    test_scale()
    input("\n按回车键退出诊断...")
