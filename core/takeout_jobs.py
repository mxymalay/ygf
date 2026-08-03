"""Durable, non-financial history for manually processed takeout tickets."""
import hashlib
import json
import os
from datetime import datetime

from config import DATA_DIR


JOB_PATH = os.path.join(DATA_DIR, "takeout_jobs.json")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TakeoutJobStore:
    """Keep a small local history so the operator can distinguish print and reprint.

    These records never enter the sales ledger: an external platform order is
    not a private-POS payment, and mixing them would corrupt turnover reports.
    """

    def __init__(self, path=JOB_PATH):
        self.path = path

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as stream:
                value = json.load(stream)
            return value if isinstance(value, list) else []
        except (OSError, ValueError, TypeError):
            return []

    def _save(self, jobs):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(jobs[:100], stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def make_key(parsed, raw_text):
        platform = str(parsed.get("platform", "外卖订单"))
        full_id = str(parsed.get("full_order_id", "")).strip()
        if full_id:
            return "%s:%s" % (platform, full_id)
        return "text:" + hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()[:24]

    def create_or_get(self, parsed, raw_text):
        jobs = self._load()
        key = self.make_key(parsed, raw_text)
        for job in jobs:
            if job.get("key") == key:
                return job, False
        job = {
            "id": hashlib.sha256((key + _now()).encode("utf-8")).hexdigest()[:16],
            "key": key,
            "created_at": _now(),
            "platform": parsed.get("platform", "外卖订单"),
            "order_no": parsed.get("order_no", "#---"),
            "full_order_id": parsed.get("full_order_id", ""),
            "is_preorder": bool(parsed.get("is_preorder")),
            "printed_at": "",
            "print_count": 0,
            "last_result": "PENDING",
            "last_error": "",
            "raw_text": raw_text,
            "sorted_text": parsed.get("sorted_text", ""),
        }
        jobs.insert(0, job)
        self._save(jobs)
        return job, True

    def get_recent(self, limit=10):
        return self._load()[:max(1, int(limit))]

    def update_print_result(self, job_id, success, copies, error=""):
        jobs = self._load()
        for job in jobs:
            if job.get("id") == job_id:
                job["print_count"] = int(job.get("print_count", 0)) + max(0, int(copies))
                job["printed_at"] = _now()
                job["last_result"] = "PRINTED" if success else "FAILED"
                job["last_error"] = "" if success else str(error or "打印失败")[:300]
                self._save(jobs)
                return job
        return None
