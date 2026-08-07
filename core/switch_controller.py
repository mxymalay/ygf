"""
智能双系统全自动流转决策引擎 (Smart Quota Auto-Decision Engine)
根据【重量门限】与【目标比例抽样算法】，全自动决策本单走官方还是走私域！
"""
import time
from datetime import date
from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from utils.window_utils import (
    bring_official_to_front,
    bring_our_pos_to_front,
    is_official_pos_available,
)
from core.app_logger import log_event, CAT_SCALE, CAT_DECISION, CAT_SWITCH, CAT_PRINT


def _safe_console(message):
    """Best-effort diagnostics that can never abort a Win7 weighing slot."""
    try:
        print(str(message))
    except Exception:
        return


def _config_float(config, key, default):
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def _config_int(config, key, default):
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return int(default)


class AutoSwitchController(QObject):
    """双系统智能决策控制器"""

    def __init__(self, main_window, config: dict, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.config = config

        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = max(0, _config_int(self.config, "auto_hide_delay_sec", 10))
        self._target_private_ratio = min(100.0, max(0.0, _config_float(self.config, "private_ratio_percent", 30)))
        amount_ratio_default = _config_float(self.config, "private_ratio_percent", 30)
        self._target_private_amount_ratio = min(
            100.0,
            max(0.0, _config_float(
                self.config,
                "private_amount_ratio_percent",
                amount_ratio_default,
            )),
        )
        self._min_private_weight = max(0.0, _config_float(self.config, "min_private_weight_kg", 0.25))
        self._official_lock_sec = max(0.0, _config_float(self.config, "official_lock_sec", 60.0))
        self._min_valid_weight = max(0.0, _config_float(self.config, "min_valid_weight_kg", 0.08))
        self._manual_override_lock_sec = max(0.0, _config_float(self.config, "manual_override_lock_sec", 30.0))
        self._load_daily_revenue_limits()

        # Quota counters are persisted per local day.  The official POS does
        # not expose its payment amount, so the routing target uses observable
        # scale weight instead of pretending that order counts equal revenue.
        self._total_evaluated_orders = 0
        self._private_orders_count = 0
        self._official_orders_count = 0
        self._total_weight_kg = 0.0
        self._private_weight_kg = 0.0
        self._forced_official_orders = 0
        self._inherited_private_orders = 0
        self._inherited_official_orders = 0
        self._quota_stat_date = date.today().isoformat()
        # Set before loading persisted state; a restart must not overwrite a
        # still-valid official continuity lock with a new zero value.
        self._last_official_time = 0.0
        self._load_persisted_quota_state()

        self._has_auto_popped = False  # 防止在同一个重量上重复判断
        # 记录上一次判定为官方 POS 的时间戳 (用于官方连单保护)。值可由
        # `_load_persisted_quota_state` 在冷启动时恢复。
        self._manual_override_until = 0.0  # 店员手动干预锁定期 (防止称重自动抢抓焦点)
        # Daily first-order baseline. None means no manual override: the first
        # automatic decision prefers the official POS when it is available.
        self._daily_first_channel_override = None
        self._zero_start_time = 0.0  # 记录归零起始时间戳
        self._last_popped_weight = 0.0  # 记录本称重周期最终用于分流的稳定重量
        self._current_is_private = False
        self._last_decision_kind = ""
        self._last_decision_reason = ""
        # Key of the latest stable weighing lifecycle record.  The quota is
        # recorded immediately for routing, while this separate record waits
        # for private payment confirmation (or an explicit non-payment state).
        self._last_route_event_key = ""
        self._last_route_event_channel = ""
        self._last_route_event_order_id = ""
        # 当前“通道周期”的切换进度：例如官方连续收单时，累计了多少
        # 官方重量后会越过目标比例并切回私有 POS。它不是全天配额统计。
        self._switch_cycle_initialized = False
        self._switch_cycle_is_private = None
        self._switch_cycle_start_total_weight = 0.0
        self._switch_cycle_start_private_weight = 0.0
        # Hardware maintenance may briefly reconnect a scale or emit a stale
        # non-zero reading. It must never trigger focus/minimise automation
        # while an operator is creating, testing or deleting COM resources.
        self._maintenance_pause_count = 0
        # After printing, do not cancel the return-to-official timer merely
        # because the old bowl keeps emitting the same non-zero reading.  A
        # real next bowl cancels it only after a zero crossing is observed.
        self._receipt_hide_pending = False
        self._receipt_zero_seen = False
        self._last_weight_kg = 0.0

        # 退场延时定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_auto_hide_timeout)

    def _load_daily_revenue_limits(self):
        """读取四组星期累计收款上限，并兼容旧版配置。"""
        legacy_present = "max_daily_revenue_limit" in self.config
        legacy = max(0.0, _config_float(self.config, "max_daily_revenue_limit", 500.0))
        weekday = max(0.0, _config_float(self.config, "weekday_max_daily_revenue_limit", legacy))
        weekend = max(
            0.0,
            _config_float(
                self.config,
                "weekend_max_daily_revenue_limit",
                legacy if legacy_present else 1000.0,
            ),
        )
        self._mon_thu_max_daily_revenue_limit = max(
            0.0, _config_float(self.config, "mon_thu_max_daily_revenue_limit", weekday)
        )
        self._friday_max_daily_revenue_limit = max(
            0.0, _config_float(self.config, "friday_max_daily_revenue_limit", weekday)
        )
        self._saturday_max_daily_revenue_limit = max(
            0.0, _config_float(self.config, "saturday_max_daily_revenue_limit", weekend)
        )
        self._sunday_max_daily_revenue_limit = max(
            0.0, _config_float(self.config, "sunday_max_daily_revenue_limit", weekend)
        )
        # Keep the old attributes for integrations that still inspect them.
        self._weekday_max_daily_revenue_limit = self._mon_thu_max_daily_revenue_limit
        self._weekend_max_daily_revenue_limit = self._saturday_max_daily_revenue_limit
        self._max_daily_revenue_limit = self._current_daily_revenue_limit()

    def _current_daily_revenue_limit(self, today=None):
        """按周一至周四、周五、周六、周日选择上限；0 表示不限制。"""
        current = today or date.today()
        limits = (
            self._mon_thu_max_daily_revenue_limit,
            self._mon_thu_max_daily_revenue_limit,
            self._mon_thu_max_daily_revenue_limit,
            self._mon_thu_max_daily_revenue_limit,
            self._friday_max_daily_revenue_limit,
            self._saturday_max_daily_revenue_limit,
            self._sunday_max_daily_revenue_limit,
        )
        limit = limits[min(max(int(current.weekday()), 0), 6)]
        self._max_daily_revenue_limit = max(0.0, float(limit))
        return self._max_daily_revenue_limit

    def _private_daily_limit_reached(self):
        """Return whether today's private-POS paid amount blocks new private routing."""
        daily_limit = self._current_daily_revenue_limit()
        if daily_limit <= 0.0:
            return False
        db = getattr(self.main_window, "db", None)
        if not db or not hasattr(db, "get_today_summary"):
            return False
        try:
            summary = db.get_today_summary() or {}
            return float(summary.get("total_amount", 0.0) or 0.0) >= daily_limit
        except Exception:
            return False

    def notify_manual_switch(self, duration_sec: float = -1.0, is_private=None):
        """店员手动点击悬浮球/快捷键触发：锁定指定秒数内不被称重自动抢抓覆盖"""
        if duration_sec < 0:
            duration_sec = self._manual_override_lock_sec
        self._manual_override_until = time.time() + duration_sec
        # If this is before today's first routed order, remember the explicit
        # operator choice.  It is the only supported way to make the first
        # automatic order start on private POS; otherwise official is the
        # daily baseline.
        if self._total_evaluated_orders == 0 and is_private is not None:
            self._daily_first_channel_override = bool(is_private)
        # A successful manual channel choice must take ownership from every
        # pending automatic action.  Stopping only the floating-ball animation
        # left the real auto-hide timer alive and it could switch windows back
        # under the operator's hand.
        self._cancel_pending_auto_hide()
        # A manual choice begins a new routing context.  Do not let an old
        # official continuation timer reassert itself after the manual grace
        # period expires.
        self._clear_official_continuation_lock()
        self.resolve_pending_route_events_manual("店员手动切换，当前称重渠道无法自动归属")
        log_event(CAT_SWITCH, f"店员手动干预锁定", f"优先尊重店员操作，暂停自动调度 {duration_sec} 秒")

    def _cancel_pending_auto_hide(self):
        """Cancel a post-receipt automatic return in both UI and controller."""
        self._hide_timer.stop()
        self._receipt_hide_pending = False
        self._receipt_zero_seen = False
        fb = getattr(self.main_window, "floating_ball", None)
        if fb and hasattr(fb, "stop_countdown"):
            fb.stop_countdown()

    def suspend_for_maintenance(self):
        """Temporarily block automatic window switching during maintenance."""
        self._maintenance_pause_count += 1
        self._hide_timer.stop()

    def resume_after_maintenance(self):
        """Release one matching maintenance pause without changing settings."""
        if self._maintenance_pause_count > 0:
            self._maintenance_pause_count -= 1

    def _load_persisted_quota_state(self):
        """Restore today's routing counters when the POS is restarted."""
        db = getattr(self.main_window, "db", None)
        if not db or not hasattr(db, "get_switch_quota_state"):
            return
        try:
            state = db.get_switch_quota_state()
            self._total_evaluated_orders = int(state.get("total_decisions", 0) or 0)
            self._private_orders_count = int(state.get("private_decisions", 0) or 0)
            self._official_orders_count = int(state.get("official_decisions", 0) or 0)
            self._total_weight_kg = float(state.get("total_weight_kg", 0.0) or 0.0)
            self._private_weight_kg = float(state.get("private_weight_kg", 0.0) or 0.0)
            self._total_weight_kg += float(state.get("inherited_total_weight_kg", 0.0) or 0.0)
            self._private_weight_kg += float(state.get("inherited_private_weight_kg", 0.0) or 0.0)
            self._forced_official_orders = int(state.get("forced_official_decisions", 0) or 0)
            self._inherited_private_orders = int(state.get("inherited_private", 0) or 0)
            self._inherited_official_orders = int(state.get("inherited_official", 0) or 0)
            get_last = getattr(db, "get_last_official_route_at", None)
            persisted_lock_at = float(get_last() or 0.0) if callable(get_last) else 0.0
            if 0.0 < time.time() - persisted_lock_at < self._official_lock_sec:
                self._last_official_time = persisted_lock_at
        except Exception as exc:
            # A corrupt/legacy runtime statistic must never prevent POS start.
            _safe_console(f"[AutoDecisionEngine] 恢复分流统计失败，使用本次运行统计: {exc}")

    def _set_official_continuation_lock(self, timestamp=None):
        """Set and persist the 60-second official continuity lock."""
        value = float(timestamp if timestamp is not None else time.time())
        self._last_official_time = max(0.0, value)
        db = getattr(self.main_window, "db", None)
        save_lock = getattr(db, "set_last_official_route_at", None)
        if callable(save_lock):
            try:
                save_lock(self._last_official_time)
            except Exception as exc:
                _safe_console(f"[AutoDecisionEngine] 保存官方连单锁失败: {exc}")

    def _clear_official_continuation_lock(self):
        """Clear both in-memory and persisted official continuity state."""
        self._last_official_time = 0.0
        db = getattr(self.main_window, "db", None)
        clear_lock = getattr(db, "clear_last_official_route_at", None)
        if callable(clear_lock):
            try:
                clear_lock()
            except Exception as exc:
                _safe_console(f"[AutoDecisionEngine] 清除官方连单锁失败: {exc}")

    def _ensure_quota_date(self):
        """Switch the in-memory counters when a long-running POS crosses midnight."""
        current = date.today().isoformat()
        if current == self._quota_stat_date:
            return
        self._quota_stat_date = current
        self._total_evaluated_orders = 0
        self._private_orders_count = 0
        self._official_orders_count = 0
        self._total_weight_kg = 0.0
        self._private_weight_kg = 0.0
        self._forced_official_orders = 0
        self._inherited_private_orders = 0
        self._inherited_official_orders = 0
        self._switch_cycle_initialized = False
        self._switch_cycle_is_private = None
        self._switch_cycle_start_total_weight = 0.0
        self._switch_cycle_start_private_weight = 0.0
        self._daily_first_channel_override = None
        self._load_persisted_quota_state()

    def _current_private_order_id(self):
        """Return the local draft id that owns a private weighing event."""
        page = getattr(self.main_window, "sale_page", None)
        return str(getattr(page, "current_order_id", "") or "")

    def _record_quota_decision(
        self, weight_kg, is_private, forced_official=False,
        routing_basis="weight", operating_mode=None, official_receipt_key="",
    ):
        """Update in-memory and persisted counters for a new decision."""
        self._ensure_quota_date()
        weight = max(0.0, float(weight_kg or 0.0))
        self._total_evaluated_orders += 1
        self._total_weight_kg += weight
        if is_private:
            self._private_orders_count += 1
            self._private_weight_kg += weight
        else:
            self._official_orders_count += 1
        if forced_official:
            self._forced_official_orders += 1

        db = getattr(self.main_window, "db", None)
        if operating_mode is None:
            operating_mode = str(self.config.get("printer_relay_mode", "compatibility") or "compatibility")
        if db and hasattr(db, "record_switch_quota_decision"):
            try:
                db.record_switch_quota_decision(weight, is_private, forced_official)
            except Exception as exc:
                # Keep the live decision working even if a removable/locked
                # database cannot be updated on an older Windows installation.
                _safe_console(f"[AutoDecisionEngine] 保存分流统计失败: {exc}")
        self._last_route_event_key = ""
        self._last_route_event_channel = ""
        self._last_route_event_order_id = ""
        if db and hasattr(db, "create_weighing_route_event"):
            try:
                event = db.create_weighing_route_event(
                    weight,
                    is_private,
                    ("forced_official" if forced_official else ("amount" if routing_basis == "amount" else "quota")),
                    # A route is observed before the cashier actually adds a
                    # soup line.  Bind it to an order only after that explicit
                    # UI action, otherwise an unused second weighing can be
                    # incorrectly confirmed as paid with the first bowl.
                    order_id="",
                    routing_basis=routing_basis,
                    operating_mode=operating_mode,
                    official_receipt_key=official_receipt_key,
                    estimated_amount=max(0.0, float(weight or 0.0)) * max(0.0, float(self.config.get("unit_price", 0.0) or 0.0)) if routing_basis == "amount" else 0.0,
                )
                self._last_route_event_key = str((event or {}).get("event_key", "") or "")
                self._last_route_event_channel = "private" if is_private else "official"
            except Exception as exc:
                _safe_console(f"[AutoDecisionEngine] 保存待确认称重记录失败: {exc}")

    def _record_inherited_decision(self, weight_kg, is_private):
        """Track continuation weight without consuming a new quota decision."""
        self._ensure_quota_date()
        weight = max(0.0, float(weight_kg or 0.0))
        self._total_weight_kg += weight
        if is_private:
            self._private_weight_kg += weight
        if is_private:
            self._inherited_private_orders += 1
        else:
            self._inherited_official_orders += 1
        db = getattr(self.main_window, "db", None)
        if db and hasattr(db, "record_switch_inherited"):
            try:
                db.record_switch_inherited(weight, is_private)
            except Exception as exc:
                _safe_console(f"[AutoDecisionEngine] 保存联单统计失败: {exc}")
        self._last_route_event_key = ""
        self._last_route_event_channel = ""
        self._last_route_event_order_id = ""
        if db and hasattr(db, "create_weighing_route_event"):
            try:
                event = db.create_weighing_route_event(
                    weight,
                    is_private,
                    "inherited",
                    order_id="",
                )
                self._last_route_event_key = str((event or {}).get("event_key", "") or "")
                self._last_route_event_channel = "private" if is_private else "official"
            except Exception as exc:
                _safe_console(f"[AutoDecisionEngine] 保存待确认联单记录失败: {exc}")

    def _official_available(self):
        """Check the configured official window before hiding this POS."""
        try:
            return bool(is_official_pos_available(self.config))
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 官方 POS 状态检测失败，按不可用处理: {exc}")
            return False

    def _verified_official_amount_state(self):
        """Return verified official-POS revenue in live enhanced mode.

        The relay status file is intentionally the gate: merely having an
        amount in a printed ticket cannot switch the routing algorithm.
        """
        try:
            from core.printer_relay_host import read_proxy_status, _is_process_alive
            state = read_proxy_status()
            if not state.get("running") or state.get("mode") != "enhanced":
                return 0.0, False
            # The status file is atomically written but can outlive a crashed
            # detached host.  Never keep using amount routing from a stale
            # ``running=true`` snapshot; the next decision must fall back to
            # the compatibility/weight path.
            pid = state.get("pid")
            if pid and not _is_process_alive(pid):
                return 0.0, False
            from datetime import date
            if hasattr(self.main_window, "db") and self.main_window.db:
                summary = self.main_window.db.get_official_stats_by_date(date.today(), date.today())
                return max(0.0, float(summary.get("amount_sum", 0.0) or 0.0)), True
            return 0.0, False
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 读取已验证官方金额失败，继续兼容模式: {exc}")
            return 0.0, False

    # Backward-compatible alias for older integrations that still call the
    # external-order-specific helper name.
    def _verified_takeout_amount_state(self):
        return self._verified_official_amount_state()

    def _amount_route_decision(self, weight_kg):
        """Choose a channel from verified revenue when enhanced mode is live.

        The current bowl amount is an estimate from its observed weight and
        configured unit price; it is never used to prove payment.  If any
        prerequisite is absent, return ``None`` so the old weight algorithm
        remains authoritative.
        """
        verified_external, ready = self._verified_official_amount_state()
        if not ready:
            return None
        db = getattr(self.main_window, "db", None)
        if not db or not hasattr(db, "get_today_summary"):
            return None
        try:
            private_revenue = max(0.0, float(db.get_today_summary().get("total_amount", 0.0) or 0.0))
            unit_price = max(0.0, float(self.config.get("unit_price", 0.0) or 0.0))
            estimated_amount = max(0.0, float(weight_kg or 0.0)) * unit_price
            target = min(1.0, max(0.0, self._target_private_amount_ratio / 100.0))
            total_after_private = private_revenue + verified_external + estimated_amount
            if total_after_private <= 0.0:
                return True
            private_ratio_after = (private_revenue + estimated_amount) / total_after_private
            return private_ratio_after < target
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 金额分流估算失败，继续兼容模式: {exc}")
            return None

    def _amount_switch_progress(self):
        """Return the enhanced-mode switch hint in currency, if available."""
        verified_official, ready = self._verified_official_amount_state()
        if not ready:
            return None
        if not self._switch_cycle_initialized or self._switch_cycle_is_private is None:
            return (0.0, None, "", self._target_private_amount_ratio)
        db = getattr(self.main_window, "db", None)
        if not db or not hasattr(db, "get_today_summary"):
            return None
        try:
            private_amount = max(0.0, float(db.get_today_summary().get("total_amount", 0.0) or 0.0))
            official_amount = max(0.0, float(verified_official or 0.0))
            total = private_amount + official_amount
            target = min(1.0, max(0.0, self._target_private_amount_ratio / 100.0))
            if self._switch_cycle_is_private:
                next_channel = "官方 POS"
                if target >= 1.0:
                    return (0.0, None, next_channel, self._target_private_amount_ratio)
                remaining = (target * total - private_amount) / (1.0 - target)
            else:
                next_channel = "私域 POS"
                if target <= 0.0:
                    return (0.0, None, next_channel, self._target_private_amount_ratio)
                remaining = private_amount / target - total
            return (0.0, max(0.0, remaining), next_channel, self._target_private_amount_ratio)
        except (TypeError, ValueError, AttributeError):
            return None

    def _switch_progress_snapshot(self):
        amount = self._amount_switch_progress()
        if amount is not None:
            progress, remaining, next_channel, target = amount
            return {
                "basis": "amount",
                "progress": progress,
                "remaining_kg": None,
                "remaining_amount": remaining,
                "next_channel": next_channel,
                "target": target,
            }
        progress, remaining, next_channel = self.get_switch_progress_status()
        return {
            "basis": "weight",
            "progress": progress,
            "remaining_kg": remaining,
            "remaining_amount": None,
            "next_channel": next_channel,
            "target": self._target_private_ratio,
        }

    @staticmethod
    def _apply_switch_progress(floating_ball, is_private, snapshot):
        if not floating_ball or not hasattr(floating_ball, "set_switch_progress"):
            return
        has_remaining = (
            snapshot["remaining_kg"] is not None
            or snapshot["remaining_amount"] is not None
        )
        floating_ball.set_switch_progress(
            snapshot["progress"],
            bool(is_private),
            next_is_private=(snapshot["next_channel"] == "私有 POS") if has_remaining else None,
            remaining_kg=snapshot["remaining_kg"],
            next_channel=snapshot["next_channel"],
            remaining_amount=snapshot["remaining_amount"],
        )

    def _fallback_to_private_after_official_failure(self, weight_kg):
        """Undo an official decision if the window disappeared in the race."""
        kind = self._last_decision_kind
        weight = max(0.0, float(weight_kg or 0.0))
        if kind == "quota_official" or kind == "forced_official":
            self._official_orders_count = max(0, self._official_orders_count - 1)
            self._private_orders_count += 1
            self._private_weight_kg += weight
            if kind == "forced_official":
                self._forced_official_orders = max(0, self._forced_official_orders - 1)
            db = getattr(self.main_window, "db", None)
            if db and hasattr(db, "convert_switch_decision_to_private"):
                try:
                    db.convert_switch_decision_to_private(weight, kind == "forced_official")
                except Exception as exc:
                    _safe_console(f"[AutoDecisionEngine] 修正官方配额统计失败: {exc}")
        elif kind == "inherited_official":
            self._inherited_official_orders = max(0, self._inherited_official_orders - 1)
            self._inherited_private_orders += 1
            self._private_weight_kg += weight
            db = getattr(self.main_window, "db", None)
            if db and hasattr(db, "convert_switch_inherited_to_private"):
                try:
                    db.convert_switch_inherited_to_private(weight)
                except Exception as exc:
                    _safe_console(f"[AutoDecisionEngine] 修正官方联单统计失败: {exc}")

        db = getattr(self.main_window, "db", None)
        if db and self._last_route_event_key and hasattr(db, "convert_weighing_route_event_to_private"):
            try:
                db.convert_weighing_route_event_to_private(
                    self._last_route_event_key,
                    "官方窗口在切换竞态中消失，实际留在私有 POS",
                    order_id="",
                )
            except Exception as exc:
                _safe_console(f"[AutoDecisionEngine] 修正待确认渠道失败: {exc}")

        self._clear_official_continuation_lock()
        self._last_route_event_channel = "private"
        self._last_route_event_order_id = ""
        self._last_decision_kind = "fallback_private"
        self._last_decision_reason = "官方 POS 未运行/已关闭，自动留在私有 POS"
        log_event(
            CAT_DECISION,
            "官方 POS 不可用 -> 回退私有 POS",
            f"重量 {weight:.3f}kg | 原决策 {kind or 'unknown'}，未隐藏本 POS",
        )

    def on_weight_changed(self, weight_kg: float):
        """Compatibility hook: raw frames never make routing decisions."""
        self._last_weight_kg = float(weight_kg or 0.0)

    def on_weighing_cycle_zeroed(self):
        """Arm exactly one next bowl after a stable multi-sample zero."""
        self._last_weight_kg = 0.0
        self._has_auto_popped = False
        self._last_popped_weight = 0.0
        self._zero_start_time = time.time()
        if self._receipt_hide_pending:
            self._receipt_zero_seen = True
        # A physical zero only ends this bowl's duplicate-detection cycle. It
        # is not evidence that the customer has left, so it must never shorten
        # the 60-second official continuation lock.
        log_event(CAT_SCALE, "称重周期稳定归零", "已允许下一碗进入分流判断；官方连单锁保持不变")

    def resolve_pending_route_events_on_zero(self, has_private_cart=False):
        """Resolve only events whose outcome is knowable at stable zero.

        An empty private cart means the bowl was removed without a local
        checkout.  Official POS has no callback, so its event is recorded as
        explicitly unknown rather than guessed as paid or cancelled.
        """
        db = getattr(self.main_window, "db", None)
        event_key = self._last_route_event_key
        channel = self._last_route_event_channel
        if not db or not event_key:
            return
        try:
            # A cart may contain an earlier, correctly selected soup while
            # the most recent private weighing was never selected at all.
            # Resolve that unbound newest event as not paid instead of
            # letting the older basket make it look paid later.
            if channel == "private" and (
                not has_private_cart or not self._last_route_event_order_id
            ):
                changed = db.resolve_weighing_route_event(
                    event_key,
                    "NOT_PAID",
                    note="稳定归零时当前称重未关联汤底，未形成本地订单",
                )
                if changed:
                    log_event(CAT_DECISION, "称重未结账", "已标记当前私有称重为未成交")
                    self._last_route_event_key = ""
                    self._last_route_event_channel = ""
                    self._last_route_event_order_id = ""
            elif channel == "official":
                changed = db.resolve_weighing_route_event(
                    event_key,
                    "OFFICIAL_UNKNOWN",
                    note="官方 POS 无支付回调，稳定归零后仅能标记为支付未知",
                )
                if changed:
                    log_event(CAT_DECISION, "官方称重支付未知", "已标记当前官方称重为支付未知")
                    self._last_route_event_key = ""
                    self._last_route_event_channel = ""
                    self._last_route_event_order_id = ""
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 结算称重待确认记录失败: {exc}")

    def confirm_pending_private_routes(self, order_id=""):
        """Mark this paid basket's already-bound private routes as paid."""
        db = getattr(self.main_window, "db", None)
        if not db or not hasattr(db, "resolve_pending_private_weighing_events") or not order_id:
            return 0
        try:
            count = db.resolve_pending_private_weighing_events(
                "PRIVATE_PAID", order_id=order_id, note="私有 POS 本地订单支付成功"
            )
            if count:
                log_event(CAT_DECISION, "私有称重确认成交", f"订单 {order_id} 确认 {count} 条称重记录")
            return count
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 确认私有称重成交失败: {exc}")
            return 0

    def claim_current_private_route_for_order(self, order_id=""):
        """Attach the live private weighing event after a soup is selected."""
        event_key = self._last_route_event_key
        if not order_id or self._last_route_event_channel != "private" or not event_key:
            return False
        db = getattr(self.main_window, "db", None)
        if not db or not hasattr(db, "assign_weighing_route_event_order"):
            return False
        try:
            claimed = bool(db.assign_weighing_route_event_order(event_key, order_id))
            if claimed:
                self._last_route_event_order_id = str(order_id)
            return claimed
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 绑定称重与订单失败: {exc}")
            return False

    def abandon_pending_private_routes(self, reason="用户清空未结订单"):
        """Mark pending private events as not paid without deleting history."""
        db = getattr(self.main_window, "db", None)
        order_id = self._current_private_order_id()
        if not db or not hasattr(db, "resolve_pending_private_weighing_events") or not order_id:
            return 0
        try:
            count = db.resolve_pending_private_weighing_events(
                "NOT_PAID", order_id=order_id, note=reason
            )
            if self._last_route_event_channel == "private" and self._last_route_event_key:
                if db.resolve_weighing_route_event(
                    self._last_route_event_key, "NOT_PAID", note=reason
                ):
                    count += 1
                    self._last_route_event_key = ""
                    self._last_route_event_channel = ""
                    self._last_route_event_order_id = ""
            if count:
                log_event(CAT_DECISION, "私有称重未成交", f"已标记 {count} 条记录: {reason}")
            return count
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 标记私有称重未成交失败: {exc}")
            return 0

    def resolve_pending_route_events_manual(self, reason="店员手动干预"):
        """Never guess a route after manual channel switching."""
        db = getattr(self.main_window, "db", None)
        event_key = self._last_route_event_key
        if not db or not hasattr(db, "resolve_weighing_route_event") or not event_key:
            return 0
        try:
            changed = db.resolve_weighing_route_event(
                event_key, "MANUAL_UNKNOWN", note=reason
            )
            if changed:
                self._last_route_event_key = ""
                self._last_route_event_channel = ""
                self._last_route_event_order_id = ""
                log_event(CAT_DECISION, "手动切换导致称重归属未知", "已标记当前称重记录")
            return 1 if changed else 0
        except Exception as exc:
            _safe_console(f"[AutoDecisionEngine] 标记手动称重归属失败: {exc}")
            return 0

    def on_weighing_cycle_started(self, weight_kg: float):
        """Route one stable non-zero weighing cycle exactly once."""
        weight_kg = float(weight_kg or 0.0)
        self._last_weight_kg = weight_kg
        if weight_kg <= self._min_valid_weight:
            return
        if self._has_auto_popped:
            return

        if self._receipt_hide_pending:
            if not self._receipt_zero_seen:
                # A second event without a stable zero is stale/duplicate and
                # must not cancel checkout retirement or consume quota.
                log_event(CAT_SCALE, "忽略未归零的重复称重周期", f"重量 {weight_kg:.3f}kg")
                return
            self._hide_timer.stop()
            self._receipt_hide_pending = False
            log_event(
                CAT_SWITCH,
                "出票后切回等待被新称重周期取消",
                f"检测到稳定归零后的新重量 {weight_kg:.3f}kg，继续留在私有 POS",
            )
            if hasattr(self.main_window, "floating_ball") and self.main_window.floating_ball:
                self.main_window.floating_ball.stop_countdown()

        self._has_auto_popped = True
        self._last_popped_weight = weight_kg
        self._zero_start_time = 0.0
        if self._maintenance_pause_count or not self._auto_switch_enabled:
            return

        now_ts = time.time()
        if now_ts < self._manual_override_until:
            return

        if not self._receipt_hide_pending:
            self._hide_timer.stop()
        log_event(CAT_SCALE, "称重检测到稳定放碗动作", f"重量: {weight_kg:.3f}kg")

        # 在本次决策前保存周期起点。若本次最终渠道发生变化，当前这份
        # 重量就是新周期的第一份；否则继续累加到原周期。
        cycle_start_total = self._total_weight_kg
        cycle_start_private = self._private_weight_kg
        previous_cycle_channel = self._switch_cycle_is_private
        is_private_turn = self._evaluate_decision(
            weight_kg, official_available=self._official_available()
        )
        if not is_private_turn:
            ok = bring_official_to_front(self.config)
            if not ok:
                self._fallback_to_private_after_official_failure(weight_kg)
                is_private_turn = True
        if (
            not self._switch_cycle_initialized
            or previous_cycle_channel is None
            or is_private_turn != previous_cycle_channel
        ):
            # 第一次没有历史重量时不能用 0 作为分母，否则阈值公式会
            # 直接得到 0kg，进度条刚开始就满格。先用本次结果建立基线，
            # 从下一份称重开始显示真实推进量。
            if not self._switch_cycle_initialized and cycle_start_total <= 0.000001:
                self._switch_cycle_start_total_weight = self._total_weight_kg
                self._switch_cycle_start_private_weight = self._private_weight_kg
            else:
                self._switch_cycle_start_total_weight = cycle_start_total
                self._switch_cycle_start_private_weight = cycle_start_private
            self._switch_cycle_is_private = is_private_turn
            self._switch_cycle_initialized = True
        self._current_is_private = is_private_turn
        self._update_switch_cycle_progress()

        if is_private_turn:
            bring_our_pos_to_front(self.main_window)
            private_reason = self._last_decision_reason or "智能算法选择: 本单走私域"
            self._update_floating_ball_status(is_private=True, reason=private_reason, show_checkmark=True)
            msg = f"智能决策：重量 {weight_kg:.2f}kg -> 弹出【私域 POS】 ({private_reason}) ({self._quota_status_text()})"
            log_event(CAT_DECISION, "决策: 走私域 POS", f"重量 {weight_kg:.2f}kg | {self._quota_status_text()}")
        else:
            official_reason = self._last_decision_reason or "智能算法选择: 本单走官方"
            self._update_floating_ball_status(is_private=False, reason=official_reason, show_checkmark=True)
            msg = f"智能决策：重量 {weight_kg:.2f}kg -> 保持【官方界面】 ({official_reason}) ({self._quota_status_text()})"
            log_event(CAT_DECISION, "决策: 走官方系统", f"重量 {weight_kg:.2f}kg | {self._quota_status_text()}")
        if hasattr(self.main_window, 'status'):
            self.main_window.status.showMessage(msg, 5000)

    def _evaluate_decision(self, weight_kg: float, official_available=None) -> bool:
        """
        全自动核心决策算法：
        0. 连单/多碗保护：已有购物车/官方连单时继承原渠道，不重复消耗配额
        1. 门限过滤：如果重量 < min_private_weight_kg，分配给官方
        2. 重量配额：比较累计私域重量与总称重重量，控制目标重量占比
        """
        self._ensure_quota_date()
        self._last_decision_kind = ""
        self._last_decision_reason = ""
        if official_available is None:
            official_available = self._official_available()

        # 规则 0A：未结账购物车保护。只要购物车仍有项目，就继续在
        # 私域 POS 完成这张订单；结账或清空购物车后立即解除。过去的
        # “保护时长”并没有实际解除锁，容易让用户误以为超时会自动
        # 切换，因此改为明确的订单状态锁，不再需要计时配置。
        if hasattr(self.main_window, 'sale_page') and self.main_window.sale_page:
            cart_items = getattr(self.main_window.sale_page, 'cart_items', [])
            if cart_items:
                self._record_inherited_decision(weight_kg, True)
                self._last_decision_kind = "inherited_private"
                self._last_decision_reason = "私域未结订单保护"
                _safe_console(f"[AutoDecisionEngine] 检测到私域 POS 购物车已有 {len(cart_items)} 项商品，保持【私域 POS】连续开单")
                log_event(CAT_DECISION, "私域未结订单保护", f"购物车已有 {len(cart_items)} 项 | 本次称重 {weight_kg:.3f}kg")
                return True

        now_ts = time.time()
        # Establish the day's baseline before amount/weight balancing. A
        # successful official POS first order gives the call-number relay a
        # reliable starting point; a deliberate pre-order manual switch to
        # private POS is respected instead.
        if self._total_evaluated_orders == 0 and self._total_weight_kg <= 0.000001:
            first_override = self._daily_first_channel_override
            if first_override is True:
                self._daily_first_channel_override = None
                self._record_quota_decision(weight_kg, True)
                self._last_decision_kind = "first_private_manual"
                self._last_decision_reason = "店员首单前手动选择私域 POS"
                log_event(CAT_DECISION, "每日首单手动选择私域", f"重量 {weight_kg:.3f}kg")
                return True
            if official_available:
                self._daily_first_channel_override = None
                self._record_quota_decision(weight_kg, False, forced_official=True)
                self._last_decision_kind = "first_official_baseline"
                self._last_decision_reason = "每日首单默认建立官方 POS 基线"
                self._set_official_continuation_lock(now_ts)
                log_event(CAT_DECISION, "每日首单默认走官方", f"重量 {weight_kg:.3f}kg | 建立官方叫号基线")
                return False

        # 规则 0B：官方多碗/连续开单保护。只有中继已进入增强模式、并
        # 且订单金额与结账状态都已验证时，才允许金额分流替代这一把锁。
        amount_route = self._amount_route_decision(weight_kg)
        if now_ts - self._last_official_time < self._official_lock_sec and amount_route is None:
            elapsed = now_ts - self._last_official_time
            self._set_official_continuation_lock(now_ts)  # 刷新连单锁定期
            if not official_available:
                # The continuation channel has disappeared.  Do not leave a
                # stale official lock that can reclaim focus if the window is
                # restarted a few seconds later.
                self._clear_official_continuation_lock()
                self._record_inherited_decision(weight_kg, True)
                self._last_decision_kind = "inherited_private"
                self._last_decision_reason = "官方 POS 未运行，连单回退私有 POS"
                log_event(CAT_DECISION, "官方不可用 -> 连单回退私有 POS", f"本次称重 {weight_kg:.3f}kg")
                return True
            self._record_inherited_decision(weight_kg, False)
            self._last_decision_kind = "inherited_official"
            self._last_decision_reason = "官方 POS 连单继承"
            _safe_console(f"[AutoDecisionEngine] 检测到 {self._official_lock_sec} 秒内已有官方开单记录 (间隔 {elapsed:.1f}s)，保持【官方界面】连续开单")
            log_event(CAT_DECISION, "官方连单继承 -> 保持官方界面", f"距离上一单官方操作 {elapsed:.1f}s < {self._official_lock_sec}s | 本次称重 {weight_kg:.3f}kg")
            return False

        if amount_route is not None:
            if not official_available or amount_route:
                self._record_quota_decision(weight_kg, True, routing_basis="amount", operating_mode="enhanced")
                self._last_decision_kind = "amount_private"
                self._last_decision_reason = "已验证官方 POS 金额参与比例计算，留在私有 POS"
                log_event(CAT_DECISION, "增强模式金额分流 -> 私有 POS", f"重量 {weight_kg:.3f}kg")
                return True
            self._record_quota_decision(weight_kg, False, routing_basis="amount", operating_mode="enhanced")
            self._last_decision_kind = "amount_official"
            self._last_decision_reason = "已验证官方 POS 金额参与比例计算，分配官方 POS"
            log_event(CAT_DECISION, "增强模式金额分流 -> 官方 POS", f"重量 {weight_kg:.3f}kg")
            return False

        # 规则 0C：当日累计收款封顶保护。按星期分组使用不同门限。
        daily_limit = self._current_daily_revenue_limit()
        if daily_limit > 0:
            try:
                db = getattr(self.main_window, 'db', None)
                if db:
                    today_summary = db.get_today_summary()
                    today_amount = float(today_summary.get("total_amount", 0.0))
                    if today_amount >= daily_limit:
                        if not official_available:
                            self._record_quota_decision(weight_kg, True)
                            self._last_decision_kind = "quota_private"
                            self._last_decision_reason = "官方 POS 未运行，突破私有金额上限后仍留在私有 POS"
                            log_event(CAT_DECISION, "官方不可用 -> 私有 POS 继续收银", f"重量 {weight_kg:.3f}kg | 私有金额上限仅在官方可用时执行")
                            return True
                        self._record_quota_decision(weight_kg, False, forced_official=True)
                        self._last_decision_kind = "forced_official"
                        self._last_decision_reason = "私有 POS 达到当日金额上限"
                        self._set_official_continuation_lock(now_ts)
                        period = {
                            0: "周一至周四",
                            1: "周一至周四",
                            2: "周一至周四",
                            3: "周一至周四",
                            4: "周五",
                            5: "周六",
                            6: "周日",
                        }.get(date.today().weekday(), "当天")
                        msg = f"今日本POS已收款 ¥{today_amount:.2f} 达到/超过{period}上限 ¥{daily_limit:.2f} -> 自动停止切换本POS，分配给【官方系统】"
                        _safe_console(f"[AutoDecisionEngine] {msg}")
                        log_event(CAT_DECISION, "当日收款封顶 -> 走官方", f"今日已收 ¥{today_amount:.2f} >= {period}门限 ¥{daily_limit:.2f}")
                        return False
            except Exception as e:
                _safe_console(f"[AutoDecisionEngine] 查询今日收款汇总异常: {e}")

        # 规则 1：小单过滤，低于设定重量一律分配给官方
        if weight_kg < self._min_private_weight:
            if not official_available:
                self._record_quota_decision(weight_kg, True)
                self._last_decision_kind = "quota_private"
                self._last_decision_reason = "官方 POS 未运行，小单留在私有 POS"
                log_event(CAT_DECISION, "官方不可用 -> 小单留在私有 POS", f"重量 {weight_kg:.3f}kg")
                return True
            self._record_quota_decision(weight_kg, False, forced_official=True)
            self._last_decision_kind = "forced_official"
            self._last_decision_reason = "低于私有 POS 最小重量门限"
            self._set_official_continuation_lock(now_ts)
            _safe_console(f"[AutoDecisionEngine] 重量 {weight_kg:.3f}kg < {self._min_private_weight:.3f}kg 属于轻量单 -> 全自动分配给【官方】")
            log_event(CAT_DECISION, f"轻量单过滤 -> 走官方", f"重量 {weight_kg:.3f}kg < 门限 {self._min_private_weight:.3f}kg")
            return False

        # 规则 2：重量配额算法 (Weight Quota Balancing)
        # 目标比例仍沿用原配置项 private_ratio_percent，但分母改为
        # 累计称重重量。这样小单被官方过滤后，大单会承担相应的配额，
        # 比按订单次数更接近营业额的可观测代理指标。
        current_ratio = self.get_actual_private_weight_ratio()
        if current_ratio < self._target_private_ratio:
            self._record_quota_decision(weight_kg, True)
            self._last_decision_kind = "quota_private"
            self._last_decision_reason = "重量配额选择私有 POS"
            return True

        if not official_available:
            self._record_quota_decision(weight_kg, True)
            self._last_decision_kind = "quota_private"
            self._last_decision_reason = "官方 POS 未运行，配额决策回退私有 POS"
            log_event(CAT_DECISION, "官方不可用 -> 配额回退私有 POS", f"重量 {weight_kg:.3f}kg")
            return True

        self._record_quota_decision(weight_kg, False)
        self._last_decision_kind = "quota_official"
        self._last_decision_reason = "重量配额选择官方 POS"
        self._set_official_continuation_lock(now_ts)
        return False

    def get_actual_private_ratio(self) -> float:
        """计算当前新决策的私域次数比例 (%)，仅作辅助观察。"""
        self._ensure_quota_date()
        if self._total_evaluated_orders == 0:
            return 0.0
        return (self._private_orders_count / self._total_evaluated_orders) * 100.0

    def get_actual_private_weight_ratio(self) -> float:
        """计算当前新决策的私域重量比例 (%)。"""
        self._ensure_quota_date()
        if self._total_weight_kg <= 0.0:
            return 0.0
        return (self._private_weight_kg / self._total_weight_kg) * 100.0

    def get_switch_progress_status(self):
        """Return ``(progress, remaining_kg, next_channel)`` for this cycle.

        ``progress`` is the fraction of weight needed to trigger the next
        automatic channel switch.  It deliberately uses the current channel
        cycle, not the day's cumulative quota.  ``remaining_kg`` is ``None``
        when the configured target makes a switch impossible (0% or 100%).
        """
        if not self._switch_cycle_initialized or self._switch_cycle_is_private is None:
            # The floating ball is created before the first bowl is weighed.
            # Callers that only need a visual refresh have no cycle baseline
            # yet, so keep the switch direction visible and let the caller
            # establish the baseline instead of silently hiding the label.
            return 0.0, None, "官方 POS"
        # The weight-ratio forecast must not advertise a private switch after
        # the private POS has hit its paid daily cap.  The actual decision
        # gate runs before the ratio rule, so this is a display/state guard to
        # keep the floating ball truthful as well.
        if not self._switch_cycle_is_private and self._private_daily_limit_reached():
            return 0.0, None, "官方 POS"
        target = min(1.0, max(0.0, self._target_private_ratio / 100.0))
        base_total = max(0.0, float(self._switch_cycle_start_total_weight or 0.0))
        base_private = max(0.0, float(self._switch_cycle_start_private_weight or 0.0))
        if base_total <= 0.000001:
            # With no accumulated weight there is no historical distance to
            # calculate.  For a usable middle target (e.g. 30/70), expose a
            # zero baseline rather than returning None and making the UI
            # remove the remaining-kg indicator altogether.  0% and 100%
            # remain intentionally non-switching configurations.
            if target <= 0.0 or (self._switch_cycle_is_private and target >= 1.0):
                return 0.0, None, "官方 POS" if self._switch_cycle_is_private else "私有 POS"
            return 0.0, 0.0, "官方 POS" if self._switch_cycle_is_private else "私有 POS"
        delta_total = max(0.0, self._total_weight_kg - base_total)
        delta_private = max(0.0, self._private_weight_kg - base_private)
        delta_official = max(0.0, delta_total - delta_private)

        if self._switch_cycle_is_private:
            next_channel = "官方 POS"
            if target >= 1.0:
                return 0.0, None, next_channel
            required = (target * base_total - base_private) / (1.0 - target)
            progressed = delta_private
        else:
            next_channel = "私有 POS"
            if target <= 0.0:
                return 0.0, None, next_channel
            required = (base_private - target * base_total) / target
            progressed = delta_official

        required = max(0.0, required)
        if required <= 0.000001:
            return 1.0, 0.0, next_channel
        remaining = max(0.0, required - progressed)
        return min(1.0, progressed / required), remaining, next_channel

    def _update_switch_cycle_progress(self):
        """Refresh the per-cycle progress bar after a stable weighing decision."""
        fb = getattr(self.main_window, "floating_ball", None)
        self._apply_switch_progress(
            fb,
            bool(self._switch_cycle_is_private),
            self._switch_progress_snapshot(),
        )

    def reset_switch_cycle_for_manual(self, is_private):
        """Start a fresh visual/forecast cycle after a manual channel switch.

        The daily quota ledger remains untouched; only the forecast baseline
        for the next automatic switch is reset to the current accumulated
        weights.  This prevents old automatic progress from misleading the
        operator after an intentional manual intervention.
        """
        self._switch_cycle_initialized = True
        self._switch_cycle_is_private = bool(is_private)
        self._switch_cycle_start_total_weight = self._total_weight_kg
        self._switch_cycle_start_private_weight = self._private_weight_kg
        self._current_is_private = bool(is_private)
        fb = getattr(self.main_window, "floating_ball", None)
        snapshot = self._switch_progress_snapshot()
        snapshot["progress"] = 0.0
        self._apply_switch_progress(fb, bool(is_private), snapshot)
        log_event(
            CAT_SWITCH,
            "手动切换后重置本轮切换进度",
            "目标通道: %s | 累计分流统计保留，下一次自动切换从当前重量起算"
            % ("私有 POS" if is_private else "官方 POS"),
        )

    def _quota_status_text(self) -> str:
        return (
            f"重量占比: {self.get_actual_private_weight_ratio():.1f}% | "
            f"决策次数: {self.get_actual_private_ratio():.1f}%"
        )

    def on_receipt_printed(self):
        """当打完制作单/小票后被触发"""
        if not self._auto_switch_enabled:
            return

        delay_ms = self._auto_hide_delay_sec * 1000
        self._receipt_hide_pending = True
        self._receipt_zero_seen = self._last_weight_kg <= self._min_valid_weight
        _safe_console(f"[AutoSwitch] 小票已打印，启动 {self._auto_hide_delay_sec} 秒延时自动隐退程序...")
        log_event(CAT_PRINT, f"小票打印完成", f"启动 {self._auto_hide_delay_sec} 秒延时自动隐退")
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            self.main_window.floating_ball.start_countdown(self._auto_hide_delay_sec)
        self._hide_timer.start(delay_ms)

    def _on_auto_hide_timeout(self):
        """延时结束，隐退切回官方系统"""
        self._receipt_hide_pending = False
        if not self._auto_switch_enabled:
            log_event(CAT_SWITCH, "自动隐退已取消", "自动切换当前关闭")
            return
        if time.time() < self._manual_override_until:
            log_event(CAT_SWITCH, "自动隐退已取消", "店员手动切换锁定中")
            return
        if self._maintenance_pause_count:
            return
        if not self._official_available():
            # The post-receipt grace period has ended.  If the official POS is
            # not running, minimize this helper as requested instead of
            # leaving a private POS window visible with nowhere to switch.
            self._current_is_private = True
            try:
                self.main_window.showMinimized()
            except Exception:
                pass
            log_event(CAT_SWITCH, "官方 POS 不可用，最小化私有 POS", "出票倒计时结束后未找到官方窗口")
            self._update_floating_ball_status(is_private=True, reason="官方 POS 未运行，私有 POS 已最小化")
            return
        _safe_console("[AutoSwitch] 延时结束，自动隐退切回官方收银界面")
        log_event(CAT_SWITCH, f"自动隐退切回官方系统", f"延时 {self._auto_hide_delay_sec} 秒结束")
        ok = bring_official_to_front(self.config)
        if ok:
            self._current_is_private = False
            self._update_floating_ball_status(is_private=False, reason="出票延时结束")
        else:
            # The window may disappear between the probe and the focus call.
            self._current_is_private = True
            bring_our_pos_to_front(self.main_window)
            log_event(CAT_SWITCH, "官方 POS 消失，保持私有 POS", "出票后切回发生竞态")
            self._update_floating_ball_status(is_private=True, reason="官方 POS 已关闭，保持私有 POS")

    def _update_floating_ball_status(self, is_private: bool, reason: str = "", show_checkmark: bool = False):
        """更新触屏悬浮球的状态与提示"""
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            fb = self.main_window.floating_ball
            fb.is_our_pos_active = is_private
            weight_pct = self.get_actual_private_weight_ratio()
            count_pct = self.get_actual_private_ratio()
            snapshot = self._switch_progress_snapshot()
            self._apply_switch_progress(fb, is_private, snapshot)
            if not is_private and self._private_daily_limit_reached():
                switch_text = "当日私域收款已封顶 | 保持官方 POS"
            elif snapshot["basis"] == "amount" and snapshot["remaining_amount"] is not None:
                switch_text = (
                    "金额分流：当前通道再收约 ¥%.2f 后切到%s"
                    % (snapshot["remaining_amount"], snapshot["next_channel"] or "下一通道")
                )
            elif snapshot["basis"] == "amount":
                switch_text = "金额分流：按目标私域金额占比自动切换"
            elif snapshot["remaining_kg"] is None:
                switch_text = "按配置不会自动切换"
            else:
                switch_text = f"切换进度: {snapshot['progress'] * 100:.0f}% | 当前通道再称约 {snapshot['remaining_kg']:.3f}kg 后切到{snapshot['next_channel']}"
            ratio_text = (
                f"目标私域金额占比: {snapshot['target']:.1f}%"
                if snapshot["basis"] == "amount"
                else f"当日累计私域重量占比: {weight_pct:.1f}% / 目标 {self._target_private_ratio:.1f}% | 次数: {count_pct:.1f}%"
            )
            fb.setToolTip(
                f"自动决策系统 | 本轮{switch_text}\n"
                f"{ratio_text}\n"
                f"{reason}\n轻触: 手动切换 | 长按/三连击: 紧急避险销毁"
            )
            if show_checkmark:
                fb.show_decision_checkmark()
            fb.update()

    def refresh_floating_ball_progress(self, is_private=None):
        """手动切屏后只刷新水位颜色，不新增一份配额快照。"""
        fb = getattr(self.main_window, "floating_ball", None)
        if not fb or not hasattr(fb, "set_switch_progress"):
            return
        if is_private is None:
            is_private = bool(getattr(fb, "is_our_pos_active", True))
        # On startup there is no first weighing event to establish a cycle.
        # If today's ledger is empty, do not manufacture a 0kg distance: the
        # first real stable weighing will establish the baseline.  This also
        # covers a bowl that was already on the scale before POS startup.
        if not self._switch_cycle_initialized:
            if self._total_weight_kg <= 0.000001:
                self._current_is_private = bool(is_private)
                fb.set_switch_progress(
                    0.0,
                    bool(is_private),
                    next_is_private=None,
                    remaining_kg=None,
                    next_channel=None,
                )
                return
            self._switch_cycle_initialized = True
            self._switch_cycle_is_private = bool(is_private)
            self._switch_cycle_start_total_weight = self._total_weight_kg
            self._switch_cycle_start_private_weight = self._private_weight_kg
            self._current_is_private = bool(is_private)
        self._apply_switch_progress(fb, bool(is_private), self._switch_progress_snapshot())

    def update_config(self, config: dict):
        """更新配置参数"""
        old_auto_switch_enabled = bool(self._auto_switch_enabled)
        self.config = config
        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        if old_auto_switch_enabled and not self._auto_switch_enabled:
            self._cancel_pending_auto_hide()
        self._auto_hide_delay_sec = max(0, _config_int(self.config, "auto_hide_delay_sec", 10))
        self._target_private_ratio = min(100.0, max(0.0, _config_float(self.config, "private_ratio_percent", 30)))
        amount_ratio_default = _config_float(self.config, "private_ratio_percent", 30)
        self._target_private_amount_ratio = min(
            100.0,
            max(0.0, _config_float(
                self.config,
                "private_amount_ratio_percent",
                amount_ratio_default,
            )),
        )
        self._min_private_weight = max(0.0, _config_float(self.config, "min_private_weight_kg", 0.25))
        self._official_lock_sec = max(0.0, _config_float(self.config, "official_lock_sec", 60.0))
        self._min_valid_weight = max(0.0, _config_float(self.config, "min_valid_weight_kg", 0.08))
        self._manual_override_lock_sec = max(0.0, _config_float(self.config, "manual_override_lock_sec", 30.0))
        self._load_daily_revenue_limits()
