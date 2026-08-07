"""PyInstaller/source-tree entry point for the independent relay service."""
import os
import sys


if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

try:
    import win32event
    import win32service
    import win32serviceutil
    import servicemanager
except ImportError:  # Static analysis/non-Windows fallback.
    win32event = win32service = win32serviceutil = servicemanager = None

from core.printer_relay_host import PrinterRelayHost, request_proxy_stop, _clear_stop_request


SERVICE_NAME = "ppposPrinterRelay"
SERVICE_DISPLAY_NAME = "ppposPrinterRelay"


if win32serviceutil:
    class PrinterRelayWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = "Independent RAW printer relay for official POS and order data."

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            request_proxy_stop()
            win32event.SetEvent(self._stop_event)

        def SvcDoRun(self):
            _clear_stop_request()
            servicemanager.LogInfoMsg("%s starting" % SERVICE_NAME)
            try:
                PrinterRelayHost().run()
            finally:
                servicemanager.LogInfoMsg("%s stopped" % SERVICE_NAME)
else:
    PrinterRelayWindowsService = None


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not win32serviceutil or not PrinterRelayWindowsService:
        raise RuntimeError("pywin32 is required to install or host the relay service")
    if getattr(sys, "frozen", False) and not args:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PrinterRelayWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
        return 0
    return int(win32serviceutil.HandleCommandLine(PrinterRelayWindowsService) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
