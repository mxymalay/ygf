"""
SQLite 数据库模块 — 销售记录的持久化存储
兼容 Python 3.8+
"""
import sqlite3
import os
from datetime import datetime, date
from config import DB_PATH


class Database:
    """本地 SQLite 数据库，管理销售记录"""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sales (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_no     TEXT    UNIQUE NOT NULL,
                weight_kg   REAL    NOT NULL,
                unit_price  REAL    NOT NULL,
                price_unit  TEXT    NOT NULL DEFAULT 'per_jin',
                total_price REAL    NOT NULL,
                remark      TEXT    DEFAULT '',
                created_at  TEXT    NOT NULL,
                printed     INTEGER DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_sales_date
                ON sales(created_at);

            CREATE INDEX IF NOT EXISTS idx_sales_no
                ON sales(sale_no);
        """)
        conn.commit()

        # 安全升级：尝试添加 cart_items_json 列，如果已存在则忽略
        try:
            conn.execute("ALTER TABLE sales ADD COLUMN cart_items_json TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        # 安全升级：尝试添加 payment_method 列 (结账方式：scan/cash/qr)
        try:
            conn.execute("ALTER TABLE sales ADD COLUMN payment_method TEXT DEFAULT ''")
            conn.commit()
        except sqlite3.OperationalError:
            pass

        conn.close()

    def generate_sale_no(self):
        """生成格式为 YGF + 日期 + 3位序号 的单号"""
        today_str = datetime.now().strftime("%Y%m%d")
        prefix = "YGF%s" % today_str

        conn = self._get_conn()
        row = conn.execute(
            "SELECT sale_no FROM sales WHERE sale_no LIKE ? ORDER BY id DESC LIMIT 1",
            ("%s%%" % prefix,)
        ).fetchone()
        conn.close()

        if row:
            last_seq = int(row["sale_no"][-3:])
            seq = last_seq + 1
        else:
            seq = 1

        return "%s%03d" % (prefix, seq)

    def insert_sale(self, weight_kg, unit_price, price_unit, total_price, remark="", cart_items_json=None, payment_method=""):
        """插入一条销售记录，返回完整记录字典"""
        sale_no = self.generate_sale_no()
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO sales
               (sale_no, weight_kg, unit_price, price_unit, total_price, remark, created_at, cart_items_json, payment_method)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sale_no, weight_kg, unit_price, price_unit, total_price, remark, created_at, cart_items_json, payment_method)
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM sales WHERE sale_no = ?", (sale_no,)
        ).fetchone()
        conn.close()

        return dict(row)

    def get_payment_stats_by_date(self, start_date, end_date=None):
        """获取指定日期范围内按结账方式分组的统计"""
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, 'strftime') else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if (end_date and hasattr(end_date, 'strftime')) else (str(end_date) if end_date else s_str)

        conn = self._get_conn()
        rows = conn.execute(
            """SELECT COALESCE(payment_method, '') AS pm,
                      COUNT(*) AS cnt,
                      COALESCE(SUM(total_price), 0) AS amt
               FROM sales
               WHERE DATE(created_at) BETWEEN ? AND ?
               GROUP BY pm""",
            (s_str, e_str)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_today_summary(self):
        """返回今日汇总：笔数、总重量、总金额"""
        today_str = date.today().strftime("%Y-%m-%d")
        conn = self._get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(*)                        AS count,
                   COALESCE(SUM(weight_kg), 0)   AS total_weight,
                   COALESCE(SUM(total_price), 0) AS total_amount
               FROM sales
               WHERE created_at LIKE ?""",
            ("%s%%" % today_str,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_sales_by_date(self, start_date, end_date=None):
        """按日期范围查询所有销售记录"""
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, 'strftime') else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if (end_date and hasattr(end_date, 'strftime')) else (str(end_date) if end_date else s_str)

        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sales WHERE DATE(created_at) BETWEEN ? AND ? ORDER BY id DESC",
            (s_str, e_str)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_stats_by_date(self, start_date, end_date=None):
        """获取指定日期范围的汇总统计信息"""
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, 'strftime') else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if (end_date and hasattr(end_date, 'strftime')) else (str(end_date) if end_date else s_str)

        conn = self._get_conn()
        row = conn.execute(
            """SELECT
                   COUNT(*)                          AS count,
                   COALESCE(SUM(weight_kg), 0)      AS weight_sum,
                   COALESCE(SUM(total_price), 0)    AS amount_sum
               FROM sales
               WHERE DATE(created_at) BETWEEN ? AND ?""",
            (s_str, e_str)
        ).fetchone()
        conn.close()
        return dict(row)

    def delete_sale(self, sale_id):
        """按 ID 删除一条记录"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def get_recent_sales(self, limit=20):
        """获取最近的 N 条销售记录"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sales ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
