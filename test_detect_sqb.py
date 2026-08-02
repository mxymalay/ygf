import ctypes
import ctypes.wintypes

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def dump():
    print("=== DUMPING VISIBLE WINDOWS ===")
    def foreach(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            l = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(l + 1)
            user32.GetWindowTextW(hwnd, buf, l + 1)
            title = buf.value.strip()
            
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls_name = cls_buf.value.strip()
            
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            
            if w > 50 and h > 50:
                # Check process ID
                pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                print(f"HWND: {hwnd} | Class: {cls_name} | Rect: {w}x{h} ({rect.left},{rect.top}) | PID: {pid.value} | Title: '{title}'")
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(foreach), 0)

if __name__ == "__main__":
    dump()
