"""Windows-service host for the ScaleBridge runtime.

No service registration occurs when this module is imported.  An elevated
technician explicitly runs its `install`, `start`, `stop` or `remove` command.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

# ``pythonservice.exe`` loads the configured service file as a stand-alone
# module on source-tree installs.  In that mode ``__package__`` is empty, so
# ordinary relative imports fail before the service can report STARTED.  Keep
# the normal package imports for the application, but make the Windows service
# host explicitly able to resolve its package from the project root too.
if __package__:
    from .bridge import ScaleBridgeRuntime
    from .configuration import DEFAULT_CONFIG_FILE, load_config
    from .ipc import StatusPipeServer
else:
    _source_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _source_root not in sys.path:
        sys.path.insert(0, _source_root)
    from scale_bridge.bridge import ScaleBridgeRuntime
    from scale_bridge.configuration import DEFAULT_CONFIG_FILE, load_config
    from scale_bridge.ipc import StatusPipeServer


SERVICE_NAME = "YgfScaleBridge"
SERVICE_DISPLAY_NAME = "YGF POS ScaleBridge"


def default_config_path() -> str:
    configured = os.environ.get("YGF_SCALE_BRIDGE_CONFIG")
    if configured:
        return os.path.abspath(configured)
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), DEFAULT_CONFIG_FILE)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", DEFAULT_CONFIG_FILE))


def configure_logging() -> None:
    directory = os.path.join(os.environ.get("ProgramData", os.getcwd()), "YgfPos", "logs")
    try:
        if not os.path.isdir(directory):
            os.makedirs(directory)
        logging.basicConfig(
            filename=os.path.join(directory, "scale_bridge_service.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)


try:
    import win32event
    import win32service
    import win32serviceutil
    import servicemanager
except ImportError:  # Allows static analysis/tests on systems without pywin32.
    win32event = win32service = win32serviceutil = servicemanager = None


if win32serviceutil:
    class ScaleBridgeWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = "Single-owner serial bridge for the DIBAL scale and POS virtual ports."

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._runtime: Optional[ScaleBridgeRuntime] = None
            self._pipe: Optional[StatusPipeServer] = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)
            if self._pipe:
                self._pipe.stop()
            if self._runtime:
                self._runtime.stop()

        def SvcDoRun(self):
            configure_logging()
            servicemanager.LogInfoMsg("%s starting" % SERVICE_NAME)
            config_path = default_config_path()
            config = load_config(config_path)
            if config.enable_debug_hex_log:
                logging.getLogger("ScaleBridge").setLevel(logging.DEBUG)
            logging.getLogger("ScaleBridge").info("loading configuration: %s", config_path)
            self._runtime = ScaleBridgeRuntime(config, config_path=config_path)
            self._pipe = StatusPipeServer(lambda: self._runtime.status().to_dict())
            self._pipe.start()
            try:
                self._runtime.start()
                win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)
            finally:
                if self._pipe:
                    self._pipe.stop()
                if self._runtime:
                    self._runtime.stop()
                servicemanager.LogInfoMsg("%s stopped" % SERVICE_NAME)
else:
    ScaleBridgeWindowsService = None


def run_foreground(config_path: Optional[str] = None) -> None:
    """Maintenance-only foreground runner; does not register a service."""
    configure_logging()
    path = config_path or default_config_path()
    runtime = ScaleBridgeRuntime(load_config(path), config_path=path)
    pipe = StatusPipeServer(lambda: runtime.status().to_dict())
    pipe.start()
    runtime.start()
    try:
        while True:
            # The service process has no GUI. Ctrl+C is intentionally the only
            # interactive maintenance stop path here.
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        pipe.stop()
        runtime.stop()


def _write_source_service_python_path() -> None:
    """Make pywin32's pythonservice.exe import the source-tree package."""
    if getattr(sys, "frozen", False):
        return
    try:
        import winreg
        service_key = r"SYSTEM\CurrentControlSet\Services\%s" % SERVICE_NAME
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            service_key,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            source_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            winreg.SetValueEx(key, "PythonPath", 0, winreg.REG_EXPAND_SZ, source_root)
    except (ImportError, OSError):
        # Installation itself already succeeded; surface import failures from
        # the service log/SCM rather than hiding the original install result.
        logging.getLogger("ScaleBridge").warning(
            "failed to write source PythonPath; service install may need elevation"
        )


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # A frozen service executable is launched by the Windows Service Control
    # Manager with no arguments.  HandleCommandLine is only for maintenance
    # commands; with no arguments it prints usage and exits instead of hosting.
    if getattr(sys, "frozen", False) and not args:
        if not servicemanager or not ScaleBridgeWindowsService:
            raise RuntimeError("pywin32 service dispatcher is unavailable")
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ScaleBridgeWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    if args[:1] == ["debug"]:
        run_foreground(args[1] if len(args) > 1 else None)
        return 0
    if not win32serviceutil:
        raise RuntimeError("pywin32 is required to install or host ScaleBridge as a Windows service")
    result = int(win32serviceutil.HandleCommandLine(ScaleBridgeWindowsService) or 0)
    if any(str(item).lower() == "install" for item in args):
        _write_source_service_python_path()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
