"""
小票打印模块 — 可配置纸宽/列数的 ESC/POS 排版，兼容 58mm 与 80mm 热敏纸
兼容 Python 3.8+
"""
import os
import time
import socket
import unicodedata
from config import DATA_DIR
from core.payment_utils import payment_display_label


def str_w(s: str) -> int:
    """计算 ESC/POS 显示列宽（全角字符=2，半角字符=1）。"""
    width = 0
    for ch in str(s or ""):
        # East Asian Width 比 ``ord(ch) > 127`` 更准确，能正确处理全角
        # 标点和 Win7 上常见的窄拉丁字符。
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def fmt_lr_48(left: str, right: str, width: int = 48) -> str:
    """在指定列宽内左右两侧对齐字符串。"""
    lw = str_w(left)
    rw = str_w(right)
    pad = max(1, width - lw - rw)
    return left + (" " * pad) + right + "\n"


# 可编辑模板的最小语法：每行可用 [C]/[L]/[R] 指定对齐，
# [B] 加粗， [D] 双倍高度， [X] 双倍宽高， [Y] 三倍宽高；其余内容使用 {变量} 替换。
OFFICIAL_CUSTOMER_TEMPLATE = """[C][B]{shop_subtitle}
[L]{separator}
[L][B][X]{pickup_line}
[L]{separator}
[L]{table_header}
[L]{separator}
[L]{items}
[L]{separator}
[L][B]{total_line}
[L][B]{due_line}
[L][B][D]{paid_line}
[L]{separator}
[L]订单号：{order_id}
[L]订单时间：{time}
[L]{separator}
[L][B]加盟电话：{service_phone}"""
OFFICIAL_KITCHEN_TEMPLATE = """[L][B][Y]取餐号：{kitchen_call_no}
[L]{separator}
[L][B][X]{kitchen_title_line}
[L]{separator}
[L][B][X]{item_name}
[R][B][X]{weight}
[L][B][X]  {flavor}
[L]{separator}
[L]操作人：{operator}
[L]下单时间：{created_at}"""


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
    OPEN_DRAWER = b'\x1b\x70\x00\x3c\xff'

    def __init__(self, config):
        self.config = config
        self.last_error = ""

    def _line_width(self):
        """Return the configured printable columns, clamped to safe bounds."""
        try:
            return min(64, max(16, int(self.config.get("printer_chars_per_line", 48))))
        except (TypeError, ValueError):
            return 48

    def _separator(self, char=None):
        """Build a separator that never exceeds the configured paper width."""
        value = char if char is not None else self.config.get("printer_separator_char", "-")
        value = str(value or "-")[:1]
        if str_w(value) != 1:
            value = "-"
        return value * self._line_width() + "\n"

    def _feed_and_cut(self):
        try:
            feed_lines = min(12, max(0, int(self.config.get("printer_feed_lines", 4))))
        except (TypeError, ValueError):
            feed_lines = 4
        data = b"\x1b\x64" + bytes([feed_lines])
        if bool(self.config.get("printer_auto_cut_enabled", True)):
            data += self.CUT_PARTIAL
        return data

    @staticmethod
    def _copies(config, key, default=1):
        try:
            return min(20, max(0, int(config.get(key, default))))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _render_template(template, context, fallback=""):
        """Render user-editable template text without allowing bad fields to crash printing."""
        text = str(template if template is not None else fallback)
        if not text:
            text = fallback

        # 口味是可选项；没有选择时，模板中的口味整行不打印。
        if not str(context.get("flavor", "") or "").strip():
            text = "\n".join(line for line in text.splitlines() if "{flavor}" not in line)

        class _SafeContext(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        try:
            return text.format_map(_SafeContext(context))
        except (ValueError, KeyError):
            return text

    def _template_lines(self, template, context, fallback):
        rendered = self._render_template(template, context, fallback)
        return [line for line in rendered.splitlines() if line.strip()]

    def _template_profile(self):
        profile = str(self.config.get("printer_template_profile", "legacy") or "legacy").strip().lower()
        return profile if profile in ("legacy", "official_v2", "custom") else "legacy"

    @staticmethod
    def _fit_column(value, width, align="left"):
        """Fit one table cell to printable columns without breaking alignment."""
        text = str(value or "")
        result = ""
        used = 0
        for char in text:
            char_width = str_w(char)
            if used + char_width > width:
                break
            result += char
            used += char_width
        padding = " " * max(0, width - used)
        return padding + result if align == "right" else result + padding

    def _customer_table_widths(self):
        width = self._line_width()
        if width >= 44:
            return (20, 6, 7, 6, width - 39)
        # Keep a usable compact layout on 58mm paper as well.
        name_width = max(8, width - 20)
        return (name_width, 4, 5, 4, width - name_width - 13)

    def _customer_table_row(self, name, spec, unit_price, quantity, subtotal):
        widths = self._customer_table_widths()
        cells = (
            self._fit_column(name, widths[0]),
            self._fit_column(spec, widths[1]),
            self._fit_column(unit_price, widths[2], "right"),
            self._fit_column(quantity, widths[3], "right"),
            self._fit_column(subtotal, widths[4], "right"),
        )
        return "".join(cells)

    def _customer_table_header(self):
        return self._customer_table_row("名称", "规格", "单价", "数量", "小计")

    def _customer_item_lines(self, sale):
        """Return compact item rows used by the official/custom templates."""
        rows = []
        for item in sale.get("cart_items", []):
            is_soup = item.get("type") == "soup" or "weight" in item
            name = str(item.get("name", "经典草本骨汤") or "经典草本骨汤")
            if is_soup:
                unit_price = float(item.get("unit_price", sale.get("unit_price", 47.60)) or 0.0)
                weight = float(item.get("weight", sale.get("weight_kg", 0.0)) or 0.0)
                subtotal = float(item.get("price", 0.0) or 0.0)
                display_name = name if name.endswith("（KG）") else name + "（KG）"
                rows.append(self._customer_table_row(
                    display_name, "KG", "%.2f" % unit_price, "%.3f" % weight, "%.2f" % subtotal
                ))
            else:
                qty = int(item.get("qty", 1) or 1)
                unit_price = float(item.get("base_price", item.get("price", 0.0) / max(1, qty)) or 0.0)
                subtotal = float(item.get("price", 0.0) or 0.0)
                rows.append(self._customer_table_row(
                    name, item.get("unit", "份"), "%.2f" % unit_price, str(qty), "%.2f" % subtotal
                ))
        return rows

    def _template_context(self, sale, item=None, index=1):
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        call_no = sale.get("call_no", "001")
        total = float(sale.get("total_price", 0.0) or 0.0)
        payment = str(sale.get("payment_method", "") or "")
        payment_labels = {
            "cash": "现金",
            "shouqianba": "微信",
            "scan": "扫码",
            "qr": "二维码",
        }
        if payment:
            if payment.lower() == "mixed":
                payment = payment_display_label(
                    payment,
                    sale.get("payment_breakdown") or sale.get("payment_breakdown_json", ""),
                )
            else:
                payment = payment_labels.get(payment.lower(), payment)
        if item is None:
            item_name = ""
            weight = ""
            flavor = ""
            created_at = sale.get("created_at", now_str)
            kitchen_index = 0
            kitchen_count = 0
        else:
            item_name = str(item.get("name", "经典草本骨汤") or "经典草本骨汤")
            weight = "%.3f" % float(item.get("weight", sale.get("weight_kg", 0.0)) or 0.0)
            flavor = str(item.get("tag", "") or "").split("/")[0].strip()
            created_at = sale.get("created_at", now_str)
            kitchen_index = index
            kitchen_count = sum(
                1 for row in sale.get("cart_items", [])
                if row.get("type") == "soup" or "weight" in row
            )
            if not item_name.endswith("（KG）"):
                item_name += "（KG）"
        kitchen_call_no = str(call_no)
        if kitchen_count > 1 and kitchen_index > 0:
            kitchen_call_no = "%s - %d" % (call_no, kitchen_index)
        return {
            "shop_name": sale.get("shop_name", "杨国福麻辣烫"),
            "shop_subtitle": sale.get("shop_subtitle", "") or "杨国福(肥西水晶城店)",
            "call_no": call_no,
            "kitchen_call_no": kitchen_call_no,
            "pos_order_no": "POS#" + kitchen_call_no,
            # 取餐号行使用双倍宽高；按一半的逻辑列宽排版，避免 ESC/POS
            # 放大后把右侧的 [POS点餐] 挤出纸面。
            "pickup_line": fmt_lr_48(
                "取餐号：" + str(call_no), "[POS点餐]",
                max(8, self._line_width() // 2),
            ).rstrip("\n"),
            "table_header": self._customer_table_header(),
            "kitchen_title_line": fmt_lr_48(
                "制作单", "POS#" + kitchen_call_no,
                max(8, self._line_width() // 2),
            ).rstrip("\n"),
            "index": index,
            "item_name": item_name,
            "weight": weight,
            "item_line": (item_name + "    " + weight) if item_name else "",
            "flavor": flavor,
            "created_at": created_at,
            "time": now_str,
            "total": "%.2f" % total,
            "total_line": fmt_lr_48("合计", "%.2f" % total, self._line_width()).rstrip("\n"),
            "due_line": fmt_lr_48("应付", "%.2f" % total, self._line_width()).rstrip("\n"),
            "paid_line": fmt_lr_48("实付", "%.2f" % total, self._line_width()).rstrip("\n"),
            "payment_method": payment or "实付",
            "order_id": sale.get("order_id") or sale.get("temp_order_no") or "",
            "service_phone": self.config.get("printer_service_phone", "400-6058-777"),
            "operator": self.config.get("printer_operator", "") or "收银员",
            "items": "\n".join(self._customer_item_lines(sale)),
            "separator": self._separator().rstrip("\n"),
        }

    def _logo_raster_bytes(self):
        """Convert the bundled Logo to a black-on-white ESC/POS raster.

        The supplied artwork has a dark preview background with white/orange
        marks.  Thermal printers need the inverse: white paper plus black dots,
        so dark background pixels are ignored and the colored/bright artwork is
        thresholded into black dots.
        """
        if not bool(self.config.get("printer_logo_enabled", True)):
            return b""
        path = str(self.config.get("printer_logo_path", "") or "").strip()
        png_path = os.path.join(DATA_DIR, "assets", "yangguofu_logo_source.png")
        svg_path = os.path.join(DATA_DIR, "assets", "yangguofu_logo.svg")
        if not path:
            # SVG 是官方提供的透明矢量 Logo，优先使用；没有 QtSvg 或 SVG
            # 文件时再回退到旧 PNG，避免把透明背景当成黑色整块打印。
            # PNG 是与官方新版小票一致的黑底预览稿，包含完整的圆形图标
            # 和白色“杨”字；优先使用它并在栅格化时反相，避免某些 QtSvg
            # 版本对 SVG mask 的处理把白字也填成黑色。
            path = png_path if os.path.isfile(png_path) else svg_path
        if not os.path.isfile(path):
            return b""
        try:
            from PyQt5.QtCore import Qt
            from PyQt5.QtGui import QImage, QPainter

            try:
                configured_width = int(self.config.get("printer_logo_width_px", 512))
                # 新版官方顾客单的 Logo 需要占据纸面头部的主要宽度。
                # 384px 是旧版默认值；切到 official_v2 时自动提升到 512px，
                # 旧版和自定义模板仍沿用原有宽度设置。
                if self._template_profile() == "official_v2":
                    configured_width = max(configured_width, 512)
                target_width = min(512, max(160, configured_width))
            except (TypeError, ValueError):
                target_width = 512 if self._template_profile() == "official_v2" else 384
            is_svg = path.lower().endswith(".svg")
            bundled_svg = is_svg and os.path.abspath(path) == os.path.abspath(svg_path)
            bundled_png = (not is_svg) and os.path.abspath(path) == os.path.abspath(png_path)
            bundled_logo = bundled_svg or bundled_png
            if is_svg:
                from PyQt5.QtSvg import QSvgRenderer

                renderer = QSvgRenderer(path)
                if not renderer.isValid():
                    return b""
                source_size = renderer.defaultSize()
                source_width = max(1, source_size.width())
                source_height = max(1, source_size.height())
                target_height = max(1, int(round(target_width * source_height / float(source_width))))
                image = QImage(target_width, target_height, QImage.Format_ARGB32)
                image.fill(0)
                painter = QPainter(image)
                renderer.render(painter)
                painter.end()
                width, height = image.width(), image.height()
                # 圆形图标是 Logo 的组成部分，不能裁掉。热敏纸没有白墨，
                # 因此圆形区域内的橙色底转成黑点，白色“杨”字保持空白，
                # 才能得到黑圆白字；右侧白色字标则正常转成黑字。
                icon_width = int(round(width * 0.32)) if bundled_logo else 0
            else:
                image = QImage(path).convertToFormat(QImage.Format_ARGB32)
                if image.isNull():
                    return b""
                if image.width() > target_width:
                    image = image.scaledToWidth(target_width, Qt.SmoothTransformation)
            width, height = image.width(), image.height()
            if not is_svg:
                icon_width = int(round(width * 0.32)) if bundled_logo else 0
            corner_points = [(0, 0), (max(0, width - 1), 0), (0, max(0, height - 1)), (max(0, width - 1), max(0, height - 1))]
            corner_luma = sum(
                sum(image.pixelColor(x, y).getRgb()[:3]) / 3.0
                for x, y in corner_points
            ) / max(1, len(corner_points))
            # 透明 SVG 没有背景，所有 alpha 非零的矢量内容都应成为黑点；
            # 旧 PNG 则继续按深色背景阈值处理。
            dark_background = False if is_svg else corner_luma < 100
            bytes_per_row = (width + 7) // 8
            payload = bytearray()
            for y in range(height):
                row = bytearray(bytes_per_row)
                for x in range(width):
                    color = image.pixelColor(x, y)
                    # Dark charcoal background is blank; white text and orange
                    # icon both become printable black dots.
                    luma = (color.red() + color.green() + color.blue()) / 3.0
                    if is_svg:
                        if bundled_svg and x < icon_width:
                            # SVG 圆形区域：保留橙色/深色底，白色“杨”字留
                            # 空（热敏纸本身就是白色），从而打印黑圆白字。
                            logo_pixel = color.alpha() >= 32 and 45 <= luma < 200
                        else:
                            logo_pixel = color.alpha() >= 32
                    elif x < icon_width and bundled_logo:
                        # PNG 预览稿的深色背景与白色字都不能打印；只把
                        # 橙色圆底（中间亮度）转为黑点。
                        logo_pixel = 45 <= luma < 200
                    else:
                        logo_pixel = luma >= 80 if dark_background else luma <= 180
                    if logo_pixel:
                        row[x // 8] |= 0x80 >> (x % 8)
                payload.extend(row)
            header = b"\x1d\x76\x30\x00" + bytes((bytes_per_row & 0xFF, (bytes_per_row >> 8) & 0xFF, height & 0xFF, (height >> 8) & 0xFF))
            return header + bytes(payload)
        except Exception:
            # A missing Qt image plugin or malformed optional asset must not
            # prevent the text ticket from printing.
            return b""

    def _write_markup_template(self, data, template, context, fallback):
        """Write a future-proof text template with simple alignment/style tags."""
        rendered = self._render_template(template, context, fallback)
        for raw_line in rendered.splitlines():
            line = raw_line.strip("\r")
            alignment = self.ALIGN_LEFT
            bold = False
            double_height = False
            double_size = False
            triple_size = False
            while True:
                if line.startswith("[C]"):
                    alignment, line = self.ALIGN_CENTER, line[3:]
                elif line.startswith("[R]"):
                    alignment, line = self.ALIGN_RIGHT, line[3:]
                elif line.startswith("[L]"):
                    alignment, line = self.ALIGN_LEFT, line[3:]
                elif line.startswith("[B]"):
                    bold, line = True, line[3:]
                elif line.startswith("[D]"):
                    double_height, line = True, line[3:]
                elif line.startswith("[X]"):
                    # 官方新版模板的大字：同时放大宽度和高度。
                    double_size, line = True, line[3:]
                elif line.startswith("[Y]"):
                    # 取餐号专用的三倍宽高，适配后厨远距离识别。
                    triple_size, line = True, line[3:]
                else:
                    break
            data += alignment
            if bold:
                data += self.BOLD_ON
            if triple_size:
                data += b'\x1d\x21\x22'
            elif double_size:
                data += self.DOUBLE_SIZE
            elif double_height:
                data += self.DOUBLE_HEIGHT
            data += (line + "\n").encode("gbk", errors="ignore")
            if triple_size or double_size or double_height:
                data += self.NORMAL_SIZE
            if bold:
                data += self.BOLD_OFF
        data += self._feed_and_cut()
        return data

    def _build_template_customer_receipt(self, sale, template):
        data = bytearray(self.INIT)
        logo = self._logo_raster_bytes()
        if logo:
            data += self.ALIGN_CENTER + logo + b"\n"
            # The bundled artwork already contains the YANGGUOFU mark; avoid
            # printing the shop name a second time below it in official mode.
            if template == OFFICIAL_CUSTOMER_TEMPLATE:
                template = template.replace("[C][D]{shop_name}\n", "")
        return bytes(self._write_markup_template(
            data, template, self._template_context(sale), OFFICIAL_CUSTOMER_TEMPLATE
        ))

    def _build_template_kitchen_slip(self, sale, item, index, template):
        data = bytearray(self.INIT)
        return bytes(self._write_markup_template(
            data, template, self._template_context(sale, item, index), OFFICIAL_KITCHEN_TEMPLATE
        ))

    def _write_centered_lines(self, data, lines, double_first=False):
        for index, line in enumerate(lines):
            data += self.ALIGN_CENTER
            if double_first and index == 0:
                data += self.DOUBLE_HEIGHT + self.BOLD_ON
            data += (line + "\n").encode("gbk", errors="ignore")
            if double_first and index == 0:
                data += self.NORMAL_SIZE + self.BOLD_OFF

    def _build_customer_receipt(self, sale):
        """构建【顾客单】 ESC/POS 数据，列宽由打印设置统一控制。"""
        profile = self._template_profile()
        if profile == "official_v2":
            return self._build_template_customer_receipt(sale, OFFICIAL_CUSTOMER_TEMPLATE)
        if profile == "custom":
            template = self.config.get("printer_customer_template_custom", "") or OFFICIAL_CUSTOMER_TEMPLATE
            return self._build_template_customer_receipt(sale, template)
        d = bytearray()
        d += self.INIT
        width = self._line_width()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        call_no = sale.get("call_no", "001")
        shop_name = sale.get("shop_name", "杨国福麻辣烫")
        sub = sale.get("shop_subtitle", "") or "杨国福(肥西水晶城店)"
        if sub.startswith("门店名称："):
            sub_display = sub
        else:
            sub_display = "门店名称：" + sub
        context = {
            "shop_name": shop_name,
            "shop_subtitle": sub,
            "call_no": call_no,
            "time": now_str,
        }

        # 1. Header
        customer_title = self.config.get("printer_customer_title", "POS点餐 堂食")
        self._write_centered_lines(
            d,
            self._template_lines(customer_title, context, "POS点餐 堂食"),
            double_first=False,
        )
        d += self._separator().encode("gbk", errors="ignore")

        # 2. 店名 & 门店名称
        d += self.ALIGN_CENTER + self.DOUBLE_SIZE + self.BOLD_ON
        d += (shop_name + "\n").encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF

        d += self.ALIGN_CENTER
        d += (sub_display + "\n").encode("gbk", errors="ignore")

        # 3. 取餐号：95
        d += self._separator().encode("gbk", errors="ignore")
        d += self.ALIGN_LEFT + self.DOUBLE_SIZE + self.BOLD_ON
        d += ("取餐号：%s\n" % call_no).encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += self._separator().encode("gbk", errors="ignore")

        # 4. 表头：48 列保留旧版完整标题，窄纸使用紧凑标题。
        d += self.ALIGN_LEFT
        header = (
            "菜品名                    规格  单价  数量  小计"
            if width >= 44 else "菜品名       规格 单价 数量 小计"
        )
        d += (header + "\n").encode("gbk", errors="ignore")
        d += self._separator().encode("gbk", errors="ignore")

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
                line_str = fmt_lr_48("", right_str, width)
                d += line_str.encode("gbk", errors="ignore")
                
                if tag and bool(self.config.get("printer_show_tags", True)):
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
                line_str = fmt_lr_48("", right_str, width)
                d += line_str.encode("gbk", errors="ignore")
                if tag and bool(self.config.get("printer_show_tags", True)):
                    d += f"  {tag}\n".encode("gbk", errors="ignore")

        d += self._separator().encode("gbk", errors="ignore")

        # 6. 合计与应收 (严格右对齐 30 列)
        total_p = sale.get("total_price", 0.0)
        tot_str = fmt_lr_48("消费合计", f"{total_p:.2f}", width)
        d += tot_str.encode("gbk", errors="ignore")
        d += self._separator().encode("gbk", errors="ignore")
        ys_str = fmt_lr_48("应收", f"{total_p:.2f}", width)
        d += ys_str.encode("gbk", errors="ignore")
        d += self._separator().encode("gbk", errors="ignore")

        # 7. 打印时间
        footer = self.config.get("printer_customer_footer", "打印时间：{time}")
        for line in self._template_lines(footer, context, "打印时间：{time}"):
            d += (line + "\n").encode("gbk", errors="ignore")
        d += self._feed_and_cut()
        return bytes(d)

    def _build_kitchen_slip(self, sale, item, index):
        """构建【制作单】 ESC/POS 数据，支持窄纸宽度与门店模板。"""
        profile = self._template_profile()
        if profile == "official_v2":
            return self._build_template_kitchen_slip(sale, item, index, OFFICIAL_KITCHEN_TEMPLATE)
        if profile == "custom":
            template = self.config.get("printer_kitchen_template_custom", "") or OFFICIAL_KITCHEN_TEMPLATE
            return self._build_template_kitchen_slip(sale, item, index, template)
        d = bytearray()
        d += self.INIT
        width = self._line_width()

        tag = item.get("tag", "")
        is_takeout = "打包" in [p.strip() for p in tag.split("/") if p.strip()]
        created_at = sale.get("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        call_no = sale.get("call_no", "001")
        context = {
            "call_no": call_no,
            "index": index,
            "created_at": created_at,
            "service_type": "打包" if is_takeout else "堂食",
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # 如果是打包，最上方密集打印3行“打包”
        if is_takeout and bool(self.config.get("printer_takeout_banner_enabled", True)):
            d += self.FONT_SMALL + self.ALIGN_CENTER
            try:
                banner_lines = min(8, max(0, int(self.config.get("printer_takeout_banner_lines", 3))))
            except (TypeError, ValueError):
                banner_lines = 3
            packed_line = "打包" * max(4, width // 4) + "\n"
            d += (packed_line * banner_lines).encode("gbk", errors="ignore")
            d += self.FONT_NORMAL

        # 1. 标题
        title_key = "printer_kitchen_title_takeout" if is_takeout else "printer_kitchen_title_dinein"
        title_default = "制作单-打包" if is_takeout else "制作单-堂食"
        d += self.ALIGN_CENTER + self.BOLD_ON + self.DOUBLE_HEIGHT
        for line in self._template_lines(self.config.get(title_key, title_default), context, title_default):
            d += (line + "\n").encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += self._separator().encode("gbk", errors="ignore")

        # 2. 取餐号：95 - 1
        call_no_full = f"{call_no} - {index}"
        
        d += self.ALIGN_LEFT + self.DOUBLE_SIZE + self.BOLD_ON
        d += ("取餐号：%s\n" % call_no_full).encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += self._separator().encode("gbk", errors="ignore")

        # 3. 渠道与下单时间
        d += "渠道：POS点餐\n".encode("gbk", errors="ignore")
        d += ("下单时间：%s\n" % created_at).encode("gbk", errors="ignore")
        d += self._separator().encode("gbk", errors="ignore")

        # 4. 表头
        hdr_str = fmt_lr_48("菜品名", "数量", width)
        d += hdr_str.encode("gbk", errors="ignore")
        
        # 5. 菜品名称、重量与口味 (大字号加粗显示，方便后厨看单)
        name = item.get("name", "经典草本骨汤")
        weight_val = item.get("weight", sale.get("weight_kg", 0.0))

        # 菜品名 & 数量大字号加粗
        d += self.DOUBLE_HEIGHT + self.BOLD_ON
        d += (name + "\n").encode("gbk", errors="ignore")
        
        w_str = f"{weight_val:.3f}"
        val_str = fmt_lr_48("", w_str, width)
        d += val_str.encode("gbk", errors="ignore")

        if tag and bool(self.config.get("printer_show_tags", True)):
            d += f"  {tag}\n".encode("gbk", errors="ignore")

        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += self._separator().encode("gbk", errors="ignore")

        # 6. 打印时间
        footer = self.config.get("printer_kitchen_footer", "打印时间：{time}")
        for line in self._template_lines(footer, context, "打印时间：{time}"):
            d += (line + "\n").encode("gbk", errors="ignore")
        
        # 如果是打包，最下方再补1行密集的“打包”
        if is_takeout:
            d += self.FONT_SMALL + self.ALIGN_CENTER
            d += ("打包" * max(4, width // 4) + "\n").encode("gbk", errors="ignore")
            d += self.FONT_NORMAL

        d += self._feed_and_cut()
        return bytes(d)

    def print_receipt(self, sale, print_type="all", respect_settings=True):
        """全流程小票打印入口。

        ``all`` 遵守打印设置中的开关和份数；历史订单的“重打”可传
        ``respect_settings=False``，明确的人工补打不会被自动打印开关拦截。
        """
        cart_items = sale.get("cart_items", [])
        has_soup = any(i.get("type") == "soup" or "weight" in i for i in cart_items)
        if not has_soup:
            print("[ReceiptPrinter] 订单中无汤底项目，跳过打票（顾客单与制作单均不出票）")
            return True

        all_raw_data = bytearray()

        customer_enabled = bool(self.config.get("printer_customer_enabled", True))
        kitchen_enabled = bool(self.config.get("printer_kitchen_enabled", True))
        if print_type in ("all", "customer") and (not respect_settings or customer_enabled):
            customer_copies = self._copies(self.config, "printer_customer_copies", 1)
            customer_bytes = self._build_customer_receipt(sale)
            all_raw_data += customer_bytes * customer_copies

        if print_type in ("all", "kitchen"):
            cart_items = sale.get("cart_items", [])
            malatang_items = [i for i in cart_items if (i.get("type") == "soup" or "weight" in i)]
            if (not respect_settings or kitchen_enabled):
                kitchen_copies = self._copies(self.config, "printer_kitchen_copies", 1)
                for idx, item in enumerate(malatang_items, start=1):
                    ks_bytes = self._build_kitchen_slip(sale, item, idx)
                    all_raw_data += ks_bytes * kitchen_copies

        if not all_raw_data:
            print("[ReceiptPrinter] 当前打印设置已关闭本次单据，跳过发单")
            return True

        pt = self.config.get("printer_type", "windows")
        if self.config.get("is_mock_mode", False):
            print("[模拟调试模式] 已完成小票及制作单模拟发单！")
            return True

        try:
            if pt == "windows":
                return self._send_raw_to_windows(bytes(all_raw_data))
            elif pt == "network":
                return self._send_raw_to_network(bytes(all_raw_data))
            elif pt == "serial":
                return self._send_raw_to_serial(bytes(all_raw_data))
        except Exception as e:
            err_msg = str(e)
            print("[打印错误] %s" % err_msg)
            self.last_error = err_msg
            return False
        return False

    def open_cash_drawer(self):
        """发送开启钱箱指令"""
        if not bool(self.config.get("printer_cash_drawer_enabled", True)):
            print("[ReceiptPrinter] 钱箱指令已在打印设置中关闭")
            return True
        print("[ReceiptPrinter] 正在发送开启钱箱指令...")
        pt = self.config.get("printer_type", "windows")
        if self.config.get("is_mock_mode", False):
            print("[模拟调试模式] 已模拟开启钱箱！")
            return True
            
        try:
            if pt == "windows":
                return self._send_raw_to_windows(self.OPEN_DRAWER)
            elif pt == "network":
                return self._send_raw_to_network(self.OPEN_DRAWER)
            elif pt == "serial":
                return self._send_raw_to_serial(self.OPEN_DRAWER)
        except Exception as e:
            err_msg = str(e)
            print("[开启钱箱错误] %s" % err_msg)
            self.last_error = err_msg
            return False
        return False

    def _build_shift_report(self, report_data):
        """构建【营业汇总报表】ESC/POS 票据 (符合店铺规范，严格 30 列排版)"""
        d = bytearray()
        d += self.INIT

        # 1. 标题
        d += self.ALIGN_CENTER + self.BOLD_ON + self.DOUBLE_HEIGHT
        report_title = self.config.get("printer_report_title", "营业汇总报表")
        d += (str(report_title) + "\n").encode("gbk", errors="ignore")
        d += self.NORMAL_SIZE + self.BOLD_OFF
        d += self._separator().encode("gbk", errors="ignore")

        # 2. 门店与时间
        shop_sub = self.config.get("shop_subtitle", "杨国福(肥西水晶城店)")
        if not shop_sub.startswith("门店名称："):
            shop_sub = "门店名称：" + shop_sub
        d += self.ALIGN_LEFT
        d += (shop_sub + "\n").encode("gbk", errors="ignore")
        date_str = report_data.get("date_str", time.strftime("%Y-%m-%d"))
        d += ("开始时间：%s\n" % date_str).encode("gbk", errors="ignore")
        d += self._separator().encode("gbk", errors="ignore")

        # 3. 销售汇总
        d += self.BOLD_ON
        d += "销售汇总\n".encode("gbk", errors="ignore")
        d += self.BOLD_OFF
        d += self._separator("=").encode("gbk", errors="ignore")

        rev_amt = report_data.get("amount_sum", 0.0)
        count = report_data.get("count", 0)
        avg = rev_amt / count if count > 0 else 0.0

        width = self._line_width()
        d += fmt_lr_48("营业收入：", "¥ %.2f" % rev_amt, width).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("订单数量：", "%d" % count, width).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("客单价：", "¥ %.2f" % avg, width).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("退款金额：", "¥ %.2f" % report_data.get("refund_amount_sum", 0.0), width).encode("gbk", errors="ignore") + b"\n"
        d += fmt_lr_48("退款数量：", "%d" % report_data.get("refund_count", 0), width).encode("gbk", errors="ignore") + b"\n"

        # 4. 收入明细 (总结)
        d += self.BOLD_ON
        d += "收入明细\n".encode("gbk", errors="ignore")
        d += self.BOLD_OFF
        d += self._separator("=").encode("gbk", errors="ignore")
        d += self.BOLD_ON
        d += fmt_lr_48("总结", "¥ %.2f" % rev_amt, width).encode("gbk", errors="ignore") + b"\n"
        d += self.BOLD_OFF
        d += self._separator().encode("gbk", errors="ignore")

        # 5. 打印时间
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        report_context = {"time": now_str, "date": report_data.get("date_str", time.strftime("%Y-%m-%d"))}
        for line in self._template_lines(
            self.config.get("printer_report_footer", "打印时间：{time}"),
            report_context,
            "打印时间：{time}",
        ):
            d += (line + "\n").encode("gbk", errors="ignore")
        d += self._feed_and_cut()
        return bytes(d)

    def print_shift_report(self, report_data):
        """营业汇总报表打印入口"""
        if not bool(self.config.get("printer_report_enabled", True)):
            print("[ReceiptPrinter] 营业报表打印已在打印设置中关闭")
            return True
        if self.config.get("is_mock_mode", False):
            print("[模拟调试模式] 已完成营业汇总报表模拟打票！")
            return True

        raw_data = self._build_shift_report(report_data)
        report_copies = self._copies(self.config, "printer_report_copies", 1)
        if report_copies <= 0:
            print("[ReceiptPrinter] 营业报表份数为 0，跳过发单")
            return True
        raw_data *= report_copies
        pt = self.config.get("printer_type", "windows")
        try:
            if pt == "windows":
                return self._send_raw_to_windows(raw_data)
            elif pt == "network":
                return self._send_raw_to_network(raw_data)
            elif pt == "serial":
                return self._send_raw_to_serial(raw_data)
        except Exception as e:
            err_msg = str(e)
            print("[打印错误] %s" % err_msg)
            self.last_error = err_msg
            return False
        return False

    def print_raw(self, raw_data):
        """Send a preformatted ESC/POS ticket through the configured printer.

        Used by takeout preparation only.  Routing through this public method
        preserves Windows/network/serial configuration instead of silently
        forcing the Windows spooler.
        """
        if self.config.get("is_mock_mode", False):
            return True
        try:
            printer_type = self.config.get("printer_type", "windows")
            if printer_type == "windows":
                return self._send_raw_to_windows(raw_data)
            if printer_type == "network":
                return self._send_raw_to_network(raw_data)
            if printer_type == "serial":
                return self._send_raw_to_serial(raw_data)
            self.last_error = "未知打印机类型: %s" % printer_type
        except Exception as exc:
            self.last_error = str(exc)
        return False

    def _send_raw_to_windows(self, raw_data):
        try:
            import win32print
            name = self.config.get("printer_name", "shouyin") or win32print.GetDefaultPrinter()
            h = win32print.OpenPrinter(name)
            try:
                win32print.StartDocPrinter(h, 1, ("POS_Receipt", None, "RAW"))
                win32print.StartPagePrinter(h)
                win32print.WritePrinter(h, raw_data)
                win32print.EndPagePrinter(h)
                win32print.EndDocPrinter(h)
                return True
            finally:
                win32print.ClosePrinter(h)
        except Exception as e:
            err_msg = str(e)
            print("[Windows 打印错误] %s" % err_msg)
            self.last_error = err_msg
            return False

    def _send_raw_to_network(self, raw_data):
        try:
            ip = self.config.get("printer_ip", "192.168.1.100")
            port = self.config.get("printer_port", 9100)
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(5)
            s.connect((ip, port))
            s.sendall(raw_data)
            s.close()
            return True
        except Exception as e:
            err_msg = str(e)
            print("[网络打印错误] %s" % err_msg)
            self.last_error = err_msg
            return False

    def _send_raw_to_serial(self, raw_data):
        try:
            import serial
            port = self.config.get("printer_serial_port", "COM4")
            ser = serial.Serial(port, 9600, timeout=2)
            ser.write(raw_data)
            ser.flush()
            time.sleep(0.5)
            ser.close()
            return True
        except Exception as e:
            err_msg = str(e)
            print("[串口打印错误] %s" % err_msg)
            self.last_error = err_msg
            return False
