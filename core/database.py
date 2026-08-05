"""SQLite 交易账本。

订单一旦确认支付便不能物理删除；打印和退款是订单上的状态变化。这样在
打印机故障、重复点击或程序重启后，门店仍能找到同一笔交易并继续处理。
"""
import os
import shutil
import sqlite3
from datetime import date, datetime

from config import DATA_DIR, DB_PATH


PAID = "PAID"
REFUNDED = "REFUNDED"
PRINT_PENDING = "PENDING"
PRINTED = "PRINTED"
PRINT_FAILED = "FAILED"


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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

                -- Routing statistics are deliberately separate from sales:
                -- official POS payments are not written to this database,
                -- while the scale routing decision is still observable.
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
                    created_at      TEXT NOT NULL,
                    resolved_at     TEXT DEFAULT '',
                    resolution_note TEXT DEFAULT ''
                );
                """
            )

            # Existing stores upgrade in place.  Legacy completed orders are
            # preserved as paid/printed instead of being guessed as failures.
            upgrades = {
                "order_id": "TEXT",
                "cart_items_json": "TEXT",
                "payment_method": "TEXT DEFAULT ''",
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
            }
            for name, definition in switch_upgrades.items():
                self._ensure_column(conn, name, definition, table="switch_quota_daily")

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
                    remark, created_at, payment_method, payment_status,
                    payment_confirmed_at, cart_items_json, printed, print_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
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
                """SELECT COALESCE(payment_method, '') AS pm, COUNT(*) AS cnt,
                          COALESCE(SUM(total_price), 0) AS amt
                   FROM sales WHERE DATE(created_at) BETWEEN ? AND ?
                     AND payment_status = ? GROUP BY pm""",
                (s_str, e_str, PAID),
            ).fetchall()
            return [dict(row) for row in rows]
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
                "updated_at": "",
            }
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
    def create_weighing_route_event(self, weight_kg, is_private, decision_kind="", event_key=None):
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
                   (event_key, weight_kg, channel, decision_kind, status, created_at)
                   VALUES (?, ?, ?, ?, 'PENDING', ?)""",
                (key, weight, channel, str(decision_kind or ""), now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM weighing_route_events WHERE event_key = ?", (key,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def resolve_weighing_route_event(self, event_key, status, order_id="", note=""):
        """Resolve one pending event without deleting its audit trail."""
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
                   SET status = ?, order_id = ?, resolved_at = ?, resolution_note = ?
                   WHERE event_key = ? AND status = 'PENDING'""",
                (status, str(order_id or ""), _now_text(), str(note or "")[:500], str(event_key)),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def convert_weighing_route_event_to_private(self, event_key, note="官方窗口在切换竞态中消失"):
        """Correct an event whose initial official route fell back to private."""
        if not event_key:
            return False
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET channel = 'private', resolution_note = ?
                   WHERE event_key = ? AND status = 'PENDING'""",
                (str(note or "")[:500], str(event_key)),
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
        """Resolve pending private events for the current unfinished basket."""
        status = str(status or "").upper()
        allowed = {"PRIVATE_PAID", "NOT_PAID", "MANUAL_UNKNOWN"}
        if status not in allowed:
            raise ValueError("invalid private route status: %s" % status)
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """UPDATE weighing_route_events
                   SET status = ?, order_id = ?, resolved_at = ?, resolution_note = ?
                   WHERE channel = 'private' AND status = 'PENDING'
                     AND DATE(created_at) = DATE('now', 'localtime')""",
                (status, str(order_id or ""), _now_text(), str(note or "")[:500]),
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
