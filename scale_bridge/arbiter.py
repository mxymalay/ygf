"""Official-POS priority arbitration, independent from serial I/O threads."""
from __future__ import annotations

from enum import Enum
import time
from typing import Callable, Optional

from .protocol import DIBAL_QUERY, DibalFrameAssembler, parse_dibal_weight


class BridgeMode(str, Enum):
    UNKNOWN = "UNKNOWN"
    OFFICIAL_ACTIVE = "OFFICIAL_ACTIVE"
    PRIVATE_ACTIVE = "PRIVATE_ACTIVE"
    RECONNECTING = "RECONNECTING"
    FAULTED = "FAULTED"


class OfficialPriorityArbiter:
    """Routes command chunks and parses scale replies without serial side effects."""

    def __init__(
        self,
        official_active_timeout_ms: int = 1000,
        maximum_frame_length: int = 128,
        suppress_private_query: bool = True,
        forward_private_non_query: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._timeout_seconds = official_active_timeout_ms / 1000.0
        self._suppress_private_query = suppress_private_query
        self._forward_private_non_query = forward_private_non_query
        self._clock = clock
        self._frames = DibalFrameAssembler(maximum_frame_length)
        self.last_official_poll: Optional[float] = None
        self.last_private_poll: Optional[float] = None
        self.last_scale_reply: Optional[float] = None
        self.last_weight_kg: Optional[float] = None
        self.suppressed_private_queries = 0
        self.invalid_frames = 0
        self.mode = BridgeMode.UNKNOWN

    def official_is_active(self, now: Optional[float] = None) -> bool:
        if self.last_official_poll is None:
            return False
        now = self._clock() if now is None else now
        return now - self.last_official_poll < self._timeout_seconds

    def refresh_mode(self, now: Optional[float] = None) -> BridgeMode:
        if self.mode in (BridgeMode.RECONNECTING, BridgeMode.FAULTED):
            return self.mode
        self.mode = BridgeMode.OFFICIAL_ACTIVE if self.official_is_active(now) else BridgeMode.PRIVATE_ACTIVE
        return self.mode

    def set_transport_state(self, mode: BridgeMode) -> None:
        if mode not in (BridgeMode.RECONNECTING, BridgeMode.FAULTED):
            raise ValueError("transport state must be RECONNECTING or FAULTED")
        self.mode = mode

    def transport_recovered(self) -> BridgeMode:
        self.mode = BridgeMode.UNKNOWN
        return self.refresh_mode()

    def route_official(self, data: bytes, now: Optional[float] = None) -> bytes:
        """Official bytes are always forwarded and make the official channel active on `$`."""
        if not data:
            return b""
        now = self._clock() if now is None else now
        if DIBAL_QUERY in data:
            self.last_official_poll = now
            self.mode = BridgeMode.OFFICIAL_ACTIVE
        return data

    def route_private(self, data: bytes, now: Optional[float] = None) -> bytes:
        """Suppress only `$` while official is active; optional non-query bytes pass through."""
        if not data:
            return b""
        now = self._clock() if now is None else now
        if DIBAL_QUERY in data:
            self.last_private_poll = now
        if not self.official_is_active(now):
            self.mode = BridgeMode.PRIVATE_ACTIVE
            return data
        self.mode = BridgeMode.OFFICIAL_ACTIVE
        if not self._suppress_private_query:
            return data
        query_count = data.count(DIBAL_QUERY)
        self.suppressed_private_queries += query_count
        remaining = data.replace(DIBAL_QUERY, b"")
        return remaining if self._forward_private_non_query else b""

    def accept_scale_bytes(self, data: bytes, now: Optional[float] = None):
        """Parse local copies of scale bytes; callers must broadcast the original bytes unchanged."""
        if not data:
            return []
        now = self._clock() if now is None else now
        self.last_scale_reply = now
        frames, _ = self._frames.feed(data)
        parsed = []
        for frame in frames:
            weight = parse_dibal_weight(frame)
            if weight is None:
                self.invalid_frames += 1
                continue
            self.last_weight_kg = weight
            parsed.append(weight)
        return parsed

    def status(self) -> dict:
        self.refresh_mode()
        return {
            "mode": self.mode.value,
            "last_weight_kg": self.last_weight_kg,
            "suppressed_private_queries": self.suppressed_private_queries,
            "invalid_frames": self.invalid_frames,
            "official_active": self.official_is_active(),
        }
