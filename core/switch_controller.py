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


class AutoSwitchController(QObject):
    """双系统智能决策控制器"""

    def __init__(self, main_window, config: dict, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.config = config

        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = self.config.get("auto_hide_delay_sec", 3)
        self._target_private_ratio = float(self.config.get("private_ratio_percent", 30))  # 默认 30%
        self._min_private_weight = float(self.config.get("min_private_weight_kg", 0.25))  # 默认 0.25kg
        self._official_lock_sec = float(self.config.get("official_lock_sec", 60.0))
        self._zeroing_unlock_sec = float(self.config.get("zeroing_unlock_sec", 5.0))
        self._private_lock_sec = float(self.config.get("private_lock_sec", 300.0))  # 默认私域购物车5分钟超时
        self._min_valid_weight = float(self.config.get("min_valid_weight_kg", 0.08))
        self._surge_correction_weight = float(self.config.get("surge_correction_weight_kg", 0.15))
        self._manual_override_lock_sec = float(self.config.get("manual_override_lock_sec", 30.0))
        self._max_daily_revenue_limit = float(self.config.get("max_daily_revenue_limit", 0.0))

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
        self._load_persisted_quota_state()

        self._has_auto_popped = False  # 防止在同一个重量上重复判断
        self._last_official_time = 0.0  # 记录上一次判定为官方 POS 的时间戳 (用于官方连单保护)
        self._manual_override_until = 0.0  # 店员手动干预锁定期 (防止称重自动抢抓焦点)
        self._zero_start_time = 0.0  # 记录归零起始时间戳
        self._last_popped_weight = 0.0  # 记录上次触发决策时的重量 (用于重量剧增二次更正)
        self._last_private_time = 0.0  # 记录上一次私域动作的时间戳 (用于私域购物车死锁超时)
        self._current_is_private = False
        self._last_decision_kind = ""
        self._last_decision_reason = ""
        # Hardware maintenance may briefly reconnect a scale or emit a stale
        # non-zero reading. It must never trigger focus/minimise automation
        # while an operator is creating, testing or deleting COM resources.
        self._maintenance_pause_count = 0

        # 退场延时定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_auto_hide_timeout)

    def notify_manual_switch(self, duration_sec: float = -1.0):
        """店员手动点击悬浮球/快捷键触发：锁定指定秒数内不被称重自动抢抓覆盖"""
        if duration_sec < 0:
            duration_sec = self._manual_override_lock_sec
        self._manual_override_until = time.time() + duration_sec
        log_event(CAT_SWITCH, f"店员手动干预锁定", f"优先尊重店员操作，暂停自动调度 {duration_sec} 秒")

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
        except Exception as exc:
            # A corrupt/legacy runtime statistic must never prevent POS start.
            print(f"[AutoDecisionEngine] 恢复分流统计失败，使用本次运行统计: {exc}")

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
        self._load_persisted_quota_state()

    def _record_quota_decision(self, weight_kg, is_private, forced_official=False):
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
        if db and hasattr(db, "record_switch_quota_decision"):
            try:
                db.record_switch_quota_decision(weight, is_private, forced_official)
            except Exception as exc:
                # Keep the live decision working even if a removable/locked
                # database cannot be updated on an older Windows installation.
                print(f"[AutoDecisionEngine] 保存分流统计失败: {exc}")

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
                print(f"[AutoDecisionEngine] 保存联单统计失败: {exc}")

    def _official_available(self):
        """Check the configured official window before hiding this POS."""
        try:
            return bool(is_official_pos_available(self.config))
        except Exception as exc:
            print(f"[AutoDecisionEngine] 官方 POS 状态检测失败，按不可用处理: {exc}")
            return False

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
                    print(f"[AutoDecisionEngine] 修正官方配额统计失败: {exc}")
        elif kind == "inherited_official":
            self._inherited_official_orders = max(0, self._inherited_official_orders - 1)
            self._inherited_private_orders += 1
            self._private_weight_kg += weight
            db = getattr(self.main_window, "db", None)
            if db and hasattr(db, "convert_switch_inherited_to_private"):
                try:
                    db.convert_switch_inherited_to_private(weight)
                except Exception as exc:
                    print(f"[AutoDecisionEngine] 修正官方联单统计失败: {exc}")

        self._last_official_time = 0.0
        self._last_decision_kind = "fallback_private"
        self._last_decision_reason = "官方 POS 未运行/已关闭，自动留在私有 POS"
        log_event(
            CAT_DECISION,
            "官方 POS 不可用 -> 回退私有 POS",
            f"重量 {weight:.3f}kg | 原决策 {kind or 'unknown'}，未隐藏本 POS",
        )

    def on_weight_changed(self, weight_kg: float):
        """当称重数据变动时被触发，全自动运行决策引擎"""
        if self._maintenance_pause_count or not self._auto_switch_enabled:
            return

        now_ts = time.time()
        # 1. 如果在店员手动干预锁定期内，尊重店员手动控制，不自动抢抓界面
        if now_ts < self._manual_override_until:
            return

        # 重量门限判断 (例如大于 0.08kg 视为有放碗动作)
        if weight_kg > self._min_valid_weight:
            self._zero_start_time = 0.0  # 重置归零时间戳

            # 2. 动态重量递增修正 (比如手刚放碗读数 0.12kg，1秒内手放开稳在 0.55kg)
            weight_diff = weight_kg - self._last_popped_weight
            is_surge = self._has_auto_popped and weight_diff > self._surge_correction_weight and not self._current_is_private

            if not self._has_auto_popped or is_surge:
                self._has_auto_popped = True
                self._last_popped_weight = weight_kg
                self._hide_timer.stop()
                log_event(CAT_SCALE, f"称重检测到放碗动作" if not is_surge else "称重稳定修正 (重量增加)", f"重量: {weight_kg:.3f}kg")

                # 🤖 执行全自动智能决策算法。先确认官方窗口存在，避免
                # “只有私有 POS”时把本 POS 隐藏到空桌面。
                is_private_turn = self._evaluate_decision(
                    weight_kg, official_available=self._official_available()
                )
                if not is_private_turn:
                    ok = bring_official_to_front(self.config)
                    if not ok:
                        self._fallback_to_private_after_official_failure(weight_kg)
                        is_private_turn = True
                self._current_is_private = is_private_turn

                if is_private_turn:
                    self._last_private_time = time.time()  # 刷新私域活动时间
                    # 决策分配给【私域 POS】 -> 自动将本系统弹出最前
                    bring_our_pos_to_front(self.main_window)
                    private_reason = self._last_decision_reason or "智能算法选择: 本单走私域"
                    self._update_floating_ball_status(is_private=True, reason=private_reason, show_checkmark=True)
                    msg = f"🤖 智能决策：重量 {weight_kg:.2f}kg -> 弹出【私域 POS】 ({private_reason}) ({self._quota_status_text()})"
                    print(f"[AutoDecisionEngine] {msg}")
                    log_event(CAT_DECISION, f"决策: 走私域 POS", f"重量 {weight_kg:.2f}kg | {self._quota_status_text()}")
                    if hasattr(self.main_window, 'status'):
                        self.main_window.status.showMessage(msg, 5000)
                else:
                    # 决策分配给【官方系统】 -> 本系统隐藏在后台，保持/拉出官方界面
                    self._update_floating_ball_status(is_private=False, reason="智能算法选择: 本单走官方", show_checkmark=True)
                    msg = f"🤖 智能决策：重量 {weight_kg:.2f}kg -> 保持【官方界面】 ({self._quota_status_text()})"
                    print(f"[AutoDecisionEngine] {msg}")
                    log_event(CAT_DECISION, f"决策: 走官方系统", f"重量 {weight_kg:.2f}kg | {self._quota_status_text()}")
                    if hasattr(self.main_window, 'status'):
                        self.main_window.status.showMessage(msg, 5000)
        else:
            # 3. 称重归零超时智能判定：若空重量保持指定时间以上，说明上一位顾客已拿碗离开，自动提前解脱官方连单锁
            if self._zero_start_time == 0.0:
                self._zero_start_time = now_ts
            elif now_ts - self._zero_start_time > self._zeroing_unlock_sec:
                # 只有真正归零超过一定时间（例如 5 秒），才算作真正的离场，此时才重置弹出标记
                if self._has_auto_popped:
                    self._has_auto_popped = False
                    self._last_popped_weight = 0.0
                    self._current_is_private = False
                    print(f"[AutoDecisionEngine] 称重归零已达 {self._zeroing_unlock_sec}s，重置决策状态，迎接下一位顾客")
                    
                if self._last_official_time > 0:
                    self._last_official_time = 0.0
                    print(f"[AutoDecisionEngine] 称重归零超时 {self._zeroing_unlock_sec}s (顾客已离场)，自动解除官方连单锁定")
                    log_event(CAT_DECISION, "顾客离场解锁", f"称重归零超过 {self._zeroing_unlock_sec} 秒，恢复新单智能决策")

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

        # 规则 0A：私域多碗/连续开单保护 (如果购物车已有未结账项目，保持私域 POS 连续开单)
        now_ts = time.time()
        if hasattr(self.main_window, 'sale_page') and self.main_window.sale_page:
            cart_items = getattr(self.main_window.sale_page, 'cart_items', [])
            if cart_items:
                if now_ts - self._last_private_time < self._private_lock_sec:
                    self._last_private_time = now_ts  # 刷新私域连单锁定期
                    self._record_inherited_decision(weight_kg, True)
                    self._last_decision_kind = "inherited_private"
                    self._last_decision_reason = "私有 POS 连单继承"
                    print(f"[AutoDecisionEngine] 检测到私域 POS 购物车已有 {len(cart_items)} 项商品，保持【私域 POS】连续开单")
                    log_event(CAT_DECISION, "私域连单继承 -> 保持私域 POS", f"购物车已有 {len(cart_items)} 项 | 本次称重 {weight_kg:.3f}kg")
                    return True
                else:
                    # A timeout must never erase an unfinished customer order.
                    # Preserve the basket/draft and keep the POS on this order
                    # until the cashier explicitly clears or checks out.
                    self._last_private_time = now_ts
                    self._record_inherited_decision(weight_kg, True)
                    self._last_decision_kind = "inherited_private"
                    self._last_decision_reason = "私有 POS 未结订单保护"
                    log_event(
                        CAT_DECISION,
                        "私域未结订单保护",
                        f"购物车超过 {self._private_lock_sec}s 未结账，已保留订单并暂停自动切换",
                    )
                    return True

        # 规则 0B：官方多碗/连续开单保护 (如果上一碗刚分配给官方 POS，继承走官方 POS，防止弹窗打断店员官方开单)
        if now_ts - self._last_official_time < self._official_lock_sec:
            elapsed = now_ts - self._last_official_time
            self._last_official_time = now_ts  # 刷新连单锁定期
            if not official_available:
                self._record_inherited_decision(weight_kg, True)
                self._last_decision_kind = "inherited_private"
                self._last_decision_reason = "官方 POS 未运行，连单回退私有 POS"
                log_event(CAT_DECISION, "官方不可用 -> 连单回退私有 POS", f"本次称重 {weight_kg:.3f}kg")
                return True
            self._record_inherited_decision(weight_kg, False)
            self._last_decision_kind = "inherited_official"
            self._last_decision_reason = "官方 POS 连单继承"
            print(f"[AutoDecisionEngine] 检测到 {self._official_lock_sec} 秒内已有官方开单记录 (间隔 {elapsed:.1f}s)，保持【官方界面】连续开单")
            log_event(CAT_DECISION, "官方连单继承 -> 保持官方界面", f"距离上一单官方操作 {elapsed:.1f}s < {self._official_lock_sec}s | 本次称重 {weight_kg:.3f}kg")
            return False

        # 规则 0C：当日累计收款封顶保护 (如果今日私域累积收款达到/超过上限，停止切回本 POS，分配给官方)
        if self._max_daily_revenue_limit > 0:
            try:
                db = getattr(self.main_window, 'db', None)
                if db:
                    today_summary = db.get_today_summary()
                    today_amount = float(today_summary.get("total_amount", 0.0))
                    if today_amount >= self._max_daily_revenue_limit:
                        if not official_available:
                            self._record_quota_decision(weight_kg, True)
                            self._last_decision_kind = "quota_private"
                            self._last_decision_reason = "官方 POS 未运行，突破私有金额上限后仍留在私有 POS"
                            log_event(CAT_DECISION, "官方不可用 -> 私有 POS 继续收银", f"重量 {weight_kg:.3f}kg | 私有金额上限仅在官方可用时执行")
                            return True
                        self._record_quota_decision(weight_kg, False, forced_official=True)
                        self._last_decision_kind = "forced_official"
                        self._last_decision_reason = "私有 POS 达到当日金额上限"
                        self._last_official_time = now_ts
                        msg = f"🛑 今日本POS已收款 ¥{today_amount:.2f} 达到/超过设定上限 ¥{self._max_daily_revenue_limit:.2f} -> 自动停止切换本POS，分配给【官方系统】"
                        print(f"[AutoDecisionEngine] {msg}")
                        log_event(CAT_DECISION, "当日收款封顶 -> 走官方", f"今日已收 ¥{today_amount:.2f} >= 门限 ¥{self._max_daily_revenue_limit:.2f}")
                        return False
            except Exception as e:
                print(f"[AutoDecisionEngine] 查询今日收款汇总异常: {e}")

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
            self._last_official_time = now_ts
            print(f"[AutoDecisionEngine] 重量 {weight_kg:.3f}kg < {self._min_private_weight:.3f}kg 属于轻量单 -> 全自动分配给【官方】")
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
        self._last_official_time = now_ts
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

    def _quota_status_text(self) -> str:
        return (
            f"重量占比: {self.get_actual_private_weight_ratio():.1f}% | "
            f"决策次数: {self.get_actual_private_ratio():.1f}%"
        )

    def on_receipt_printed(self):
        """当打完制作单/小票后被触发"""
        self._last_official_time = 0.0  # 结账出票完成，重置官方锁
        if not self._auto_switch_enabled:
            return

        delay_ms = self._auto_hide_delay_sec * 1000
        print(f"[AutoSwitch] 小票已打印，启动 {self._auto_hide_delay_sec} 秒延时自动隐退程序...")
        log_event(CAT_PRINT, f"小票打印完成", f"启动 {self._auto_hide_delay_sec} 秒延时自动隐退")
        if hasattr(self.main_window, 'floating_ball') and self.main_window.floating_ball:
            self.main_window.floating_ball.start_countdown(self._auto_hide_delay_sec)
        self._hide_timer.start(delay_ms)

    def _on_auto_hide_timeout(self):
        """延时结束，隐退切回官方系统"""
        if self._maintenance_pause_count:
            return
        if not self._official_available():
            # Standalone/private-only mode is valid.  Never minimize the only
            # usable POS merely because the optional official POS is closed.
            self._current_is_private = True
            bring_our_pos_to_front(self.main_window)
            log_event(CAT_SWITCH, "官方 POS 不可用，保持私有 POS", "出票后未执行自动隐退")
            self._update_floating_ball_status(is_private=True, reason="官方 POS 未运行，保持私有 POS")
            return
        print("[AutoSwitch] 延时结束，自动隐退切回官方收银界面")
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
            fb.setToolTip(
                f"自动决策系统 | 私域重量占比: {weight_pct:.1f}% | 次数: {count_pct:.1f}%\n"
                f"{reason}\n轻触: 手动切换 | 长按/三连击: 紧急避险销毁"
            )
            if show_checkmark:
                fb.show_decision_checkmark()
            fb.update()

    def update_config(self, config: dict):
        """更新配置参数"""
        self.config = config
        self._auto_switch_enabled = self.config.get("auto_switch_enabled", True)
        self._auto_hide_delay_sec = self.config.get("auto_hide_delay_sec", 3)
        self._target_private_ratio = float(self.config.get("private_ratio_percent", 30))
        self._min_private_weight = float(self.config.get("min_private_weight_kg", 0.25))
        self._official_lock_sec = float(self.config.get("official_lock_sec", 60.0))
        self._zeroing_unlock_sec = float(self.config.get("zeroing_unlock_sec", 5.0))
        self._private_lock_sec = float(self.config.get("private_lock_sec", 300.0))
        self._min_valid_weight = float(self.config.get("min_valid_weight_kg", 0.08))
        self._surge_correction_weight = float(self.config.get("surge_correction_weight_kg", 0.15))
        self._manual_override_lock_sec = float(self.config.get("manual_override_lock_sec", 30.0))
        self._max_daily_revenue_limit = float(self.config.get("max_daily_revenue_limit", 0.0))
