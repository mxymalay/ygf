"""Windows service controller for the independent external-order relay."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import subprocess
import sys
import time


SERVICE_NAME = "ppposPrinterRelay"
SERVICE_DISPLAY_NAME = "ppposPrinterRelay"
LEGACY_SERVICE_NAME = "ppposTakeoutRelay"


def _application_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _decode(result):
    raw = (getattr(result, "stdout", b"") or b"") + (getattr(result, "stderr", b"") or b"")
    if isinstance(raw, str):
        return raw
    return raw.decode("mbcs", errors="replace")


@dataclass
class RelayServiceState:
    installed: bool
    state_code: int = 0
    state: str = "NOT_INSTALLED"
    detail: str = ""
    service_name: str = SERVICE_NAME
    legacy: bool = False


class PrinterRelayServiceController:
    _STATES = {1: "STOPPED", 2: "START_PENDING", 3: "STOP_PENDING", 4: "RUNNING", 5: "CONTINUE_PENDING", 6: "PAUSE_PENDING", 7: "PAUSED"}

    def __init__(self, command_prefix=None, runner=subprocess.run):
        self.runner = runner
        self.command_prefix = list(command_prefix) if command_prefix else self._default_command_prefix()

    @staticmethod
    def _default_command_prefix():
        if getattr(sys, "frozen", False):
            for filename in ("PrinterRelayService.exe", "TakeoutRelayService.exe"):
                executable = os.path.join(_application_root(), filename)
                if os.path.isfile(executable):
                    return [executable]
            return []
        interpreter = sys.executable
        pythonw = os.path.join(os.path.dirname(os.path.abspath(interpreter)), "pythonw.exe")
        if sys.platform == "win32" and os.path.isfile(pythonw):
            interpreter = pythonw
        return [interpreter, os.path.join(_application_root(), "printer_relay_service.py")]

    def _query_name(self, name):
        result = self.runner(
            ["sc.exe", "query", name], capture_output=True, timeout=10,
            check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        detail = _decode(result).strip()
        if result.returncode:
            return RelayServiceState(False, detail=detail)
        match = re.search(r"(?:STATE|状态)\s*:\s*([1-7])", detail, re.IGNORECASE)
        code = int(match.group(1)) if match else 0
        return RelayServiceState(True, code, self._STATES.get(code, "UNKNOWN"), detail, name, name == LEGACY_SERVICE_NAME)

    def query(self):
        state = self._query_name(SERVICE_NAME)
        if state.installed:
            return state
        legacy = self._query_name(LEGACY_SERVICE_NAME)
        if legacy.installed:
            legacy.detail = "发现旧服务 %s；安装新服务时会自动迁移。\n%s" % (LEGACY_SERVICE_NAME, legacy.detail)
            return legacy
        return state

    def _run(self, args, timeout=30):
        if not self.command_prefix:
            raise FileNotFoundError("部署目录缺少 PrinterRelayService.exe")
        result = self.runner(
            self.command_prefix + list(args), capture_output=True, timeout=timeout,
            check=False, creationflags=0,
        )
        if result.returncode:
            raise RuntimeError(_decode(result).strip() or "打印机中继服务命令失败")
        return result

    @staticmethod
    def _require_admin():
        if sys.platform != "win32":
            raise RuntimeError("打印机中继 Windows 服务只能在 Windows 上安装")
        try:
            import ctypes
            if not ctypes.windll.shell32.IsUserAnAdmin():
                raise PermissionError("安装或控制打印机中继服务需要管理员权限")
        except AttributeError:
            raise RuntimeError("无法确认 Windows 管理员权限")

    def _wait_for(self, expected, timeout_seconds=15):
        deadline = time.monotonic() + timeout_seconds
        state = self.query()
        while time.monotonic() < deadline:
            if expected is None and not state.installed:
                return state
            if expected is not None and state.installed and state.state_code == expected:
                return state
            time.sleep(0.2)
            state = self.query()
        raise RuntimeError("等待打印机中继服务状态超时：%s" % state.state)

    def _remove_legacy_service(self):
        legacy = self._query_name(LEGACY_SERVICE_NAME)
        if not legacy.installed:
            return False
        if legacy.state_code != 1:
            self.runner(["sc.exe", "stop", LEGACY_SERVICE_NAME], capture_output=True,
                        timeout=30, check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.runner(["sc.exe", "delete", LEGACY_SERVICE_NAME], capture_output=True,
                    timeout=30, check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not self._query_name(LEGACY_SERVICE_NAME).installed:
                return True
            time.sleep(0.2)
        raise RuntimeError("旧打印机中继服务 %s 未能删除" % LEGACY_SERVICE_NAME)

    def install(self):
        self._require_admin()
        state = self.query()
        if state.installed and not state.legacy:
            return False
        if state.legacy:
            self._remove_legacy_service()
        self._run(["--startup", "auto", "install"], timeout=60)
        self._wait_for(1)
        return True

    def start(self):
        self._require_admin()
        state = self.query()
        if state.legacy:
            self.install()
            state = self.query()
        if not state.installed:
            raise RuntimeError("打印机中继 Windows 服务尚未安装")
        if state.state_code == 4:
            return False
        self._run(["start"])
        self._wait_for(4)
        return True

    def stop(self):
        self._require_admin()
        state = self.query()
        if not state.installed or state.state_code == 1:
            return False
        if state.legacy:
            self.runner(["sc.exe", "stop", LEGACY_SERVICE_NAME], capture_output=True,
                        timeout=30, check=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True
        self._run(["stop"])
        self._wait_for(1)
        return True

    def remove(self):
        self._require_admin()
        state = self.query()
        if not state.installed:
            return False
        if state.legacy:
            return self._remove_legacy_service()
        self.stop()
        self._run(["remove"])
        self._wait_for(None)
        return True


# Source compatibility for older plugins/imports. The Windows service itself
# is now registered as ppposPrinterRelay; this alias is not a service name.
TakeoutRelayServiceController = PrinterRelayServiceController
