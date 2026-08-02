from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QImage
import sys
import ctypes

def test_grab_window():
    app = QApplication(sys.argv)
    user32 = ctypes.windll.user32
    
    print("=== TESTING WIN32 + PYQT5 WINDOW GRAB ===")
    def foreach_window(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            l = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(l + 1)
            user32.GetWindowTextW(hwnd, buf, l + 1)
            title = buf.value.strip()
            
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls_name = cls_buf.value.strip()
            
            if any(k in title for k in ["收钱吧", "PC收款", "Shouqianba"]) or any(k in cls_name for k in ["Qt", "Chrome"]):
                screen = QApplication.primaryScreen()
                pixmap = screen.grabWindow(hwnd)
                if not pixmap.isNull():
                    print(f"Successfully grabbed window HWND={hwnd} title='{title}' class='{cls_name}' size={pixmap.width()}x{pixmap.height()}")
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(foreach_window), 0)

if __name__ == "__main__":
    test_grab_window()
