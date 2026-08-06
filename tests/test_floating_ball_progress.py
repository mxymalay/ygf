import unittest
from types import SimpleNamespace

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
        ball._switch_hint_text = lambda: FloatingBall._switch_hint_text(ball)
        self.assertEqual(FloatingBall._switch_hint_text(ball), "下次切官方 POS")
        self.assertEqual(FloatingBall._switch_hint_width(ball), 86)

        ball._switch_next_channel = "私有 POS"
        self.assertEqual(FloatingBall._switch_hint_text(ball), "下次切私域 POS")


if __name__ == "__main__":
    unittest.main()
