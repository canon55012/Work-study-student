import csv
import os
import re

from config import settings


def _f(v, default: float = 0.0) -> float:
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return default


def _rows() -> list:
    path = settings.PROJECTS_CSV
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _norm(row: dict) -> dict:
    code = (row.get("類別代碼") or "").strip().upper()
    members = [m.strip() for m in (row.get("成員") or "").split(",") if m.strip()]
    return {
        "project_id": (row.get("project_id") or "").strip(),
        "名稱": (row.get("計畫名稱") or "").strip(),
        "類別代碼": code,
        "類別": settings.PROJECT_CATEGORY_LABELS.get(code, code or "—"),
        "計畫別": settings.PROJECT_CATEGORIES.get(code, settings.DEFAULT_PLAN_TYPE),
        "狀態": (row.get("狀態") or "").strip() or settings.PROJECT_ACTIVE,
        "核定額度": _f(row.get("核定額度")),
        "起始日": (row.get("起始日") or "").strip(),
        "結束日": (row.get("結束日") or "").strip(),
        "管理者": (row.get("管理者") or "").strip(),
        "成員": members,
        "quota": {key: _f(row.get("quota_" + key)) for key, _, _ in settings.QUOTA_ITEMS},
    }


def all_projects() -> list:
    return [_norm(r) for r in _rows() if (r.get("project_id") or "").strip()]


def get(project_id: str) -> dict:
    pid = (project_id or "").strip().lower()
    if not pid:
        return None
    for p in all_projects():
        if p["project_id"].lower() == pid:
            return p
    return None


def for_user(user_id: str) -> list:
    uid = settings.safe_user(user_id)
    mine = [p for p in all_projects() if uid in p["成員"]]
    mine.sort(key=lambda p: not is_active(p))
    return mine


def is_active(project: dict) -> bool:
    return bool(project) and project.get("狀態") == settings.PROJECT_ACTIVE


def is_member(project: dict, user_id: str) -> bool:
    return bool(project) and settings.safe_user(user_id) in project.get("成員", [])


def gpu_count(gpu_field: str) -> float:
    m = re.search(r"\*\s*(\d+(?:\.\d+)?)", gpu_field or "")
    if m:
        return float(m.group(1))
    return 1.0 if (gpu_field or "").strip() else 0.0


def spec_usage(plan_row: dict) -> dict:
    if not plan_row:
        return {key: (1.0 if key == "vm" else 0.0) for key, _, _ in settings.QUOTA_ITEMS}
    return {
        "gpu": gpu_count(plan_row.get("GPU")),
        "vcpu": _f(plan_row.get("vCPU")),
        "memory_gb": _f(plan_row.get("記憶體(GB)")),
        "storage_gb": _f(plan_row.get("系統碟(GB)")),
        "vm": 1.0,
    }


def empty_usage() -> dict:
    return {key: 0.0 for key, _, _ in settings.QUOTA_ITEMS}


def add_usage(total: dict, one: dict) -> dict:
    for key in total:
        total[key] = round(total[key] + one.get(key, 0.0), 4)
    return total


def quota_lines(project: dict, usage: dict) -> list:
    out = []
    for key, label, unit in settings.QUOTA_ITEMS:
        limit = project["quota"].get(key, 0.0)
        used = usage.get(key, 0.0)
        unlimited = limit <= 0
        remain = None if unlimited else round(limit - used, 4)
        ratio = None if unlimited else (used / limit if limit else 0.0)
        out.append({
            "key": key, "label": label, "unit": unit,
            "limit": limit, "used": used, "remain": remain,
            "unlimited": unlimited, "ratio": ratio,
            "exhausted": (not unlimited) and remain is not None and remain <= 0,
            "warn": (not unlimited) and ratio is not None
                    and ratio >= settings.QUOTA_WARN_RATIO,
        })
    return out


def check_admission(project: dict, usage: dict, want: dict) -> tuple:
    if not is_active(project):
        return False, (f"計畫 {project['project_id']}（{project['名稱']}）目前狀態為"
                       f"「{project['狀態']}」，無法開立新資源。請先確認計畫是否已到期或需續用。")
    for key, label, unit in settings.QUOTA_ITEMS:
        limit = project["quota"].get(key, 0.0)
        if limit <= 0:
            continue
        used = usage.get(key, 0.0)
        need = want.get(key, 0.0)
        if used + need > limit + 1e-9:
            return False, (f"計畫 Quota 不足：{label} 核定 {limit:g}{unit}、"
                           f"已用 {used:g}{unit}、本次需要 {need:g}{unit}，"
                           f"剩餘 {limit - used:g}{unit} 不夠。"
                           f"可先關閉／刪除不需要的資源，或向計畫管理者申請調高額度。")
    return True, ""
