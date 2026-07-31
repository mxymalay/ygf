import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtWidgets import QApplication
from ui.sale_widget import TasteSelectionDialog

app = QApplication(sys.argv)
dlg = TasteSelectionDialog("草本骨汤")

def on_change(t):
    print("SIGNAL RECEIVED:", t)

dlg.flavor_changed.connect(on_change)
print("Initial tag:", dlg.get_tag_string())
dlg._select_spice("重辣")
dlg._toggle_pref("免蒜")
dlg._toggle_pref("免醋")
