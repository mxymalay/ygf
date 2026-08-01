import ctypes
import time

user32 = ctypes.windll.user32

VK_MAPPING = {
    "CTRL": 0x11,
    "CONTROL": 0x11,
    "ALT": 0x12,
    "SHIFT": 0x10,
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09,
}

# A-Z mapping
for i in range(26):
    ch = chr(ord('A') + i)
    VK_MAPPING[ch] = 0x41 + i

# 0-9 mapping
for i in range(10):
    VK_MAPPING[str(i)] = 0x30 + i

KEYEVENTF_KEYUP = 0x0002

def send_hotkey(hotkey_str: str):
    parts = [p.strip().upper() for p in hotkey_str.split("+") if p.strip()]
    vk_codes = []
    for p in parts:
        if p in VK_MAPPING:
            vk_codes.append(VK_MAPPING[p])
        else:
            print(f"Unknown key in hotkey: {p}")

    if not vk_codes:
        return False

    # Key down
    for vk in vk_codes:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)

    time.sleep(0.05)

    # Key up in reverse order
    for vk in reversed(vk_codes):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)

    print(f"Successfully simulated hotkey: {hotkey_str}")
    return True

send_hotkey("F12")
