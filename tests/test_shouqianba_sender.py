import subprocess
import sys
import unittest
from pathlib import Path


class ShouqianbaSenderImportTests(unittest.TestCase):
    def test_hotkey_must_contain_only_supported_keys(self):
        from core import shouqianba_sender as sender
        # Avoid exercising Windows keyboard injection in a unit test; validate
        # the supported vocabulary instead.
        self.assertTrue(sender.is_supported_hotkey("Shift+Q"))
        self.assertFalse(sender.is_supported_hotkey("Ctrl+BadKey"))

    def test_keyboard_dependency_is_optional(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = r'''
import builtins

real_import = builtins.__import__

def import_without_keyboard(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "keyboard":
        raise ImportError("simulated missing optional keyboard package")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = import_without_keyboard
import core.shouqianba_sender as sender
assert sender.keyboard is None
'''
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
