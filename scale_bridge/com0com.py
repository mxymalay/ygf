"""Safe, explicit maintenance support for persistent com0com pairs.

This module deliberately does not run during normal ScaleBridge startup.  A
technician can use its read-only inspection from the diagnostics screen; pair
creation/removal is an elevated, explicitly authorised maintenance operation.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import subprocess
from typing import Dict, Iterable, List, Optional, Tuple


SETUPC_CANDIDATES = (
    ("ProgramFiles", "com0com", "setupc.exe"),
    ("ProgramFiles(x86)", "com0com", "setupc.exe"),
    ("ProgramW6432", "com0com", "setupc.exe"),
)


@dataclass(frozen=True)
class Com0ComPair:
    index: int
    side_a: str
    side_b: str

    def contains(self, port: str) -> bool:
        return port.upper() in (self.side_a.upper(), self.side_b.upper())


@dataclass(frozen=True)
class PairCheck:
    client_port: str
    bridge_port: str
    present: bool
    pair: Optional[Com0ComPair] = None
    message: str = ""


def find_setupc(extra_paths: Iterable[str] = ()) -> Optional[str]:
    """Find the command tool after a human has installed com0com."""
    candidates = list(extra_paths)
    for variable, *parts in SETUPC_CANDIDATES:
        root = os.environ.get(variable)
        if root:
            candidates.append(os.path.join(root, *parts))
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def parse_setupc_list(output: str) -> List[Com0ComPair]:
    """Parse `setupc list` output without assuming its display language.

    setupc exposes a pair as CNCA<n> / CNCB<n>, optionally with a PortName
    property.  If a side has no PortName it is still usable via its CNCA/B name.
    """
    sides: Dict[int, Dict[str, str]] = {}
    side_pattern = re.compile(r"\bCNC([AB])(\d+)\b", re.I)
    name_pattern = re.compile(r"\bPortName\s*=\s*([^,\s]+)", re.I)
    for line in output.splitlines():
        match = side_pattern.search(line)
        if not match:
            continue
        side, index_text = match.groups()
        name_match = name_pattern.search(line)
        port_name = name_match.group(1) if name_match else ""
        index = int(index_text)
        endpoint = (port_name or "CNC%s%s" % (side.upper(), index)).upper()
        sides.setdefault(index, {})[side.upper()] = endpoint
    pairs = []
    for index, endpoints in sorted(sides.items()):
        if "A" in endpoints and "B" in endpoints:
            pairs.append(Com0ComPair(index, endpoints["A"], endpoints["B"]))
    return pairs


def list_pairs(setupc_path: Optional[str] = None, timeout_seconds: int = 10) -> List[Com0ComPair]:
    """Read installed pairs.  This operation never changes driver state."""
    executable = setupc_path or find_setupc()
    if not executable:
        raise FileNotFoundError("com0com setupc.exe was not found; install/repair it in maintenance mode first")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [executable, "list"],
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        creationflags=flags,
    )
    text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    if result.returncode:
        raise RuntimeError("setupc list failed (%s): %s" % (result.returncode, text.strip()))
    return parse_setupc_list(text)


def check_pair(client_port: str, bridge_port: str, pairs: Iterable[Com0ComPair]) -> PairCheck:
    client = client_port.upper()
    bridge = bridge_port.upper()
    for pair in pairs:
        if pair.contains(client) and pair.contains(bridge):
            return PairCheck(client, bridge, True, pair, "paired by com0com")
    return PairCheck(client, bridge, False, None, "required com0com pair is not present")


def create_pair(
    client_port: str,
    bridge_port: str,
    pair_index: int,
    setupc_path: Optional[str] = None,
    allow_mutation: bool = False,
) -> None:
    """Create one explicitly requested named pair.

    The documented setupc form is used (`install <index> PortName=<name> -`).
    `allow_mutation` has no default override so a normal POS/service execution
    cannot accidentally alter a driver or a live port mapping.
    """
    if not allow_mutation:
        raise PermissionError("com0com pair creation requires explicit maintenance authorisation")
    executable = setupc_path or find_setupc()
    if not executable:
        raise FileNotFoundError("com0com setupc.exe was not found")
    if pair_index < 0:
        raise ValueError("pair_index must not be negative")
    for port in (client_port, bridge_port):
        if not re.match(r"^(COM\d+|CNC[AB]\d+)$", port.upper()):
            raise ValueError("invalid com0com endpoint: " + port)
    expected_bridge = "CNCB%s" % pair_index
    if bridge_port.upper() != expected_bridge:
        raise ValueError(
            "this safe create form produces %s as the bridge endpoint; requested %s"
            % (expected_bridge, bridge_port.upper())
        )
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # The second endpoint is '-' so com0com supplies its paired CNC endpoint;
    # using two caller-visible COM names is avoided because it can collide with
    # legacy hardware mappings.
    result = subprocess.run(
        [executable, "install", str(pair_index), "PortName=" + client_port.upper() + ",EmuBR=yes", "-"],
        capture_output=True,
        timeout=20,
        check=False,
        creationflags=flags,
    )
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    if result.returncode:
        raise RuntimeError("setupc install failed (%s): %s" % (result.returncode, output.strip()))
    # setupc chooses the CNC peer for the '-' side.  The caller must inspect
    # list_pairs/check_pair and put that actual peer in bridge configuration.
