"""
收钱吧 PC收款助手 串口推送模块 (非阻塞异步版)
用于向收钱吧 PC 客户端（虚拟串口/串口截取模式）发送收款金额。
支持 QA标记 (如 QA12.50\\r\\n) 与 纯数字 (如 12.50\\r\\n) 模式。
采用后台 daemon 线程，绝不卡顿 POS 主界面！
PyQt5 + Python 3.8 兼容
"""
import serial
import serial.tools.list_ports
import threading
import logging

logger = logging.getLogger("ShouqianbaSender")


def get_available_com_ports():
    """获取本机可用的 COM 串口列表"""
    ports = []
    try:
        for p in serial.tools.list_ports.comports():
            ports.append(p.device)
    except Exception as e:
        logger.error(f"扫描 COM 端口出错: {e}")
    return sorted(ports)


def _do_send_amount(amount: float, config: dict):
    """后台子线程实际发送串口逻辑"""
    enabled = config.get("shouqianba_enabled", True)
    if not enabled:
        return

    port = config.get("shouqianba_port", "COM3")
    baudrate = int(config.get("shouqianba_baudrate", 9600))
    fmt = config.get("shouqianba_format", "QA")  # "QA" 或 "FLOAT"

    if fmt == "QA":
        payload = f"QA{amount:.2f}\r\n"
    else:
        payload = f"{amount:.2f}\r\n"

    try:
        # write_timeout 设为 0.5 秒，避免打开无效 COM 端口阻塞
        with serial.Serial(port, baudrate=baudrate, timeout=0.5, write_timeout=0.5) as ser:
            ser.write(payload.encode("ascii"))
            ser.flush()
            logger.info(f"成功向收钱吧串口 {port} 发送金额: {payload.strip()}")
            print(f"[收钱吧推送] 成功推送到 {port}: {payload.strip()}")
    except Exception as e:
        logger.warning(f"推送金额到收钱吧串口 {port} 失败: {e}")
        print(f"[收钱吧推送] 端口 {port} 写入失败/未就绪 (不影响系统运行): {e}")


def send_shouqianba_amount(amount: float, config: dict):
    """
    非阻塞异步发送金额到收钱吧串口（完全不占用主线程，确保界面流畅）
    """
    t = threading.Thread(target=_do_send_amount, args=(amount, config), daemon=True)
    t.start()
