"""PyInstaller and source-tree entry point for the ScaleBridge service.

The source-tree subclass is deliberate: pywin32 records it as this file's
absolute path.  pythonservice.exe can load that path before it imports the
``scale_bridge`` package.  The frozen build keeps using the original class.
"""
import os
import sys


def _ensure_standard_streams():
    """Give pywin32 safe streams in a PyInstaller windowed service host."""
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


_ensure_standard_streams()

from scale_bridge.service import ScaleBridgeWindowsService as _RuntimeService
from scale_bridge.service import main as _runtime_main


if _RuntimeService:
    class ScaleBridgeWindowsService(_RuntimeService):
        """Source-tree host class registered by pywin32."""
        pass
else:  # pragma: no cover - only used where pywin32 is unavailable.
    ScaleBridgeWindowsService = None


def main(argv=None):
    return _runtime_main(argv, service_class=ScaleBridgeWindowsService)


if __name__ == "__main__":
    raise SystemExit(main())
