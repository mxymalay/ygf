"""Crash-safe local draft for the current unfinished POS order."""
import json
import os
from datetime import datetime

from config import DATA_DIR


DRAFT_PATH = os.path.join(DATA_DIR, "current_order_draft.json")


def load_draft():
    if not os.path.isfile(DRAFT_PATH):
        return None
    try:
        with open(DRAFT_PATH, "r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict) or not isinstance(value.get("cart_items"), list):
            return None
        return value
    except Exception:
        # A damaged draft must never prevent the cashier from starting POS.
        return None


def save_draft(order_id, temp_order_no, cart_items):
    if not cart_items:
        clear_draft()
        return
    payload = {
        "order_id": str(order_id or ""),
        "temp_order_no": str(temp_order_no or ""),
        "cart_items": cart_items,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    temporary = DRAFT_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, DRAFT_PATH)


def clear_draft():
    try:
        if os.path.exists(DRAFT_PATH):
            os.remove(DRAFT_PATH)
    except OSError:
        # The order is still protected in memory; the next save will retry.
        pass
