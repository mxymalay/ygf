"""Official POS log discovery with a small, predictable search scope."""
import os
import time


LEGACY_LOG_DIRS = (
    r"C:\YANGGUOFU-POS\serial",
    r"C:\YGF-POS\serial",
    r"C:\ProgramData\YANGGUOFU-POS\serial",
)


def get_official_log_dirs(config=None):
    """Configured folder first, then known compatibility locations only."""
    configured = str((config or {}).get("official_pos_log_dir", "") or "").strip()
    candidates = [configured] if configured else []
    candidates.extend(LEGACY_LOG_DIRS)
    for drive in ("D:", "E:"):
        candidates.append(drive + r"\YANGGUOFU-POS\serial")
    seen = set()
    result = []
    for path in candidates:
        lowered = path.lower()
        if lowered not in seen:
            seen.add(lowered)
            result.append(path)
    return result


def find_active_official_log(config=None, max_age_seconds=5.0):
    """Return newest recent serial log, or ``None`` when official POS is idle."""
    candidates = []
    for folder in get_official_log_dirs(config):
        if not os.path.isdir(folder):
            continue
        try:
            for filename in os.listdir(folder):
                if not filename.lower().startswith("log_serial_ports"):
                    continue
                full_path = os.path.join(folder, filename)
                if not os.path.isfile(full_path):
                    continue
                mtime = os.path.getmtime(full_path)
                if time.time() - mtime <= max_age_seconds:
                    candidates.append((mtime, full_path))
        except OSError:
            continue
    return max(candidates, default=(None, None))[1]
