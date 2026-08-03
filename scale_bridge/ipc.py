"""Local named-pipe status endpoint for ScaleBridge diagnostics."""
from __future__ import annotations

import json
import logging
import threading
from typing import Callable, Dict, Optional


logger = logging.getLogger("ScaleBridge")
DEFAULT_PIPE_NAME = r"\\.\pipe\YgfScaleBridgeStatus"


def _win32_modules():
    try:
        import pywintypes
        import win32file
        import win32pipe
        return pywintypes, win32file, win32pipe
    except ImportError as exc:
        raise RuntimeError("ScaleBridge named-pipe status needs pywin32") from exc


class StatusPipeServer:
    """Each local connection receives one JSON status snapshot and closes."""

    def __init__(self, status_provider: Callable[[], Dict], pipe_name: str = DEFAULT_PIPE_NAME):
        self._status_provider = status_provider
        self.pipe_name = pipe_name
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="ScaleBridgeStatusPipe", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        # Connecting once wakes a blocking ConnectNamedPipe call.
        try:
            read_status(self.pipe_name, timeout_ms=250)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout)

    def _serve(self) -> None:
        pywintypes, win32file, win32pipe = _win32_modules()
        while not self._stop.is_set():
            handle = None
            try:
                handle = win32pipe.CreateNamedPipe(
                    self.pipe_name,
                    win32pipe.PIPE_ACCESS_OUTBOUND,
                    win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
                    1,
                    8192,
                    8192,
                    0,
                    None,
                )
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except pywintypes.error as exc:
                    if exc.winerror != 535:  # ERROR_PIPE_CONNECTED
                        raise
                if not self._stop.is_set():
                    response = json.dumps(self._status_provider(), ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
                    win32file.WriteFile(handle, response)
            except Exception:
                if not self._stop.is_set():
                    logger.exception("ScaleBridge status pipe failed")
            finally:
                if handle is not None:
                    try:
                        win32file.CloseHandle(handle)
                    except Exception:
                        pass


def read_status(pipe_name: str = DEFAULT_PIPE_NAME, timeout_ms: int = 1500) -> Dict:
    """Read a single local status snapshot without touching serial ports."""
    _pywintypes, win32file, _win32pipe = _win32_modules()
    handle = win32file.CreateFile(
        pipe_name,
        win32file.GENERIC_READ,
        0,
        None,
        win32file.OPEN_EXISTING,
        0,
        None,
    )
    try:
        _code, data = win32file.ReadFile(handle, 8192, None)
        return json.loads(data.decode("utf-8"))
    finally:
        win32file.CloseHandle(handle)
