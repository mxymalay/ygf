import os
import tempfile
import unittest
from unittest.mock import patch

from core.scale_reader import ScaleReader


class ScaleReaderFreshnessTests(unittest.TestCase):
    def test_official_log_does_not_reemit_cached_weight_when_file_is_unchanged(self):
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

            self.assertEqual(emitted, [0.35])


if __name__ == "__main__":
    unittest.main()
