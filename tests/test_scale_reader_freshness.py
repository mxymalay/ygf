import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.scale_reader import ScaleReader


class ScaleReaderFreshnessTests(unittest.TestCase):
    def test_official_log_ignores_pre_start_cached_weight(self):
        with tempfile.TemporaryDirectory() as directory:
            logfile = os.path.join(directory, "log_serial_ports.txt")
            with open(logfile, "w", encoding="utf-8") as stream:
                stream.write('["00.350","00.350"] --- 2\n')

            reader = ScaleReader({"stable_count": 5})
            reader._running = True
            emitted = []
            reader.weight_updated.connect(emitted.append)
            responses = iter([logfile, logfile, None])
            with patch.object(reader, "_find_active_ygf_log", side_effect=lambda: next(responses)), patch(
                "core.scale_reader.time.sleep"
            ):
                reader._read_from_ygf_log(logfile)

            self.assertEqual(emitted, [])

    def test_stable_cycle_emits_once_until_multi_sample_zero(self):
        reader = ScaleReader({"stable_count": 5, "zero_stable_count": 2, "stable_threshold": 0.01})
        cycles = []
        zeroes = []
        reader.weighing_cycle_started.connect(cycles.append)
        reader.zero_stable.connect(lambda: zeroes.append(True))

        for _ in range(2):
            reader._check_stability(0.0)
        for _ in range(5):
            reader._check_stability(0.4)
        for _ in range(5):
            reader._check_stability(0.55)
        self.assertEqual(cycles, [0.4])

        for _ in range(2):
            reader._check_stability(0.0)
        for _ in range(5):
            reader._check_stability(0.6)
        self.assertEqual(len(zeroes), 2)
        self.assertEqual(cycles, [0.4, 0.6])

    def test_two_fresh_zero_samples_rearm_before_full_weight_window(self):
        reader = ScaleReader({"stable_count": 5, "zero_stable_count": 2})
        zeroes = []
        reader.zero_stable.connect(lambda: zeroes.append(True))

        reader._check_stability(0.0)
        self.assertEqual(zeroes, [])
        reader._check_stability(0.0)
        self.assertEqual(zeroes, [True])
        self.assertTrue(reader._cycle_armed)

    def test_sub_threshold_plateau_does_not_consume_next_bowl(self):
        reader = ScaleReader({"stable_count": 5, "min_valid_weight_kg": 0.08})
        cycles = []
        reader.weighing_cycle_started.connect(cycles.append)
        for _ in range(5):
            reader._check_stability(0.0)
        for _ in range(5):
            reader._check_stability(0.05)
        for _ in range(5):
            reader._check_stability(0.4)
        self.assertEqual(cycles, [0.4])

    def test_negative_weight_is_zero_and_over_range_is_rejected(self):
        reader = ScaleReader({"scale_max_weight_kg": 15.0})
        self.assertEqual(reader._parse_com_weight("-00.350"), 0.0)
        self.assertEqual(reader._parse_ygf_log_line("DI_BAO read - -00.350"), 0.0)
        self.assertIsNone(reader._parse_com_weight("16.000"))

    def test_official_batch_uses_freshest_value_including_zero(self):
        reader = ScaleReader({})
        self.assertEqual(
            reader._parse_ygf_log_line('["00.350","00.200","00.000"] --- 3'),
            0.0,
        )
        self.assertIsNone(
            reader._parse_ygf_log_line('["00.350","16.000"] --- 2')
        )

    def test_same_size_official_log_overwrite_has_a_new_snapshot_token(self):
        stat = SimpleNamespace(st_mtime=1.0, st_ctime=1.0, st_size=32)
        first = ScaleReader._ygf_log_snapshot_token(
            "C:/official/log.txt", stat, '["00.350"] --- 1\n'
        )
        second = ScaleReader._ygf_log_snapshot_token(
            "C:/official/log.txt", stat, '["00.000"] --- 1\n'
        )
        self.assertNotEqual(first, second)

    def test_unterminated_official_log_line_waits_for_a_settled_reread(self):
        reader = ScaleReader({})
        content = '["00.350"] --- 1'
        self.assertIsNone(reader._latest_ygf_log_record(content))
        self.assertEqual(
            reader._latest_ygf_log_record(content, allow_unterminated=True),
            (0.35, '["00.350"] --- 1'),
        )

    def test_fluctuation_filter_has_no_upward_only_bias(self):
        reader = ScaleReader({})
        self.assertEqual(reader._apply_fluctuation_filter(0.400), 0.400)
        self.assertEqual(reader._apply_fluctuation_filter(0.395), 0.395)

    def test_restart_refuses_to_spawn_when_old_reader_is_stuck(self):
        class StuckThread(object):
            def __init__(self):
                self.join_timeout = None

            def is_alive(self):
                return True

            def join(self, timeout=None):
                self.join_timeout = timeout

        reader = ScaleReader({})
        stuck = StuckThread()
        reader._thread = stuck
        reader._running = True
        errors = []
        reader.error_occurred.connect(errors.append)
        self.assertFalse(reader.restart())
        self.assertEqual(stuck.join_timeout, 3.0)
        self.assertTrue(errors)

    def test_restart_state_does_not_rearm_bowl_before_zero(self):
        reader = ScaleReader({})
        reader._cycle_armed = False
        reader._zero_reported = False
        reader._reset_runtime_state(preserve_cycle=True)
        self.assertFalse(reader._cycle_armed)

    def test_invalid_legacy_numeric_settings_fall_back_safely(self):
        reader = ScaleReader({
            "stable_count": "bad",
            "stable_threshold": None,
            "scale_max_weight_kg": "",
        })
        self.assertEqual(reader._stable_count, 5)
        self.assertEqual(reader._stable_threshold, 0.01)
        self.assertEqual(reader._maximum_weight, 15.0)


if __name__ == "__main__":
    unittest.main()
