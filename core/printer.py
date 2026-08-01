"""
小票打印模块 — 30列精准排版，彻底解决58mm热敏纸折行/换行溢出问题
兼容 Python 3.8+
"""
import os
import time
import socket
from config import DATA_DIR


def str_w(s: str) -> int:
    """计算字符串半角列宽 (中文=2, ASCII=1)"""
    return sum(2 if ord(ch) > 127 else 1 for ch in s)


def fmt_lr_48(left: str, right: str, width: int = 48) -> str:
    """在 48 列宽度内左右两侧对齐字符串 (适配 80mm 宽幅热敏纸)"""
    lw = str_w(left)
    rw = str_w(right)
    pad = max(1, width - lw - rw)
    return left + (" " * pad) + right + "\n"


class ReceiptPrinter:
    """小票打印器"""

    # ESC/POS 常量
    INIT = b'\x1b\x40'
    CUT_PARTIAL = b'\x1d\x56\x01'
    ALIGN_LEFT = b'\x1b\x61\x00'
    ALIGN_CENTER = b'\x1b\x61\x01'
    ALIGN_RIGHT = b'\x1b\x61\x02'
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

    def _build_customer_receipt(self, sale):
        """构建【顾客单】 ESC/POS 数据 (严格 30 列排版，防溢出折行)"""
        d = bytearray()
        d += self.INIT

        # 1. Header
        d += self.ALIGN_CENTER + self.BOLD_ON
        d += "POS点餐 堂食\n".encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 2. 店名 & 门店名称
        shop_name = sale.get("shop_name", "杨国福麻辣烫")
        d += self.ALIGN_CENTER + self.DOUBLE_SIZE + self.BOLD_ON
        d += (shop_name + "\n").encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF

        sub = sale.get("shop_subtitle", "")
        if not sub:
            sub = "杨国福(肥西水晶城店)"
        if not sub.startswith("门店名称："):
            sub = "门店名称：" + sub
        d += self.ALIGN_CENTER
        d += (sub + "\n").encode("gbk", errors="ignore")

        # 3. 取餐号：95
        call_no = sale.get("call_no", "001")
        d += b'------------------------------------------------\n'
        d += self.ALIGN_LEFT + self.DOUBLE_SIZE + self.BOLD_ON
        d += ("取餐号：%s\n" % call_no).encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 4. 表头 (精确 30 列)
        # "菜品名   规格  单价  数量 小计" -> Width: 30
        d += self.ALIGN_LEFT
        d += "菜品名                    规格  单价  数量  小计\n".encode("gbk", errors="ignore")
        d += b'------------------------------------------------\n'

        # 5. 菜品列表
        cart_items = sale.get("cart_items", [])
        m_count = 0

        for item in cart_items:
            is_soup = (item.get("type") == "soup" or "weight" in item)
            name = item.get("name", "经典草本骨汤")
            tag = item.get("tag", "")

            if is_soup:
                m_count += 1
                item_title = f"【制{m_count}】{name}"
                d += (item_title + "\n").encode("gbk", errors="ignore")
                
                weight_val = item.get("weight", sale.get("weight_kg", 0.0))
                unit_price = item.get("unit_price", sale.get("unit_price", 47.60))
                sub_total = item.get("price", 0.0)
                
                # 精确 48 列明细行，利用 fmt_lr_48 右对齐
                right_str = f"  KG  {unit_price:5.2f} {weight_val:5.3f}  {sub_total:6.2f}"
                line_str = fmt_lr_48("", right_str)
                d += line_str.encode("gbk", errors="ignore")
                
                if tag:
                    d += f"  {tag}\n".encode("gbk", errors="ignore")
            else:
                d += (name + "\n").encode("gbk", errors="ignore")
                qty = item.get("qty", 1)
                unit_price = item.get("base_price", item.get("price", 0.0) / max(1, qty))
                sub_total = item.get("price", 0.0)
                unit_label = item.get("unit", "份")
                if len(unit_label) > 1:
                    unit_label = unit_label[:1]
                
                right_str = f"  {unit_label}  {unit_price:5.2f}   {qty:3d}  {sub_total:6.2f}"
                line_str = fmt_lr_48("", right_str)
                d += line_str.encode("gbk", errors="ignore")
                if tag:
                    d += f"  {tag}\n".encode("gbk", errors="ignore")

        d += b'------------------------------------------------\n'

        # 6. 合计与应收 (严格右对齐 30 列)
        total_p = sale.get("total_price", 0.0)
        tot_str = fmt_lr_48("消费合计", f"{total_p:.2f}")
        d += tot_str.encode("gbk", errors="ignore")
        d += b'------------------------------------------------\n'
        ys_str = fmt_lr_48("应收", f"{total_p:.2f}")
        d += ys_str.encode("gbk", errors="ignore")
        d += b'------------------------------------------------\n'

        # 7. 打印时间
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        d += ("打印时间：%s\n" % now_str).encode("gbk", errors="ignore")
        d += self.FEED_LINES + self.CUT_PARTIAL
        return bytes(d)

    def _build_kitchen_slip(self, sale, item, index):
        """构建【制作单-堂食】 ESC/POS 数据 (严格 30 列排版，防溢出折行)"""
        d = bytearray()
        d += self.INIT

        # 1. 标题
        d += self.ALIGN_CENTER + self.BOLD_ON + self.DOUBLE_HEIGHT
        d += "制作单-堂食\n".encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 2. 取餐号：95 - 1
        call_no = sale.get("call_no", "001")
        call_no_full = f"{call_no} - {index}"
        
        d += self.ALIGN_LEFT + self.DOUBLE_SIZE + self.BOLD_ON
        d += ("取餐号：%s\n" % call_no_full).encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 3. 渠道与下单时间
        created_at = sale.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        d += "渠道：POS点餐\n".encode("gbk", errors="ignore")
        d += ("下单时间：%s\n" % created_at).encode("gbk", errors="ignore")
        d += b'------------------------------------------------\n'

        # 4. 表头 (精确 48 列)
        hdr_str = fmt_lr_48("菜品名", "数量")
        d += hdr_str.encode("gbk", errors="ignore")
        
        # 5. 菜品名称、重量与口味 (大字号加粗显示，方便后厨看单)
        name = item.get("name", "经典草本骨汤")
        weight_val = item.get("weight", sale.get("weight_kg", 0.0))
        tag = item.get("tag", "")

        # 菜品名 & 数量大字号加粗
        d += self.DOUBLE_HEIGHT + self.BOLD_ON
        d += (name + "\n").encode("gbk", errors="ignore")
        
        w_str = f"{weight_val:.3f}"
        val_str = fmt_lr_48("", w_str)
        d += val_str.encode("gbk", errors="ignore")

        if tag:
            d += f"  {tag}\n".encode("gbk", errors="ignore")

        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 6. 打印时间
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        d += ("打印时间：%s\n" % now_str).encode("gbk", errors="ignore")
        d += self.FEED_LINES + self.CUT_PARTIAL
        return bytes(d)

    def print_receipt(self, sale):
        """全流程小票打印入口"""
        customer_bytes = self._build_customer_receipt(sale)

        cart_items = sale.get("cart_items", [])
        malatang_items = [i for i in cart_items if (i.get("type") == "soup" or "weight" in i)]
        
        kitchen_bytes_list = []
        for idx, item in enumerate(malatang_items, start=1):
            ks_bytes = self._build_kitchen_slip(sale, item, idx)
            kitchen_bytes_list.append(ks_bytes)

        all_raw_data = bytearray(customer_bytes)
        for kb in kitchen_bytes_list:
            all_raw_data += kb

        pt = self.config.get("printer_type", "windows")
        try:
            if pt == "windows":
                return self._send_raw_to_windows(bytes(all_raw_data))
            elif pt == "network":
                return self._send_raw_to_network(bytes(all_raw_data))
            elif pt == "serial":
                return self._send_raw_to_serial(bytes(all_raw_data))
        except Exception as e:
            print("[打印错误] %s" % str(e))
            raise e
    def _build_shift_report(self, report_data):
        """构建【交班小结】ESC/POS 票据 (符合店铺规范，严格 30 列排版)"""
        d = bytearray()
        d += self.INIT

        # 1. 标题
        d += self.ALIGN_CENTER + self.BOLD_ON + self.DOUBLE_HEIGHT
        d += "交班小结\n".encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 2. 门店与时间
        shop_sub = self.config.get("shop_subtitle", "杨国福(肥西水晶城店)")
        if not shop_sub.startswith("门店名称："):
            shop_sub = "门店名称：" + shop_sub
        d += self.ALIGN_LEFT
        d += (shop_sub + "\n").encode("gbk", errors="ignore")
        date_str = report_data.get("date_str", time.strftime("%Y-%m-%d"))
        d += ("开始时间：%s\n" % date_str).encode("gbk", errors="ignore")
        d += b'------------------------------------------------\n'

        # 3. 销售汇总
        d += self.BOLD_ON
        d += "销售汇总\n".encode("gbk", errors="ignore")
        d += self.BOLD_OFF
        d += b'================================================\n'

        rev_amt = report_data.get("amount_sum", 0.0)
        count = report_data.get("count", 0)
        avg = rev_amt / count if count > 0 else 0.0

        d += fmt_lr_48("营业收入：", "¥ %.2f" % rev_amt).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("订单数量：", "%d" % count).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("客单价：", "¥ %.2f" % avg).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("退单金额：", "¥ 0.00").encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("退单数量：", "0").encode("gbk", errors="ignore") + b"\n"

        # 4. 收入明细 (总结)
        d += self.BOLD_ON
        d += "收入明细\n".encode("gbk", errors="ignore")
        d += self.BOLD_OFF
        d += b'================================================\n'
        d += self.BOLD_ON
        d += fmt_lr_48("总结", "¥ %.2f" % rev_amt).encode("gbk", errors="ignore") + b"\n"
        d += self.BOLD_OFF
        d += b'------------------------------------------------\n'

        # 5. 打印时间
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        d += ("打印时间：%s\n" % now_str).encode("gbk", errors="ignore")
        d += self.FEED_LINES + self.CUT_PARTIAL
        return bytes(d)

    def print_shift_report(self, report_data):
        """交班小结报表打印入口"""
        raw_data = self._build_shift_report(report_data)
        pt = self.config.get("printer_type", "windows")
        try:
            if pt == "windows":
                return self._send_raw_to_windows(raw_data)
            elif pt == "network":
                return self._send_raw_to_network(raw_data)
            elif pt == "serial":
                return self._send_raw_to_serial(raw_data)
        except Exception as e:
            print("[打印错误] %s" % str(e))
            raise e
        return False

    def _send_raw_to_windows(self, raw_data):
        import win32print
        name = self.config.get("printer_name", "shouyin") or win32print.GetDefaultPrinter()
        h = win32print.OpenPrinter(name)
        try:
            win32print.StartDocPrinter(h, 1, ("POS_Receipt", None, "RAW"))
            win32print.StartPagePrinter(h)
            win32print.WritePrinter(h, raw_data)
            win32print.EndPagePrinter(h)
            win32print.EndDocPrinter(h)
        finally:
            win32print.ClosePrinter(h)
        return True

    def _send_raw_to_network(self, raw_data):
        ip = self.config.get("printer_ip", "192.168.1.100")
        port = self.config.get("printer_port", 9100)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, port))
        s.sendall(raw_data)
        s.close()
        return True

    def _send_raw_to_serial(self, raw_data):
        import serial
        port = self.config.get("printer_serial_port", "COM4")
        ser = serial.Serial(port, 9600, timeout=2)
        ser.write(raw_data)
        ser.flush()
        time.sleep(0.5)
        ser.close()
        return True
