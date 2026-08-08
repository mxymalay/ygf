import os
import tempfile
import unittest

from build_exe import _backup_previous_setup, _is_setup_artifact


class BuildOutputTests(unittest.TestCase):
    def test_setup_artifact_names_and_single_previous_backup(self):
        self.assertTrue(_is_setup_artifact("YGF-POS-Setup.exe"))
        self.assertTrue(_is_setup_artifact("setup_20260808_120000.exe"))
        self.assertFalse(_is_setup_artifact("启动.exe"))

        with tempfile.TemporaryDirectory() as root:
            dist = os.path.join(root, "dist")
            backup = os.path.join(dist, "backup")
            os.makedirs(backup)
            with open(os.path.join(backup, "setup_old.exe"), "wb") as stream:
                stream.write(b"old backup")
            previous = os.path.join(dist, "YGF-POS-Setup.exe")
            with open(previous, "wb") as stream:
                stream.write(b"previous build")

            self.assertTrue(_backup_previous_setup(dist))
            root_files = [name for name in os.listdir(dist) if name != "backup"]
            backup_files = os.listdir(backup)
            self.assertEqual(root_files, [])
            self.assertEqual(backup_files, ["YGF-POS-Setup.exe"])
            with open(os.path.join(backup, backup_files[0]), "rb") as stream:
                self.assertEqual(stream.read(), b"previous build")


if __name__ == "__main__":
    unittest.main()
