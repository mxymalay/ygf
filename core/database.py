"""SQLite 交易账本。

订单一旦确认支付便不能物理删除；打印和退款是订单上的状态变化。这样在
打印机故障、重复点击或程序重启后，门店仍能找到同一笔交易并继续处理。
"""
import os
import json
import re
import shutil
import sqlite3
from datetime import date, datetime

from config import DATA_DIR, DB_PATH
from core.payment_utils import parse_payment_breakdown


PAID = "PAID"
REFUNDED = "REFUNDED"
PRINT_PENDING = "PENDING"
PRINTED = "PRINTED"
PRINT_FAILED = "FAILED"


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_official_call_no(value):
    """Normalize POS call numbers so ``#0001`` and ``POS#001`` match."""
    text = str(value or "").strip()
    match = re.search(r"(\d+)$", text)
    if not match:
        return text.casefold()
    digits = match.group(1).lstrip("0")
    return digits or "0"


def archive_database_files(db_path=DB_PATH, reason="manual_reset"):
    """Move the SQLite database and sidecars to a dated backup folder.

    Moving rather than unlinking makes the explicit "clear data" action
    recoverable if it was pressed by mistake.  The caller must ensure no
    active database transaction is in progress.
    """
    if not os.path.exists(db_path) and not any(
        os.path.exists(db_path + suffix) for suffix in ("-wal", "-shm")
    ):
        return ""
    backup_dir = os.path.join(DATA_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = os.path.join(backup_dir, "sales_%s_%s" % (reason, stamp))
    os.makedirs(target_dir, exist_ok=False)
    moved = False
    for suffix in ("", "-wal", "-shm"):
        source = db_path + suffix
        if os.path.exists(source):
            shutil.move(source, os.path.join(target_dir, os.path.basename(source)))
            moved = True
    return target_dir if moved else ""


class Database:
    """本地 SQLite 销售账本。"""

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        # A short busy timeout makes two UI actions fail gracefully instead of
        # immediately raising "database is locked" on slower Win7 machines.
        conn = sqlite3.connect(self.db_path, timeout=8)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=8000")
        return conn

    @staticmethod
    def _ensure_column(conn, name, definition, table="sales"):
        columns = {row[1] for row in conn.execute("PRAGMA table_info(%s)" % table)}
        if name not in columns:
            conn.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, name, definition))

    def _init_db(self):
        """Create and transactionally migrate the append-only order schema."""
        conn = self._get_conn()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sales (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_no         TEXT UNIQUE NOT NULL,
                    order_id        TEXT UNIQUE,
                    weight_kg       REAL NOT NULL,
                    unit_price      REAL NOT NULL,
                    price_unit      TEXT NOT NULL DEFAULT 'per_jin',
                    total_price     REAL NOT NULL,
                    remark          TEXT DEFAULT '',
                    created_at      TEXT NOT NULL,
                    payment_method  TEXT DEFAULT '',
                    payment_breakdown_json TEXT DEFAULT '',
                    payment_status  TEXT NOT NULL DEFAULT 'PAID',
                    payment_confirmed_at TEXT DEFAULT '',
                    cart_items_json TEXT,
                    printed         INTEGER NOT NULL DEFAULT 0,
                    print_status    TEXT NOT NULL DEFAULT 'PENDING',
                    print_attempts  INTEGER NOT NULL DEFAULT 0,
                    last_printed_at TEXT DEFAULT '',
                    print_error     TEXT DEFAULT '',
                    refunded_at     TEXT DEFAULT '',
                    refund_reason   TEXT DEFAULT '',
                    refund_operator TEXT DEFAULT ''
                );

                -- Routing statistics are deliberately separate from sales;
                -- official POS payments use the dedicated verified ledger
                -- below, while scale routing decisions remain observable.
                -- One row per local day keeps the quota stable across a POS
                -- restart without pretending to know the official amount.
                CREATE TABLE IF NOT EXISTS switch_quota_daily (
                    stat_date TEXT PRIMARY KEY,
                    total_weight_kg REAL NOT NULL DEFAULT 0,
                    private_weight_kg REAL NOT NULL DEFAULT 0,
                    total_decisions INTEGER NOT NULL DEFAULT 0,
                    private_decisions INTEGER NOT NULL DEFAULT 0,
                    official_decisions INTEGER NOT NULL DEFAULT 0,
                    forced_official_decisions INTEGER NOT NULL DEFAULT 0,
                    inherited_private INTEGER NOT NULL DEFAULT 0,
                    inherited_official INTEGER NOT NULL DEFAULT 0,
                    inherited_total_weight_kg REAL NOT NULL DEFAULT 0,
                    inherited_private_weight_kg REAL NOT NULL DEFAULT 0,
                    last_official_route_at REAL NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT ''
                );

                -- One row per stable weighing event.  This is deliberately
                -- separate from both ``sales`` and the operational quota:
                -- private payment can be confirmed locally, while official
                -- POS payment has no callback and must remain "unknown".
                CREATE TABLE IF NOT EXISTS weighing_route_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_key       TEXT UNIQUE NOT NULL,
                    weight_kg       REAL NOT NULL,
                    channel         TEXT NOT NULL,
                    decision_kind   TEXT DEFAULT '',
                    status          TEXT NOT NULL DEFAULT 'PENDING',
                    order_id        TEXT DEFAULT '',
                    routing_basis   TEXT NOT NULL DEFAULT 'weight',
                    operating_mode  TEXT NOT NULL DEFAULT 'compatibility',
                    official_receipt_key TEXT DEFAULT '',
                    estimated_amount REAL NOT NULL DEFAULT 0,
                    created_at      TEXT NOT NULL,
                    resolved_at     TEXT DEFAULT '',
                    resolution_note TEXT DEFAULT ''
                );

                -- Verified official-POS revenue is kept separate from the
                -- private POS ``sales`` ledger.  The stable order key makes
                -- original prints, reprints and retries idempotent.
                CREATE TABLE IF NOT EXISTS official_pos_revenue (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_key       TEXT UNIQUE NOT NULL,
                    platform        TEXT DEFAULT '',
                    order_id        TEXT DEFAULT '',
                    order_no        TEXT DEFAULT '',
                    amount          REAL NOT NULL,
                    payment_status  TEXT NOT NULL DEFAULT 'PAID',
                    payment_method  TEXT DEFAULT '',
                    payment_breakdown_json TEXT DEFAULT '',
                    source          TEXT DEFAULT 'takeout_relay',
                    created_at      TEXT NOT NULL,
                    refunded_at     TEXT DEFAULT '',
                    refund_amount   REAL NOT NULL DEFAULT 0,
                    refund_receipt_key TEXT DEFAULT ''
                );

                -- Parsed external-order history is separate from both POS
                -- ledgers.  It keeps recognition/audit fields without storing
                -- the original receipt payload or unnecessary customer data.
                CREATE TABLE IF NOT EXISTS takeout_orders (
                    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_key                TEXT UNIQUE NOT NULL,
                    platform                 TEXT DEFAULT '',
                    full_order_id            TEXT DEFAULT '',
                    order_no                 TEXT DEFAULT '',
                    amount                   REAL,
                    amount_valid             INTEGER NOT NULL DEFAULT 0,
                    payment_status           TEXT NOT NULL DEFAULT 'unknown',
                    payment_status_confidence TEXT DEFAULT 'unknown',
                    key_confidence           TEXT DEFAULT 'low',
                    item_count               INTEGER NOT NULL DEFAULT 0,
                    item_names_json          TEXT DEFAULT '[]',
                    is_duplicate             INTEGER NOT NULL DEFAULT 0,
                    conflict_detected        INTEGER NOT NULL DEFAULT 0,
                    created_at               TEXT NOT NULL,
                    printed_at               TEXT DEFAULT '',
                    print_count              INTEGER NOT NULL DEFAULT 0,
                    last_result              TEXT DEFAULT 'PENDING',
                    last_error               TEXT DEFAULT ''
                );

                -- All recognized official-POS receipts are retained here,
                -- including unknown/unpaid observations. Only rows that pass
                -- the final evidence checks are copied to official revenue.
                CREATE TABLE IF NOT EXISTS official_pos_receipts (
                    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_key                TEXT UNIQUE NOT NULL,
                    receipt_kind               TEXT NOT NULL DEFAULT 'unknown',
                    platform                   TEXT DEFAULT '',
                    order_id                   TEXT DEFAULT '',
                    order_no                   TEXT DEFAULT '',
                    amount                     REAL,
                    amount_valid               INTEGER NOT NULL DEFAULT 0,
                    payment_status            TEXT NOT NULL DEFAULT 'unknown',
                    payment_method             TEXT DEFAULT '',
                    payment_breakdown_json     TEXT DEFAULT '',
                    payment_status_confidence TEXT DEFAULT 'unknown',
                    key_confidence             TEXT DEFAULT 'low',
                    payload_type               TEXT DEFAULT '',
                    capture_path               TEXT DEFAULT '',
                    observed_at                TEXT NOT NULL,
                    print_count                INTEGER NOT NULL DEFAULT 1,
                    is_duplicate               INTEGER NOT NULL DEFAULT 0,
                    conflict_detected          INTEGER NOT NULL DEFAULT 0,
                    last_result                TEXT DEFAULT 'RECEIVED',
                    last_error                 TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS relay_mode_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    previous_mode TEXT NOT NULL DEFAULT '',
                    new_mode      TEXT NOT NULL,
                    policy        TEXT NOT NULL DEFAULT 'auto',
                    reason        TEXT DEFAULT '',
                    created_at    TEXT NOT NULL
                );

                -- Refunds are append-only observations.  When the official
                -- POS omits the long order id, the relay links this row to a
                -- paid revenue row by normalized call number and amount.
                CREATE TABLE IF NOT EXISTS official_pos_refunds (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    refund_key          TEXT UNIQUE NOT NULL,
                    refund_receipt_key  TEXT DEFAULT '',
                    refund_order_no     TEXT DEFAULT '',
                    refund_amount       REAL NOT NULL DEFAULT 0,
                    original_order_key  TEXT DEFAULT '',
                    original_order_id   TEXT DEFAULT '',
                    status              TEXT NOT NULL DEFAULT 'UNMATCHED',
                    match_reason        TEXT DEFAULT '',
                    created_at          TEXT NOT NULL
                );
                """
            )

            # Existing stores upgrade in place.  Legacy completed orders are
            # preserved as paid/printed instead of being guessed as failures.
            upgrades = {
                "order_id": "TEXT",
                "cart_items_json": "TEXT",
                "payment_method": "TEXT DEFAULT ''",
                "payment_breakdown_json": "TEXT DEFAULT ''",
                "payment_status": "TEXT NOT NULL DEFAULT 'PAID'",
                "payment_confirmed_at": "TEXT DEFAULT ''",
                "print_status": "TEXT NOT NULL DEFAULT 'PENDING'",
                "print_attempts": "INTEGER NOT NULL DEFAULT 0",
                "last_printed_at": "TEXT DEFAULT ''",
                "print_error": "TEXT DEFAULT ''",
                "refunded_at": "TEXT DEFAULT ''",
                "refund_reason": "TEXT DEFAULT ''",
                "refund_operator": "TEXT DEFAULT ''",
            }
            for name, definition in upgrades.items():
                self._ensure_column(conn, name, definition)

            # A previous version may already have created the routing table;
            # add its continuation-weight columns without touching sales data.
            switch_upgrades = {
                "inherited_total_weight_kg": "REAL NOT NULL DEFAULT 0",
                "inherited_private_weight_kg": "REAL NOT NULL DEFAULT 0",
                "last_official_route_at": "REAL NOT NULL DEFAULT 0",
            }
            for name, definition in switch_upgrades.items():
                self._ensure_column(conn, name, definition, table="switch_quota_daily")

            route_upgrades = {
                "routing_basis": "TEXT NOT NULL DEFAULT 'weight'",
                "operating_mode": "TEXT NOT NULL DEFAULT 'compatibility'",
                "official_receipt_key": "TEXT DEFAULT ''",
                "estimated_amount": "REAL NOT NULL DEFAULT 0",
            }
            for name, definition in route_upgrades.items():
                self._ensure_column(conn, name, definition, table="weighing_route_events")
            self._ensure_column(conn, "conflict_detected", "INTEGER NOT NULL DEFAULT 0", table="official_pos_receipts")
            for name, definition in {
                "order_no": "TEXT DEFAULT ''",
                "payment_method": "TEXT DEFAULT ''",
                "payment_breakdown_json": "TEXT DEFAULT ''",
                "refunded_at": "TEXT DEFAULT ''",
                "refund_amount": "REAL NOT NULL DEFAULT 0",
                "refund_receipt_key": "TEXT DEFAULT ''",
            }.items():
                self._ensure_column(conn, name, definition, table="official_pos_revenue")
            for name, definition in {
                "payment_method": "TEXT DEFAULT ''",
                "payment_breakdown_json": "TEXT DEFAULT ''",
            }.items():
                self._ensure_column(conn, name, definition, table="official_pos_receipts")

            # Do not create indexes until after the column migration.  An old
            # store can have a valid ``sales`` table without ``order_id``;
            # creating the index in the initial CREATE script would make
            # SQLite abort before `_ensure_column` ever gets a chance to run.
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sales_no ON sales(sale_no)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_route_events_date "
                "ON weighing_route_events(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_route_events_status "
                "ON weighing_route_events(status, channel)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_official_revenue_date "
                "ON official_pos_revenue(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_takeout_orders_date "
                "ON takeout_orders(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_official_receipts_observed "
                "ON official_pos_receipts(observed_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_relay_mode_events_date "
                "ON relay_mode_events(created_at)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_order_id "
                "ON sales(order_id) WHERE order_id IS NOT NULL"
            )
            conn.execute(
                "UPDATE sales SET order_id = 'LEGACY-' || id "
                "WHERE order_id IS NULL OR order_id = ''"
            )
            conn.execute(
                "UPDATE sales SET payment_status = ? "
                "WHERE payment_status IS NULL OR payment_status = ''",
                (PAID,),
            )
            conn.execute(
                "UPDATE sales SET print_status = ?, printed = 1 "
                "WHERE (print_status IS NULL OR print_status = '') AND printed = 1",
                (PRINTED,),
            )
            conn.execute(
                "UPDATE sales SET print_status = ? "
                "WHERE print_status IS NULL OR print_status = ''",
                (PRINT_PENDING,),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _next_sale_no(conn):
        today_str = datetime.now().strftime("%Y%m%d")
        prefix = "YGF%s" % today_str
        row = conn.execute(
            "SELECT sale_no FROM sales WHERE sale_no LIKE ? ORDER BY id DESC LIMIT 1",
            ("%s%%" % prefix,),
        ).fetchone()
        try:
            sequence = int(row["sale_no"][-3:]) + 1 if row else 1
        except (TypeError, ValueError):
            sequence = 1
        return "%s%03d" % (prefix, sequence)

    def generate_sale_no(self):
        """Preview only. insert_sale generates the final number atomically."""
        conn = self._get_conn()
        try:
            return self._next_sale_no(conn)
        finally:
            conn.close()

    def get_sale_by_order_id(self, order_id):
        if not order_id:
            return None
        conn = self._get_conn()
        try:
            row = conn.execute("SELECT * FROM sales WHERE order_id = ?", (order_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_latest_sale(self):
        """Return the most recent local sale for the empty-cart summary card."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM sales ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def insert_sale(
        self,
        weight_kg,
        unit_price,
        price_unit,
        total_price,
        remark="",
        cart_items_json=None,
        payment_method="",
        payment_breakdown_json="",
        order_id=None,
    ):
        """Create one paid order, returning ``(record, created)``.

        ``order_id`` is created before the payment dialog opens.  A repeated
        callback for the same dialog therefore returns the original order and
        cannot create a second sale number or consume a second call number.
        """
        if not order_id:
            raise ValueError("订单缺少唯一标识，拒绝入库")
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute("SELECT * FROM sales WHERE order_id = ?", (order_id,)).fetchone()
            if existing:
                conn.commit()
                return dict(existing), False

            sale_no = self._next_sale_no(conn)
            created_at = _now_text()
            conn.execute(
                """INSERT INTO sales
                   (sale_no, order_id, weight_kg, unit_price, price_unit, total_price,
                    remark, created_at, payment_method, payment_breakdown_json, payment_status,
                    payment_confirmed_at, cart_items_json, printed, print_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                (
                    sale_no,
                    order_id,
                    weight_kg,
                    unit_price,
                    price_unit,
                    total_price,
                    remark,
                    created_at,
                    payment_method,
                    payment_breakdown_json or "",
                    PAID,
                    created_at,
                    cart_items_json,
                    PRINT_PENDING,
                ),
            )
            row = conn.execute("SELECT * FROM sales WHERE order_id = ?", (order_id,)).fetchone()
            conn.commit()
            return dict(row), True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def mark_print_result(self, sale_id, success, error=""):
        """Persist every print attempt; failed paid orders remain reprintable."""
        conn = self._get_conn()
        try:
            now = _now_text()
            if success:
                conn.execute(
                    """UPDATE sales SET printed=1, print_status=?, print_attempts=print_attempts+1,
                       last_printed_at=?, print_error='' WHERE id=?""",
                    (PRINTED, now, sale_id),
                )
            else:
                conn.execute(
                    """UPDATE sales SET printed=0, print_status=?, print_attempts=print_attempts+1,
                       print_error=? WHERE id=?""",
                    (PRINT_FAILED, str(error or "打印失败")[:500], sale_id),
                )
            conn.commit()
        finally:
            conn.close()

    def refund_sale(self, sale_id, reason="门店退单", operator=""):
        """Mark a paid sale refunded without deleting its audit trail."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE sales SET payment_status=?, refunded_at=?, refund_reason=?, refund_operator=?
                   WHERE id=? AND payment_status=?""",
                (REFUNDED, _now_text(), str(reason or "门店退单")[:200], str(operator or "")[:100], sale_id, PAID),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_payment_stats_by_date(self, start_date, end_date=None):
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT COALESCE(payment_method, '') AS pm,
                          COALESCE(total_price, 0) AS amt,
                          COALESCE(payment_breakdown_json, '') AS breakdown
                   FROM sales WHERE DATE(created_at) BETWEEN ? AND ?
                     AND payment_status = ?""",
                (s_str, e_str, PAID),
            ).fetchall()
            totals = {}
            for row in rows:
                item = dict(row)
                method = str(item.get("pm", "") or "")
                if method == "mixed":
                    breakdown = parse_payment_breakdown(item.get("breakdown", ""))
                    if breakdown:
                        for component, amount in breakdown.items():
                            bucket = totals.setdefault(component, {"pm": component, "cnt": 0, "amt": 0.0})
                            bucket["cnt"] += 1
                            bucket["amt"] += amount
                        continue
                bucket = totals.setdefault(method, {"pm": method, "cnt": 0, "amt": 0.0})
                bucket["cnt"] += 1
                bucket["amt"] += float(item.get("amt", 0.0) or 0.0)
            for bucket in totals.values():
                bucket["amt"] = round(bucket["amt"], 2)
            return list(totals.values())
        finally:
            conn.close()

    def get_refund_stats_by_date(self, start_date, end_date=None):
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS count, COALESCE(SUM(total_price), 0) AS amount_sum
                   FROM sales WHERE DATE(refunded_at) BETWEEN ? AND ? AND payment_status=?""",
                (s_str, e_str, REFUNDED),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_today_summary(self):
        today_str = date.today().strftime("%Y-%m-%d")
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS count, COALESCE(SUM(weight_kg), 0) AS total_weight,
                          COALESCE(SUM(total_price), 0) AS total_amount
                   FROM sales WHERE created_at LIKE ? AND payment_status=?""",
                ("%s%%" % today_str, PAID),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_sales_by_date(self, start_date, end_date=None):
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM sales WHERE DATE(created_at) BETWEEN ? AND ? ORDER BY id DESC",
                (s_str, e_str),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_stats_by_date(self, start_date, end_date=None):
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS count, COALESCE(SUM(weight_kg), 0) AS weight_sum,
                          COALESCE(SUM(total_price), 0) AS amount_sum
                   FROM sales WHERE DATE(created_at) BETWEEN ? AND ? AND payment_status=?""",
                (s_str, e_str, PAID),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_recent_sales(self, limit=20):
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT * FROM sales ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def record_official_revenue(self, order_key, platform, order_id, amount,
                                payment_status="PAID", source="takeout_relay",
                                created_at=None, order_no="", payment_method="",
                                payment_breakdown_json=""):
        """Persist one verified official-POS amount, once per stable order key."""
        key = str(order_key or "").strip()
        try:
            value = float(amount)
        except (TypeError, ValueError):
            return False
        if not key or value < 0 or str(payment_status or "").upper() != PAID:
            return False
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO official_pos_revenue
                   (order_key, platform, order_id, order_no, amount, payment_status,
                    payment_method, payment_breakdown_json, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, str(platform or ""), str(order_id or ""), str(order_no or ""), round(value, 2),
                 PAID, str(payment_method or ""), str(payment_breakdown_json or ""),
                 str(source or "takeout_relay"), str(created_at or _now_text())),
            )
            conn.commit()
            return bool(cursor.rowcount)
        finally:
            conn.close()

    def record_official_refund(self, refund_key, refund_receipt_key, order_no,
                               amount, order_id="", observed_at=None):
        """Record a refund and link it to the original official revenue row.

        Refund slips from this POS often contain only ``POS#001`` instead of
        the long order id.  Matching therefore requires both normalized call
        number and absolute amount; ambiguous or missing matches remain in the
        refund ledger as UNMATCHED and never alter revenue silently.
        """
        key = str(refund_key or "").strip()
        if not key:
            return {"linked": False, "status": "UNMATCHED", "reason": "退款缺少稳定票据键"}
        try:
            refund_amount = abs(float(amount))
        except (TypeError, ValueError):
            refund_amount = 0.0
        refund_amount = round(refund_amount, 2)
        now = str(observed_at or _now_text())
        normalized_call = normalize_official_call_no(order_no)
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT * FROM official_pos_refunds WHERE refund_key=?", (key,)
            ).fetchone()
            if existing is not None:
                return {
                    "linked": existing["status"] == "LINKED",
                    "status": existing["status"],
                    "original_order_key": existing["original_order_key"],
                    "reason": existing["match_reason"],
                }

            candidates = []
            rows = conn.execute(
                """SELECT v.*, COALESCE(NULLIF(v.order_no, ''), r.order_no, '')
                          AS match_order_no
                   FROM official_pos_revenue v
                   LEFT JOIN official_pos_receipts r ON r.receipt_key=v.order_key
                   WHERE v.payment_status=?""",
                (PAID,),
            ).fetchall()
            for row in rows:
                row_call = normalize_official_call_no(row["match_order_no"])
                call_matches = bool(normalized_call and row_call and normalized_call == row_call)
                id_matches = bool(order_id and row["order_id"] and str(order_id) == str(row["order_id"]))
                amount_matches = abs(float(row["amount"] or 0) - refund_amount) <= 0.01
                if (id_matches or call_matches) and amount_matches:
                    candidates.append(row)

            linked = len(candidates) == 1
            status = "LINKED" if linked else "UNMATCHED"
            reason = (
                "完整订单号+金额匹配" if linked and order_id and candidates[0]["order_id"] == str(order_id)
                else ("规范化叫号+金额匹配" if linked else "未找到唯一的已结账原单")
            )
            original = candidates[0] if linked else None
            conn.execute(
                """INSERT INTO official_pos_refunds
                   (refund_key, refund_receipt_key, refund_order_no, refund_amount,
                    original_order_key, original_order_id, status, match_reason, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, str(refund_receipt_key or ""), str(order_no or ""), refund_amount,
                 str(original["order_key"] if original else ""),
                 str(original["order_id"] if original else ""), status, reason, now),
            )
            if linked:
                conn.execute(
                    """UPDATE official_pos_revenue
                       SET payment_status='REFUNDED', refunded_at=?,
                           refund_amount=?, refund_receipt_key=?
                       WHERE order_key=? AND payment_status=?""",
                    (now, refund_amount, str(refund_receipt_key or ""),
                     original["order_key"], PAID),
                )
            conn.commit()
            return {
                "linked": linked,
                "status": status,
                "original_order_key": str(original["order_key"] if original else ""),
                "original_order_id": str(original["order_id"] if original else ""),
                "reason": reason,
            }
        finally:
            conn.close()

    def record_official_receipt(self, receipt_key, parsed=None, payload_type="",
                                capture_path="", observed_at=None):
        """Persist a generic official-POS receipt without assuming payment.

        Reprints update the observation count but do not create a second
        revenue row. The caller separately decides whether the evidence is
        strong enough for ``record_official_revenue``.
        """
        parsed = parsed or {}
        key = str(receipt_key or parsed.get("receipt_key") or "").strip()
        if not key:
            return False, None
        amount = parsed.get("order_amount")
        try:
            amount = None if amount is None else round(float(amount), 2)
        except (TypeError, ValueError):
            amount = None
        now = str(observed_at or _now_text())
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO official_pos_receipts
                   (receipt_key, receipt_kind, platform, order_id, order_no,
                    amount, amount_valid, payment_status, payment_method,
                    payment_breakdown_json, payment_status_confidence,
                    key_confidence, payload_type, capture_path, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    str(parsed.get("receipt_kind", "unknown") or "unknown"),
                    str(parsed.get("platform", "") or ""),
                    str(parsed.get("full_order_id", "") or ""),
                    str(parsed.get("order_no", "") or ""),
                    amount,
                    1 if parsed.get("amount_valid") is True else 0,
                    str(parsed.get("payment_status", "unknown") or "unknown"),
                    str(parsed.get("payment_method", "") or ""),
                    str(parsed.get("payment_breakdown_json", "") or ""),
                    str(parsed.get("payment_status_confidence", "unknown") or "unknown"),
                    str(parsed.get("key_confidence", "low") or "low"),
                    str(payload_type or parsed.get("payload_type", "") or ""),
                    str(capture_path or parsed.get("capture_path", "") or ""),
                    now,
                ),
            )
            created = bool(cursor.rowcount)
            if not created:
                existing = conn.execute(
                    "SELECT amount, payment_status, payment_method, payment_breakdown_json FROM official_pos_receipts WHERE receipt_key=?",
                    (key,),
                ).fetchone()
                conflict = False
                if existing is not None:
                    old_amount = existing[0]
                    if amount is not None and old_amount is not None:
                        conflict = round(float(old_amount), 2) != round(float(amount), 2)
                    old_status = str(existing[1] or "unknown").lower()
                    new_status = str(parsed.get("payment_status", "unknown") or "unknown").lower()
                    if old_status != "unknown" and new_status != "unknown" and old_status != new_status:
                        conflict = True
                conn.execute(
                    """UPDATE official_pos_receipts
                       SET observed_at=?, print_count=print_count+1,
                           is_duplicate=1,
                           conflict_detected=CASE WHEN ? THEN 1 ELSE conflict_detected END,
                           amount=CASE WHEN amount IS NULL THEN ? ELSE amount END,
                           amount_valid=CASE WHEN amount_valid=0 AND ? THEN 1 ELSE amount_valid END,
                           payment_status=CASE WHEN payment_status='unknown' AND ? <> 'unknown' THEN ? ELSE payment_status END,
                           payment_method=CASE WHEN payment_method='' AND ? <> '' THEN ? ELSE payment_method END,
                           payment_breakdown_json=CASE WHEN payment_breakdown_json='' AND ? <> '' THEN ? ELSE payment_breakdown_json END,
                           payment_status_confidence=CASE WHEN payment_status='unknown' AND ? <> 'unknown' THEN ? ELSE payment_status_confidence END,
                           payload_type=COALESCE(NULLIF(?, ''), payload_type),
                           capture_path=COALESCE(NULLIF(?, ''), capture_path)
                       WHERE receipt_key=?""",
                    (
                        now, 1 if conflict else 0, amount,
                        1 if parsed.get("amount_valid") is True else 0,
                        str(parsed.get("payment_status", "unknown") or "unknown").lower(),
                        str(parsed.get("payment_status", "unknown") or "unknown"),
                        str(parsed.get("payment_method", "") or ""),
                        str(parsed.get("payment_method", "") or ""),
                        str(parsed.get("payment_breakdown_json", "") or ""),
                        str(parsed.get("payment_breakdown_json", "") or ""),
                        str(parsed.get("payment_status", "unknown") or "unknown").lower(),
                        str(parsed.get("payment_status_confidence", "unknown") or "unknown"),
                        str(payload_type or ""), str(capture_path or ""), key,
                    ),
                )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM official_pos_receipts WHERE receipt_key=?", (key,)
            ).fetchone()
            return created, (dict(row) if row else None)
        finally:
            conn.close()

    def get_official_receipts(self, start_date=None, end_date=None, limit=200):
        """Return generic official-POS receipt observations for diagnostics."""
        clauses = []
        params = []
        if start_date:
            clauses.append("DATE(observed_at) >= ?")
            params.append(str(start_date))
        if end_date:
            clauses.append("DATE(observed_at) <= ?")
            params.append(str(end_date))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM official_pos_receipts%s ORDER BY id DESC LIMIT ?" % where,
                tuple(params + [max(1, int(limit or 200))]),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def record_relay_mode_event(self, previous_mode, new_mode, policy="auto",
                                reason="", created_at=None):
        """Keep mode transitions auditable without rewriting past decisions."""
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO relay_mode_events
                   (previous_mode, new_mode, policy, reason, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(previous_mode or ""), str(new_mode or ""),
                 str(policy or "auto"), str(reason or "")[:500],
                 str(created_at or _now_text())),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_relay_mode_events(self, start_date=None, end_date=None, limit=200):
        clauses = []
        params = []
        if start_date:
            clauses.append("DATE(created_at) >= ?")
            params.append(str(start_date))
        if end_date:
            clauses.append("DATE(created_at) <= ?")
            params.append(str(end_date))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM relay_mode_events%s ORDER BY id DESC LIMIT ?" % where,
                tuple(params + [max(1, int(limit or 200))]),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_official_stats_by_date(self, start_date, end_date=None):
        """Return only persisted, verified official-POS revenue for a range."""
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS amount_sum
                   FROM official_pos_revenue
                   WHERE DATE(created_at) BETWEEN ? AND ? AND payment_status=?""",
                (s_str, e_str, PAID),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def get_official_revenue_by_date(self, start_date, end_date=None):
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT v.*,
                          COALESCE(NULLIF(v.payment_method, ''), r.payment_method, '') AS payment_method,
                          COALESCE(NULLIF(v.payment_breakdown_json, ''), r.payment_breakdown_json, '') AS payment_breakdown_json
                   FROM official_pos_revenue v
                   LEFT JOIN official_pos_receipts r ON r.receipt_key=v.order_key
                   WHERE DATE(v.created_at) BETWEEN ? AND ? AND v.payment_status=?
                   ORDER BY v.created_at ASC""",
                (s_str, e_str, PAID),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def record_takeout_order(self, order_key, parsed=None, job=None,
                             duplicate=False, observed_at=None):
        """Persist parsed external-order metadata with a stable dedup key."""
        parsed = parsed or {}
        job = job or {}
        key = str(order_key or job.get("key") or "").strip()
        if not key:
            return False
        item_names = parsed.get("item_names") or []
        try:
            item_json = json.dumps([str(item) for item in item_names], ensure_ascii=False)
        except (TypeError, ValueError):
            item_json = "[]"
        amount = job.get("order_amount", parsed.get("order_amount"))
        try:
            amount = None if amount is None else round(float(amount), 2)
        except (TypeError, ValueError):
            amount = None
        created_at = str(job.get("created_at") or observed_at or _now_text())
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO takeout_orders
                   (order_key, platform, full_order_id, order_no, amount,
                    amount_valid, payment_status, payment_status_confidence,
                    key_confidence, item_count, item_names_json, is_duplicate,
                    conflict_detected, created_at, printed_at, print_count,
                    last_result, last_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    str(job.get("platform", parsed.get("platform", "外卖订单")) or ""),
                    str(job.get("full_order_id", parsed.get("full_order_id", "")) or ""),
                    str(job.get("order_no", parsed.get("order_no", "")) or ""),
                    amount,
                    1 if job.get("amount_valid", parsed.get("amount_valid")) is True else 0,
                    str(job.get("payment_status", parsed.get("payment_status", "unknown")) or "unknown"),
                    str(job.get("payment_status_confidence", parsed.get("payment_status_confidence", "unknown")) or "unknown"),
                    str(job.get("key_confidence", "low") or "low"),
                    int(parsed.get("item_count", job.get("item_count", 0)) or 0),
                    item_json,
                    1 if duplicate else 0,
                    1 if job.get("conflict_detected") else 0,
                    created_at,
                    str(job.get("printed_at", "") or ""),
                    int(job.get("print_count", 0) or 0),
                    str(job.get("last_result", "PENDING") or "PENDING"),
                    str(job.get("last_error", "") or "")[:300],
                ),
            )
            if not cursor.rowcount and str(parsed.get("payment_status", "unknown") or "unknown").lower() in ("paid", "cancelled"):
                conn.execute(
                    """UPDATE takeout_orders
                       SET payment_status=CASE WHEN payment_status='unknown' THEN ? ELSE payment_status END,
                           payment_status_confidence=CASE WHEN payment_status='unknown' THEN ? ELSE payment_status_confidence END,
                           amount=CASE WHEN amount IS NULL THEN ? ELSE amount END,
                           amount_valid=CASE WHEN amount_valid=0 AND ? THEN 1 ELSE amount_valid END,
                           is_duplicate=1
                       WHERE order_key=?""",
                    (
                        str(parsed.get("payment_status") or "unknown"),
                        str(parsed.get("payment_status_confidence") or "unknown"),
                        amount,
                        1 if parsed.get("amount_valid") is True else 0,
                        key,
                    ),
                )
            conn.commit()
            return bool(cursor.rowcount)
        finally:
            conn.close()

    def update_takeout_order_print_result(self, order_key, success, copies, error=""):
        key = str(order_key or "").strip()
        if not key:
            return False
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE takeout_orders
                   SET printed_at=?, print_count=print_count+?, last_result=?, last_error=?
                   WHERE order_key=?""",
                (_now_text(), max(0, int(copies or 0)), "PRINTED" if success else "FAILED",
                 "" if success else str(error or "打印失败")[:300], key),
            )
            conn.commit()
            return bool(cursor.rowcount)
        finally:
            conn.close()

    def get_takeout_orders_by_date(self, start_date, end_date=None):
        s_str = start_date.strftime("%Y-%m-%d") if hasattr(start_date, "strftime") else str(start_date)
        e_str = end_date.strftime("%Y-%m-%d") if end_date and hasattr(end_date, "strftime") else (str(end_date) if end_date else s_str)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM takeout_orders
                   WHERE DATE(created_at) BETWEEN ? AND ? ORDER BY created_at DESC, id DESC""",
                (s_str, e_str),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def _switch_stat_date(stat_date=None):
        value = stat_date or date.today()
        return value.strftime("%Y-%m-%d") if hasattr(value, "strftime") else str(value)

    def get_switch_quota_state(self, stat_date=None):
        """Return today's persisted routing counters.

        These counters describe scale routing decisions only.  They are not
        sales and therefore must not be interpreted as official POS revenue.
        """
        key = self._switch_stat_date(stat_date)
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM switch_quota_daily WHERE stat_date = ?", (key,)
            ).fetchone()
            if row:
                return dict(row)
            return {
                "stat_date": key,
                "total_weight_kg": 0.0,
                "private_weight_kg": 0.0,
                "total_decisions": 0,
                "private_decisions": 0,
                "official_decisions": 0,
                "forced_official_decisions": 0,
                "inherited_private": 0,
                "inherited_official": 0,
                "inherited_total_weight_kg": 0.0,
                "inherited_private_weight_kg": 0.0,
                "last_official_route_at": 0.0,
                "updated_at": "",
            }
        finally:
            conn.close()

    def get_last_official_route_at(self):
        """Return the latest persisted official continuity-lock timestamp."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(last_official_route_at), 0) AS value "
                "FROM switch_quota_daily"
            ).fetchone()
            return float((row["value"] if row else 0.0) or 0.0)
        finally:
            conn.close()

    def set_last_official_route_at(self, timestamp, stat_date=None):
        """Persist the final official routing decision for restart continuity."""
        key = self._switch_stat_date(stat_date)
        value = max(0.0, float(timestamp or 0.0))
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO switch_quota_daily (stat_date, updated_at) VALUES (?, ?)",
                (key, _now_text()),
            )
            conn.execute(
                "UPDATE switch_quota_daily SET last_official_route_at = ?, updated_at = ? "
                "WHERE stat_date = ?",
                (value, _now_text(), key),
            )
            conn.commit()
        finally:
            conn.close()

    def clear_last_official_route_at(self):
        """Clear every persisted lock after a manual/fallback channel change."""
        conn = self._get_conn()
        try:
            conn.execute("UPDATE switch_quota_daily SET last_official_route_at = 0")
            conn.commit()
        finally:
            conn.close()

    def record_switch_quota_decision(self, weight_kg, is_private, forced_official=False, stat_date=None):
        """Persist one new (non-inherited) scale routing decision."""
        key = self._switch_stat_date(stat_date)
        weight = max(0.0, float(weight_kg or 0.0))
        now = _now_text()
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO switch_quota_daily (stat_date, updated_at) VALUES (?, ?)",
                (key, now),
            )
            conn.execute(
                """UPDATE switch_quota_daily
                   SET total_weight_kg = total_weight_kg + ?,
                       private_weight_kg = private_weight_kg + ?,
                       total_decisions = total_decisions + 1,
                       private_decisions = private_decisions + ?,
                       official_decisions = official_decisions + ?,
                       forced_official_decisions = forced_official_decisions + ?,
                       updated_at = ?
                   WHERE stat_date = ?""",
                (
                    weight,
                    weight if is_private else 0.0,
                    1 if is_private else 0,
                    0 if is_private else 1,
                    1 if forced_official else 0,
                    now,
                    key,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_switch_inherited(self, weight_kg, is_private, stat_date=None):
        """Persist a continuation's weight without consuming a new quota decision."""
        key = self._switch_stat_date(stat_date)
        weight = max(0.0, float(weight_kg or 0.0))
        now = _now_text()
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO switch_quota_daily (stat_date, updated_at) VALUES (?, ?)",
                (key, now),
            )
            conn.execute(
                """UPDATE switch_quota_daily
                   SET inherited_private = inherited_private + ?,
                       inherited_official = inherited_official + ?,
                       inherited_total_weight_kg = inherited_total_weight_kg + ?,
                       inherited_private_weight_kg = inherited_private_weight_kg + ?,
                       updated_at = ?
                   WHERE stat_date = ?""",
                (
                    1 if is_private else 0,
                    0 if is_private else 1,
                    weight,
                    weight if is_private else 0.0,
                    now,
                    key,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def convert_switch_decision_to_private(self, weight_kg, forced_official=False, stat_date=None):
        """Correct a just-recorded official route when its window vanished."""
        key = self._switch_stat_date(stat_date)
        weight = max(0.0, float(weight_kg or 0.0))
        now = _now_text()
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE switch_quota_daily
                   SET private_weight_kg = private_weight_kg + ?,
                       private_decisions = private_decisions + 1,
                       official_decisions = MAX(0, official_decisions - 1),
                       forced_official_decisions = MAX(0, forced_official_decisions - ?),
                       updated_at = ?
                   WHERE stat_date = ?""",
                (weight, 1 if forced_official else 0, now, key),
            )
            conn.commit()
        finally:
            conn.close()

    def convert_switch_inherited_to_private(self, weight_kg, stat_date=None):
        """Correct a just-recorded official continuation when its window vanished."""
        key = self._switch_stat_date(stat_date)
        weight = max(0.0, float(weight_kg or 0.0))
        now = _now_text()
        conn = self._get_conn()
        try:
            conn.execute(
                """UPDATE switch_quota_daily
                   SET inherited_private = inherited_private + 1,
                       inherited_official = MAX(0, inherited_official - 1),
                       inherited_private_weight_kg = inherited_private_weight_kg + ?,
                       updated_at = ?
                   WHERE stat_date = ?""",
                (weight, now, key),
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Stable-weighing lifecycle ledger
    # ------------------------------------------------------------------
    def create_weighing_route_event(
        self, weight_kg, is_private, decision_kind="", event_key=None, order_id="",
        routing_basis="weight", operating_mode="compatibility",
        official_receipt_key="", estimated_amount=0.0,
    ):
        """Create a pending record for one stable weighing decision.

        The routing quota remains an immediate, observable-weight counter so
        the POS can switch without waiting for payment.  This ledger carries
        the separate truth state: private payment can later be confirmed,
        while official payment is explicitly unknown.
        """
        import uuid

        key = str(event_key or uuid.uuid4().hex)
        channel = "private" if is_private else "official"
        weight = max(0.0, float(weight_kg or 0.0))
        now = _now_text()
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO weighing_route_events
                   (event_key, weight_kg, channel, decision_kind, status, order_id,
                    routing_basis, operating_mode, official_receipt_key,
                    estimated_amount, created_at)
                   VALUES (?, ?, ?, ?, 'PENDING', ?, ?, ?, ?, ?, ?)""",
                (
                    key, weight, channel, str(decision_kind or ""), str(order_id or ""),
                    str(routing_basis or "weight"), str(operating_mode or "compatibility"),
                    str(official_receipt_key or ""), max(0.0, float(estimated_amount or 0.0)), now,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM weighing_route_events WHERE event_key = ?", (key,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def resolve_weighing_route_event(self, event_key, status, order_id=None, note=""):
        """Resolve one pending event without deleting its audit trail.

        ``order_id=None`` preserves a route's existing order binding.  A
        lifecycle change such as "not paid" must never erase the identity of
        the order that originally selected that bowl.
        """
        if not event_key:
            return False
        allowed = {"PRIVATE_PAID", "NOT_PAID", "OFFICIAL_UNKNOWN", "MANUAL_UNKNOWN"}
        status = str(status or "").upper()
        if status not in allowed:
            raise ValueError("invalid weighing route status: %s" % status)
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET status = ?, order_id = COALESCE(?, order_id), resolved_at = ?, resolution_note = ?
                   WHERE event_key = ? AND status = 'PENDING'""",
                (
                    status,
                    None if order_id is None else str(order_id),
                    _now_text(),
                    str(note or "")[:500],
                    str(event_key),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def assign_weighing_route_event_order(self, event_key, order_id):
        """Bind one still-pending private route to the soup line just added."""
        if not event_key or not order_id:
            return False
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET order_id = ?
                   WHERE event_key = ? AND channel = 'private' AND status = 'PENDING'
                     AND (order_id IS NULL OR order_id = '')""",
                (str(order_id), str(event_key)),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def convert_weighing_route_event_to_private(
        self, event_key, note="官方窗口在切换竞态中消失", order_id=""
    ):
        """Correct an event whose initial official route fell back to private."""
        if not event_key:
            return False
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET channel = 'private', order_id = ?, resolution_note = ?
                   WHERE event_key = ? AND status = 'PENDING'""",
                (str(order_id or ""), str(note or "")[:500], str(event_key)),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def resolve_pending_weighing_events(self, channel=None, status="NOT_PAID", note=""):
        """Resolve all current-day pending events matching ``channel``.

        Returning the count lets the UI log what happened without exposing
        SQLite details to the checkout flow.
        """
        status = str(status or "").upper()
        allowed = {"PRIVATE_PAID", "NOT_PAID", "OFFICIAL_UNKNOWN", "MANUAL_UNKNOWN"}
        if status not in allowed:
            raise ValueError("invalid weighing route status: %s" % status)
        where = "status = 'PENDING' AND DATE(created_at) = DATE('now', 'localtime')"
        params = []
        if channel:
            where += " AND channel = ?"
            params.append(str(channel))
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET status = ?, resolved_at = ?, resolution_note = ?
                   WHERE """ + where,
                [status, _now_text(), str(note or "")[:500]] + params,
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def resolve_pending_private_weighing_events(self, status, order_id="", note=""):
        """Resolve only the pending private events owned by one local order.

        A former broad current-day update allowed a later customer to confirm
        or cancel an orphaned route event from an earlier interrupted order.
        An empty id intentionally matches nothing; old unbound rows remain
        auditable instead of being guessed as part of a new checkout.
        """
        status = str(status or "").upper()
        allowed = {"PRIVATE_PAID", "NOT_PAID", "MANUAL_UNKNOWN"}
        if status not in allowed:
            raise ValueError("invalid private route status: %s" % status)
        order_id = str(order_id or "")
        if not order_id:
            return 0
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET status = ?, order_id = ?, resolved_at = ?, resolution_note = ?
                   WHERE channel = 'private' AND status = 'PENDING' AND order_id = ?
                     AND DATE(created_at) = DATE('now', 'localtime')""",
                (status, order_id, _now_text(), str(note or "")[:500], order_id),
            )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def get_weighing_route_summary(self, stat_date=None):
        """Return confirmed/unknown route-event totals for diagnostics/UI."""
        key = self._switch_stat_date(stat_date)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT channel, status, COUNT(*) AS count,
                          COALESCE(SUM(weight_kg), 0) AS weight_kg
                   FROM weighing_route_events
                   WHERE DATE(created_at) = ?
                   GROUP BY channel, status
                   ORDER BY channel, status""",
                (key,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_weighing_route_events(self, stat_date=None):
        """Return the day's individual weighing decisions for visualisation.

        This is intentionally a read-only view of the route-event ledger.  A
        chart must show every stable weighing decision, including official
        events whose payment is unknown, so it must not be built from the
        sales table or from the quota aggregate alone.
        """
        key = self._switch_stat_date(stat_date)
        conn = self._get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM weighing_route_events
                   WHERE DATE(created_at) = ?
                   ORDER BY created_at ASC, id ASC""",
                (key,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
