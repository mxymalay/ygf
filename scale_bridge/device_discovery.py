"""Physical serial-port discovery and stable identity matching for Windows 7."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional, Tuple

from .configuration import ScaleDeviceIdentity


_COM_RE = re.compile(r"^COM\d+$", re.IGNORECASE)
_VID_PID_RE = re.compile(r"VID_([0-9A-F]{4}).*PID_([0-9A-F]{4})", re.IGNORECASE)
_VIRTUAL_MARKERS = ("com0com", "cnca", "cncb", "vspd", "virtual serial", "eltima", "pair")


@dataclass
class SerialPortCandidate:
    port: str
    friendly_name: str
    pnp_device_id: str = ""
    hardware_id: str = ""
    manufacturer: str = ""
    product: str = ""
    service: str = ""
    vid: str = ""
    pid: str = ""
    serial_number: str = ""
    is_virtual: bool = False

    def to_identity(self) -> ScaleDeviceIdentity:
        return ScaleDeviceIdentity(
            port=self.port,
            pnp_device_id=self.pnp_device_id,
            hardware_id=self.hardware_id,
            vid=self.vid,
            pid=self.pid,
            serial_number=self.serial_number,
            friendly_name=self.friendly_name,
            manufacturer=self.manufacturer,
            service=self.service,
        )

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "friendly_name": self.friendly_name,
            "pnp_device_id": self.pnp_device_id,
            "hardware_id": self.hardware_id,
            "manufacturer": self.manufacturer,
            "product": self.product,
            "service": self.service,
            "vid": self.vid,
            "pid": self.pid,
            "serial_number": self.serial_number,
            "is_virtual": self.is_virtual,
        }


def _pnp_properties_by_port() -> dict:
    """Best-effort WMI enrichment; pyserial remains the required fallback."""
    entries = {}
    try:
        import win32com.client

        wmi = win32com.client.GetObject("winmgmts:")
        for item in wmi.ExecQuery("SELECT Name,DeviceID,HardwareID,Manufacturer,Service FROM Win32_PnPEntity"):
            name = str(getattr(item, "Name", "") or "")
            match = re.search(r"\((COM\d+)\)", name, re.IGNORECASE)
            if not match:
                continue
            hardware = getattr(item, "HardwareID", "") or ""
            if isinstance(hardware, (list, tuple)):
                hardware = "; ".join(str(value) for value in hardware)
            entries[match.group(1).upper()] = {
                "friendly_name": name,
                "pnp_device_id": str(getattr(item, "DeviceID", "") or ""),
                "hardware_id": str(hardware),
                "manufacturer": str(getattr(item, "Manufacturer", "") or ""),
                "service": str(getattr(item, "Service", "") or ""),
            }
    except Exception:
        pass
    return entries


def _is_virtual(*values: str) -> bool:
    text = " ".join(value.lower() for value in values if value)
    return any(marker in text for marker in _VIRTUAL_MARKERS)


def enumerate_serial_ports(include_virtual: bool = False) -> List[SerialPortCandidate]:
    """List real serial candidates, enriched with WMI identity when it is available."""
    try:
        import serial.tools.list_ports
    except ImportError as exc:
        raise RuntimeError("pyserial is required for serial-port discovery") from exc

    pnp = _pnp_properties_by_port()
    result: List[SerialPortCandidate] = []
    for port in serial.tools.list_ports.comports():
        name = str(port.device or "").upper()
        if not _COM_RE.fullmatch(name):
            continue
        extra = pnp.get(name, {})
        hwid = str(port.hwid or extra.get("hardware_id", ""))
        vid = ("%04X" % port.vid) if getattr(port, "vid", None) is not None else ""
        pid = ("%04X" % port.pid) if getattr(port, "pid", None) is not None else ""
        if not vid or not pid:
            match = _VID_PID_RE.search(hwid)
            if match:
                vid, pid = match.group(1).upper(), match.group(2).upper()
        candidate = SerialPortCandidate(
            port=name,
            friendly_name=str(extra.get("friendly_name") or port.description or name),
            pnp_device_id=str(extra.get("pnp_device_id") or hwid),
            hardware_id=hwid,
            manufacturer=str(extra.get("manufacturer") or port.manufacturer or ""),
            product=str(port.product or ""),
            service=str(extra.get("service") or ""),
            vid=vid,
            pid=pid,
            serial_number=str(port.serial_number or ""),
        )
        candidate.is_virtual = _is_virtual(
            candidate.friendly_name,
            candidate.pnp_device_id,
            candidate.hardware_id,
            candidate.manufacturer,
            candidate.service,
        )
        if include_virtual or not candidate.is_virtual:
            result.append(candidate)
    return sorted(result, key=lambda item: int(item.port[3:]))


def port_is_available(port_name: str, candidates: Optional[Iterable[SerialPortCandidate]] = None) -> bool:
    """A port name is available only when no enumerated device already owns it."""
    candidates = enumerate_serial_ports(include_virtual=True) if candidates is None else candidates
    target = port_name.upper()
    return all(candidate.port.upper() != target for candidate in candidates)


def _identity_score(saved: ScaleDeviceIdentity, candidate: SerialPortCandidate) -> int:
    score = 0
    if saved.pnp_device_id and saved.pnp_device_id.lower() == candidate.pnp_device_id.lower():
        score += 100
    if saved.serial_number and saved.serial_number.lower() == candidate.serial_number.lower():
        score += 80
    if saved.hardware_id and saved.hardware_id.lower() == candidate.hardware_id.lower():
        score += 60
    if saved.vid and saved.pid and saved.vid == candidate.vid and saved.pid == candidate.pid:
        score += 30
    if saved.friendly_name and saved.friendly_name.lower() == candidate.friendly_name.lower():
        score += 10
    return score


def resolve_saved_device(
    saved: ScaleDeviceIdentity,
    candidates: Optional[Iterable[SerialPortCandidate]] = None,
) -> Tuple[Optional[SerialPortCandidate], List[SerialPortCandidate]]:
    """Return one safe match, otherwise ``None`` and equally plausible candidates.

    A VID/PID-only result is intentionally ambiguous: several CH340 adapters may
    expose the same identity and must be selected by an installer/operator.
    """
    candidates = list(enumerate_serial_ports() if candidates is None else candidates)
    if saved.port:
        current = next((item for item in candidates if item.port == saved.port.upper()), None)
        if current and _identity_score(saved, current) >= 60:
            return current, []
    scored = [(candidate, _identity_score(saved, candidate)) for candidate in candidates]
    scored = [(candidate, score) for candidate, score in scored if score > 0]
    if not scored:
        return None, []
    best_score = max(score for _, score in scored)
    winners = [candidate for candidate, score in scored if score == best_score]
    if len(winners) == 1 and best_score >= 60:
        return winners[0], []
    return None, winners
