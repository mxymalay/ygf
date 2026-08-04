"""Console output that cannot take down the touch POS on legacy Windows."""
from __future__ import annotations

import os
import sys


class ResilientConsoleStream:
    """Proxy stdout/stderr and ignore transient Win7 console-handle errors."""

    def __init__(self, stream):
        self._stream = stream

    def write(self, value):
        text = str(value)
        try:
            return self._stream.write(text)
        except (OSError, IOError, ValueError):
            # Win7 can return ERROR_GEN_FAILURE (31) when the launcher/UAC
            # console handle was replaced or detached. Application logging is
            # file-backed; console diagnostics are deliberately best-effort.
            return len(text)

    def flush(self):
        try:
            return self._stream.flush()
        except (OSError, IOError, ValueError):
            return None

    def isatty(self):
        try:
            return bool(self._stream.isatty())
        except Exception:
            return False

    @property
    def encoding(self):
        return getattr(self._stream, "encoding", "utf-8") or "utf-8"

    @property
    def errors(self):
        return getattr(self._stream, "errors", "replace") or "replace"

    def __getattr__(self, name):
        return getattr(self._stream, name)


def install_safe_console_streams():
    """Install safe proxies once for the GUI process and detached launchers."""
    for name in ("stdout", "stderr"):
        current = getattr(sys, name, None)
        if current is None:
            current = open(os.devnull, "w")
        if not isinstance(current, ResilientConsoleStream):
            setattr(sys, name, ResilientConsoleStream(current))

