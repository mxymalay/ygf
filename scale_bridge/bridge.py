"""Concurrent, single-owner serial runtime for ScaleBridge."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, asdict, field
import logging
import threading
import time
from typing import Callable, Deque, Optional

from .arbiter import BridgeMode, OfficialPriorityArbiter
from .configuration import ScaleBridgeConfig, save_config
from .device_discovery import enumerate_serial_ports, has_saved_hardware_identity, resolve_saved_device


logger = logging.getLogger("ScaleBridge")


class QueueOverflow(RuntimeError):
    pass


class BoundedPriorityQueue:
    """Thread-safe FIFO queue with official traffic ahead of private traffic."""

    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._high: Deque[bytes] = deque()
        self._normal: Deque[bytes] = deque()
        self._condition = threading.Condition()
        self.dropped = 0

    def put(self, data: bytes, high_priority: bool = False) -> bool:
        if not data:
            return True
        with self._condition:
            if len(self._high) + len(self._normal) >= self.maxsize:
                if high_priority and self._normal:
                    # Never lose the first official command behind a backlog of
                    # private polls. Evict the oldest normal item instead.
                    self._normal.popleft()
                    self.dropped += 1
                else:
                    self.dropped += 1
                    return False
            (self._high if high_priority else self._normal).append(bytes(data))
            self._condition.notify()
            return True

    def get(self, timeout: float = 0.2) -> Optional[bytes]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._high and not self._normal:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return self._high.popleft() if self._high else self._normal.popleft()

    def clear(self) -> None:
        with self._condition:
            self._high.clear()
            self._normal.clear()

    def __len__(self) -> int:
        with self._condition:
            return len(self._high) + len(self._normal)


@dataclass
class BridgeStatus:
    mode: str = BridgeMode.UNKNOWN.value
    physical_port: str = ""
    physical_device_identity: dict = field(default_factory=dict)
    official_pos_virtual_port: str = ""
    private_pos_virtual_port: str = ""
    official_bridge_port: str = ""
    private_bridge_port: str = ""
    physical_open: bool = False
    official_bridge_open: bool = False
    private_bridge_open: bool = False
    last_weight_kg: Optional[float] = None
    suppressed_private_queries: int = 0
    invalid_frames: int = 0
    valid_frames: int = 0
    last_official_poll_age_ms: Optional[int] = None
    last_private_poll_age_ms: Optional[int] = None
    last_scale_reply_age_ms: Optional[int] = None
    reconnect_count: int = 0
    rebound_count: int = 0
    physical_queue_length: int = 0
    official_output_queue_length: int = 0
    private_output_queue_length: int = 0
    physical_queue_dropped: int = 0
    official_output_queue_dropped: int = 0
    private_output_queue_dropped: int = 0
    last_error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ScaleBridgeRuntime:
    """Owns the physical scale port and bridges two com0com peer endpoints.

    The runtime may be hosted by a Windows service or run in foreground for a
    maintenance test. No POS process needs access to the physical scale port.
    """

    def __init__(
        self,
        config: ScaleBridgeConfig,
        config_path: Optional[str] = None,
        serial_factory=None,
        on_status: Optional[Callable[[BridgeStatus], None]] = None,
    ):
        self.config = config
        self.config_path = config_path
        self._serial_factory = serial_factory
        self._on_status = on_status
        self._arbiter = OfficialPriorityArbiter(
            official_active_timeout_ms=config.official_active_timeout_ms,
            maximum_frame_length=config.maximum_frame_length,
            suppress_private_query=config.suppress_private_query_when_official_active,
            forward_private_non_query=config.forward_private_non_query_when_official_active,
        )
        # Three reader workers use the same framing/mode state.  The serial
        # ports are concurrent, the protocol arbiter is intentionally not.
        self._arbiter_lock = threading.Lock()
        self._physical_queue = BoundedPriorityQueue(config.queue_maxsize)
        self._official_output_queue = BoundedPriorityQueue(config.queue_maxsize)
        self._private_output_queue = BoundedPriorityQueue(config.queue_maxsize)
        self._stop = threading.Event()
        self._session_failed = threading.Event()
        self._manager_thread: Optional[threading.Thread] = None
        self._session_threads = []
        self._ports_lock = threading.Lock()
        self._physical = None
        self._official = None
        self._private = None
        self._status_lock = threading.Lock()
        self._status = BridgeStatus(
            physical_port=config.physical_scale_port,
            physical_device_identity=asdict(config.physical_scale),
            official_pos_virtual_port=config.official_pos_virtual_port,
            private_pos_virtual_port=config.private_pos_virtual_port,
            official_bridge_port=config.official_bridge_port,
            private_bridge_port=config.private_bridge_port,
        )
        self._last_logged_mode = ""
        self._last_logged_suppressed = 0

    def start(self) -> None:
        if self._manager_thread and self._manager_thread.is_alive():
            return
        self.config.validate()
        self._stop.clear()
        self._manager_thread = threading.Thread(target=self._manager_loop, name="ScaleBridgeManager", daemon=True)
        self._manager_thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        # Never send stale POS queries during shutdown. Allow already received
        # scale replies a short bounded window to reach both POS endpoints.
        self._physical_queue.clear()
        drain_deadline = time.monotonic() + min(0.5, max(0.0, timeout))
        while time.monotonic() < drain_deadline:
            if not len(self._official_output_queue) and not len(self._private_output_queue):
                break
            time.sleep(0.01)
        self._session_failed.set()
        self._close_ports()
        if self._manager_thread:
            self._manager_thread.join(timeout)

    def status(self) -> BridgeStatus:
        with self._status_lock:
            self._update_status_from_arbiter()
            return BridgeStatus(**self._status.to_dict())

    def _publish_status(self, **changes) -> None:
        with self._status_lock:
            for key, value in changes.items():
                setattr(self._status, key, value)
            self._update_status_from_arbiter()
            snapshot = BridgeStatus(**self._status.to_dict())
        if self._on_status:
            try:
                self._on_status(snapshot)
            except Exception:
                logger.exception("ScaleBridge status callback failed")

    def _update_status_from_arbiter(self) -> None:
        with self._arbiter_lock:
            arbiter_status = self._arbiter.status()
        self._status.mode = arbiter_status["mode"]
        self._status.last_weight_kg = arbiter_status["last_weight_kg"]
        self._status.suppressed_private_queries = arbiter_status["suppressed_private_queries"]
        self._status.invalid_frames = arbiter_status["invalid_frames"]
        self._status.valid_frames = arbiter_status["valid_frames"]
        self._status.last_official_poll_age_ms = arbiter_status["last_official_poll_age_ms"]
        self._status.last_private_poll_age_ms = arbiter_status["last_private_poll_age_ms"]
        self._status.last_scale_reply_age_ms = arbiter_status["last_scale_reply_age_ms"]
        self._status.physical_queue_length = len(self._physical_queue)
        self._status.official_output_queue_length = len(self._official_output_queue)
        self._status.private_output_queue_length = len(self._private_output_queue)
        self._status.physical_queue_dropped = self._physical_queue.dropped
        self._status.official_output_queue_dropped = self._official_output_queue.dropped
        self._status.private_output_queue_dropped = self._private_output_queue.dropped
        if self._status.mode != self._last_logged_mode:
            logger.info("ScaleBridge mode changed: %s -> %s", self._last_logged_mode or "START", self._status.mode)
            self._last_logged_mode = self._status.mode

    def _manager_loop(self) -> None:
        delay = self.config.reconnect_initial_delay_ms / 1000.0
        maximum_delay = self.config.reconnect_maximum_delay_ms / 1000.0
        while not self._stop.is_set():
            with self._arbiter_lock:
                self._arbiter.set_transport_state(BridgeMode.RECONNECTING)
            self._publish_status(last_error="")
            try:
                self._prepare_physical_port()
                self._open_session()
                with self._arbiter_lock:
                    self._arbiter.transport_recovered()
                self._publish_status(
                    physical_open=True,
                    official_bridge_open=True,
                    private_bridge_open=True,
                    last_error="",
                )
                delay = self.config.reconnect_initial_delay_ms / 1000.0
                self._session_failed.wait()
            except Exception as exc:
                message = str(exc)
                logger.warning("ScaleBridge connection failed: %s", message)
                self._publish_status(last_error=message)
            finally:
                self._close_ports()
                self._join_session_threads()
                self._publish_status(
                    physical_open=False,
                    official_bridge_open=False,
                    private_bridge_open=False,
                )
            if self._stop.is_set():
                break
            with self._status_lock:
                self._status.reconnect_count += 1
            self._stop.wait(delay)
            delay = min(maximum_delay, delay * 2)
        with self._arbiter_lock:
            self._arbiter.set_transport_state(BridgeMode.FAULTED)
        self._publish_status()

    def _prepare_physical_port(self) -> None:
        """Rebind a USB adapter only when saved identity produces one safe match."""
        candidates = enumerate_serial_ports(include_virtual=False)
        resolved, ambiguous = resolve_saved_device(self.config.physical_scale, candidates)
        configured = next((item for item in candidates if item.port == self.config.physical_scale_port.upper()), None)
        if resolved and resolved.port != self.config.physical_scale_port:
            self.config.physical_scale = resolved.to_identity()
            if self.config_path:
                save_config(self.config, self.config_path)
            with self._status_lock:
                self._status.rebound_count += 1
            self._publish_status(
                physical_port=resolved.port,
                physical_device_identity=asdict(resolved.to_identity()),
            )
            logger.info("Scale device re-bound to %s by saved hardware identity", resolved.port)
        elif not configured and ambiguous:
            choices = ", ".join(item.port for item in ambiguous)
            raise RuntimeError("scale device identity is ambiguous; operator selection required: " + choices)
        elif not configured and not resolved:
            raise RuntimeError("configured physical scale port is not present: " + self.config.physical_scale_port)
        elif configured and has_saved_hardware_identity(self.config.physical_scale) and not resolved:
            raise RuntimeError(
                "configured port %s is now a different device; saved scale identity did not match"
                % self.config.physical_scale_port
            )

    def _new_serial(self, port: str):
        if self._serial_factory is None:
            import serial
            factory = serial.Serial
        else:
            factory = self._serial_factory
        ser = factory(
            port=port,
            baudrate=self.config.baudrate,
            bytesize=self.config.data_bits,
            parity=self.config.parity,
            stopbits=self.config.stop_bits,
            timeout=0.1,
            write_timeout=0.5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        ser.dtr = self.config.dtr_enable
        ser.rts = self.config.rts_enable
        return ser

    def _open_session(self) -> None:
        self._session_failed.clear()
        # Queries captured before a disconnect are no longer meaningful after a
        # device/USB reconnect.  Never replay them to a newly opened scale.
        self._physical_queue.clear()
        self._official_output_queue.clear()
        self._private_output_queue.clear()
        opened = []
        try:
            physical = self._new_serial(self.config.physical_scale_port)
            opened.append(physical)
            official = self._new_serial(self.config.official_bridge_port)
            opened.append(official)
            private = self._new_serial(self.config.private_bridge_port)
            opened.append(private)
        except Exception:
            for ser in opened:
                try:
                    ser.close()
                except Exception:
                    pass
            raise
        with self._ports_lock:
            self._physical, self._official, self._private = physical, official, private
        logger.info(
            "ScaleBridge ports opened: physical=%s official=%s private=%s",
            self.config.physical_scale_port,
            self.config.official_bridge_port,
            self.config.private_bridge_port,
        )
        self._session_threads = [
            self._start_worker("ScaleBridgePhysicalRead", self._physical_reader),
            self._start_worker("ScaleBridgeOfficialRead", lambda: self._bridge_reader("official")),
            self._start_worker("ScaleBridgePrivateRead", lambda: self._bridge_reader("private")),
            self._start_worker("ScaleBridgePhysicalWrite", self._physical_writer),
            self._start_worker("ScaleBridgeOfficialWrite", lambda: self._output_writer("official")),
            self._start_worker("ScaleBridgePrivateWrite", lambda: self._output_writer("private")),
        ]

    @staticmethod
    def _start_worker(name: str, target: Callable[[], None]) -> threading.Thread:
        thread = threading.Thread(target=target, name=name, daemon=True)
        thread.start()
        return thread

    def _read_available(self, ser) -> bytes:
        waiting = getattr(ser, "in_waiting", 0) or 0
        return ser.read(max(1, min(256, int(waiting))))

    def _physical_reader(self) -> None:
        try:
            while not self._stop.is_set() and not self._session_failed.is_set():
                data = self._read_available(self._physical)
                if not data:
                    continue
                if self.config.enable_debug_hex_log:
                    logger.debug("Scale -> Both: %s", data.hex(" "))
                # Broadcast exact bytes first. Local frame parsing never alters POS output.
                if not self._official_output_queue.put(data):
                    logger.warning("official output queue overflow")
                if not self._private_output_queue.put(data):
                    logger.warning("private output queue overflow")
                with self._arbiter_lock:
                    self._arbiter.accept_scale_bytes(data)
                self._publish_status()
        except Exception as exc:
            self._fail_session("physical read failed: " + str(exc))

    def _bridge_reader(self, source: str) -> None:
        ser = self._official if source == "official" else self._private
        try:
            while not self._stop.is_set() and not self._session_failed.is_set():
                data = self._read_available(ser)
                if not data:
                    continue
                if self.config.enable_debug_hex_log:
                    logger.debug("%s -> Scale: %s", source.title(), data.hex(" "))
                with self._arbiter_lock:
                    outbound = self._arbiter.route_official(data) if source == "official" else self._arbiter.route_private(data)
                    suppressed = self._arbiter.suppressed_private_queries
                if suppressed != self._last_logged_suppressed:
                    self._last_logged_suppressed = suppressed
                    if suppressed == 1 or suppressed % 50 == 0:
                        logger.info("suppressed private scale queries: %d", suppressed)
                if outbound:
                    if not self._physical_queue.put(outbound, high_priority=(source == "official")):
                        logger.warning("physical write queue overflow (%s)", source)
                self._publish_status()
        except Exception as exc:
            self._fail_session("%s bridge read failed: %s" % (source, exc))

    def _physical_writer(self) -> None:
        self._queue_writer(self._physical_queue, lambda: self._physical, "physical")

    def _output_writer(self, target: str) -> None:
        queue = self._official_output_queue if target == "official" else self._private_output_queue
        serial_getter = (lambda: self._official) if target == "official" else (lambda: self._private)
        self._queue_writer(queue, serial_getter, target + " output")

    def _queue_writer(self, queue: BoundedPriorityQueue, serial_getter: Callable[[], object], label: str) -> None:
        try:
            while not self._session_failed.is_set() and (not self._stop.is_set() or len(queue) > 0):
                data = queue.get()
                if data is None:
                    continue
                ser = serial_getter()
                if ser is None:
                    return
                ser.write(data)
                ser.flush()
        except Exception as exc:
            self._fail_session("%s write failed: %s" % (label, exc))

    def _fail_session(self, message: str) -> None:
        if not self._session_failed.is_set():
            logger.warning("ScaleBridge session failure: %s", message)
            self._publish_status(last_error=message)
            self._session_failed.set()

    def _close_ports(self) -> None:
        with self._ports_lock:
            ports = (self._physical, self._official, self._private)
            self._physical = self._official = self._private = None
        for ser in ports:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

    def _join_session_threads(self) -> None:
        current = threading.current_thread()
        for thread in self._session_threads:
            if thread is not current:
                thread.join(1.0)
        self._session_threads = []
