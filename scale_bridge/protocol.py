"""Byte-safe DIBAL ACS-G315 framing and weight parsing."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

DIBAL_QUERY = b"$"
FRAME_END = 0x0D
_WEIGHT_RE = re.compile(rb"^[+-]?\d{1,5}\.\d{1,4}")


class DibalFrameAssembler:
    """Accumulates arbitrary serial chunks and emits CR-terminated frames."""

    def __init__(self, maximum_frame_length: int = 128):
        self.maximum_frame_length = maximum_frame_length
        self._buffer = bytearray()
        self.oversize_frames = 0

    def feed(self, data: bytes) -> Tuple[List[bytes], int]:
        """Return complete frames without CR and number of discarded bytes."""
        if not data:
            return [], 0
        self._buffer.extend(data)
        frames: List[bytes] = []
        discarded = 0
        while True:
            try:
                end = self._buffer.index(FRAME_END)
            except ValueError:
                if len(self._buffer) > self.maximum_frame_length:
                    discarded += len(self._buffer)
                    self._buffer.clear()
                    self.oversize_frames += 1
                break
            frame = bytes(self._buffer[:end])
            del self._buffer[:end + 1]
            if len(frame) > self.maximum_frame_length:
                discarded += len(frame)
                self.oversize_frames += 1
                continue
            if frame:
                frames.append(frame)
        return frames, discarded


def parse_dibal_weight(frame: bytes) -> Optional[float]:
    """Parse one DIBAL frame without changing the forwarded bytes.

    Some ACS-G315 firmware appends a one-byte protocol/status value after the
    numeric weight and before CR (for example ``b"000.402\\xb2"``).  Accept
    those non-printable/high-bit status bytes while still rejecting printable
    garbage after the numeric value.
    """
    raw = bytes(frame or b"").strip(b" \t")
    match = _WEIGHT_RE.match(raw) if raw else None
    if not match:
        return None
    suffix = raw[match.end():]
    if len(suffix) > 4 or any(0x20 <= value < 0x80 for value in suffix):
        return None
    try:
        return float(raw[:match.end()].decode("ascii"))
    except ValueError:
        return None
