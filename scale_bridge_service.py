"""PyInstaller entry point for the standalone ScaleBridge Windows service."""
from scale_bridge.service import main


if __name__ == "__main__":
    raise SystemExit(main())
