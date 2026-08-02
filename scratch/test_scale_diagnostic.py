import sys
import time
import serial
import serial.tools.list_ports

def diagnose():
    print("=" * 60)
    print("      电子秤 串口诊断与探针测试工具")
    print("=" * 60)

    ports = [p.device for p in serial.tools.list_ports.comports()]
    print(f"[*] 检测到当前系统可用串口: {ports}")

    if not ports:
        print("[!] 错误：未检测到任何可用 COM 串口！")
        return

    baudrates = [9600, 4800, 2400, 19200, 115200]
    probe_cmds = [
        ("被动监听(静默)", None),
        ("发送 W\\r\\n", b"W\r\n"),
        ("发送 ENQ(\\x05)", b"\x05"),
        ("发送 \\x0201\\x03", b"\x0201\x03"),
        ("发送 01\\r\\n", b"01\r\n"),
        ("发送 R\\r\\n", b"R\r\n"),
    ]

    for port in ports:
        print(f"\n--------------------------------------------------")
        print(f"开始测试串口: {port}")
        print(f"--------------------------------------------------")

        for baud in baudrates:
            try:
                ser = serial.Serial(
                    port=port,
                    baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.6
                )
                ser.dtr = True
                ser.rts = True

                for cmd_name, cmd_bytes in probe_cmds:
                    if cmd_bytes:
                        try:
                            ser.write(cmd_bytes)
                            ser.flush()
                        except Exception as e:
                            pass

                    time.sleep(0.2)
                    raw_data = ser.read(128)

                    if raw_data:
                        hex_str = raw_data.hex(' ').upper()
                        ascii_str = raw_data.decode('ascii', errors='ignore').strip()
                        print(f"  [SUCCESS] {port} | 波特率 {baud} | 模式: {cmd_name}")
                        print(f"    HEX 数据 : {hex_str}")
                        print(f"    ASCII文本: {repr(ascii_str)}")
                        ser.close()
                        return
                ser.close()
            except serial.SerialException as se:
                print(f"  [X] 无法打开 {port} (波特率 {baud}): {se}")
                break
            except Exception as e:
                print(f"  [X] {port} 测试出错: {e}")

    print("\n[!] 所有串口探针测试完毕。未能在任何端口捕获到返回数据。")

if __name__ == "__main__":
    diagnose()
