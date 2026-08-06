import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from ui.switch_settings_widget import DecisionWeightChart


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
        self.assertEqual(histogram.minimumWidth(), 720)


if __name__ == "__main__":
    unittest.main()
