import csv
import os
from datetime import datetime

from config import settings
from common import storage
from mcp_server.tools.pricing import _find_plan

RUNNING = "running"
STOPPED = "stopped"
MAINTENANCE = "maintenance"
DELETED = "deleted"

_STATE_ZH = {
    RUNNING: "運行中",
    STOPPED: "已關機",
    MAINTENANCE: "維護中",
    DELETED: "已刪除",
}

_TRANSITIONS = {
    "start":    ({STOPPED, MAINTENANCE},          RUNNING,     "開機"),
    "stop":     ({RUNNING, MAINTENANCE},          STOPPED,     "關機"),
    "maintain": ({RUNNING, STOPPED},              MAINTENANCE, "進入維護"),
    "delete":   ({RUNNING, STOPPED, MAINTENANCE}, DELETED,     "刪除"),
}

_FIELDS = ["vm_id", "名稱", "方案", "區域", "計畫", "狀態", "建立時間", "更新時間",
           "最後動作", "計費起點", "累計時數", "累計費用"]

_FMT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    return datetime.now().strftime(_FMT)


def _vm_csv(user_id: str) -> str:
    return settings.user_vm_csv(user_id)


def _init_csv(path: str):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_FIELDS)


def _read_vms(user_id: str) -> list:
    path = _vm_csv(user_id)
    _init_csv(path)
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_vms(user_id: str, rows: list):
    path = _vm_csv(user_id)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _FIELDS})


def _next_vm_id(rows: list) -> str:
    max_n = 0
    for r in rows:
        vid = (r.get("vm_id") or "").strip()
        if vid.startswith("vm-") and vid[3:].isdigit():
            max_n = max(max_n, int(vid[3:]))
    return f"vm-{max_n + 1:04d}"


def _find_vm(rows: list, ref: str):
    ref = (ref or "").strip()
    if not ref:
        return None
    for r in rows:
        if (r.get("vm_id") or "").strip() == ref:
            return r
    for r in rows:
        if (r.get("名稱") or "").strip() == ref:
            return r
    for r in rows:
        if (r.get("vm_id") or "").strip().lower() == ref.lower():
            return r
    return None


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _hourly_price(plan_row) -> float:
    if not plan_row:
        return 0.0
    return _f(plan_row.get("價格(小時)"))


def _spec_line(plan_row: dict) -> str:
    gpu = f"GPU:{plan_row['GPU']} " if plan_row.get("GPU") else ""
    price = _hourly_price(plan_row)
    return (f"{gpu}vCPU:{plan_row.get('vCPU') or '—'} | "
            f"記憶體:{plan_row.get('記憶體(GB)') or '—'}GB | "
            f"系統碟:{plan_row.get('系統碟(GB)') or '—'}GB | "
            f"${price:.2f}/小時")


def _accrue(vm: dict) -> float:
    start = (vm.get("計費起點") or "").strip()
    if not start:
        return 0.0
    try:
        dt = datetime.strptime(start, _FMT)
    except ValueError:
        vm["計費起點"] = ""
        return 0.0
    elapsed_h = max(0.0, (datetime.now() - dt).total_seconds() / 3600.0)
    hourly = _hourly_price(_find_plan(vm.get("方案", ""), vm.get("區域")))
    delta = elapsed_h * hourly
    vm["累計時數"] = f"{_f(vm.get('累計時數')) + elapsed_h:.6f}"
    vm["累計費用"] = f"{_f(vm.get('累計費用')) + delta:.6f}"
    vm["計費起點"] = ""
    return delta


