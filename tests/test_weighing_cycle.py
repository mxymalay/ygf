import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from core.switch_controller import AutoSwitchController
from ui.sale_widget import SaleWidget


class _Label(object):
    def setText(self, _value):
        pass

    def setStyleSheet(self, _value):
        pass

    def setToolTip(self, _value):
        pass


class WeighingCycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _controller(self):
        config = {
            "auto_switch_enabled": True,
            "auto_hide_delay_sec": 10,
            "private_ratio_percent": 100,
            "min_private_weight_kg": 0.25,
            "min_valid_weight_kg": 0.08,
            "official_lock_sec": 60,
            "zeroing_unlock_sec": 5,
        }
        window = SimpleNamespace(
            db=None,
            sale_page=SimpleNamespace(cart_items=[]),
            floating_ball=None,
        )
        return AutoSwitchController(window, config)

    def test_one_stable_cycle_consumes_quota_once(self):
        controller = self._controller()
        with patch("core.switch_controller.log_event"), patch(
            "core.switch_controller.is_official_pos_available", return_value=False
        ), patch("core.switch_controller.bring_our_pos_to_front", return_value=True):
            controller.on_weighing_cycle_started(0.5)
            controller.on_weighing_cycle_started(0.55)
            self.assertEqual(controller._total_evaluated_orders, 1)
            self.assertAlmostEqual(controller._total_weight_kg, 0.5)

            controller.on_weighing_cycle_zeroed()
            controller.on_weighing_cycle_started(0.6)
            self.assertEqual(controller._total_evaluated_orders, 2)
            self.assertAlmostEqual(controller._total_weight_kg, 1.1)
        controller._zero_unlock_timer.stop()

    def test_receipt_old_weight_cannot_start_a_second_order(self):
        controller = self._controller()
        with patch("core.switch_controller.log_event"), patch(
            "core.switch_controller.is_official_pos_available", return_value=False
        ), patch("core.switch_controller.bring_our_pos_to_front", return_value=True):
            controller.on_weighing_cycle_started(0.5)
            controller.on_receipt_printed()
            controller.on_weighing_cycle_started(0.5)
            self.assertEqual(controller._total_evaluated_orders, 1)

            controller.on_weighing_cycle_zeroed()
            controller.on_weighing_cycle_started(0.6)
            self.assertEqual(controller._total_evaluated_orders, 2)
            self.assertFalse(controller._receipt_hide_pending)
        controller._hide_timer.stop()
        controller._zero_unlock_timer.stop()

    def test_raw_frames_never_route(self):
        controller = self._controller()
        controller.on_weight_changed(0.5)
        self.assertEqual(controller._total_evaluated_orders, 0)
        self.assertFalse(controller._has_auto_popped)

    def test_invalid_legacy_algorithm_numbers_do_not_crash(self):
        window = SimpleNamespace(
            db=None,
            sale_page=SimpleNamespace(cart_items=[]),
            floating_ball=None,
        )
        controller = AutoSwitchController(window, {
            "private_ratio_percent": "bad",
            "min_valid_weight_kg": None,
            "auto_hide_delay_sec": "",
        })
        self.assertEqual(controller._target_private_ratio, 30.0)
        self.assertEqual(controller._min_valid_weight, 0.08)
        self.assertEqual(controller._auto_hide_delay_sec, 10)

    def test_daily_revenue_limit_uses_weekday_and_weekend_values(self):
        controller = AutoSwitchController(
            SimpleNamespace(db=None, sale_page=SimpleNamespace(cart_items=[]), floating_ball=None),
            {
                "weekday_max_daily_revenue_limit": 500,
                "weekend_max_daily_revenue_limit": 1000,
            },
        )
        self.assertEqual(controller._current_daily_revenue_limit(SimpleNamespace(weekday=lambda: 2)), 500.0)
        self.assertEqual(controller._current_daily_revenue_limit(SimpleNamespace(weekday=lambda: 5)), 1000.0)

    def test_daily_revenue_limit_legacy_value_is_used_when_new_keys_missing(self):
        controller = AutoSwitchController(
            SimpleNamespace(db=None, sale_page=SimpleNamespace(cart_items=[]), floating_ball=None),
            {"max_daily_revenue_limit": 123},
        )
        self.assertEqual(controller._weekday_max_daily_revenue_limit, 123.0)
        self.assertEqual(controller._weekend_max_daily_revenue_limit, 123.0)

    def test_cart_clear_keeps_cycle_locked_until_stable_zero(self):
        dummy = SimpleNamespace(
            cart_items=[{"type": "soup"}],
            selected_item_index=0,
            menu_buttons={},
            temp_order_no="old",
            current_order_id="old-id",
            _weight_cycle_ready=False,
            _draft_signature="old",
            _gen_temp_order_no=lambda: "new",
            _update_price_display=lambda: None,
        )
        with patch("ui.sale_widget.clear_draft"):
            SaleWidget._on_clear(dummy)
        self.assertFalse(dummy._weight_cycle_ready)

    def test_deleted_soup_allows_in_place_reselection_without_zeroing(self):
        """Replacing an item is allowed, but only while the basket has no soup."""
        dummy = SimpleNamespace(
            cart_items=[{"type": "soup", "name": "旧汤底"}],
            selected_item_index=0,
            menu_buttons={},
            _weight_cycle_ready=False,
            _soup_replacement_allowed=False,
            _update_price_display=lambda: None,
        )
        with patch("ui.sale_widget.log_event"):
            SaleWidget._delete_selected_item(dummy)

        self.assertEqual(dummy.cart_items, [])
        self.assertTrue(dummy._soup_replacement_allowed)
        self.assertTrue(SaleWidget._can_replace_soup_without_zero(dummy))

        # Once a replacement is present, another soup cannot be appended to
        # the same bowl; the operator must delete it again or finish the order.
        dummy.cart_items = [{"type": "soup", "name": "新汤底"}]
        self.assertFalse(SaleWidget._can_replace_soup_without_zero(dummy))

    def test_replacement_does_not_unlock_routing_cycle(self):
        dummy = SimpleNamespace(
            _weight_cycle_ready=False,
            _soup_replacement_allowed=True,
            cart_items=[],
        )
        self.assertTrue(SaleWidget._can_replace_soup_without_zero(dummy))
        # The physical weighing cycle remains locked; only the basket edit
        # exception is open.
        self.assertFalse(dummy._weight_cycle_ready)

    def test_two_equal_ui_frames_do_not_bypass_reader_stability(self):
        dummy = SimpleNamespace(
            current_weight=0.0,
            _last_weight_monotonic=0.0,
            lbl_weight=_Label(),
            _stable_weight=0.0,
            _is_stable=False,
            lbl_scale_status_icon=_Label(),
        )
        SaleWidget._on_weight_update(dummy, 0.4)
        SaleWidget._on_weight_update(dummy, 0.4)
        self.assertFalse(dummy._is_stable)

    def test_switch_progress_is_for_current_channel_cycle_not_daily_ratio(self):
        controller = self._controller()
        controller._target_private_ratio = 30.0
        controller._switch_cycle_initialized = True
        controller._switch_cycle_is_private = False  # 当前连续使用官方 POS
        controller._switch_cycle_start_total_weight = 1.0
        controller._switch_cycle_start_private_weight = 0.5
        controller._total_weight_kg = 1.5
        controller._private_weight_kg = 0.5

        progress, remaining, next_channel = controller.get_switch_progress_status()
        # 目标私域 30%：从 0.5/1.0 开始，还需约 0.667kg 官方重量降到 30%。
        self.assertAlmostEqual(progress, 0.75, places=3)
        self.assertAlmostEqual(remaining, 1.0 / 6.0, places=3)
        self.assertEqual(next_channel, "私有 POS")
        controller._hide_timer.stop()
        controller._zero_unlock_timer.stop()

    def test_manual_switch_resets_cycle_baseline_but_keeps_daily_counters(self):
        controller = self._controller()
        controller._target_private_ratio = 30.0
        controller._total_weight_kg = 4.0
        controller._private_weight_kg = 2.0
        controller._total_evaluated_orders = 8
        controller._private_orders_count = 3
        controller.reset_switch_cycle_for_manual(False)

        self.assertTrue(controller._switch_cycle_initialized)
        self.assertFalse(controller._switch_cycle_is_private)
        self.assertAlmostEqual(controller._switch_cycle_start_total_weight, 4.0)
        self.assertAlmostEqual(controller._switch_cycle_start_private_weight, 2.0)
        self.assertEqual(controller._total_evaluated_orders, 8)
        self.assertEqual(controller._private_orders_count, 3)
        progress, remaining, next_channel = controller.get_switch_progress_status()
        self.assertAlmostEqual(progress, 0.0)
        self.assertAlmostEqual(remaining, (2.0 - 0.3 * 4.0) / 0.3)
        self.assertEqual(next_channel, "私有 POS")
        controller._hide_timer.stop()
        controller._zero_unlock_timer.stop()

    def test_restored_locked_order_does_not_forward_old_bowl(self):
        emitted = Mock()
        dummy = SimpleNamespace(
            config={"min_valid_weight_kg": 0.08},
            _weight_cycle_ready=False,
            _cycle_present=False,
            weighing_cycle_started=SimpleNamespace(emit=emitted),
        )
        with patch("ui.sale_widget.log_event"):
            SaleWidget._on_scale_cycle_started(dummy, 0.5)
        self.assertTrue(dummy._cycle_present)
        emitted.assert_not_called()

    def test_simulation_uses_same_zero_gated_cycle_signal(self):
        config = {
            "is_mock_mode": True,
            "min_valid_weight_kg": 0.08,
            "unit_price": 47.6,
            "price_unit": "per_kg",
        }
        with patch.object(SaleWidget, "_build_ui", lambda _self: None), patch.object(
            SaleWidget, "_restore_draft", lambda _self: None
        ), patch.object(SaleWidget, "_refresh_previous_order_card", lambda _self: None), patch.object(
            SaleWidget, "_setup_scale", lambda _self: None
        ), patch.object(SaleWidget, "refresh_call_number_display", lambda _self: None), patch(
            "ui.sale_widget.ReceiptPrinter", return_value=SimpleNamespace()
        ):
            widget = SaleWidget(config, SimpleNamespace(), SimpleNamespace())
        self.addCleanup(widget.deleteLater)
        widget.lbl_weight = _Label()
        widget.lbl_scale_status_icon = _Label()
        cycles = []
        zeroes = []
        widget.weighing_cycle_started.connect(cycles.append)
        widget.weighing_cycle_zeroed.connect(lambda: zeroes.append(True))

        widget._apply_mock_weight(0.4)
        widget._apply_mock_weight(0.5)
        self.assertEqual(cycles, [0.4])
        widget._apply_mock_weight(0.0)
        widget._apply_mock_weight(0.5)
        self.assertEqual(len(zeroes), 1)
        self.assertEqual(cycles, [0.4, 0.5])


if __name__ == "__main__":
    unittest.main()
