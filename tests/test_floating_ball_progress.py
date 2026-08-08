import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ui.floating_ball import FloatingBall


class FloatingBallProgressTests(unittest.TestCase):
    def test_keeps_previous_quota_snapshot_and_ignores_duplicate_refresh(self):
        ball = SimpleNamespace(
            _quota_progress=0.0,
            _quota_previous_progress=0.0,
            _quota_is_private=True,
            _quota_previous_is_private=True,
            _next_switch_is_private=None,
            update=lambda: None,
        )

        FloatingBall.set_quota_progress(ball, 15.0, 30.0, False)
        self.assertAlmostEqual(ball._quota_progress, 0.5)
        self.assertAlmostEqual(ball._quota_previous_progress, 0.0)
        self.assertFalse(ball._quota_is_private)

        FloatingBall.set_quota_progress(ball, 15.0, 30.0, False)
        self.assertAlmostEqual(ball._quota_previous_progress, 0.0)

        FloatingBall.set_quota_progress(ball, 21.0, 30.0, False)
        self.assertAlmostEqual(ball._quota_progress, 0.7)
        self.assertAlmostEqual(ball._quota_previous_progress, 0.5)

        FloatingBall.set_switch_progress(ball, 0.7, False, next_is_private=True)
        self.assertTrue(ball._next_switch_is_private)

    def test_zero_remaining_hint_names_the_next_channel(self):
        ball = SimpleNamespace(
            _switch_remaining_kg=0.0,
            _switch_next_channel="官方 POS",
            _next_switch_is_private=False,
            is_our_pos_active=True,
        )
        ball._next_switch_hint = lambda: FloatingBall._next_switch_hint(ball)
        ball._switch_hint_lines = lambda: FloatingBall._switch_hint_lines(ball)
        ball._switch_hint_text = lambda: FloatingBall._switch_hint_text(ball)
        self.assertEqual(
            FloatingBall._switch_hint_text(ball),
            "下次切官方 POS\n还需 0.000 kg",
        )
        self.assertEqual(FloatingBall._switch_hint_width(ball), 86)

        ball._switch_next_channel = "私有 POS"
        self.assertEqual(
            FloatingBall._switch_hint_text(ball),
            "下次切私域 POS\n还需 0.000 kg",
        )

    def test_timer_refreshes_routing_hint_when_relay_mode_changes(self):
        calls = []
        ball = SimpleNamespace(
            main_window=SimpleNamespace(
                switch_controller=SimpleNamespace(
                    refresh_floating_ball_progress=lambda: calls.append(True),
                )
            ),
            update=lambda: calls.append("paint"),
        )

        FloatingBall._refresh_state(ball)

        self.assertEqual(calls, [True, "paint"])

    @patch("ui.floating_ball.detect_foreground_pos_channel", return_value=False)
    def test_timer_syncs_taskbar_selected_official_pos(self, _detect):
        calls = []
        ball = SimpleNamespace(
            main_window=SimpleNamespace(
                config={},
                switch_controller=SimpleNamespace(
                    sync_foreground_channel=lambda value: calls.append(("sync", value)),
                    refresh_floating_ball_progress=lambda: calls.append("refresh"),
                ),
            ),
            update=lambda: calls.append("paint"),
        )

        FloatingBall._refresh_state(ball)

        self.assertEqual(calls, [("sync", False), "refresh", "paint"])


if __name__ == "__main__":
    unittest.main()