def project_snapshot(project_id: str) -> dict:
    from common import projects
    p = projects.get(project_id)
    usage = projects.empty_usage()
    if not p:
        return {"usage": usage, "spent_list": 0.0, "spent_net": 0.0, "vms": []}

    spent_list, spent_net, items = 0.0, 0.0, []
    for uid in p["成員"]:
        for r in _read_vms(uid):
            if (r.get("狀態") or "").strip() == DELETED:
                continue
            if (r.get("計畫") or "").strip().lower() != p["project_id"].lower():
                continue
            region = settings.safe_region(r.get("區域"))
            plan_row = _find_plan(r.get("方案", ""), region)
            projects.add_usage(usage, projects.spec_usage(plan_row))
            _, cost, _ = _current_bill(r)
            disc = settings.discount_rate(region, p["計畫別"])
            spent_list += cost
            spent_net += cost * disc
            items.append({
                "vm_id": r.get("vm_id", ""), "名稱": r.get("名稱", ""),
                "成員": uid, "方案": r.get("方案", ""), "區域": region,
                "狀態": (r.get("狀態") or "").strip(),
                "cost": round(cost, 2), "net": round(cost * disc, 2),
            })
    return {"usage": usage, "spent_list": round(spent_list, 2),
            "spent_net": round(spent_net, 2), "vms": items}


def _current_bill(vm: dict) -> tuple:
    hourly = _hourly_price(_find_plan(vm.get("方案", ""), vm.get("區域")))
    hours = _f(vm.get("累計時數"))
    cost = _f(vm.get("累計費用"))
    start = (vm.get("計費起點") or "").strip()
    if (vm.get("狀態") or "").strip() == RUNNING and start:
        try:
            dt = datetime.strptime(start, _FMT)
            live_h = max(0.0, (datetime.now() - dt).total_seconds() / 3600.0)
            hours += live_h
            cost += live_h * hourly
        except ValueError:
            pass
    return hours, cost, hourly


def create_vm(plan: str, name: str = "", region: str = None,
              user_id: str = "default") -> str:
    region = settings.safe_region(region)
    plan_row = _find_plan(plan, region)
    if not plan_row:
        return (f"在 {settings.REGION_LABELS.get(region, region)} 找不到方案：{plan}，"
                f"請先用 query_pricing 確認該區域可用的方案名稱")
    if _hourly_price(plan_row) <= 0:
        return (f"{plan_row['方案']} 沒有實際規格與價格，無法建立。"
                f"請改用具體方案，可用 query_pricing 查看可建立的方案名稱")

    from common import accounts, projects
    proj = accounts.current_project(user_id)
    want = projects.spec_usage(plan_row)
    if proj:
        snap = project_snapshot(proj["project_id"])
        ok, reason = projects.check_admission(proj, snap["usage"], want)
        if not ok:
            return (f"❌ 無法建立 {plan_row['方案']}（計畫 {proj['project_id']}"
                    f"／{proj['名稱']}）\n{reason}\n"
                    f"提示：可用 get_quota 查看目前額度使用情形、list_vms 看有哪些機器可關閉或刪除")

    with storage.file_lock(_vm_csv(user_id)):
        rows = _read_vms(user_id)
        vm_id = _next_vm_id(rows)
        ts = _now()
        name = (name or "").strip() or vm_id
        rows.append({
            "vm_id": vm_id, "名稱": name, "方案": plan_row["方案"], "區域": region,
            "計畫": proj["project_id"] if proj else "",
            "狀態": RUNNING, "建立時間": ts, "更新時間": ts,
            "最後動作": "建立並開機",
            "計費起點": ts, "累計時數": "0", "累計費用": "0",
        })
        _write_vms(user_id, rows)

    price = _hourly_price(plan_row)
    lines = [
        f"✅ 已建立並開機 VM：{vm_id}（{name}）",
        f"區域：{settings.REGION_LABELS.get(region, region)}",
    ]
    if proj:
        lines.append(f"計畫：{proj['project_id']}（{proj['名稱']}／{proj['類別']}）")
    lines += [
        f"方案：{plan_row['方案']}",
        f"規格：{_spec_line(plan_row)}",
        f"狀態：{_STATE_ZH[RUNNING]}",
        f"計費：開始計費，約 ${price:.2f}/小時（月費約 ${price * 24 * 30:.2f}）",
    ]
    if proj:
        after = project_snapshot(proj["project_id"])["usage"]
        used = "、".join(
            f"{label} {after.get(key, 0):g}/{proj['quota'][key]:g}{unit}"
            for key, label, unit in settings.QUOTA_ITEMS
            if proj["quota"].get(key, 0) > 0)
        if used:
            lines.append(f"計畫額度：{used}")
    lines.append("提示：可用 stop_vm 關機停止計費、get_vm_bill 查目前累計費用、delete_vm 刪除")
    return "\n".join(lines)


