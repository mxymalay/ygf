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
