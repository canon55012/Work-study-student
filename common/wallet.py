"""錢包（Wallet)"""
from datetime import datetime

from config import settings
from common import storage

_FMT = "%Y-%m-%d %H:%M:%S"
TOP_UP = "儲值"
CHARGE = "扣抵"


def _path(user_id: str) -> str:
    return str(settings.user_dir(user_id) / "wallet.jsonl")


def _now() -> str:
    return datetime.now().strftime(_FMT)


def history(user_id: str, limit: int = None) -> list:
    return storage.read_jsonl(_path(user_id), limit)


def balance(user_id: str) -> float:
    total = 0.0
    for t in storage.read_jsonl(_path(user_id)):
        try:
            total += float(t.get("金額") or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 4)


def add_funds(user_id: str, amount: float, note: str = "儲值") -> float:
    try:
        amt = round(float(amount), 4)
    except (TypeError, ValueError):
        return balance(user_id)
    if amt <= 0:
        return balance(user_id)
    storage.append_jsonl(_path(user_id), {
        "時間": _now(), "類型": TOP_UP, "金額": amt, "說明": note, "vm_id": "",
    })
    return balance(user_id)


def record_charge(user_id: str, amount: float, note: str = "", vm_id: str = "") -> float:
    try:
        amt = round(float(amount), 4)
    except (TypeError, ValueError):
        return balance(user_id)
    if amt <= 0:
        return balance(user_id)
    storage.append_jsonl(_path(user_id), {
        "時間": _now(), "類型": CHARGE, "金額": -amt, "說明": note, "vm_id": vm_id,
    })
    return balance(user_id)
