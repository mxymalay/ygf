"""
小票打印模块 — 支持 Windows驱动/网络/串口 打印方式
已增强：特大字号取餐叫号牌与附加加价明细打小票
兼容 Python 3.8+
"""
import os
import time
import socket
from config import DATA_DIR


class ReceiptPrinter:
    """小票打印器"""

    # ESC/POS 常量
    INIT = b'\x1b\x40'
    CUT_PARTIAL = b'\x1d\x56\x01'
    ALIGN_LEFT = b'\x1b\x61\x00'
    ALIGN_CENTER = b'\x1b\x61\x01'
    BOLD_ON = b'\x1b\x45\x01'
    BOLD_OFF = b'\x1b\x45\x00'
    FONT_SMALL = b'\x1b\x4d\x01'
    FONT_NORMAL = b'\x1b\x4d\x00'
    DOUBLE_HEIGHT = b'\x1d\x21\x01'
    DOUBLE_SIZE = b'\x1d\x21\x11'
    NORMAL_SIZE = b'\x1d\x21\x00'
    FEED_LINES = b'\x1b\x64\x04'

    def __init__(self, config):
        self.config = config

    def _fmt(self, sale):
        """提取格式化信息"""
        w = sale["weight_kg"]
        pu = sale.get("price_unit", "per_jin")
        if pu == "per_jin":
            return "%.2f 斤" % (w * 2), "元/斤"
        return "%.3f kg" % w, "元/公斤"

    def _build_receipt_data(self, sale):
        """构建 ESC/POS 小票数据"""
        d = bytearray()
        d += self.INIT

        # 店名
        d += self.ALIGN_CENTER + self.DOUBLE_SIZE + self.BOLD_ON
        d += sale.get("shop_name", "杨国福麻辣烫").encode("gbk", errors="ignore") + b'\n'
        d += self.NORMAL_SIZE + self.BOLD_OFF

        sub = sale.get("shop_subtitle", "")
        if sub:
            d += self.FONT_SMALL
            d += sub.encode("gbk", errors="ignore") + b'\n'
            d += self.FONT_NORMAL

        # 特大显眼叫号牌 (如果有)
        call_no = sale.get("call_no", "")
        if call_no:
            d += b'=' * 32 + b'\n'
            d += self.ALIGN_CENTER + self.DOUBLE_SIZE + self.BOLD_ON
            d += ("取餐叫号: # %s #\n" % call_no).encode("gbk", errors="ignore")
            d += self.NORMAL_SIZE + self.BOLD_OFF

        d += b'-' * 32 + b'\n'
        d += self.ALIGN_LEFT
        d += ("日期：%s\n" % sale['created_at']).encode("gbk", errors="ignore")
        d += ("单号：%s\n" % sale['sale_no']).encode("gbk", errors="ignore")
        d += b'-' * 32 + b'\n'

        wd, ul = self._fmt(sale)
        d += self.DOUBLE_HEIGHT
        d += ("重量：%s\n" % wd).encode("gbk", errors="ignore")
        d += ("单价：%.2f %s\n" % (sale['unit_price'], ul)).encode("gbk", errors="ignore")

        extra_fee = sale.get("extra_fee", 0.0)
        if extra_fee > 0:
            d += ("附加加价：+￥%.2f\n" % extra_fee).encode("gbk", errors="ignore")

        d += self.NORMAL_SIZE + b'-' * 32 + b'\n'

        # 应收总金额
        d += self.ALIGN_CENTER + self.DOUBLE_SIZE + self.BOLD_ON
        d += ("￥%.2f\n" % sale['total_price']).encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF

        # 底部再印一次叫号牌方便撕单
        if call_no:
            d += b'-' * 32 + b'\n'
            d += self.ALIGN_CENTER + self.DOUBLE_SIZE + self.BOLD_ON
            d += ("请凭此号 [# %s #] 取餐\n" % call_no).encode("gbk", errors="ignore")
            d += self.NORMAL_SIZE + self.BOLD_OFF

        d += b'-' * 32 + b'\n'
        d += self.ALIGN_CENTER + self.FONT_SMALL
        d += sale.get("receipt_footer", "谢谢惠顾！").encode("gbk", errors="ignore") + b'\n'
        d += self.FONT_NORMAL + self.FEED_LINES + self.CUT_PARTIAL
        return bytes(d)

    def print_receipt(self, sale):
        """打印小票入口"""
        pt = self.config.get("printer_type", "windows")
        try:
            if pt == "windows":
                return self._print_windows(sale)
            elif pt == "network":
                return self._print_network(sale)
            elif pt == "serial":
                return self._print_serial(sale)
        except Exception as e:
            print("[打印错误] %s" % str(e))
            raise e
        return False

    def _print_windows(self, sale):
        import win32print
        name = self.config.get("printer_name", "shouyin") or win32print.GetDefaultPrinter()
        data = self._build_receipt_data(sale)
        h = win32print.OpenPrinter(name)
        try:
            win32print.StartDocPrinter(h, 1, ("Receipt", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return True

    def _print_network(self, sale):
        ip = self.config.get("printer_ip", "192.168.1.100")
        port = self.config.get("printer_port", 9100)
        data = self._build_receipt_data(sale)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, port))
        s.sendall(data)
        s.close()
        return True

    def _print_serial(self, sale):
        import serial
        port = self.config.get("printer_serial_port", "COM4")
        data = self._build_receipt_data(sale)
        ser = serial.Serial(port, 9600, timeout=2)
        ser.write(data)
        ser.flush()
        time.sleep(0.5)
        ser.close()
        return True
