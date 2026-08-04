"""Persistent ScaleBridge configuration, kept separate from the POS UI config."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
import re
import shutil
import tempfile
import time
from typing import Any, Dict


DEFAULT_CONFIG_FILE = os.path.join("data", "scale_bridge.json")


def _as_bool(value: Any, default: bool) -> bool:
    """Parse JSON values and legacy string values without treating 'false' as true."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off", ""):
            return False
    raise ValueError("invalid boolean setting: %r" % (value,))


def _safe_bool(value: Any, default: bool) -> bool:
    try:
        return _as_bool(value, default)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        # Do not accept booleans as serial numbers even though bool is an int
        # subclass in Python.
        if isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()


# The current file uses stable PascalCase names.  A few early development
# builds wrote dataclass-style snake_case names, so accept those aliases while
# serialising only the canonical names in ``to_dict``.  Unknown fields remain
# ignored instead of being copied into the runtime configuration.
LEGACY_FIELD_ALIASES = {
    "PhysicalScalePort": ("scale_port",),
    "OfficialPosVirtualPort": ("official_port",),
    "PrivatePosVirtualPort": ("private_port",),
    "OfficialBridgePort": ("official_peer",),
    "PrivateBridgePort": ("private_peer",),
    "BaudRate": ("baudrate",),
}


def _value(raw: Dict[str, Any], canonical: str, default: Any) -> Any:
    for key in (canonical, _snake_case(canonical)) + LEGACY_FIELD_ALIASES.get(canonical, ()):
        if key in raw:
            return raw[key]
    return default


@dataclass
class ScaleDeviceIdentity:
    port: str = ""
    pnp_device_id: str = ""
    hardware_id: str = ""
    vid: str = ""
    pid: str = ""
    serial_number: str = ""
    friendly_name: str = ""
    manufacturer: str = ""
    service: str = ""


