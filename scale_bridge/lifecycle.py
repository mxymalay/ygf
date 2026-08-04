"""First-run, repair and removal lifecycle for ScaleBridge on Windows 7.

Normal POS startup never imports or invokes mutation methods from this module.
Every mutating operation requires an explicit UI confirmation and administrator
rights.  Pair ownership is recorded so removal can target only resources that
this product actually created.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import ctypes
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .com0com import (
    Com0ComPair,
    SetupcMutationTimeout,
    create_pair,
    find_pair_by_endpoint,
    find_setupc,
    list_pairs,
    next_available_pair_index,
    remove_pair,
    update_driver_bindings,
)
from .configuration import ScaleBridgeConfig, ScaleDeviceIdentity, save_config
from .device_discovery import (
    SerialPortCandidate,
    enumerate_com0com_device_problems,
    enumerate_serial_ports,
    windows_serial_port_exists,
)
from .protocol import DibalFrameAssembler, parse_dibal_weight


MANIFEST_FILENAME = "scale_bridge_installation.json"
SERVICE_NAME = "YgfScaleBridge"
COM0COM_INSTALLER_SHA256 = "26486B28604B49A9008C54FEB11B9ECE0008A8287EE5CAF0BCF2A62F4317128F"
SERVICE_STATES = {
    1: "STOPPED",
    2: "START_PENDING",
    3: "STOP_PENDING",
    4: "RUNNING",
    5: "CONTINUE_PENDING",
    6: "PAUSE_PENDING",
    7: "PAUSED",
}


def application_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def default_manifest_path() -> str:
    return os.path.join(application_root(), "data", MANIFEST_FILENAME)


def is_administrator() -> bool:
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _decode_process_output(result) -> str:
    stdout = getattr(result, "stdout", b"") or b""
    stderr = getattr(result, "stderr", b"") or b""
    raw = stdout + stderr
    if isinstance(raw, str):
        return raw
    return raw.decode("mbcs", errors="replace")


def _atomic_json_write(path: str, data: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        os.makedirs(directory)
    fd, temporary = tempfile.mkstemp(prefix="scale_bridge_install_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


@dataclass
class OwnedPair:
    purpose: str
    index: int
    side_a: str
    side_b: str

    def matches(self, pair: Com0ComPair) -> bool:
        return self.index == pair.index and {
            self.side_a.upper(), self.side_b.upper()
        } == {pair.side_a.upper(), pair.side_b.upper()}


@dataclass
class InstallationManifest:
    version: int = 3
    created_pairs: List[OwnedPair] = field(default_factory=list)
    pending_pairs: List[OwnedPair] = field(default_factory=list)
    service_owned: bool = False
    driver_installed_by_product: bool = False
    created_at: str = ""
    reboot_required: bool = False
    reboot_required_boot_id: str = ""
    reboot_required_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "created_pairs": [asdict(item) for item in self.created_pairs],
            "pending_pairs": [asdict(item) for item in self.pending_pairs],
            "service_owned": self.service_owned,
            "driver_installed_by_product": self.driver_installed_by_product,
            "created_at": self.created_at,
            "reboot_required": self.reboot_required,
            "reboot_required_boot_id": self.reboot_required_boot_id,
            "reboot_required_reason": self.reboot_required_reason,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "InstallationManifest":
        return cls(
            version=max(3, int(raw.get("version", 1))),
            created_pairs=[OwnedPair(**item) for item in raw.get("created_pairs", [])],
            pending_pairs=[OwnedPair(**item) for item in raw.get("pending_pairs", [])],
            service_owned=bool(raw.get("service_owned", False)),
            driver_installed_by_product=bool(raw.get("driver_installed_by_product", False)),
            created_at=str(raw.get("created_at", "")),
            reboot_required=bool(raw.get("reboot_required", False)),
            reboot_required_boot_id=str(raw.get("reboot_required_boot_id", "")),
            reboot_required_reason=str(raw.get("reboot_required_reason", "")),
        )


def load_manifest(path: Optional[str] = None) -> InstallationManifest:
    target = path or default_manifest_path()
    if not os.path.isfile(target):
        return InstallationManifest(created_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    with open(target, "r", encoding="utf-8") as handle:
        return InstallationManifest.from_dict(json.load(handle))


def save_manifest(manifest: InstallationManifest, path: Optional[str] = None) -> None:
    _atomic_json_write(path or default_manifest_path(), manifest.to_dict())


def _current_boot_marker() -> str:
    """Return a stable marker for the current Windows boot session.

    com0com 3.0.0 can leave deleted PnP device objects pending until Windows
    restarts.  The marker lets us distinguish a repeated create attempt in the
    same boot from the first safe attempt after a real reboot without relying
    on a port-number workaround.
    """
    if sys.platform != "win32":
        return "non-windows"
    try:
        get_tick_count = ctypes.windll.kernel32.GetTickCount64
        get_tick_count.restype = ctypes.c_ulonglong
        uptime_seconds = int(get_tick_count()) / 1000.0
        boot_epoch = time.time() - uptime_seconds
        # The derived boot time is stable within a few milliseconds.  A
        # minute bucket avoids false changes caused by timer precision.
        return str(int(round(boot_epoch / 60.0)))
    except Exception:
        return ""


def _mark_reboot_required(
    manifest: InstallationManifest,
    path: str,
    reason: str,
) -> None:
    manifest.reboot_required = True
    manifest.reboot_required_boot_id = _current_boot_marker()
    manifest.reboot_required_reason = str(reason or "已删除 com0com 虚拟串口")
    save_manifest(manifest, path)


def _reboot_requirement_is_active(
    manifest: InstallationManifest,
    path: str,
) -> bool:
    if not manifest.reboot_required:
        return False
    current_boot = _current_boot_marker()
    recorded_boot = manifest.reboot_required_boot_id
    if current_boot and recorded_boot and current_boot != recorded_boot:
        manifest.reboot_required = False
        manifest.reboot_required_boot_id = ""
        manifest.reboot_required_reason = ""
        save_manifest(manifest, path)
        return False
    return True


def _wait_for_serial_ports(
    port_names: Iterable[str],
    port_enumerator: Callable = enumerate_serial_ports,
    timeout_seconds: float = 8.0,
) -> List[str]:
    """Return COM names still absent after Win7 enumeration settles."""
    expected = {str(port or "").strip().upper() for port in port_names if port}
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        # QueryDosDevice is fast, works for occupied ports and is the closest
        # check to what CreateFile("\\\\.\\COMx") will resolve. Avoid a slow
        # Win7 WMI query entirely when this authoritative namespace is ready.
        available = {port for port in expected if windows_serial_port_exists(port)}
        if available != expected:
            try:
                candidates = port_enumerator(include_virtual=True)
                available.update(item.port.upper() for item in candidates)
            except Exception:
                pass
        missing = sorted(expected - available)
        if not missing or time.monotonic() >= deadline:
            return missing
        time.sleep(0.4)


def _format_com0com_device_problems(problems) -> str:
    if not problems:
        return ""
    counts: Dict[int, int] = {}
    for item in problems:
        counts[item.error_code] = counts.get(item.error_code, 0) + 1
    parts = []
    for code, count in sorted(counts.items()):
        if code == 28:
            detail = "驱动程序未安装"
        elif code == 52:
            detail = "Windows 无法验证驱动数字签名"
        elif code == 10:
            detail = "设备无法启动"
        else:
            detail = "设备异常"
        parts.append("%d 个设备为代码 %d（%s）" % (count, code, detail))
    return "；".join(parts)


def _repair_and_wait_for_serial_ports(
    port_names: Iterable[str],
    setupc_path: str,
    runner: Callable,
    port_enumerator: Callable,
    timeout_seconds: float,
) -> Tuple[List[str], str]:
    """Repair PnP driver binding once when configured pairs have no COM names."""
    missing = _wait_for_serial_ports(port_names, port_enumerator, timeout_seconds)
    if not missing:
        return [], ""
    repair_error = ""
    try:
        update_driver_bindings(
            setupc_path,
            allow_mutation=True,
            runner=runner,
        )
    except Exception as exc:
        repair_error = str(exc) or exc.__class__.__name__
    missing = _wait_for_serial_ports(
        port_names,
        port_enumerator,
        max(12.0, timeout_seconds),
    )
    return missing, repair_error


def find_com0com_installer(explicit_path: Optional[str] = None) -> Optional[str]:
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    root = application_root()
    candidates.extend(glob.glob(os.path.join(root, "ThirdParty", "com0com", "Setup_com0com*.exe")))
    candidates.extend(glob.glob(os.path.join(root, "ThirdParty", "com0com", "setup*.exe")))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def find_hub4com(explicit_path: Optional[str] = None) -> Optional[str]:
    """Locate the optional hub4com diagnostic utility in a deployment tree.

    ScaleBridge does not launch hub4com in production; it owns the physical
    scale port itself.  Keeping discovery here lets a technician's diagnostic
    report state clearly whether the optional manual multiplexer was bundled,
    without making it a required dependency for normal POS startup.
    """
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    root = application_root()
    candidates.append(os.path.join(root, "ThirdParty", "hub4com", "hub4com.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().upper()


def install_com0com_driver(
    installer_path: Optional[str] = None,
    runner: Callable = subprocess.run,
) -> str:
    """Run the bundled signed installer once in explicit maintenance mode."""
    if not is_administrator():
        raise PermissionError("安装 com0com 必须以管理员身份运行 POS")
    installer = find_com0com_installer(installer_path)
    if not installer:
        raise FileNotFoundError("未找到随部署包提供的 Windows 7 x64 com0com 安装程序")
    actual_hash = sha256_file(installer)
    if actual_hash != COM0COM_INSTALLER_SHA256:
        raise RuntimeError(
            "com0com 安装包 SHA-256 不匹配，拒绝执行。实际值: %s" % actual_hash
        )
    # The signed com0com setup package contains com0com.inf and launches its
    # helper through a relative path.  When POS was started from the project
    # root (the normal desktop shortcut case), inheriting that CWD made the
    # helper look for ``<project>\\com0com.inf`` and show SetupOpenInfFile
    # ERROR 2.  Run it beside the installer so its bundled driver files are
    # resolved from the package directory.
    result = runner(
        [installer],
        capture_output=False,
        timeout=300,
        check=False,
        cwd=os.path.dirname(os.path.abspath(installer)),
    )
    if result.returncode not in (0, 1641, 3010):
        raise RuntimeError("com0com 安装程序退出码: %s" % result.returncode)
    setupc = find_setupc()
    if not setupc:
        raise RuntimeError("安装程序已结束，但仍未找到 setupc.exe；可能安装被取消或需要重启")
    return setupc


def _windows_command_line_to_argv(command_line: str) -> List[str]:
    """Parse a registry UninstallString with Windows' own quoting rules."""
    if not command_line:
        return []
    argc = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
    pointer = command_line_to_argv(command_line, ctypes.byref(argc))
    if not pointer:
        raise OSError("无法解析 com0com 卸载命令")
    try:
        return [pointer[index] for index in range(argc.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(pointer)


def find_com0com_uninstall_command() -> List[str]:
    """Return only the exact registered com0com uninstall command."""
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    roots = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for root_path in roots:
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path)
        except OSError:
            continue
        try:
            index = 0
            while True:
                try:
                    key_name = winreg.EnumKey(root, index)
                    index += 1
                except OSError:
                    break
                try:
                    item = winreg.OpenKey(root, key_name)
                    display_name = str(winreg.QueryValueEx(item, "DisplayName")[0])
                    if not display_name.strip().lower().startswith("com0com"):
                        continue
                    try:
                        command = str(winreg.QueryValueEx(item, "QuietUninstallString")[0])
                    except OSError:
                        command = str(winreg.QueryValueEx(item, "UninstallString")[0])
                    return _windows_command_line_to_argv(command)
                except OSError:
                    continue
        finally:
            winreg.CloseKey(root)
    return []


def uninstall_com0com_driver(
    setupc_path: Optional[str] = None,
    uninstall_command: Optional[Sequence[str]] = None,
    runner: Callable = subprocess.run,
) -> bool:
    """Uninstall com0com only when no virtual pair of any owner remains."""
    if not is_administrator():
        raise PermissionError("卸载 com0com 必须以管理员身份运行 POS")
    setupc = setupc_path or find_setupc()
    if setupc and list_pairs(setupc, runner=runner):
        raise RuntimeError("系统中仍存在 com0com 配对，为保护其他用途，拒绝卸载驱动")
    command = list(uninstall_command or find_com0com_uninstall_command())
    if not command:
        return False
    result = runner(command, capture_output=False, timeout=300, check=False)
    if result.returncode not in (0, 1605, 1641, 3010):
        raise RuntimeError("com0com 卸载程序退出码: %s" % result.returncode)
    return True


class PortConflictError(RuntimeError):
    pass


class RebootRequiredError(RuntimeError):
    pass


@dataclass
class ProvisionReport:
    existing: List[str] = field(default_factory=list)
    created: List[str] = field(default_factory=list)
    removed_obsolete: List[str] = field(default_factory=list)


class Com0ComProvisioner:
    """Idempotently create required pairs and safely remove only owned pairs."""

    def __init__(
        self,
        setupc_path: Optional[str] = None,
        manifest_path: Optional[str] = None,
        runner: Callable = subprocess.run,
        port_enumerator: Callable = enumerate_serial_ports,
    ):
        self.setupc_path = setupc_path or find_setupc()
        self.manifest_path = manifest_path or default_manifest_path()
        self.runner = runner
        self.port_enumerator = port_enumerator

    def _require_setupc(self) -> str:
        if not self.setupc_path:
            self.setupc_path = find_setupc()
        if not self.setupc_path:
            raise FileNotFoundError("未找到 com0com setupc.exe，请先安装驱动")
        return self.setupc_path

    def _pairs(self) -> List[Com0ComPair]:
        return list_pairs(self._require_setupc(), runner=self.runner)

    def _port_owners(self) -> Dict[str, SerialPortCandidate]:
        return {
            item.port.upper(): item
            for item in self.port_enumerator(include_virtual=True)
        }

    @staticmethod
    def _pair_description(pair: Com0ComPair) -> str:
        return "%s ↔ %s (#%d)" % (pair.side_a, pair.side_b, pair.index)

    def _check_name_free(
        self,
        port: str,
        pairs: Iterable[Com0ComPair],
        owners: Dict[str, SerialPortCandidate],
    ) -> None:
        target = port.upper()
        existing_pair = find_pair_by_endpoint(target, pairs)
        if existing_pair:
            raise PortConflictError(
                "%s 已属于现有配对 %s，不能重复用于新配对"
                % (target, self._pair_description(existing_pair))
            )
        owner = owners.get(target)
        if owner:
            kind = "虚拟设备" if owner.is_virtual else "真实设备"
            raise PortConflictError(
                "%s 已被%s占用：%s。不会覆盖该端口。"
                % (target, kind, owner.friendly_name or owner.hardware_id or "未知设备")
            )

    def _remember_created(self, purpose: str, pair: Com0ComPair) -> None:
        manifest = load_manifest(self.manifest_path)
        existing = next(
            (item for item in manifest.created_pairs if item.index == pair.index),
            None,
        )
        if existing is not None and not existing.matches(pair):
            raise RuntimeError("配对 #%d 与已有所有权记录不一致" % pair.index)
        if existing is None:
            manifest.created_pairs.append(OwnedPair(purpose, pair.index, pair.side_a, pair.side_b))
        manifest.pending_pairs = [
            item for item in manifest.pending_pairs
            if not (item.purpose == purpose and item.index == pair.index)
        ]
        save_manifest(manifest, self.manifest_path)

    def _remember_pending(
        self,
        purpose: str,
        index: int,
        client: str,
        peer: str,
    ) -> None:
        """Persist creation intent before setupc mutates Windows.

        On Win7 setupc can time out while its PnP worker still finishes later.
        Keeping the exact intent lets the next run safely recognise only the
        pair requested by this product instead of treating it as foreign.
        """
        manifest = load_manifest(self.manifest_path)
        manifest.pending_pairs = [
            item for item in manifest.pending_pairs if item.purpose != purpose
        ]
        manifest.pending_pairs.append(OwnedPair(purpose, index, client, peer))
        save_manifest(manifest, self.manifest_path)

    def _forget_pending(self, purpose: str, index: int) -> None:
        manifest = load_manifest(self.manifest_path)
        remaining = [
            item for item in manifest.pending_pairs
            if not (item.purpose == purpose and item.index == index)
        ]
        if len(remaining) != len(manifest.pending_pairs):
            manifest.pending_pairs = remaining
            save_manifest(manifest, self.manifest_path)

    def _ensure_one(
        self,
        purpose: str,
        client_port: str,
        requested_peer: str,
        pairs: List[Com0ComPair],
        owners: Dict[str, SerialPortCandidate],
    ) -> Tuple[Com0ComPair, bool]:
        client = client_port.upper()
        peer = requested_peer.upper() if requested_peer else ""
        manifest = load_manifest(self.manifest_path)
        pending = next(
            (item for item in manifest.pending_pairs if item.purpose == purpose),
            None,
        )
        current = find_pair_by_endpoint(client, pairs)
        if current:
            if peer and not current.contains(peer):
                raise PortConflictError(
                    "%s 已属于 %s，和配置的对端 %s 不一致"
                    % (client, self._pair_description(current), peer)
                )
            known_owned = any(
                item.purpose == purpose and item.matches(current)
                for item in manifest.created_pairs
            )
            pending_owned = bool(pending and pending.matches(current))
            if pending_owned:
                self._remember_created(purpose, current)
                known_owned = True
            if not peer and not known_owned:
                actual_peer = current.other(client) or ""
                # A configured POS-facing COM port paired with an internal CNC
                # endpoint can be reused without claiming deletion ownership.
                # This recovers old/partially completed installations safely:
                # removal still leaves an unowned pair untouched.
                if not re.fullmatch(r"CNC[AB]\d+", actual_peer, re.IGNORECASE):
                    raise PortConflictError(
                        "%s 已属于现有配对 %s，但配置未指定对端。"
                        "请先用“检查虚拟端口配对”核对并明确选择，程序不会自动接管。"
                        % (client, self._pair_description(current))
                    )
            return current, False

        self._check_name_free(client, pairs, owners)
        if peer.startswith("COM"):
            self._check_name_free(peer, pairs, owners)

        requested_index = None
        if pending:
            pending_client = pending.side_a.upper()
            pending_peer = pending.side_b.upper()
            pending_current = next(
                (item for item in pairs if item.index == pending.index),
                None,
            )
            if pending_client != client:
                if pending_current is not None:
                    raise PortConflictError(
                        "上次未完成的 %s 创建记录仍对应 %s ↔ %s (#%d)。"
                        "请先核对该配对，不会用新配置覆盖。"
                        % (purpose, pending.side_a, pending.side_b, pending.index)
                    )
                self._forget_pending(purpose, pending.index)
                pending = None
            elif peer and peer != pending_peer:
                if pending_current is not None:
                    raise PortConflictError(
                        "上次未完成的创建记录要求对端 %s，当前填写为 %s；不会自动改写。"
                        % (pending_peer, peer)
                    )
                self._forget_pending(purpose, pending.index)
                pending = None
            else:
                requested_index = pending.index
                if not peer:
                    peer = pending_peer
        match = re.fullmatch(r"CNCB(\d+)", peer, re.IGNORECASE) if peer else None
        if match:
            peer_index = int(match.group(1))
            if requested_index is not None and peer_index != requested_index:
                raise PortConflictError(
                    "待恢复配对序号 #%d 与对端 %s 不一致"
                    % (requested_index, peer)
                )
            requested_index = peer_index
            if any(item.index == requested_index for item in pairs):
                raise PortConflictError("内部配对序号 #%d 已被其他端口使用" % requested_index)
        index = requested_index if requested_index is not None else next_available_pair_index(pairs)
        actual_peer = peer or "CNCB%d" % index
        self._remember_pending(purpose, index, client, actual_peer)
        try:
            create_pair(
                client,
                actual_peer,
                index,
                setupc_path=self._require_setupc(),
                allow_mutation=True,
                runner=self.runner,
            )
        except SetupcMutationTimeout as exc:
            # subprocess may time out while Windows' PnP worker completes in
            # the background. Reconcile once immediately; if it is not visible
            # yet, retain the exact pending intent for the next retry/reboot.
            try:
                refreshed = self._pairs()
            except Exception:
                refreshed = []
            created = find_pair_by_endpoint(client, refreshed)
            if created and created.index == index and created.contains(actual_peer):
                self._remember_created(purpose, created)
                return created, True
            raise RuntimeError(
                "com0com 创建 %s ↔ %s (#%d) 超时，结果暂时无法确认。"
                "程序已保存本次创建记录，不会改用其他端口。请等待 Windows 完成设备安装后，"
                "直接再次点击“初始化 / 修复”；若重试仍超时，再重启电脑。"
                % (client, actual_peer, index)
            ) from exc
        except Exception:
            self._forget_pending(purpose, index)
            raise
        refreshed = self._pairs()
        created = find_pair_by_endpoint(client, refreshed)
        if not created:
            raise RuntimeError(
                "setupc 已返回成功，但暂未找到刚创建的端口 %s。"
                "程序已保存本次创建记录；请稍候后直接再次初始化，不会改用其他端口。"
                % client
            )
        if peer and not created.contains(peer):
            raise RuntimeError(
                "创建后的实际配对为 %s，与请求对端 %s 不一致"
                % (self._pair_description(created), peer)
            )
        self._remember_created(purpose, created)
        return created, True

    def ensure_required_pairs(
        self,
        config: ScaleBridgeConfig,
        include_scale: bool = True,
        include_payment: bool = False,
    ) -> ProvisionReport:
        if not is_administrator():
            raise PermissionError("创建虚拟串口必须以管理员身份运行 POS")
        if not include_scale and not include_payment:
            raise ValueError("至少选择一种需要维护的虚拟串口配对")
        manifest = load_manifest(self.manifest_path)
        if _reboot_requirement_is_active(manifest, self.manifest_path):
            reason = manifest.reboot_required_reason or "本次开机已删除过 com0com 虚拟串口"
            raise RebootRequiredError(
                "%s。旧版 com0com 驱动在同一次开机内重新创建可能卡住或不枚举设备。"
                "请先重启 Windows；重启后程序会自动解除限制，再执行创建/修复。"
                % reason
            )
        if include_scale:
            config.validate_for_setup()
        if include_payment:
            payment_ports = (config.payment_pos_port, config.payment_plugin_port)
            if not all(payment_ports):
                raise ValueError("收钱吧发送端和插件接收端必须同时填写")
            for value in payment_ports:
                if not re.fullmatch(r"COM[1-9]\d*", value, re.IGNORECASE):
                    raise ValueError("支付配对端口必须是 COM 端口：%s" % value)
            if config.payment_pos_port.upper() == config.payment_plugin_port.upper():
                raise ValueError("收钱吧发送端和插件接收端不能相同")
        pairs = self._pairs()
        owners = self._port_owners()
        report = ProvisionReport()
        active_pair_indices = set()

        desired = []
        if include_payment:
            desired.append(("payment", config.payment_pos_port, config.payment_plugin_port))
        if include_scale:
            desired.extend([
                ("official_scale", config.official_pos_virtual_port, config.official_bridge_port),
                ("private_scale", config.private_pos_virtual_port, config.private_bridge_port),
            ])
        managed_purposes = {item[0] for item in desired}

        # Validate every ownership record before the first mutation. If an
        # external tool renamed or reused one of our historical pair indices,
        # repair must fail without creating or deleting anything else.
        manifest = load_manifest(self.manifest_path)
        for owned in manifest.created_pairs:
            if owned.purpose not in managed_purposes:
                continue
            current = next((item for item in pairs if item.index == owned.index), None)
            if current is not None and not owned.matches(current):
                raise RuntimeError(
                    "配对 #%d 已被外部修改，拒绝修复或清理" % owned.index
                )

        for purpose, client, peer in desired:
            pair, was_created = self._ensure_one(purpose, client, peer, pairs, owners)
            actual_peer = pair.other(client)
            if purpose == "official_scale":
                config.official_bridge_port = actual_peer or ""
            elif purpose == "private_scale":
                config.private_bridge_port = actual_peer or ""
            elif purpose == "payment":
                config.payment_plugin_port = actual_peer or ""
            description = self._pair_description(pair)
            active_pair_indices.add(pair.index)
            (report.created if was_created else report.existing).append(description)
            pairs = self._pairs()

        # A repair may change configured endpoints. Remove only obsolete pairs
        # that are still an exact match for this product's ownership record.
        manifest = load_manifest(self.manifest_path)
        for owned in list(reversed(manifest.created_pairs)):
            if owned.purpose not in managed_purposes or owned.index in active_pair_indices:
                continue
            current = next((item for item in pairs if item.index == owned.index), None)
            if current is None:
                manifest.created_pairs.remove(owned)
                save_manifest(manifest, self.manifest_path)
                continue
            if not owned.matches(current):
                raise RuntimeError(
                    "旧配对 #%d 已被外部修改，拒绝自动清理" % owned.index
                )
            remove_pair(
                current.index,
                setupc_path=self._require_setupc(),
                allow_mutation=True,
                runner=self.runner,
            )
            pairs = self._pairs()
            if any(item.index == current.index for item in pairs):
                raise RuntimeError("setupc 未能删除旧配对 #%d" % current.index)
            report.removed_obsolete.append(self._pair_description(current))
            manifest.created_pairs.remove(owned)
            _mark_reboot_required(
                manifest,
                self.manifest_path,
                "修复配置时已删除旧的 com0com 虚拟串口",
            )
        if include_scale:
            config.validate()
        return report

    def remove_owned_pairs(
        self,
        purposes: Optional[Iterable[str]] = None,
    ) -> Tuple[List[str], List[str]]:
        """Return (removed, skipped); changed/unowned pairs are never removed."""
        if not is_administrator():
            raise PermissionError("删除虚拟串口必须以管理员身份运行 POS")
        manifest = load_manifest(self.manifest_path)
        selected_purposes = set(purposes) if purposes is not None else None
        removed: List[str] = []
        skipped: List[str] = []
        pairs = self._pairs()

        # Reconcile an operation that timed out after Windows accepted it.
        # Exact pending intents are ours to remove; missing intents are merely
        # stale metadata, while any mismatch remains protected.
        for pending in list(manifest.pending_pairs):
            if selected_purposes is not None and pending.purpose not in selected_purposes:
                continue
            current = next((item for item in pairs if item.index == pending.index), None)
            if current is None:
                manifest.pending_pairs.remove(pending)
                continue
            if not pending.matches(current):
                skipped.append(
                    "#%d 当前为 %s ↔ %s，和待完成创建记录不符"
                    % (current.index, current.side_a, current.side_b)
                )
                continue
            if not any(item.index == current.index for item in manifest.created_pairs):
                manifest.created_pairs.append(
                    OwnedPair(pending.purpose, current.index, current.side_a, current.side_b)
                )
            manifest.pending_pairs.remove(pending)

        # Preflight all records before deleting the first pair. This prevents a
        # partial delete when a later pair was renamed/reused outside the POS.
        for owned in list(manifest.created_pairs):
            if selected_purposes is not None and owned.purpose not in selected_purposes:
                continue
            current = next((item for item in pairs if item.index == owned.index), None)
            if current is None:
                manifest.created_pairs.remove(owned)
                continue
            if not owned.matches(current):
                skipped.append(
                    "#%d 当前为 %s ↔ %s，和所有权记录不符"
                    % (current.index, current.side_a, current.side_b)
                )
        save_manifest(manifest, self.manifest_path)
        if skipped:
            return removed, skipped

        for owned in list(reversed(manifest.created_pairs)):
            if selected_purposes is not None and owned.purpose not in selected_purposes:
                continue
            pairs = self._pairs()
            current = next((item for item in pairs if item.index == owned.index), None)
            if current is None:
                manifest.created_pairs.remove(owned)
                save_manifest(manifest, self.manifest_path)
                continue
            remove_pair(
                current.index,
                setupc_path=self._require_setupc(),
                allow_mutation=True,
                runner=self.runner,
            )
            after = self._pairs()
            if any(item.index == current.index for item in after):
                raise RuntimeError("setupc 未能删除配对 #%d" % current.index)
            removed.append(self._pair_description(current))
            manifest.created_pairs.remove(owned)
            _mark_reboot_required(
                manifest,
                self.manifest_path,
                "本次开机已删除过 com0com 虚拟串口",
            )
        return removed, skipped


@dataclass
class PhysicalScaleTestResult:
    ok: bool
    port: str
    weight_kg: Optional[float] = None
    raw_hex: str = ""
    message: str = ""


@dataclass
class VirtualPairTestResult:
    ok: bool
    side_a: str
    side_b: str
    message: str = ""


def test_scale_channel(
    config: ScaleBridgeConfig,
    pos_port: str,
    serial_factory=None,
    timeout_seconds: float = 2.5,
) -> PhysicalScaleTestResult:
    """Send the confirmed query through one POS-side virtual endpoint."""
    try:
        config.validate()
    except Exception as exc:
        return PhysicalScaleTestResult(False, str(pos_port or "").upper(), message=str(exc))
    port = str(pos_port or "").strip().upper()
    allowed = {
        config.official_pos_virtual_port.upper(),
        config.private_pos_virtual_port.upper(),
    }
    if port not in allowed:
        return PhysicalScaleTestResult(
            False, port, message="只能测试配置中的官方 POS 或私有 POS 虚拟端口"
        )
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
    ser = None
    received = bytearray()
    assembler = DibalFrameAssembler(config.maximum_frame_length)
    try:
        ser = serial_factory(
            port=port,
            baudrate=config.baudrate,
            bytesize=config.data_bits,
            parity=config.parity,
            stopbits=config.stop_bits,
            timeout=0.05,
            write_timeout=0.5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        ser.dtr = config.dtr_enable
        ser.rts = config.rts_enable
        deadline = time.monotonic() + timeout_seconds
        next_query = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_query:
                ser.write(b"$")
                ser.flush()
                next_query = now + 0.2
            waiting = int(getattr(ser, "in_waiting", 0) or 0)
            chunk = ser.read(min(256, waiting) if waiting else 1)
            if not chunk:
                continue
            received.extend(chunk)
            frames, _discarded = assembler.feed(chunk)
            for frame in frames:
                weight = parse_dibal_weight(frame)
                if weight is not None:
                    return PhysicalScaleTestResult(
                        True,
                        port,
                        weight,
                        bytes(received).hex(" "),
                        "虚拟端口到物理秤的端到端查询正常",
                    )
        return PhysicalScaleTestResult(
            False,
            port,
            raw_hex=bytes(received).hex(" "),
            message="端口已打开，但 %.1f 秒内没有收到合法重量回包" % timeout_seconds,
        )
    except Exception as exc:
        return PhysicalScaleTestResult(
            False, port, raw_hex=bytes(received).hex(" "), message=str(exc)
        )
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def test_physical_scale(
    config: ScaleBridgeConfig,
    serial_factory=None,
    timeout_seconds: float = 2.5,
) -> PhysicalScaleTestResult:
    """Maintenance-only direct test used before the Windows service starts."""
    if config.development_simulation:
        return PhysicalScaleTestResult(
            True,
            "SIMULATED",
            0.500,
            "30 2E 35 30 30 0D",
            "开发模拟秤回包正常",
        )
    port = config.physical_scale_port.upper()
    if not port:
        return PhysicalScaleTestResult(False, port, message="尚未选择物理电子秤端口")
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
        # Reject an absent/virtual port before opening it.  Some Win7 serial
        # drivers can block inside CreateFile for a surprisingly long time;
        # the UI should report a clear no-device result instead of appearing
        # frozen.  Injected factories remain unrestricted for protocol tests.
        try:
            candidates = enumerate_serial_ports(include_virtual=False)
            if not any(item.port.upper() == port for item in candidates):
                return PhysicalScaleTestResult(
                    False,
                    port,
                    message="该端口当前未出现在 Windows 真实串口设备列表中；请连接电子秤后再测试。",
                )
        except Exception:
            # Opening the port below still provides the definitive diagnostic
            # when discovery is unavailable (for example during a driver scan).
            pass
    ser = None
    received = bytearray()
    assembler = DibalFrameAssembler(config.maximum_frame_length)
    try:
        ser = serial_factory(
            port=port,
            baudrate=config.baudrate,
            bytesize=config.data_bits,
            parity=config.parity,
            stopbits=config.stop_bits,
            timeout=0.05,
            write_timeout=0.5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        ser.dtr = config.dtr_enable
        ser.rts = config.rts_enable
        deadline = time.monotonic() + timeout_seconds
        next_query = 0.0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_query:
                ser.write(b"$")
                ser.flush()
                next_query = now + 0.2
            waiting = int(getattr(ser, "in_waiting", 0) or 0)
            chunk = ser.read(min(256, waiting) if waiting else 1)
            if not chunk:
                continue
            received.extend(chunk)
            frames, _discarded = assembler.feed(chunk)
            for frame in frames:
                weight = parse_dibal_weight(frame)
                if weight is not None:
                    return PhysicalScaleTestResult(
                        True, port, weight, bytes(received).hex(" "), "电子秤查询和回包正常"
                    )
        return PhysicalScaleTestResult(
            False,
            port,
            raw_hex=bytes(received).hex(" "),
            message="端口已打开，但 %.1f 秒内没有收到合法重量回包" % timeout_seconds,
        )
    except Exception as exc:
        return PhysicalScaleTestResult(False, port, raw_hex=bytes(received).hex(" "), message=str(exc))
    finally:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass


def test_virtual_pair(
    side_a: str,
    side_b: str,
    serial_factory=None,
    timeout_seconds: float = 1.5,
) -> VirtualPairTestResult:
    """Verify transparent bytes in both directions without changing configuration."""
    first = str(side_a or "").strip().upper()
    second = str(side_b or "").strip().upper()
    if not first or not second:
        return VirtualPairTestResult(False, first, second, "测试需要填写两个端口")
    if first == second:
        return VirtualPairTestResult(False, first, second, "两个端口不能相同")
    if serial_factory is None:
        import serial
        serial_factory = serial.Serial
        use_windows_device_path = True
    else:
        use_windows_device_path = False

    def open_name(port):
        # com0com's internal CNC endpoints are not DOS COM aliases.  On
        # Windows they must be opened through the Win32 device namespace;
        # passing plain ``CNCB2`` makes pyserial search for a file with that
        # literal name and returns ERROR_FILE_NOT_FOUND.  Keep injected test
        # factories on their original logical names.
        value = str(port or "").strip().upper()
        if use_windows_device_path and value.startswith("CNC"):
            return r"\\.\%s" % value
        return port

    opened = []
    token_a = b"YGF-A-" + os.urandom(8).hex().encode("ascii")
    token_b = b"YGF-B-" + os.urandom(8).hex().encode("ascii")
    try:
        for port in (first, second):
            ser = serial_factory(
                port=open_name(port),
                baudrate=9600,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.05,
                write_timeout=0.5,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            ser.dtr = False
            ser.rts = False
            opened.append(ser)

        def transfer(sender, receiver, token):
            sender.write(token)
            sender.flush()
            received = bytearray()
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline and len(received) < len(token):
                waiting = int(getattr(receiver, "in_waiting", 0) or 0)
                chunk = receiver.read(waiting if waiting else 1)
                if chunk:
                    received.extend(chunk)
            return bytes(received)

        forward = transfer(opened[0], opened[1], token_a)
        if forward != token_a:
            return VirtualPairTestResult(False, first, second, "%s → %s 数据不一致" % (first, second))
        reverse = transfer(opened[1], opened[0], token_b)
        if reverse != token_b:
            return VirtualPairTestResult(False, first, second, "%s → %s 数据不一致" % (second, first))
        return VirtualPairTestResult(True, first, second, "双向透明通信正常")
    except Exception as exc:
        return VirtualPairTestResult(False, first, second, str(exc))
    finally:
        for ser in opened:
            try:
                ser.close()
            except Exception:
                pass


@dataclass
class ServiceState:
    installed: bool
    state_code: int = 0
    state: str = "NOT_INSTALLED"
    detail: str = ""


class ScaleBridgeServiceController:
    def __init__(self, command_prefix: Optional[Sequence[str]] = None, runner: Callable = subprocess.run):
        self.runner = runner
        self.command_prefix = list(command_prefix) if command_prefix else self._default_command_prefix()

    @staticmethod
    def _default_command_prefix() -> List[str]:
        if getattr(sys, "frozen", False):
            executable = os.path.join(application_root(), "ScaleBridgeService.exe")
            if not os.path.isfile(executable):
                return []
            return [executable]
        # The root-level host intentionally defines the registered subclass.
        # pywin32 therefore records this absolute file path, allowing
        # pythonservice.exe to locate the project before importing the
        # ``scale_bridge`` package.
        return [sys.executable, os.path.join(application_root(), "scale_bridge_service.py")]

    def _run(self, arguments: Sequence[str], timeout: int = 30, check: bool = True):
        if not self.command_prefix:
            raise FileNotFoundError("部署目录缺少 ScaleBridgeService.exe")
        result = self.runner(
            self.command_prefix + list(arguments),
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if check and result.returncode:
            raise RuntimeError(_decode_process_output(result).strip() or "服务命令执行失败")
        return result

    def query(self) -> ServiceState:
        result = self.runner(
            ["sc.exe", "query", SERVICE_NAME],
            capture_output=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = _decode_process_output(result)
        if result.returncode:
            return ServiceState(False, detail=text.strip())
        match = re.search(r"(?:STATE|状态)\s*:\s*([1-7])", text, re.IGNORECASE)
        if not match:
            # SC output keeps the numeric state even on localized systems.
            match = re.search(r"\n\s*(?:STATE|状态)?[^:]*:\s*([1-7])\s", text, re.IGNORECASE)
        code = int(match.group(1)) if match else 0
        return ServiceState(True, code, SERVICE_STATES.get(code, "UNKNOWN"), text.strip())

    def _wait_for(self, expected: Optional[int], timeout_seconds: float = 15.0) -> ServiceState:
        deadline = time.monotonic() + timeout_seconds
        state = self.query()
        while time.monotonic() < deadline:
            if expected is None and not state.installed:
                return state
            if expected is not None and state.installed and state.state_code == expected:
                return state
            time.sleep(0.2)
            state = self.query()
        raise RuntimeError("等待 Windows 服务状态超时，当前状态: %s" % state.state)

    def install(self) -> bool:
        if not is_administrator():
            raise PermissionError("安装 Windows 服务必须以管理员身份运行 POS")
        if self.query().installed:
            return False
        self._run(["--startup", "auto", "install"], timeout=60)
        self._wait_for(1)
        return True

    def start(self) -> bool:
        if not is_administrator():
            raise PermissionError("启动 Windows 服务必须以管理员身份运行 POS")
        state = self.query()
        if not state.installed:
            raise RuntimeError("ScaleBridge Windows 服务尚未安装")
        if state.state_code == 4:
            return False
        self._run(["start"])
        self._wait_for(4)
        return True

    def stop(self) -> bool:
        if not is_administrator():
            raise PermissionError("停止 Windows 服务必须以管理员身份运行 POS")
        state = self.query()
        if not state.installed or state.state_code == 1:
            return False
        self._run(["stop"])
        self._wait_for(1)
        return True

    def remove(self) -> bool:
        if not is_administrator():
            raise PermissionError("删除 Windows 服务必须以管理员身份运行 POS")
        if not self.query().installed:
            return False
        self.stop()
        self._run(["remove"])
        self._wait_for(None)
        return True


@dataclass
class InitializeReport:
    physical_test: PhysicalScaleTestResult
    pairs: ProvisionReport
    service_installed: bool
    service_started: bool


@dataclass
class RemovalReport:
    service_removed: bool = False
    removed_pairs: List[str] = field(default_factory=list)
    skipped_pairs: List[str] = field(default_factory=list)
    config_deleted: bool = False
    driver_removed: bool = False
    driver_retained_reason: str = ""


class ScaleBridgeLifecycle:
    def __init__(
        self,
        config_path: str,
        manifest_path: Optional[str] = None,
        provisioner: Optional[Com0ComProvisioner] = None,
        service: Optional[ScaleBridgeServiceController] = None,
        verify_enumeration: Optional[bool] = None,
        enumeration_timeout_seconds: float = 8.0,
    ):
        self.config_path = os.path.abspath(config_path)
        self.manifest_path = manifest_path or default_manifest_path()
        self.provisioner = provisioner
        self.service = service or ScaleBridgeServiceController()
        # A real provisioning run must verify that Windows has enumerated the
        # two POS-facing COM endpoints after setupc reports success.  Injected
        # provisioners used by tests/tools may intentionally omit a device
        # enumerator, so they remain opt-in unless explicitly requested.
        self.verify_enumeration = (provisioner is None) if verify_enumeration is None else bool(verify_enumeration)
        self.enumeration_timeout_seconds = max(0.0, float(enumeration_timeout_seconds))

    def initialize(
        self,
        config: ScaleBridgeConfig,
        physical_tester: Callable[[ScaleBridgeConfig], PhysicalScaleTestResult] = test_physical_scale,
        installer_path: Optional[str] = None,
    ) -> InitializeReport:
        if not is_administrator():
            raise PermissionError("初始化 ScaleBridge 必须以管理员身份运行 POS")
        config.validate_for_setup()
        state = self.service.query()
        existing_manifest = load_manifest(self.manifest_path)
        if state.installed and not existing_manifest.service_owned:
            raise RuntimeError("检测到同名 ScaleBridge 服务但缺少本产品所有权记录，请先人工核对")
        was_running = state.installed and state.state_code == 4
        if state.installed and state.state_code not in (0, 1):
            self.service.stop()

        try:
            physical = physical_tester(config)
            if not physical.ok:
                raise RuntimeError("物理电子秤测试失败：" + physical.message)
        except Exception:
            # No driver, pair or config mutation has happened yet. Restore the
            # previously healthy service so a failed maintenance test cannot
            # interrupt normal weighing.
            if was_running:
                self.service.start()
            raise

        setupc = find_setupc()
        driver_installed = False
        if not setupc:
            setupc = install_com0com_driver(installer_path)
            driver_installed = True
            manifest = load_manifest(self.manifest_path)
            manifest.driver_installed_by_product = True
            save_manifest(manifest, self.manifest_path)
        provisioner = self.provisioner or Com0ComProvisioner(setupc, self.manifest_path)
        # Payment/shouqianba pairing has its own page and lifecycle. Scale
        # initialization must never create, change or remove that pair.
        pairs = provisioner.ensure_required_pairs(
            config, include_scale=True, include_payment=False
        )
        # Persist the exact peers as soon as setupc confirms both pairs. Later
        # Win7 enumeration or service startup may still fail; a retry/reboot
        # must resume this successful state instead of rediscovering it as an
        # unexplained foreign pair.
        save_config(config, self.config_path)
        if self.verify_enumeration:
            missing, repair_error = _repair_and_wait_for_serial_ports(
                (
                    config.official_pos_virtual_port,
                    config.private_pos_virtual_port,
                ),
                setupc,
                provisioner.runner,
                provisioner.port_enumerator,
                self.enumeration_timeout_seconds,
            )
            if missing:
                problem_text = _format_com0com_device_problems(
                    enumerate_com0com_device_problems()
                )
                details = []
                if problem_text:
                    details.append("设备管理器检测到：" + problem_text + "。")
                if repair_error:
                    details.append("自动执行 setupc update 未完成：" + repair_error + "。")
                raise RuntimeError(
                    "setupc 已确认两组配对，但 Windows 仍未注册 %s。程序已经自动执行过 "
                    "setupc update 修复端点驱动。%s请在 Windows 驱动安装提示中选择“安装”；"
                    "若设备管理器仍显示黄色叹号，请用“更新驱动程序”指向 com0com 安装目录。"
                    % ("、".join(missing), "".join(details))
                )

        installed = self.service.install()
        manifest = load_manifest(self.manifest_path)
        manifest.service_owned = manifest.service_owned or installed
        manifest.driver_installed_by_product = manifest.driver_installed_by_product or driver_installed
        save_manifest(manifest, self.manifest_path)
        started = self.service.start()
        return InitializeReport(physical, pairs, installed, started)

    def initialize_virtual_only(
        self,
        config: ScaleBridgeConfig,
        installer_path: Optional[str] = None,
    ) -> ProvisionReport:
        """Create and verify the two POS-facing pairs without a real scale.

        This is a development-only maintenance path.  It deliberately does
        not run the physical protocol test, install/start the Windows service,
        or write ``scale_bridge.json``.  A temporary, non-device COM identity
        is used only to satisfy the normal pair planner; the caller's physical
        scale selection is restored before returning.
        """
        if not is_administrator():
            raise PermissionError("创建虚拟串口必须以管理员身份运行 POS")
        original_physical = config.physical_scale
        original_simulation = config.development_simulation
        # The pair planner validates the complete production configuration. A
        # sentinel is used only in memory so a developer does not have to fake
        # a real scale COM port or persist an invalid hardware identity.
        config.physical_scale = ScaleDeviceIdentity(
            port="COM9999", friendly_name="开发模拟秤（不写入配置）"
        )
        config.development_simulation = False
        try:
            config.validate_for_setup()
            setupc = find_setupc()
            if not setupc:
                setupc = install_com0com_driver(installer_path)
                manifest = load_manifest(self.manifest_path)
                manifest.driver_installed_by_product = True
                save_manifest(manifest, self.manifest_path)
            provisioner = self.provisioner or Com0ComProvisioner(
                setupc, self.manifest_path
            )
            report = provisioner.ensure_required_pairs(
                config, include_scale=True, include_payment=False
            )
            if self.verify_enumeration:
                missing, repair_error = _repair_and_wait_for_serial_ports(
                    (
                        config.official_pos_virtual_port,
                        config.private_pos_virtual_port,
                    ),
                    setupc,
                    provisioner.runner,
                    provisioner.port_enumerator,
                    self.enumeration_timeout_seconds,
                )
                if missing:
                    problem_text = _format_com0com_device_problems(
                        enumerate_com0com_device_problems()
                    )
                    detail = ("设备管理器检测到：" + problem_text + "。") if problem_text else ""
                    if repair_error:
                        detail += "setupc update 未完成：" + repair_error + "。"
                    raise RuntimeError(
                        "setupc 已返回虚拟配对，但 Windows 未注册 %s。程序已自动执行驱动修复。"
                        "%s请处理 Windows 驱动安装提示；如果仍有黄色叹号，请在设备管理器中"
                        "把驱动目录指向 com0com 安装目录。"
                        % ("、".join(missing), detail)
                    )
            return report
        finally:
            config.physical_scale = original_physical
            config.development_simulation = original_simulation

    def remove(
        self,
        remove_driver: bool = False,
        allow_unowned_service: bool = False,
    ) -> RemovalReport:
        """Remove bridge resources, with an explicit legacy-service escape hatch.

        Normal removal only touches resources recorded in the product manifest.
        ``allow_unowned_service`` is intentionally limited to the exact
        ``YgfScaleBridge`` Windows service and is used only after the touch UI
        shows a separate high-risk confirmation for pre-manifest installations.
        It never widens COM-pair deletion: unrecorded virtual pairs remain.
        """
        if not is_administrator():
            raise PermissionError("删除 ScaleBridge 必须以管理员身份运行 POS")
        manifest = load_manifest(self.manifest_path)
        report = RemovalReport()
        if manifest.service_owned:
            report.service_removed = self.service.remove()
            manifest.service_owned = False
            save_manifest(manifest, self.manifest_path)
        elif self.service.query().installed:
            if not allow_unowned_service:
                raise RuntimeError("检测到同名服务但缺少本产品所有权记录，为安全起见拒绝删除")
            report.service_removed = self.service.remove()

        provisioner = self.provisioner or Com0ComProvisioner(manifest_path=self.manifest_path)
        scale_purposes = {"official_scale", "private_scale"}
        if any(
            item.purpose in scale_purposes
            for item in (manifest.created_pairs + manifest.pending_pairs)
        ):
            report.removed_pairs, report.skipped_pairs = provisioner.remove_owned_pairs(scale_purposes)
        if report.skipped_pairs:
            raise RuntimeError("存在所有权不匹配的配对，已停止删除：" + "; ".join(report.skipped_pairs))

        manifest = load_manifest(self.manifest_path)
        if remove_driver:
            if not manifest.driver_installed_by_product:
                report.driver_retained_reason = "com0com 不是由本产品安装，已安全保留"
            else:
                try:
                    report.driver_removed = uninstall_com0com_driver()
                except RuntimeError as exc:
                    report.driver_retained_reason = str(exc)
                if report.driver_removed:
                    manifest.driver_installed_by_product = False
                    save_manifest(manifest, self.manifest_path)

        if os.path.isfile(self.config_path):
            os.unlink(self.config_path)
            report.config_deleted = True
        final_manifest = load_manifest(self.manifest_path)
        if (
            not final_manifest.created_pairs
            and not final_manifest.pending_pairs
            and not final_manifest.service_owned
            and not final_manifest.driver_installed_by_product
            and not final_manifest.reboot_required
        ):
            try:
                os.unlink(self.manifest_path)
            except FileNotFoundError:
                pass
        return report


class PaymentPairLifecycle:
    """Independent lifecycle for the optional Shouqianba serial pair."""

    def __init__(
        self,
        manifest_path: Optional[str] = None,
        provisioner: Optional[Com0ComProvisioner] = None,
        verify_enumeration: Optional[bool] = None,
        enumeration_timeout_seconds: float = 8.0,
    ):
        self.manifest_path = manifest_path or default_manifest_path()
        self.provisioner = provisioner
        # The real UI uses the Windows device list as a postcondition.  Tests
        # and injected provisioners may intentionally use an empty fake port
        # list, so verification is enabled automatically only for the real
        # lifecycle path unless explicitly overridden.
        self.verify_enumeration = (provisioner is None) if verify_enumeration is None else bool(verify_enumeration)
        self.enumeration_timeout_seconds = max(0.0, float(enumeration_timeout_seconds))

    def initialize(
        self,
        sender_port: str,
        plugin_port: str,
        installer_path: Optional[str] = None,
    ) -> ProvisionReport:
        if not is_administrator():
            raise PermissionError("创建收钱吧虚拟串口配对必须以管理员身份运行 POS")
        config = ScaleBridgeConfig(
            payment_pos_port=str(sender_port or "").strip().upper(),
            payment_plugin_port=str(plugin_port or "").strip().upper(),
        )
        setupc = find_setupc()
        if not setupc:
            setupc = install_com0com_driver(installer_path)
            manifest = load_manifest(self.manifest_path)
            manifest.driver_installed_by_product = True
            save_manifest(manifest, self.manifest_path)
        provisioner = self.provisioner or Com0ComProvisioner(
            setupc, self.manifest_path
        )
        report = provisioner.ensure_required_pairs(
            config, include_scale=False, include_payment=True
        )
        if self.verify_enumeration:
            missing = _wait_for_serial_ports(
                (config.payment_pos_port, config.payment_plugin_port),
                provisioner.port_enumerator,
                self.enumeration_timeout_seconds,
            )
            if missing:
                raise RuntimeError(
                    "setupc 已返回配对，但 Windows 设备管理器未枚举出 %s。"
                    "请确认 com0com 驱动安装完成，必要时重启电脑后再创建。"
                    % "、".join(missing)
                )
        return report

    def remove(self) -> Tuple[List[str], List[str]]:
        if not is_administrator():
            raise PermissionError("删除收钱吧虚拟串口配对必须以管理员身份运行 POS")
        manifest = load_manifest(self.manifest_path)
        if not any(
            item.purpose == "payment"
            for item in (manifest.created_pairs + manifest.pending_pairs)
        ):
            return [], []
        provisioner = self.provisioner or Com0ComProvisioner(
            manifest_path=self.manifest_path
        )
        return provisioner.remove_owned_pairs({"payment"})

    def remove_exact(
        self,
        sender_port: str,
        plugin_port: str,
        allow_unowned: bool = False,
    ) -> Tuple[List[str], List[str]]:
        """Remove exactly the configured payment pair after explicit confirmation.

        This is the migration path for pairs created by an older release before
        ownership records existed. It never performs a broad scan/delete: the
        two configured endpoints must belong to the same com0com pair, and an
        unowned pair is accepted only when the UI has obtained a second,
        explicit confirmation from the operator.
        """
        if not is_administrator():
            raise PermissionError("删除收钱吧虚拟串口配对必须以管理员身份运行 POS")
        sender = str(sender_port or "").strip().upper()
        plugin = str(plugin_port or "").strip().upper()
        if not re.fullmatch(r"COM[1-9]\d*", sender) or not re.fullmatch(r"COM[1-9]\d*", plugin):
            return [], ["当前收钱吧发送端和插件接收端必须都是 COM 端口"]
        if sender == plugin:
            return [], ["当前两个端口不能相同"]

        provisioner = self.provisioner or Com0ComProvisioner(
            manifest_path=self.manifest_path
        )
        pairs = provisioner._pairs()
        pair = find_pair_by_endpoint(sender, pairs)
        if not pair or not pair.contains(plugin):
            return [], ["当前填写的 %s ↔ %s 不属于同一个 com0com 配对" % (sender, plugin)]

        manifest = load_manifest(self.manifest_path)
        owned = next(
            (item for item in manifest.created_pairs
             if item.purpose == "payment" and item.matches(pair)),
            None,
        )
        if not owned and not allow_unowned:
            return [], [
                "%s ↔ %s 未在本系统所有权清单中；需要再次确认后才能清理旧版本配对"
                % (sender, plugin)
            ]

        remove_pair(
            pair.index,
            setupc_path=provisioner._require_setupc(),
            allow_mutation=True,
            runner=provisioner.runner,
        )
        if any(item.index == pair.index for item in provisioner._pairs()):
            raise RuntimeError("setupc 未能删除配对 #%d" % pair.index)
        if owned:
            manifest.created_pairs.remove(owned)
        _mark_reboot_required(
            manifest,
            self.manifest_path,
            "本次开机已删除过收钱吧 com0com 虚拟串口",
        )
        return [Com0ComProvisioner._pair_description(pair)], []


def collect_diagnostics(
    config: ScaleBridgeConfig,
    service: Optional[ScaleBridgeServiceController] = None,
) -> dict:
    candidates = enumerate_serial_ports(include_virtual=True)
    setupc = find_setupc()
    hub4com = find_hub4com()
    try:
        pairs = list_pairs(setupc) if setupc else []
        pair_error = ""
    except Exception as exc:
        pairs = []
        pair_error = str(exc)
    service_state = (service or ScaleBridgeServiceController()).query()
    try:
        from .ipc import read_status
        runtime_status = read_status(timeout_ms=500)
        runtime_status_error = ""
    except Exception as exc:
        runtime_status = {}
        runtime_status_error = str(exc)
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "windows": sys.getwindowsversion().platform_version if sys.platform == "win32" else sys.platform,
        "administrator": is_administrator(),
        "config": config.to_dict(),
        "setupc_path": setupc or "",
        "hub4com_path": hub4com or "",
        "hub4com_role": "optional_manual_diagnostic_only",
        "pair_error": pair_error,
        "pairs": [asdict(item) for item in pairs],
        "service": asdict(service_state),
        "runtime_status": runtime_status,
        "runtime_status_error": runtime_status_error,
        "serial_ports": [item.to_dict() for item in candidates],
        "manifest": load_manifest().to_dict(),
    }


def write_diagnostic_report(path: str, data: dict) -> None:
    _atomic_json_write(path, data)
