"""Win7-safe text helpers for the PyQt5 UI.

Windows 7 commonly has no emoji font. Qt then paints a square glyph for
otherwise valid labels, which is especially confusing in the settings and
takeout category tables. Keep the source wording but replace emoji only at
the presentation boundary with short, readable ASCII/Unicode-safe tags.
"""
from PyQt5.QtCore import QObject, QEvent, QTimer
from PyQt5.QtWidgets import (
    QAbstractButton, QLabel, QComboBox, QTabWidget, QTableWidget,
    QListWidget, QTreeWidget, QTreeWidgetItem,
)


_REPLACEMENTS = {
    "⚠️": "[!]", "⚠": "[!]", "❌": "[X]", "✅": "[OK]",
    "❓": "[?]", "ℹ️": "[i]", "ℹ": "[i]", "⭐": "*",
    "🍲": "[汤]", "🥩": "[肉]", "🥬": "[菜]", "🥤": "[饮]",
    "💵": "[钱]", "💳": "[卡]", "📱": "[码]", "💻": "[电脑]",
    "🖥️": "[窗口]", "🖥": "[窗口]", "⚖️": "[秤]", "⚖": "[秤]",
    "📋": "[表]", "📊": "[图]", "📈": "[图]", "📉": "[图]",
    "📦": "[包]", "📥": "[入]", "📤": "[出]", "🖨️": "[印]",
    "🖨": "[印]", "🔄": "[刷新]", "🔍": "[查]", "🧹": "[清理]",
    "🗑️": "[删]", "🗑": "[删]", "🎨": "[图标]", "🎵": "[音乐]",
    "🌐": "[网络]", "🏪": "[店]", "⚙️": "[设置]", "⚙": "[设置]",
    "🔔": "[提醒]", "🧠": "[算法]", "🔥": "[重置]", "🚨": "[警告]",
    "🛠️": "[工具]", "🛠": "[工具]", "🛡️": "[保护]", "🛡": "[保护]",
    "💡": "[提示]", "📌": "[固定]", "🔤": "[文字]", "🧪": "[测试]",
    "👨‍🍳": "[制作]", "🎉": "[完成]", "🎯": "[命中]", "⏳": "[等待]",
    "🍜": "[餐]", "🧾": "[票]", "👋": "[欢迎]", "💰": "[钱]",
}


def win7_safe_text(value):
    """Return text that has no emoji glyphs unsupported by the Win7 font set."""
    text = str(value or "")
    for source, replacement in sorted(_REPLACEMENTS.items(), key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(source, replacement)
    # Remove variation selectors left by a platform-specific emoji sequence.
    return text.replace("\ufe0f", "")


def _set_text_if_needed(widget, getter, setter):
    try:
        current = getter()
        safe = win7_safe_text(current)
        if safe != current:
            setter(safe)
    except (AttributeError, RuntimeError, TypeError):
        pass


def sanitize_widget_text(root):
    """Sanitize visible text controls below ``root`` in place."""
    widgets = [root]
    try:
        widgets.extend(root.findChildren(QObject))
    except (AttributeError, RuntimeError):
        return
    for widget in widgets:
        if isinstance(widget, (QAbstractButton, QLabel)):
            _set_text_if_needed(widget, widget.text, widget.setText)
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                current = widget.itemText(index)
                safe = win7_safe_text(current)
                if safe != current:
                    widget.setItemText(index, safe)
        if isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                current = widget.tabText(index)
                safe = win7_safe_text(current)
                if safe != current:
                    widget.setTabText(index, safe)
        if isinstance(widget, QTableWidget):
            for row in range(widget.rowCount()):
                for col in range(widget.columnCount()):
                    item = widget.item(row, col)
                    if item is not None:
                        current = item.text()
                        safe = win7_safe_text(current)
                        if safe != current:
                            item.setText(safe)
        if isinstance(widget, QListWidget):
            for index in range(widget.count()):
                item = widget.item(index)
                current = item.text()
                safe = win7_safe_text(current)
                if safe != current:
                    item.setText(safe)
        if isinstance(widget, QTreeWidget):
            def sanitize_item(item):
                for column in range(widget.columnCount()):
                    current = item.text(column)
                    safe = win7_safe_text(current)
                    if safe != current:
                        item.setText(column, safe)
                for child_index in range(item.childCount()):
                    sanitize_item(item.child(child_index))
            for index in range(widget.topLevelItemCount()):
                sanitize_item(widget.topLevelItem(index))


class Win7TextCompatFilter(QObject):
    """Sanitize controls when shown or when a dynamic child is added."""
    def eventFilter(self, obj, event):  # noqa: N802 - Qt API name
        if event.type() in (QEvent.Show, QEvent.ChildAdded, QEvent.LayoutRequest):
            QTimer.singleShot(0, lambda target=obj: sanitize_widget_text(target))
        return False


def install_win7_text_compat(app):
    """Install one retained application-wide filter and return it."""
    compat = Win7TextCompatFilter(app)
    app.installEventFilter(compat)
    app._win7_text_compat = compat
    return compat

