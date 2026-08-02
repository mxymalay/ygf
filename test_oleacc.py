import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
oleacc = ctypes.windll.oleacc
ole32 = ctypes.windll.ole32

OBJID_CLIENT = 0xFFFFFFFC
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E

def scan_window_text_oleacc(hwnd):
    texts = []
    # 1. Standard GetWindowTextW
    l = user32.GetWindowTextLengthW(hwnd)
    if l > 0:
        buf = ctypes.create_unicode_buffer(l + 1)
        user32.GetWindowTextW(hwnd, buf, l + 1)
        if buf.value.strip():
            texts.append(buf.value.strip())
            
    # 2. WM_GETTEXT
    try:
        l2 = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if 0 < l2 < 2048:
            buf2 = ctypes.create_unicode_buffer(l2 + 1)
            user32.SendMessageW(hwnd, WM_GETTEXT, l2 + 1, buf2)
            if buf2.value.strip() and buf2.value.strip() not in texts:
                texts.append(buf2.value.strip())
    except Exception:
        pass
        
    return texts

def dump_all_texts():
    print("=== SCANNING ALL WINDOWS TEXTS VIA CTYPES ===")
    found = []
    def foreach_window(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            t_list = scan_window_text_oleacc(hwnd)
            
            # Enum child windows
            def foreach_child(chnd, lp):
                ct_list = scan_window_text_oleacc(chnd)
                t_list.extend(ct_list)
                return True
                
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
            user32.EnumChildWindows(hwnd, WNDENUMPROC(foreach_child), 0)
            
            if t_list:
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                print(f"HWND: {hwnd} ({cls_buf.value}) -> Texts: {t_list[:5]}")
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(foreach_window), 0)

if __name__ == "__main__":
    dump_all_texts()