def _transition(ref: str, action: str, user_id: str) -> str:
    allowed_from, target, verb = _TRANSITIONS[action]
    settle_delta = 0.0
    with storage.file_lock(_vm_csv(user_id)):
        rows = _read_vms(user_id)
        vm = _find_vm(rows, ref)
        if not vm:
            return f"找不到 VM：{ref}，請用 list_vms 查看現有機器編號"

        cur = (vm.get("狀態") or "").strip()
        if cur == DELETED:
            return f"{vm['vm_id']}（{vm.get('名稱', '')}）已刪除，無法再{verb}"
        if cur == target and action != "delete":
            return (f"{vm['vm_id']}（{vm.get('名稱', '')}）目前已是"
                    f"「{_STATE_ZH[target]}」，無需再{verb}")
        if cur not in allowed_from:
            allow_zh = "、".join(_STATE_ZH[s] for s in allowed_from)
            return (f"無法{verb}：{vm['vm_id']} 目前為「{_STATE_ZH.get(cur, cur)}」，"
                    f"只有「{allow_zh}」狀態的機器可以{verb}")

        if cur == RUNNING:
            settle_delta = _accrue(vm)

        vm["狀態"] = target
        vm["更新時間"] = _now()
        vm["最後動作"] = verb
        if target == RUNNING:
            vm["計費起點"] = _now()

        hours, cost, hourly = _current_bill(vm)
        _write_vms(user_id, rows)

    charged_net, wallet_bal = 0.0, None
    if settle_delta > 0:
        from common import accounts, wallet
        region = settings.safe_region(vm.get("區域"))
        disc = settings.discount_rate(region, accounts.plan_type(user_id))
        charged_net = settle_delta * disc
        try:
            wallet_bal = wallet.record_charge(
                user_id, charged_net,
                f"{vm['vm_id']}（{vm.get('名稱', '')}）{vm.get('方案', '')} 運行費用",
                vm["vm_id"])
        except Exception:
            wallet_bal = None

    msg = f"✅ {vm['vm_id']}（{vm.get('名稱', '')}）已{verb}，狀態：{_STATE_ZH[target]}"
    if action == "stop":
        msg += (f"\n（已停止計費；保留系統碟，可隨時用 start_vm 重新開機。"
                f"目前累計約 {hours:.4f} 小時、${cost:.2f}）")
    elif action == "start":
        msg += f"\n（恢復計費，約 ${hourly:.2f}/小時）"
    elif action == "maintain":
        msg += (f"\n（維護期間暫停對外服務並停止計費，維護完成可用 start_vm 復機。"
                f"目前累計約 ${cost:.2f}）")
    elif action == "delete":
        msg += (f"\n（資源已釋放、停止計費，此操作不可復原。"
                f"本機總用量約 {hours:.4f} 小時、總費用 ${cost:.2f}）")
    if charged_net > 0 and wallet_bal is not None:
        msg += (f"\n（本段運行已從錢包扣抵 ${charged_net:.2f}，"
                f"錢包餘額 ${wallet_bal:.2f}）")
    return msg


def start_vm(vm_id: str, user_id: str = "default") -> str:
    return _transition(vm_id, "start", user_id)


def stop_vm(vm_id: str, user_id: str = "default") -> str:
    return _transition(vm_id, "stop", user_id)


