import csv
import os
from datetime import datetime

from config import settings
from common import storage

_HEADER = ["時間", "查詢類型", "關鍵字", "選擇方案", "備註",
           "輸入tokens", "輸出tokens", "負載類型"]
_OLD_HEADER = ["時間", "查詢類型", "關鍵字", "選擇方案", "備註"]


def _history_csv(user_id: str) -> str:
    return settings.user_history_csv(user_id)


def _init_csv(path: str):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_HEADER)


def _read_rows(user_id: str) -> list:
    path = _history_csv(user_id)
    _init_csv(path)
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for col in _HEADER:
            r.setdefault(col, "")
            if r.get(col) is None:
                r[col] = ""
    return rows


def log_query(query_type: str, keyword: str = "", selected_plan: str = "",
              note: str = "", user_id: str = "default") -> str:
    from agent import providers
    from common import workload

    in_tok, out_tok = getattr(providers, "LAST_USAGE", (0, 0)) or (0, 0)
    label = workload.bucket(in_tok, out_tok) if (in_tok or out_tok) else ""

    path = _history_csv(user_id)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with storage.file_lock(path):
        _init_csv(path)
        _migrate_header(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([timestamp, query_type, keyword, selected_plan,
                                    note, in_tok, out_tok, label])
    return f"已記錄：{query_type} | {keyword} | {selected_plan}"


def _migrate_header(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            rows = list(csv.reader(f))
    except Exception:
        return
    if not rows or rows[0] == _HEADER:
        return
    if rows[0] != _OLD_HEADER:
        return
    pad = [""] * (len(_HEADER) - len(_OLD_HEADER))
    out = [_HEADER] + [r + pad[:max(0, len(_HEADER) - len(r))] for r in rows[1:]]
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)


def get_user_history(limit: int = 10, user_id: str = "default") -> str:
    rows = _read_rows(user_id)
    if not rows:
        return "尚無查詢記錄"
    recent = rows[-limit:]
    lines = [f"{r['時間']} | {r['查詢類型']} | 關鍵字:{r['關鍵字']} | 方案:{r['選擇方案']}"
             for r in recent]
    return "\n".join(lines)


def get_recommendations(user_id: str = "default") -> str:
    rows = _read_rows(user_id)
    if not rows:
        return "尚無歷史記錄，無法推薦，請先進行幾次查詢"
    keyword_count, plan_count = {}, {}
    for r in rows:
        kw, plan = r["關鍵字"], r["選擇方案"]
        if kw:
            keyword_count[kw] = keyword_count.get(kw, 0) + 1
        if plan:
            plan_count[plan] = plan_count.get(plan, 0) + 1
    lines = ["根據您的使用記錄："]
    if keyword_count:
        top_kw = sorted(keyword_count.items(), key=lambda x: -x[1])[:3]
        lines.append(f"最常查詢：{', '.join([k for k, v in top_kw])}")
    if plan_count:
        top_plan = sorted(plan_count.items(), key=lambda x: -x[1])[:3]
        lines.append(f"最常選擇：{', '.join([p for p, v in top_plan])}")
        lines.append(f"建議下次直接考慮：{top_plan[0][0]}")
    return "\n".join(lines)


def _statistical_summary(rows: list) -> str:
    keyword_count, plan_count = {}, {}
    for r in rows:
        if r["關鍵字"]:
            keyword_count[r["關鍵字"]] = keyword_count.get(r["關鍵字"], 0) + 1
        if r["選擇方案"]:
            plan_count[r["選擇方案"]] = plan_count.get(r["選擇方案"], 0) + 1
    lines = ["根據您的歷史記錄統計："]
    if keyword_count:
        top = sorted(keyword_count.items(), key=lambda x: -x[1])[:2]
        lines.append(f"您最常查詢：{', '.join([k for k, v in top])}")
    if plan_count:
        top = sorted(plan_count.items(), key=lambda x: -x[1])[:1]
        lines.append(f"您最常選擇：{top[0][0]}，建議下次可直接從此方案開始評估")
    return "\n".join(lines)


def analyze_usage(user_id: str = "default") -> str:
    rows = _read_rows(user_id)
    if not rows:
        return "尚無歷史記錄，無法分析，請先進行幾次查詢"

    data_text = "\n".join(
        f"{r['時間']} | {r['查詢類型']} | 關鍵字:{r['關鍵字']} | 選擇:{r['選擇方案']}"
        for r in rows
    )
    prompt = f"""以下是使用者的查詢歷史：

{data_text}

請分析：
1. 使用者最常需要什麼類型的資源
2. 需求趨勢（是否有升級或降級的傾向）
3. 給一個具體的個人化建議

請用繁體中文回答，簡潔清楚。"""

    from agent import providers
    text = providers.generate(prompt)
    return text if text else _statistical_summary(rows)
