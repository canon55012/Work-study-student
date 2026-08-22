from common import accounts, projects
from config import settings
from mcp_server.tools.vm_lifecycle import project_snapshot

_BAR_WIDTH = 10


def _bar(ratio: float) -> str:
    filled = max(0, min(_BAR_WIDTH, int(round(ratio * _BAR_WIDTH))))
    return "█" * filled + "░" * (_BAR_WIDTH - filled)


def _quota_summary(project: dict, usage: dict) -> str:
    parts = []
    for key, label, unit in settings.QUOTA_ITEMS:
        limit = project["quota"].get(key, 0.0)
        if limit > 0:
            parts.append(f"{label} {usage.get(key, 0.0):g}/{limit:g}{unit}")
    return "、".join(parts) if parts else "未設額度上限"


def _discount_note(project: dict) -> str:
    pt = project["計畫別"]
    bits = []
    for region in settings.REGIONS:
        d = settings.discount_rate(region, pt)
        bits.append(f"{region} {'牌價' if d >= 1.0 else f'{d * 10:.0f} 折'}")
    return f"計畫別 {pt}（{'、'.join(bits)}）"


def _accessible(project_id: str, user_id: str):
    p = projects.get(project_id)
    if not p:
        return None, (f"找不到計畫：{project_id}。可用 list_projects 查看你參與的計畫編號")
    if not projects.is_member(p, user_id):
        return None, (f"你不是計畫 {p['project_id']} 的成員，無法查看其額度與資源。"
                      f"可用 list_projects 查看你參與的計畫")
    return p, ""


def list_projects(user_id: str = "default") -> str:
    mine = projects.for_user(user_id)
    if not mine:
        return ("你目前沒有參與任何計畫（以個人身分使用，適用牌價、不受計畫額度限制）。\n"
                "真實環境中計畫需經申請與核定；可用 search_faq 問「計畫要怎麼申請」了解流程。")

    cur = accounts.current_project(user_id)
    cur_id = cur["project_id"] if cur else ""
    lines = [f"我的計畫（共 {len(mine)} 個；★ 為目前使用中）"]
    for p in mine:
        snap = project_snapshot(p["project_id"])
        mark = "★" if p["project_id"] == cur_id else "　"
        state = p["狀態"] if projects.is_active(p) else f"{p['狀態']}（無法開立新資源）"
        lines.append("")
        lines.append(f"{mark} {p['project_id']}｜{p['名稱']}")
        lines.append(f"   類別：{p['類別']}｜{_discount_note(p)}")
        lines.append(f"   狀態：{state}｜期間 {p['起始日']} ~ {p['結束日']}"
                     f"｜管理者 {p['管理者']}｜成員 {len(p['成員'])} 人")
        lines.append(f"   核定額度：${p['核定額度']:,.0f}　已用（實收）：${snap['spent_net']:,.2f}")
        lines.append(f"   額度使用：{_quota_summary(p, snap['usage'])}")
    lines.append("")
    lines.append("提示：可用 get_quota 看單一計畫的詳細額度與警示、get_project 看計畫下的資源明細")
    return "\n".join(lines)


