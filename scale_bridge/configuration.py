"""Persistent ScaleBridge configuration, kept separate from the POS UI config."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
import re
import tempfile
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

    def _validate(self, require_bridge_ports: bool) -> None:
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
        if bool(self.payment_pos_port) != bool(self.payment_plugin_port):
            raise ValueError("PaymentPosPort and PaymentPluginPort must both be configured or both be empty")
        ports = [value.upper() for value in required.values()]
        if not require_bridge_ports:
            ports.extend(
                value.upper()
                for value in (self.official_bridge_port, self.private_bridge_port)
                if value
            )
        if self.payment_pos_port:
            ports.extend([self.payment_pos_port.upper(), self.payment_plugin_port.upper()])
        if len(ports) != len(set(ports)):
            raise ValueError("ScaleBridge ports must be unique")
        application_ports = {
            "physical_scale.port": self.physical_scale.port,
            "official_pos_virtual_port": self.official_pos_virtual_port,
            "private_pos_virtual_port": self.private_pos_virtual_port,
            "payment_pos_port": self.payment_pos_port,
            "payment_plugin_port": self.payment_plugin_port,
        }
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
        self._validate(require_bridge_ports=False)

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
            "PaymentPosPort": self.payment_pos_port,
            "PaymentPluginPort": self.payment_plugin_port,
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
        identity = ScaleDeviceIdentity(
            port=str(raw.get("PhysicalScalePort", "")).upper(),
            pnp_device_id=str(raw.get("PhysicalScalePnpDeviceId", "")),
            hardware_id=str(raw.get("PhysicalScaleHardwareId", "")),
            vid=str(raw.get("PhysicalScaleVid", "")).upper(),
            pid=str(raw.get("PhysicalScalePid", "")).upper(),
            serial_number=str(raw.get("PhysicalScaleSerialNumber", "")),
            friendly_name=str(raw.get("PhysicalScaleFriendlyName", "")),
            manufacturer=str(raw.get("PhysicalScaleManufacturer", "")),
            service=str(raw.get("PhysicalScaleService", "")),
        )
        parity = str(raw.get("Parity", "N")).upper()
        if parity == "NONE":
            parity = "N"
        cfg = cls(
            physical_scale=identity,
            official_pos_virtual_port=str(raw.get("OfficialPosVirtualPort", "COM2")).upper(),
            private_pos_virtual_port=str(raw.get("PrivatePosVirtualPort", "COM3")).upper(),
            official_bridge_port=str(raw.get("OfficialBridgePort", "")).upper(),
            private_bridge_port=str(raw.get("PrivateBridgePort", "")).upper(),
            payment_pos_port=str(raw.get("PaymentPosPort", "")).upper(),
            payment_plugin_port=str(raw.get("PaymentPluginPort", "")).upper(),
            baudrate=int(raw.get("BaudRate", 9600)),
            data_bits=int(raw.get("DataBits", 8)),
            parity=parity,
            stop_bits=int(raw.get("StopBits", 1)),
            dtr_enable=_as_bool(raw.get("DtrEnable"), True),
            rts_enable=_as_bool(raw.get("RtsEnable"), False),
            official_active_timeout_ms=int(raw.get("OfficialActiveTimeoutMs", 1000)),
            reconnect_initial_delay_ms=int(raw.get("ReconnectInitialDelayMs", 1000)),
            reconnect_maximum_delay_ms=int(raw.get("ReconnectMaximumDelayMs", 10000)),
            maximum_frame_length=int(raw.get("MaximumFrameLength", 128)),
            queue_maxsize=int(raw.get("QueueMaxSize", 256)),
            suppress_private_query_when_official_active=_as_bool(raw.get("SuppressPrivateQueryWhenOfficialActive"), True),
            forward_private_non_query_when_official_active=_as_bool(raw.get("ForwardPrivateNonQueryWhenOfficialActive"), True),
            enable_debug_hex_log=_as_bool(raw.get("EnableDebugHexLog"), False),
        )
        return cfg


def load_config(path: str = DEFAULT_CONFIG_FILE) -> ScaleBridgeConfig:
    if not os.path.exists(path):
        return ScaleBridgeConfig()
    with open(path, "r", encoding="utf-8") as handle:
        return ScaleBridgeConfig.from_dict(json.load(handle))


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