def maintain_vm(vm_id: str, user_id: str = "default") -> str:
    return _transition(vm_id, "maintain", user_id)


def delete_vm(vm_id: str, user_id: str = "default") -> str:
    return _transition(vm_id, "delete", user_id)


def list_vms(include_deleted: bool = False, user_id: str = "default") -> str:
    rows = _read_vms(user_id)
    if not include_deleted:
        rows = [r for r in rows if (r.get("狀態") or "").strip() != DELETED]
    if not rows:
        return "目前沒有任何 VM。可用 create_vm 建立一台（先用 query_pricing 看方案）"

    lines = [f"目前共 {len(rows)} 台 VM："]
    for r in rows:
        state = (r.get("狀態") or "").strip()
        _, cost, _ = _current_bill(r)
        region = settings.safe_region(r.get("區域"))
        lines.append(f"{r['vm_id']} | {r.get('名稱', '')} | {region} | 方案:{r.get('方案', '')} "
                     f"| 狀態:{_STATE_ZH.get(state, state)} | 累計費用:${cost:.2f} "
                     f"| 更新:{r.get('更新時間', '')}")
    return "\n".join(lines)


def get_vm(vm_id: str, user_id: str = "default") -> str:
    rows = _read_vms(user_id)
    vm = _find_vm(rows, vm_id)
    if not vm:
        return f"找不到 VM：{vm_id}，請用 list_vms 查看現有機器編號"

    state = (vm.get("狀態") or "").strip()
    region = settings.safe_region(vm.get("區域"))
    plan_row = _find_plan(vm.get("方案", ""), region)
    hours, cost, hourly = _current_bill(vm)
    lines = [
        f"VM 詳情：{vm['vm_id']}（{vm.get('名稱', '')}）",
        f"區域　：{settings.REGION_LABELS.get(region, region)}",
        f"方案　：{vm.get('方案', '')}",
        f"規格　：{_spec_line(plan_row) if plan_row else '（方案規格已不存在）'}",
        f"狀態　：{_STATE_ZH.get(state, state)}",
        f"建立　：{vm.get('建立時間', '')}",
        f"更新　：{vm.get('更新時間', '')}（{vm.get('最後動作', '')}）",
        f"累計　：運行 {hours:.4f} 小時、費用 ${cost:.2f}",
    ]
    if state == RUNNING:
        lines.append(f"計費　：運行中，約 ${hourly:.2f}/小時（持續累計中）")
    elif state in (STOPPED, MAINTENANCE):
        lines.append("計費　：未運行，目前不計費（累計費用保留）")
    elif state == DELETED:
        lines.append("計費　：已刪除，資源已釋放")
    return "\n".join(lines)


def _discount_lines(list_cost: float, disc: float, pt: str) -> list:
    if disc < 1.0:
        return [f"帳號身分：{pt}（差別費率 {disc*10:.0f} 折）",
                f"牌價費用：${list_cost:.2f}",
                f"實收費用：${list_cost*disc:.2f}"]
    return [f"帳號身分：{pt}（牌價，無折扣）",
            f"累計費用：${list_cost:.2f}"]


def get_vm_bill(vm_id: str, user_id: str = "default") -> str:
    from common import accounts
    rows = _read_vms(user_id)
    vm = _find_vm(rows, vm_id)
    if not vm:
        return f"找不到 VM：{vm_id}，請用 list_vms 查看現有機器編號"
    state = (vm.get("狀態") or "").strip()
    region = settings.safe_region(vm.get("區域"))
    hours, cost, hourly = _current_bill(vm)
    disc = settings.discount_rate(region, accounts.plan_type(user_id))
    running = "（含運行中即時累計）" if state == RUNNING else ""
    lines = [
        f"計費明細：{vm['vm_id']}（{vm.get('名稱', '')}）",
        f"區域　　：{settings.REGION_LABELS.get(region, region)}",
        f"方案時價：${hourly:.2f}/小時",
        f"目前狀態：{_STATE_ZH.get(state, state)}",
        f"累計運行：{hours:.4f} 小時{running}",
    ] + _discount_lines(cost, disc, accounts.plan_type(user_id))
    return "\n".join(lines)


