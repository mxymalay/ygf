import io
import unittest

from core.safe_console import ResilientConsoleStream


class _BrokenStream(object):
    encoding = "cp936"
    errors = "strict"

    def write(self, _value):
        raise PermissionError(31, "device unavailable")

    def flush(self):
        raise PermissionError(31, "device unavailable")

    def isatty(self):
        return True


class SafeConsoleTests(unittest.TestCase):
    def test_win7_console_error_is_swallowed(self):
        stream = ResilientConsoleStream(_BrokenStream())
        self.assertEqual(stream.write("diagnostic\n"), len("diagnostic\n"))
        self.assertIsNone(stream.flush())
        self.assertTrue(stream.isatty())

    def test_normal_stream_is_unchanged(self):
        target = io.StringIO()
        stream = ResilientConsoleStream(target)
        stream.write("ok")
        stream.flush()
        self.assertEqual(target.getvalue(), "ok")