@dataclass
class ScaleBridgeConfig:
    """Configuration for the bridge service, not for a POS UI process."""
    physical_scale: ScaleDeviceIdentity = field(default_factory=ScaleDeviceIdentity)
    official_pos_virtual_port: str = "COM2"
    private_pos_virtual_port: str = "COM3"
    official_bridge_port: str = ""
    private_bridge_port: str = ""
    # Legacy fields retained for backward-compatible config loading only.
    # Payment pairing is now configured independently on the Shouqianba page.
    payment_pos_port: str = ""
    payment_plugin_port: str = ""
    baudrate: int = 9600
    data_bits: int = 8
    parity: str = "N"
    stop_bits: int = 1
    dtr_enable: bool = True
    rts_enable: bool = False
    official_active_timeout_ms: int = 1000
    reconnect_initial_delay_ms: int = 1000
    reconnect_maximum_delay_ms: int = 10000
    maximum_frame_length: int = 128
    queue_maxsize: int = 256
    suppress_private_query_when_official_active: bool = True
    forward_private_non_query_when_official_active: bool = True
    enable_debug_hex_log: bool = False

    @property
    def physical_scale_port(self) -> str:
        return self.physical_scale.port

    def _validate(self, require_bridge_ports: bool, require_payment: bool = True) -> None:
        required = {
            "physical_scale.port": self.physical_scale.port,
            "official_pos_virtual_port": self.official_pos_virtual_port,
            "private_pos_virtual_port": self.private_pos_virtual_port,
        }
        if require_bridge_ports:
            required.update({
                "official_bridge_port": self.official_bridge_port,
                "private_bridge_port": self.private_bridge_port,
            })
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("ScaleBridge configuration missing: " + ", ".join(missing))
        if require_payment and bool(self.payment_pos_port) != bool(self.payment_plugin_port):
            raise ValueError("PaymentPosPort and PaymentPluginPort must both be configured or both be empty")
        ports = [value.upper() for value in required.values()]
        if not require_bridge_ports:
            ports.extend(
                value.upper()
                for value in (self.official_bridge_port, self.private_bridge_port)
                if value
            )
        if require_payment and self.payment_pos_port:
            ports.extend([self.payment_pos_port.upper(), self.payment_plugin_port.upper()])
        if len(ports) != len(set(ports)):
            raise ValueError("ScaleBridge ports must be unique")
        application_ports = {
            "physical_scale.port": self.physical_scale.port,
            "official_pos_virtual_port": self.official_pos_virtual_port,
            "private_pos_virtual_port": self.private_pos_virtual_port,
        }
        if require_payment:
            application_ports.update({
                "payment_pos_port": self.payment_pos_port,
                "payment_plugin_port": self.payment_plugin_port,
            })
        for name, value in application_ports.items():
            if value and not re.fullmatch(r"COM[1-9]\d*", value, re.IGNORECASE):
                raise ValueError("%s must be a COM port name: %s" % (name, value))
        for name, value in {
            "official_bridge_port": self.official_bridge_port,
            "private_bridge_port": self.private_bridge_port,
        }.items():
            if value and not re.fullmatch(r"(?:COM[1-9]\d*|CNC[AB]\d+)", value, re.IGNORECASE):
                raise ValueError("%s is not a valid bridge endpoint: %s" % (name, value))
        if self.baudrate <= 0 or self.maximum_frame_length < 16:
            raise ValueError("Invalid serial or frame configuration")
        if self.data_bits not in (5, 6, 7, 8):
            raise ValueError("DataBits must be 5, 6, 7 or 8")
        if self.parity not in ("N", "E", "O", "M", "S"):
            raise ValueError("Parity must be N, E, O, M or S")
        if self.stop_bits not in (1, 2):
            raise ValueError("StopBits must be 1 or 2")
        if self.official_active_timeout_ms <= 0 or self.reconnect_initial_delay_ms <= 0:
            raise ValueError("Timeout and reconnect delays must be positive")
        if self.reconnect_maximum_delay_ms < self.reconnect_initial_delay_ms:
            raise ValueError("ReconnectMaximumDelayMs must not be below the initial delay")
        if self.queue_maxsize <= 0:
            raise ValueError("QueueMaxSize must be positive")

    def validate(self) -> None:
        """Validate a runtime-ready configuration with resolved bridge peers."""
        self._validate(require_bridge_ports=True)

    def validate_for_setup(self) -> None:
        """Validate first-run fields before com0com assigns internal peers."""
        # Payment pairing is maintained on a separate page.  Ignore stale
        # legacy PaymentPosPort/PaymentPluginPort values while preparing the
        # scale bridge; ensure_required_pairs validates them only when the
        # payment purpose is explicitly requested.
        self._validate(require_bridge_ports=False, require_payment=False)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # External config names are intentionally stable and independent of Python fields.
        return {
            "PhysicalScalePort": data["physical_scale"]["port"],
            "PhysicalScalePnpDeviceId": data["physical_scale"]["pnp_device_id"],
            "PhysicalScaleHardwareId": data["physical_scale"]["hardware_id"],
            "PhysicalScaleVid": data["physical_scale"]["vid"],
            "PhysicalScalePid": data["physical_scale"]["pid"],
            "PhysicalScaleSerialNumber": data["physical_scale"]["serial_number"],
            "PhysicalScaleFriendlyName": data["physical_scale"]["friendly_name"],
            "PhysicalScaleManufacturer": data["physical_scale"]["manufacturer"],
            "PhysicalScaleService": data["physical_scale"]["service"],
            "OfficialPosVirtualPort": self.official_pos_virtual_port,
            "PrivatePosVirtualPort": self.private_pos_virtual_port,
            "OfficialBridgePort": self.official_bridge_port,
            "PrivateBridgePort": self.private_bridge_port,
            # Payment pairing moved to the independent Shouqianba settings
            # page.  ``from_dict`` still reads these two names for one-way
            # migration of old files, but new ScaleBridge files must not keep
            # duplicate/stale payment configuration.
            "BaudRate": self.baudrate,
            "DataBits": self.data_bits,
            "Parity": self.parity,
            "StopBits": self.stop_bits,
            "DtrEnable": self.dtr_enable,
            "RtsEnable": self.rts_enable,
            "OfficialActiveTimeoutMs": self.official_active_timeout_ms,
            "ReconnectInitialDelayMs": self.reconnect_initial_delay_ms,
            "ReconnectMaximumDelayMs": self.reconnect_maximum_delay_ms,
            "MaximumFrameLength": self.maximum_frame_length,
            "QueueMaxSize": self.queue_maxsize,
            "SuppressPrivateQueryWhenOfficialActive": self.suppress_private_query_when_official_active,
            "ForwardPrivateNonQueryWhenOfficialActive": self.forward_private_non_query_when_official_active,
            "EnableDebugHexLog": self.enable_debug_hex_log,
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "ScaleBridgeConfig":
        if not isinstance(raw, dict):
            raise ValueError("ScaleBridge 配置根节点必须是对象")
        identity = ScaleDeviceIdentity(
            port=_as_text(_value(raw, "PhysicalScalePort", "")).upper(),
            pnp_device_id=_as_text(_value(raw, "PhysicalScalePnpDeviceId", "")),
            hardware_id=_as_text(_value(raw, "PhysicalScaleHardwareId", "")),
            vid=_as_text(_value(raw, "PhysicalScaleVid", "")).upper(),
            pid=_as_text(_value(raw, "PhysicalScalePid", "")).upper(),
            serial_number=_as_text(_value(raw, "PhysicalScaleSerialNumber", "")),
            friendly_name=_as_text(_value(raw, "PhysicalScaleFriendlyName", "")),
            manufacturer=_as_text(_value(raw, "PhysicalScaleManufacturer", "")),
            service=_as_text(_value(raw, "PhysicalScaleService", "")),
        )
        parity = _as_text(_value(raw, "Parity", "N"), "N").upper()
        if parity == "NONE":
            parity = "N"
        cfg = cls(
            physical_scale=identity,
            official_pos_virtual_port=_as_text(_value(raw, "OfficialPosVirtualPort", "COM2"), "COM2").upper(),
            private_pos_virtual_port=_as_text(_value(raw, "PrivatePosVirtualPort", "COM3"), "COM3").upper(),
            official_bridge_port=_as_text(_value(raw, "OfficialBridgePort", "")).upper(),
            private_bridge_port=_as_text(_value(raw, "PrivateBridgePort", "")).upper(),
            payment_pos_port=_as_text(_value(raw, "PaymentPosPort", "")).upper(),
            payment_plugin_port=_as_text(_value(raw, "PaymentPluginPort", "")).upper(),
            baudrate=_as_int(_value(raw, "BaudRate", 9600), 9600),
            data_bits=_as_int(_value(raw, "DataBits", 8), 8),
            parity=parity,
            stop_bits=_as_int(_value(raw, "StopBits", 1), 1),
            dtr_enable=_safe_bool(_value(raw, "DtrEnable", None), True),
            rts_enable=_safe_bool(_value(raw, "RtsEnable", None), False),
            official_active_timeout_ms=_as_int(_value(raw, "OfficialActiveTimeoutMs", 1000), 1000),
            reconnect_initial_delay_ms=_as_int(_value(raw, "ReconnectInitialDelayMs", 1000), 1000),
            reconnect_maximum_delay_ms=_as_int(_value(raw, "ReconnectMaximumDelayMs", 10000), 10000),
            maximum_frame_length=_as_int(_value(raw, "MaximumFrameLength", 128), 128),
            queue_maxsize=_as_int(_value(raw, "QueueMaxSize", 256), 256),
            suppress_private_query_when_official_active=_safe_bool(_value(raw, "SuppressPrivateQueryWhenOfficialActive", None), True),
            forward_private_non_query_when_official_active=_safe_bool(_value(raw, "ForwardPrivateNonQueryWhenOfficialActive", None), True),
            enable_debug_hex_log=_safe_bool(_value(raw, "EnableDebugHexLog", None), False),
        )
        return cfg


def load_config(path: str = DEFAULT_CONFIG_FILE) -> ScaleBridgeConfig:
    if not os.path.exists(path):
        return ScaleBridgeConfig()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        config = ScaleBridgeConfig.from_dict(raw)
        # Migrate valid legacy/foreign fields immediately, using the same
        # atomic writer as normal saves.  A read-only deployment simply keeps
        # the in-memory canonical object if the rewrite is not permitted.
        canonical = config.to_dict()
        if raw != canonical:
            try:
                save_config(config, path)
            except OSError as exc:
                print("[ScaleBridge 配置 Warning] 无法写回规范格式: %s" % exc)
        return config
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # A half-written/old file must not crash the POS or the Windows
        # service.  Preserve the exact bytes for support and start from the
        # safe unconfigured defaults; the setup page can then initialise it.
        backup = "%s.corrupt.%s" % (path, time.strftime("%Y%m%d_%H%M%S"))
        try:
            shutil.copy2(path, backup)
        except OSError:
            backup = ""
        print(
            "[ScaleBridge 配置 Warning] 无法读取 %s: %s%s"
            % (path, exc, ("，已备份到 " + backup) if backup else "")
        )
        return ScaleBridgeConfig()


def save_config(config: ScaleBridgeConfig, path: str = DEFAULT_CONFIG_FILE) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="scale_bridge_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config.to_dict(), handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
