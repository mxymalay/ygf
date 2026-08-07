# -*- coding: utf-8 -*-
"""Bounded raw-print capture for the official POS relay monitor.

Every received job is retained as a ``.bin``/``.json`` pair. The retention
limit is configurable; capture is not optional because the live monitor and
field-remapping workflow read these sidecars directly.
"""
import hashlib
import json
import os
from datetime import datetime

from config import DATA_DIR


DEFAULT_CAPTURE_DIR = os.path.join(DATA_DIR, "printer_relay_capture")


def _now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def capture_print_payload(payload, parsed=None, config=None, capture_dir=None):
    """Persist one raw payload and a compact metadata sidecar.

    Returns the binary sample path, or an empty string when capture fails.
    Capture failures never belong on the printing critical path and are
    therefore swallowed by design.
    """
    config = config or {}
    data = bytes(payload or b"")
    if not data:
        return ""
    try:
        max_bytes = max(1024, int(config.get("takeout_capture_max_bytes", 2 * 1024 * 1024) or 0))
    except (TypeError, ValueError):
        max_bytes = 2 * 1024 * 1024
    # The interceptor itself caps one TCP job at 1 MiB.  Keep this guard for
    # direct callers and mark truncation explicitly if it ever applies.
    truncated = len(data) > max_bytes
    stored = data[:max_bytes]
    root = capture_dir or config.get("takeout_capture_dir") or DEFAULT_CAPTURE_DIR
    os.makedirs(root, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    digest = hashlib.sha256(data).hexdigest()[:12]
    stem = "printer_relay_%s_%s" % (stamp, digest)
    bin_path = os.path.join(root, stem + ".bin")
    meta_path = os.path.join(root, stem + ".json")
    temporary_bin = bin_path + ".tmp"
    temporary_meta = meta_path + ".tmp"
    parsed = parsed or {}
    metadata = {
        "captured_at": _now_text(),
        "payload_size": len(data),
        "stored_size": len(stored),
        "truncated": truncated,
        "sha256": hashlib.sha256(data).hexdigest(),
        "payload_type": parsed.get("payload_type", "binary_or_unknown"),
        "parse_failed": bool(parsed.get("parse_failed")),
        "receipt_kind": parsed.get("receipt_kind", "unknown"),
        "receipt_key": parsed.get("receipt_key", ""),
        "key_confidence": parsed.get("key_confidence", "low"),
        "platform": parsed.get("platform", ""),
        "order_no": parsed.get("order_no", ""),
        "full_order_id": parsed.get("full_order_id", ""),
        "order_amount": parsed.get("order_amount"),
        "amount_source": parsed.get("amount_source", ""),
        "amount_valid": bool(parsed.get("amount_valid")),
        "payment_status": parsed.get("payment_status", "unknown"),
        "payment_status_evidence": parsed.get("payment_status_evidence", ""),
        "payment_status_confidence": parsed.get("payment_status_confidence", "unknown"),
        "payment_method": parsed.get("payment_method", ""),
        "order_time": parsed.get("order_time", ""),
        "item_count": int(parsed.get("item_count", 0) or 0),
        # Text extraction is useful for template comparison.  The binary file
        # remains the source of truth for reproducing parser behavior.
        "extracted_text": str(parsed.get("raw_text", "") or ""),
    }
    try:
        with open(temporary_bin, "wb") as stream:
            stream.write(stored)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_bin, bin_path)
        with open(temporary_meta, "w", encoding="utf-8") as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_meta, meta_path)
        try:
            max_files = max(1, int(config.get("takeout_capture_max_files", 20) or 0))
        except (TypeError, ValueError):
            max_files = 20
        # Count one raw sample as a .bin/.json pair.  Deleting by individual
        # files could leave an orphaned sidecar; remove the oldest stems as a
        # pair so the directory always contains at most ``max_files`` samples.
        stems = {}
        for name in os.listdir(root):
            if not name.endswith((".bin", ".json")):
                continue
            stem, _extension = os.path.splitext(name)
            path = os.path.join(root, name)
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            stems[stem] = max(mtime, stems.get(stem, 0.0))
        ordered_stems = sorted(stems, key=stems.get)
        for stem in ordered_stems[:-max_files]:
            for extension in (".bin", ".json"):
                try:
                    os.remove(os.path.join(root, stem + extension))
                except OSError:
                    pass
        return bin_path
    except (OSError, ValueError, TypeError):
        for path in (temporary_bin, temporary_meta):
            try:
                os.remove(path)
            except OSError:
                pass
        return ""
