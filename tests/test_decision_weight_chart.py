import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage, QPainter

from ui.switch_settings_widget import DecisionWeightChart, SwitchSettingsWidget


class DecisionWeightChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_route_points_form_one_monotonic_cumulative_series(self):
        chart = DecisionWeightChart()
        self.addCleanup(chart.deleteLater)
        chart.set_events([
            {"created_at": "2026-08-06 12:00:03", "weight_kg": 0.30, "channel": "official"},
            {"created_at": "2026-08-06 12:00:01", "weight_kg": 0.40, "channel": "private"},
            {"created_at": "2026-08-06 12:00:05", "weight_kg": 0.50, "channel": "private"},
        ])

        routes = [item for item in chart._normalised_events() if item[2] != "manual"]
        series = chart._cumulative_route_points(routes)

        self.assertEqual([round(item[1], 3) for item in series], [0.4, 0.7, 1.2])
        self.assertEqual([item[2] for item in series], ["private", "official", "private"])
        self.assertEqual([round(item[4], 3) for item in series], [0.4, 0.3, 0.5])

    def test_histogram_mode_keeps_fixed_width_for_its_own_scroll_card(self):
        line = DecisionWeightChart(chart_mode="line")
        histogram = DecisionWeightChart(chart_mode="histogram")
        self.addCleanup(line.deleteLater)
        self.addCleanup(histogram.deleteLater)
        events = [
            {"created_at": "2026-08-06 12:%02d:00" % (index % 60), "weight_kg": 0.25, "channel": "official"}
            for index in range(80)
        ]
        line.set_events(events)
        histogram.set_events(events)
        self.assertGreater(line.minimumWidth(), histogram.minimumWidth())
        self.assertEqual(histogram.minimumWidth(), 960)

    def test_line_chart_horizontal_zoom_changes_canvas_width(self):
        chart = DecisionWeightChart(chart_mode="line")
        self.addCleanup(chart.deleteLater)
        chart.set_events([
            {"created_at": "2026-08-06 12:%02d:00" % index, "weight_kg": 0.25, "channel": "official"}
            for index in range(4)
        ])
        normal_width = chart.minimumWidth()
        chart.zoom_in_horizontal()
        self.assertGreater(chart.minimumWidth(), normal_width)
        chart.reset_horizontal_zoom()
        self.assertEqual(chart.minimumWidth(), normal_width)

        chart.set_horizontal_scale(99.0)
        self.assertEqual(chart.horizontal_scale, chart.MAX_HORIZONTAL_SCALE)

    def test_restart_between_weighings_is_a_downtime_gap(self):
        events = [
            {"created_at": "2026-08-06 12:00:00", "weight_kg": 0.40, "channel": "official"},
            {"created_at": "2026-08-06 13:00:00", "weight_kg": 0.50, "channel": "private"},
        ]
        gaps = DecisionWeightChart.infer_downtime_gaps(
            events,
            ["2026-08-06 12:30:00"],
            ["2026-08-06 12:20:00"],
        )
        self.assertEqual(
            [(start.strftime("%H:%M"), end.strftime("%H:%M")) for start, end in gaps],
            [("12:00", "13:00")],
        )

    def test_startup_without_close_does_not_claim_downtime(self):
        events = [
            {"created_at": "2026-08-06 12:00:00", "weight_kg": 0.40, "channel": "official"},
            {"created_at": "2026-08-06 13:00:00", "weight_kg": 0.50, "channel": "private"},
        ]
        self.assertEqual(
            DecisionWeightChart.infer_downtime_gaps(
                events, ["2026-08-06 12:30:00"], []
            ),
            [],
        )

    def test_full_day_context_tracks_closed_and_open_before_first_bowl(self):
        chart = DecisionWeightChart(chart_mode="line")
        self.addCleanup(chart.deleteLater)
        chart.set_events([
            {"created_at": "2026-08-06 10:00:00", "weight_kg": 0.40, "channel": "official"}
        ])
        chart.set_timeline_context("2026-08-06", ["2026-08-06 08:00:00"], [])
        self.assertEqual(chart.timeline_start.strftime("%H:%M"), "00:00")
        self.assertEqual(chart.timeline_end.strftime("%H:%M"), "00:00")
        self.assertEqual(chart._app_state_at(chart.timeline_start), "closed")
        self.assertEqual(chart._app_state_at(chart.timeline_start.replace(hour=9)), "open")

        chart.set_timeline_context(
            "2026-08-06", [], ["2026-08-05 23:00:00"]
        )
        self.assertEqual(chart._app_state_at(chart.timeline_start), "closed")

    def test_prior_day_shutdown_keeps_closed_line_without_fake_close_marker(self):
        chart = DecisionWeightChart(chart_mode="line")
        self.addCleanup(chart.deleteLater)
        chart.set_timeline_context(
            "2026-08-06",
            ["2026-08-06 09:00:00"],
            ["2026-08-05 23:00:00"],
        )
        image = QImage(900, 520, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        chart.resize(900, 520)
        chart.render(painter)
        painter.end()
        markers = [target for target in chart._hit_targets if target.get("kind") == "app_shutdown"]
        self.assertEqual(markers, [])
        self.assertEqual(chart._app_state_at(chart.timeline_start), "closed")

    def test_nearby_points_are_visually_spread_with_data_point_connector(self):
        chart = DecisionWeightChart(chart_mode="line")
        self.addCleanup(chart.deleteLater)
        timestamp = "2026-08-06 12:00:00"
        chart.set_events([
            {"created_at": timestamp, "weight_kg": 0.001, "channel": "official"},
            {"created_at": timestamp, "weight_kg": 0.001, "channel": "private"},
            {"created_at": timestamp, "weight_kg": 0.001, "channel": "official"},
        ])
        chart.resize(900, 520)
        image = QImage(900, 520, QImage.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        chart.render(painter)
        painter.end()
        points = [target for target in chart._hit_targets if target.get("kind") == "weighing"]
        self.assertEqual(len(points), 3)
        self.assertGreater(len({round(target["point"].x(), 1) for target in points}), 1)
        self.assertTrue(all("data_point" in target for target in points))

    def test_line_continues_flat_after_last_route_point(self):
        chart = DecisionWeightChart(chart_mode="line")
        self.addCleanup(chart.deleteLater)
        chart.set_events([
            {"created_at": "2026-08-06 10:00:00", "weight_kg": 0.40, "channel": "official"},
        ])
        chart.set_timeline_context(
            "2026-08-06",
            ["2026-08-06 08:00:00"],
            ["2026-08-06 11:00:00"],
        )
        chart.resize(900, 520)
        image = QImage(900, 520, QImage.Format_ARGB32)
        image.fill(0)
        with patch.object(chart, "_draw_state_segments", wraps=chart._draw_state_segments) as draw_state:
            painter = QPainter(image)
            chart.render(painter)
            painter.end()
        intervals = {
            (args[1].strftime("%H:%M"), args[2].strftime("%H:%M"))
            for args, _kwargs in draw_state.call_args_list
        }
        self.assertIn(("10:00", "00:00"), intervals)

    def test_histogram_private_ratio_label(self):
        self.assertEqual(DecisionWeightChart._private_ratio_label(3.0, 1.0), "25%")
        self.assertEqual(DecisionWeightChart._private_ratio_label(0.0, 0.5), "100%")
        self.assertEqual(DecisionWeightChart._private_ratio_label(0.0, 0.0), "--")

    def test_private_point_uses_the_project_dialog_with_named_actions(self):
        widget = SwitchSettingsWidget({})
        self.addCleanup(widget.deleteLater)
        target = {
            "kind": "weighing",
            "when": "2026-08-06 12:00:00",
            "weight_kg": 0.5,
            "channel": "private",
            "event": {"order_id": "2608061200001", "status": "PRIVATE_PAID"},
        }
        with patch("ui.switch_settings_widget.show_question", return_value=False) as question:
            widget._on_weight_chart_point_clicked(target)

        question.assert_called_once()
        self.assertEqual(question.call_args.kwargs["confirm_text"], u"打开订单")
        self.assertEqual(question.call_args.kwargs["cancel_text"], u"关闭")

    def test_chart_translates_internal_decision_kinds_for_cashiers(self):
        quota_name, quota_detail = SwitchSettingsWidget._decision_kind_display("quota")
        inherited_name, inherited_detail = SwitchSettingsWidget._decision_kind_display("inherited")

        self.assertEqual(quota_name, u"自动重量配额分流")
        self.assertIn(u"目标占比", quota_detail)
        self.assertEqual(inherited_name, u"连单继承")
        self.assertIn(u"不", inherited_detail)


if __name__ == "__main__":
    unittest.main()
