"""PyInstaller entry point for the standalone ScaleBridge repair CLI."""
from scale_bridge.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