def get_account_bill(user_id: str = "default") -> str:
    from common import accounts, wallet
    rows = _read_vms(user_id)
    pt = accounts.plan_type(user_id)
    if not rows:
        bal = wallet.balance(user_id)
        tail = f"\n錢包餘額：${bal:,.2f}" if bal else ""
        return f"帳號身分：{pt}\n目前沒有任何 VM，總費用為 $0.00{tail}"
    total_list, total_net, total_hours, active = 0.0, 0.0, 0.0, 0
    lines = [f"帳單總覽（帳號身分：{pt}）："]
    for r in rows:
        state = (r.get("狀態") or "").strip()
        region = settings.safe_region(r.get("區域"))
        hours, cost, _ = _current_bill(r)
        disc = settings.discount_rate(region, pt)
        net = cost * disc
        total_list += cost
        total_net += net
        total_hours += hours
        if state == RUNNING:
            active += 1
        tail = f"｜實收 ${net:.2f}（{disc*10:.0f}折）" if disc < 1.0 else ""
        lines.append(f"  {r['vm_id']}（{r.get('名稱', '')}）| {region} "
                     f"| {_STATE_ZH.get(state, state)} | {hours:.4f} 小時 | 牌價 ${cost:.2f}{tail}")
    lines.append("─────────────────────────")
    if total_net < total_list:
        lines.append(f"運行中：{active} 台　總運行：{total_hours:.4f} 小時")
        lines.append(f"牌價總額：${total_list:.2f}　→　實收總額：${total_net:.2f}")
    else:
        lines.append(f"運行中：{active} 台　總運行：{total_hours:.4f} 小時　"
                     f"總費用：${total_list:.2f}（牌價）")

    bal = wallet.balance(user_id)
    proj = wallet_projection(user_id)
    daily, pending = proj["daily_burn"], proj["pending"]
    available = bal - pending
    if pending > 0:
        lines.append(f"錢包餘額：${bal:,.2f}（扣運行中未結算 ${pending:,.2f} → 可用 ${available:,.2f}）")
    else:
        lines.append(f"錢包餘額：${bal:,.2f}")
    if daily > 0:
        if available > 0:
            lines.append(f"每日燃燒 ${daily:,.2f}（實收）→ 預估可用約 {available / daily:.1f} 天")
        else:
            lines.append("⚠ 可用餘額已用罄，請用 top_up_wallet 儲值或關閉不需要的機器")
    return "\n".join(lines)


def _continuous_hours(vm: dict) -> float:
    if (vm.get("狀態") or "").strip() != RUNNING:
        return 0.0
    start = (vm.get("計費起點") or "").strip()
    if not start:
        return 0.0
    try:
        dt = datetime.strptime(start, _FMT)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now() - dt).total_seconds() / 3600.0)


def wallet_projection(user_id: str) -> dict:
    from common import accounts
    rows = _read_vms(user_id)
    pt = accounts.plan_type(user_id)
    daily, pending, running = 0.0, 0.0, 0
    items = []
    for r in rows:
        if (r.get("狀態") or "").strip() != RUNNING:
            continue
        region = settings.safe_region(r.get("區域"))
        hourly = _hourly_price(_find_plan(r.get("方案", ""), region))
        disc = settings.discount_rate(region, pt)
        net_h = hourly * disc
        cont = _continuous_hours(r)
        daily += net_h * 24
        pending += net_h * cont
        running += 1
        items.append({
            "vm_id": r.get("vm_id", ""), "名稱": r.get("名稱", ""),
            "region": region, "方案": r.get("方案", ""),
            "net_hourly": round(net_h, 4), "cont_hours": round(cont, 4),
            "pending": round(net_h * cont, 4),
        })
    return {"daily_burn": round(daily, 4), "pending": round(pending, 4),
            "running": running, "items": items}


