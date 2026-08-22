import csv
import os
from datetime import datetime

from config import settings
from common import storage

HEADER = ["時間", "供應商", "模型", "輸入tokens", "輸出tokens",
          "耗時ms", "負載類型", "使用者"]

IN_BUCKETS = (("短", 0, 512), ("中", 512, 1536), ("長", 1536, float("inf")))
OUT_BUCKETS = (("短", 0, 64), ("中", 64, 384), ("長", 384, float("inf")))


def bucket(in_tok: int, out_tok: int) -> str:
    def pick(n, buckets):
        for name, lo, hi in buckets:
            if lo <= n < hi:
                return name
        return buckets[-1][0]
    return f"{pick(in_tok or 0, IN_BUCKETS)}輸入/{pick(out_tok or 0, OUT_BUCKETS)}輸出"


def _init(path: str):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)


def record(provider: str, model: str, in_tok, out_tok,
           elapsed_ms: float = 0.0, user_id: str = "") -> None:
    try:
        path = settings.WORKLOAD_CSV
        i, o = int(in_tok or 0), int(out_tok or 0)
        row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), provider or "", model or "",
               i, o, round(float(elapsed_ms or 0), 1), bucket(i, o), user_id or ""]
        with storage.file_lock(path):
            _init(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(row)
    except Exception:
        pass


def rows() -> list:
    path = settings.WORKLOAD_CSV
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _num(r, key):
    try:
        return int(float(r.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def distribution() -> dict:
    rs = rows()
    total = len(rs)
    out = {}
    unknown = 0
    for r in rs:
        i, o = _num(r, "輸入tokens"), _num(r, "輸出tokens")
        if i == 0 and o == 0:
            unknown += 1
            continue
        label = r.get("負載類型") or bucket(i, o)
        b = out.setdefault(label, {"n": 0, "in_sum": 0, "out_sum": 0})
        b["n"] += 1
        b["in_sum"] += i
        b["out_sum"] += o
    counted = sum(b["n"] for b in out.values())
    for b in out.values():
        b["ratio"] = b["n"] / counted if counted else 0.0
        b["in_avg"] = b["in_sum"] / b["n"] if b["n"] else 0
        b["out_avg"] = b["out_sum"] / b["n"] if b["n"] else 0
    return {"total": total, "counted": counted, "unknown": unknown, "buckets": out}
