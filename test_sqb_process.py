import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.c_size_t),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', ctypes.c_wchar * 260)
    ]

def get_shouqianba_pids():
    pids = []
    hSnapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if hSnapshot != -1:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(hSnapshot, ctypes.byref(pe)):
            while True:
                exe = pe.szExeFile.lower()
                if "shouqianba" in exe or "收钱吧" in exe:
                    pids.append((pe.th32ProcessID, pe.szExeFile))
                if not kernel32.Process32NextW(hSnapshot, ctypes.byref(pe)):
                    break
        kernel32.CloseHandle(hSnapshot)
    return pids

def find_shouqianba_windows():
    sqb_pids = dict(get_shouqianba_pids())
    print(f"Found Shouqianba processes: {sqb_pids}")
    
    sqb_hwnds = []
    def foreach_window(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in sqb_pids:
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                
                title_len = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(title_len + 1)
                user32.GetWindowTextW(hwnd, buf, title_len + 1)
                
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                
                print(f"Shouqianba HWND={hwnd} Rect={w}x{h} ({rect.left},{rect.top}) Title='{buf.value}' Class='{cls_buf.value}' Exe='{sqb_pids[pid.value]}'")
                sqb_hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(foreach_window), 0)
    return sqb_hwnds

if __name__ == "__main__":
    find_shouqianba_windows()