def suggest_savings(user_id: str = "default", business_hours: float = 8) -> str:
    from common import accounts
    if business_hours <= 0 or business_hours >= 24:
        business_hours = 8
    rows = _read_vms(user_id)
    pt = accounts.plan_type(user_id)
    running = [r for r in rows if (r.get("狀態") or "").strip() == RUNNING]
    if not running:
        return (f"帳號身分：{pt}\n目前沒有運行中的 VM，沒有正在產生費用的機器可優化。"
                "（已關機／維護中的機器不計費）")

    lines = [f"成本健檢（帳號身分：{pt}；假設每天實際只需 {business_hours:g} 小時）", ""]
    total_now, total_after, total_save = 0.0, 0.0, 0.0
    running.sort(key=_continuous_hours, reverse=True)
    for r in running:
        region = settings.safe_region(r.get("區域"))
        hourly = _hourly_price(_find_plan(r.get("方案", ""), region))
        disc = settings.discount_rate(region, pt)
        net_hourly = hourly * disc
        month_now = net_hourly * 24 * 30
        month_after = net_hourly * business_hours * 30
        save = month_now - month_after
        total_now += month_now
        total_after += month_after
        total_save += save
        cont = _continuous_hours(r)
        flag = "　⚠ 已連續運行 %.0f 小時，建議評估是否需要 24h 運轉" % cont if cont >= 24 else ""
        lines.append(f"{r['vm_id']}（{r.get('名稱', '')}）| {region} | {r.get('方案', '')} "
                     f"| ${net_hourly:.2f}/h（實收）")
        lines.append(f"　現況 24h 月費 ${month_now:.2f} → 每天 {business_hours:g}h 月費 "
                     f"${month_after:.2f}　→ 月省 ${save:.2f}{flag}")
    lines.append("─────────────────────────")
    lines.append(f"若全部改為每天 {business_hours:g} 小時運行：每月合計最多可省 "
                 f"${total_save:.2f}（{total_now:.2f} → {total_after:.2f}）")
    lines.append("註：使用率以「連續運行時數」為近似訊號；接實體環境後改用真實 "
                 "CPU/GPU 使用率可更精準判斷閒置。可用 stop_vm 手動關機，或評估排程關機。")
    return "\n".join(lines)


def account_summary(user_id: str) -> dict:
    from common import accounts
    rows = _read_vms(user_id)
    prof = accounts.get_profile(user_id)
    pt = prof["plan_type"]
    vms, total_list, total_net, running = [], 0.0, 0.0, 0
    for r in rows:
        state = (r.get("狀態") or "").strip()
        region = settings.safe_region(r.get("區域"))
        hours, cost, hourly = _current_bill(r)
        disc = settings.discount_rate(region, pt)
        total_list += cost
        total_net += cost * disc
        if state == RUNNING:
            running += 1
        vms.append({
            "vm_id": r.get("vm_id", ""), "名稱": r.get("名稱", ""),
            "方案": r.get("方案", ""), "區域": region,
            "狀態": state, "狀態中文": _STATE_ZH.get(state, state),
            "hours": round(hours, 4), "cost": round(cost, 2),
            "net": round(cost * disc, 2), "hourly": round(hourly, 2),
            "更新時間": r.get("更新時間", ""),
        })
    return {
        "user_id": user_id,
        "plan_type": pt,
        "plan_source": prof["plan_source"],
        "project_id": prof["project_id"],
        "project_name": prof["project_name"],
        "vm_count": len([v for v in vms if v["狀態"] != DELETED]),
        "running": running,
        "total_cost": round(total_list, 2),
        "total_net": round(total_net, 2),
        "vms": vms,
    }