def get_project(project_id: str = "", user_id: str = "default") -> str:
    if not (project_id or "").strip():
        cur = accounts.current_project(user_id)
        if not cur:
            return ("你目前沒有參與任何計畫。可用 list_projects 確認，"
                    "或用 search_faq 問「計畫要怎麼申請」。")
        p = cur
    else:
        p, err = _accessible(project_id, user_id)
        if not p:
            return err

    snap = project_snapshot(p["project_id"])
    lines = [
        f"計畫詳情：{p['project_id']}（{p['名稱']}）",
        f"類別　　：{p['類別']}｜{_discount_note(p)}",
        f"狀態　　：{p['狀態']}" + ("" if projects.is_active(p) else "（無法開立新資源）"),
        f"期間　　：{p['起始日']} ~ {p['結束日']}",
        f"管理者　：{p['管理者']}｜成員（{len(p['成員'])} 人）：{'、'.join(p['成員'])}",
        f"核定額度：${p['核定額度']:,.0f}",
        f"已用金額：牌價 ${snap['spent_list']:,.2f} → 實收 ${snap['spent_net']:,.2f}"
        f"（依計畫類別折扣）",
        f"額度使用：{_quota_summary(p, snap['usage'])}",
    ]
    if p["核定額度"] > 0:
        remain = p["核定額度"] - snap["spent_net"]
        lines.append(f"核定餘額：${remain:,.2f}"
                     + ("　已超出核定額度" if remain < 0 else ""))
    lines.append("")
    if snap["vms"]:
        lines.append(f"計畫底下的資源（{len(snap['vms'])} 台，已刪除者不列入）：")
        for v in snap["vms"]:
            lines.append(f"  {v['vm_id']}（{v['名稱']}）| 成員 {v['成員']} | {v['區域']} "
                         f"| {v['方案']} | {v['狀態']} | 實收 ${v['net']:,.2f}")
    else:
        lines.append("計畫底下目前沒有任何資源。")
    lines.append("提示：可用 get_quota 看各項額度剩餘與警示")
    return "\n".join(lines)


def get_quota(project_id: str = "", user_id: str = "default") -> str:
    if not (project_id or "").strip():
        cur = accounts.current_project(user_id)
        if not cur:
            return ("你目前沒有參與任何計畫，因此不受計畫額度限制（以個人身分使用、適用牌價）。\n"
                    "費用面仍以錢包餘額為準，可用 get_wallet_balance 查詢。")
        p = cur
    else:
        p, err = _accessible(project_id, user_id)
        if not p:
            return err

    snap = project_snapshot(p["project_id"])
    rows = projects.quota_lines(p, snap["usage"])

    lines = [
        f"計畫額度：{p['project_id']}（{p['名稱']}）",
        f"類別：{p['類別']}｜狀態：{p['狀態']}"
        + ("" if projects.is_active(p) else "（無法開立新資源）"),
        "",
    ]
    for r in rows:
        if r["unlimited"]:
            lines.append(f"{r['label']}　未設上限（已用 {r['used']:g}{r['unit']}）")
            continue
        flag = ""
        if r["exhausted"]:
            flag = "　已用罄"
        elif r["warn"]:
            flag = "　即將用罄"
        lines.append(f"{r['label']}　[{_bar(r['ratio'])}] {r['ratio'] * 100:.0f}%"
                     f"　已用 {r['used']:g} / 核定 {r['limit']:g}{r['unit']}"
                     f"　剩餘 {r['remain']:g}{r['unit']}{flag}")

    if p["核定額度"] > 0:
        remain = p["核定額度"] - snap["spent_net"]
        ratio = min(1.0, max(0.0, snap["spent_net"] / p["核定額度"]))
        flag = "　已超出核定額度" if remain < 0 else (
            "　核定額度即將用罄" if ratio >= settings.QUOTA_WARN_RATIO else "")
        lines.append(f"核定金額　[{_bar(ratio)}] {ratio * 100:.0f}%"
                     f"　已用 ${snap['spent_net']:,.2f} / ${p['核定額度']:,.0f}"
                     f"　剩餘 ${remain:,.2f}{flag}")

    exhausted = [r["label"] for r in rows if r["exhausted"]]
    warn = [r["label"] for r in rows if r["warn"] and not r["exhausted"]]
    lines.append("─────────────────────────")
    if exhausted:
        lines.append(f"已用罄：{'、'.join(exhausted)}——無法再開立新資源。"
                     f"請關閉並刪除不需要的機器，或向計畫管理者（{p['管理者']}）申請調高額度。")
    if warn:
        lines.append(f"即將用罄（達 {settings.QUOTA_WARN_RATIO * 100:.0f}%）：{'、'.join(warn)}"
                     f"——建議提前規劃或申請加額。")
    if not exhausted and not warn:
        lines.append("目前各項額度均充足。")
    lines.append("註：已關機／維護中的機器仍佔用額度（資源仍配置著），刪除才會釋放；"
                 "計費則只算 running 時間。")
    return "\n".join(lines)
