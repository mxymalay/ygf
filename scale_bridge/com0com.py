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
from typing import Callable, Dict, Iterable, List, Optional, Sequence


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

    def other(self, port: str) -> Optional[str]:
        target = port.upper()
        if self.side_a.upper() == target:
            return self.side_b
        if self.side_b.upper() == target:
            return self.side_a
        return None


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


def find_pair_by_endpoint(port: str, pairs: Iterable[Com0ComPair]) -> Optional[Com0ComPair]:
    target = port.upper()
    return next((pair for pair in pairs if pair.contains(target)), None)


def next_available_pair_index(pairs: Iterable[Com0ComPair], start: int = 0) -> int:
    used = {pair.index for pair in pairs}
    candidate = max(0, int(start))
    while candidate in used:
        candidate += 1
    return candidate


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


def _run_setupc(
    executable: str,
    arguments: Sequence[str],
    timeout_seconds: int,
    runner: Callable = subprocess.run,
) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = runner(
        [executable] + list(arguments),
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        creationflags=flags,
    )
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    if result.returncode:
        raise RuntimeError(
            "setupc %s failed (%s): %s"
            % (arguments[0] if arguments else "command", result.returncode, output.strip())
        )
    return output


def list_pairs(
    setupc_path: Optional[str] = None,
    timeout_seconds: int = 10,
    runner: Callable = subprocess.run,
) -> List[Com0ComPair]:
    """Read installed pairs.  This operation never changes driver state."""
    executable = setupc_path or find_setupc()
    if not executable:
        raise FileNotFoundError("com0com setupc.exe was not found; install/repair it in maintenance mode first")
    return parse_setupc_list(_run_setupc(executable, ["list"], timeout_seconds, runner))


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
    runner: Callable = subprocess.run,
) -> None:
    """Create one explicitly requested named pair.

    The documented setupc form is used (`install <index> PortName=<name> -`).
    If both endpoints are COM names, both names are passed explicitly.  If the
    bridge endpoint is the natural CNCB name for the chosen index, `-` lets
    com0com retain that internal name.
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
    client = client_port.upper()
    bridge = bridge_port.upper()
    expected_bridge = "CNCB%s" % pair_index
    if bridge == expected_bridge:
        bridge_argument = "-"
    elif bridge.startswith("COM"):
        bridge_argument = "PortName=" + bridge + ",EmuBR=yes"
    else:
        raise ValueError(
            "a new internal bridge endpoint must match the selected pair index (%s); requested %s"
            % (expected_bridge, bridge)
        )
    _run_setupc(
        executable,
        ["install", str(pair_index), "PortName=" + client + ",EmuBR=yes", bridge_argument],
        20,
        runner,
    )


def remove_pair(
    pair_index: int,
    setupc_path: Optional[str] = None,
    allow_mutation: bool = False,
    runner: Callable = subprocess.run,
) -> None:
    """Remove exactly one indexed pair after ownership has been verified."""
    if not allow_mutation:
        raise PermissionError("com0com pair removal requires explicit maintenance authorisation")
    executable = setupc_path or find_setupc()
    if not executable:
        raise FileNotFoundError("com0com setupc.exe was not found")
    if pair_index < 0:
        raise ValueError("pair_index must not be negative")
    _run_setupc(executable, ["remove", str(pair_index)], 20, runner)
