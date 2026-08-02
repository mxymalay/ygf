import ctypes
from ctypes import wintypes
import comtypes
from comtypes import GUID
from comtypes.client import CreateObject

def test_uia_text():
    print("=== TESTING UIA TEXT DETECTION ===")
    try:
        # Load UIAutomation
        uia = CreateObject("{ffb92f62-a52a-4138-9a96-6eb107cf7cae}") # CLSID_CUIAutomation
        root = uia.GetRootElement()
        
        # Find all elements with Name or Value containing 支付成功 / 打印小票
        condition = uia.CreateTrueCondition()
        element_array = root.FindAll(comtypes.gen.UIAutomationClient.TreeScope_Subtree, condition)
        count = element_array.Length
        print(f"Total UIA elements found: {count}")
        
        for i in range(count):
            try:
                el = element_array.GetElement(i)
                name = el.CurrentName
                if name and any(k in name for k in ["支付成功", "支付失败", "支付中", "打印小票", "收钱吧"]):
                    print(f"Found UIA match: '{name}' | ControlType: {el.CurrentControlType}")
            except Exception:
                pass
    except Exception as e:
        print(f"UIA Error: {e}")

if __name__ == "__main__":
    test_uia_text()
