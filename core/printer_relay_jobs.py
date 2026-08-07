"""Durable, non-financial history for printer-relay tickets."""
import hashlib
import json
import os
from datetime import datetime

from config import DATA_DIR


JOB_PATH = os.path.join(DATA_DIR, "printer_relay_jobs.json")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class PrinterRelayJobStore:
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
        # A reprint often changes the print timestamp or ESC/POS control
        # bytes.  Use stable order content before falling back to the exact
        # raw hash, and expose the confidence to the UI/audit log.
        order_no = str(parsed.get("order_no", "")).strip()
        order_time = str(parsed.get("order_time", "")).strip()
        amount = parsed.get("order_amount")
        item_names = parsed.get("item_names") or []
        stable = "|".join(
            [platform, order_no, order_time, "" if amount is None else "%.2f" % float(amount),
             ",".join(str(item) for item in item_names)]
        ).strip("|")
        if order_no and order_time and item_names:
            return "stable:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
        return "text:" + hashlib.sha256(raw_text.strip().encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def key_confidence(parsed):
        return "high" if str(parsed.get("full_order_id", "")).strip() else (
            "medium" if parsed.get("order_no") and parsed.get("order_time") and parsed.get("item_names") else "low"
        )

    def create_or_get(self, parsed, raw_text):
        jobs = self._load()
        key = self.make_key(parsed, raw_text)
        for job in jobs:
            if job.get("key") == key:
                old_amount = job.get("order_amount")
                new_amount = parsed.get("order_amount")
                old_status = job.get("payment_status", "unknown")
                new_status = parsed.get("payment_status", "unknown")
                try:
                    amount_changed = old_amount is not None and new_amount is not None and abs(float(old_amount) - float(new_amount)) > 0.01
                except (TypeError, ValueError):
                    amount_changed = old_amount != new_amount
                status_changed = old_status != new_status and new_status != "unknown"
                # An initial print may carry only an amount.  A later final
                # receipt that explicitly says paid/cancelled is a valid
                # state transition, not a conflict; paid->cancelled or a
                # changed final amount remains suspicious and is quarantined.
                state_transition = old_status == "unknown" and new_status in ("paid", "cancelled")
                if amount_changed or (status_changed and not state_transition):
                    job["conflict_detected"] = True
                    job["last_error"] = "同一订单的补打/重试出现金额或状态变化，未重复计算分流"
                    self._save(jobs)
                elif state_transition:
                    job["payment_status"] = new_status
                    job["payment_status_confidence"] = parsed.get("payment_status_confidence", "unknown")
                    if old_amount is None and new_amount is not None:
                        job["order_amount"] = new_amount
                        job["amount_valid"] = bool(parsed.get("amount_valid"))
                    self._save(jobs)
                return job, False
        job = {
            "id": hashlib.sha256((key + _now()).encode("utf-8")).hexdigest()[:16],
            "key": key,
            "created_at": _now(),
            "platform": parsed.get("platform", "外卖订单"),
            "order_no": parsed.get("order_no", "#---"),
            "full_order_id": parsed.get("full_order_id", ""),
            "order_amount": parsed.get("order_amount"),
            "amount_valid": bool(parsed.get("amount_valid")),
            "payment_status": parsed.get("payment_status", "unknown"),
            "payment_status_confidence": parsed.get("payment_status_confidence", "unknown"),
            "key_confidence": self.key_confidence(parsed),
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

    def get_verified_amount_total(self, day=None):
        """Sum only unique relay jobs with validated amount and paid evidence."""
        return self.get_verified_summary(day, day).get("amount_sum", 0.0)

    def get_verified_summary(self, start_day=None, end_day=None):
        """Return unique, verified official-POS totals for an inclusive date range.

        Only records with a validated amount *and explicit paid evidence* are
        included.  Unknown-payment and parse-failed relay jobs deliberately do
        not contribute to turnover reports.
        """
        start = str(start_day or datetime.now().strftime("%Y-%m-%d"))[:10]
        end = str(end_day or start)[:10]
        if start > end:
            start, end = end, start
        total = 0.0
        count = 0
        for job in self._load():
            created_day = str(job.get("created_at", ""))[:10]
            if not (start <= created_day <= end):
                continue
            if job.get("amount_valid") is not True or job.get("payment_status") != "paid":
                continue
            try:
                total += max(0.0, float(job.get("order_amount") or 0.0))
                count += 1
            except (TypeError, ValueError):
                continue
        return {"count": count, "amount_sum": round(total, 2)}

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
