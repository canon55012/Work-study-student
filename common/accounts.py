import json
import os

from config import settings
from common import projects, storage

PLAN_SOURCE_PROJECT = "project"
PLAN_SOURCE_SELF = "self"


def _path(user_id: str) -> str:
    return str(settings.user_dir(user_id) / "profile.json")


def _read(user_id: str) -> dict:
    try:
        with open(_path(user_id), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(user_id: str, data: dict):
    path = _path(user_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with storage.file_lock(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


def current_project(user_id: str) -> dict:
    mine = projects.for_user(user_id)
    if not mine:
        return None
    pid = str(_read(user_id).get("project_id") or "").strip().lower()
    if pid:
        for p in mine:
            if p["project_id"].lower() == pid:
                return p
    return mine[0]


def set_current_project(user_id: str, project_id: str) -> tuple:
    p = projects.get(project_id)
    if not p:
        return False, f"找不到計畫：{project_id}"
    if not projects.is_member(p, user_id):
        return False, f"你不是計畫 {p['project_id']}（{p['名稱']}）的成員，無法使用其資源與額度"
    data = _read(user_id)
    data["project_id"] = p["project_id"]
    _write(user_id, data)
    return True, p


def get_profile(user_id: str) -> dict:
    proj = current_project(user_id)
    if proj:
        return {
            "user_id": user_id,
            "plan_type": proj["計畫別"],
            "plan_source": PLAN_SOURCE_PROJECT,
            "project_id": proj["project_id"],
            "project_name": proj["名稱"],
            "project_category": proj["類別"],
            "project_status": proj["狀態"],
        }
    pt = _read(user_id).get("plan_type")
    if pt not in settings.PLAN_TYPES:
        pt = settings.DEFAULT_PLAN_TYPE
    return {
        "user_id": user_id,
        "plan_type": pt,
        "plan_source": PLAN_SOURCE_SELF,
        "project_id": "",
        "project_name": "",
        "project_category": "",
        "project_status": "",
    }


def set_profile(user_id: str, plan_type: str) -> dict:
    pt = plan_type if plan_type in settings.PLAN_TYPES else settings.DEFAULT_PLAN_TYPE
    data = _read(user_id)
    data["plan_type"] = pt
    _write(user_id, data)
    return get_profile(user_id)


def plan_type(user_id: str) -> str:
    return get_profile(user_id)["plan_type"]


def discount_for(user_id: str, region: str) -> float:
    return settings.discount_rate(region, plan_type(user_id))
