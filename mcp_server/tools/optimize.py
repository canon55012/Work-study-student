import math
import os
import time

from config import settings

LAST_STATS = {}

MILP_STATS = {}

_MAX_MACHINES = 24
_MAX_NODES = 400_000
_MAX_DISK_GB = 100_000

_MIX_MIN_SAVING = 0.03


def _candidate_plans(region: str, need_gpu: bool, user_id: str) -> list:
    from mcp_server.tools.pricing import _load_plans
    from common import accounts

    pt = accounts.plan_type(user_id)
    disc = settings.discount_rate(region, pt)

    plans = []
    for row in _load_plans(region).values():
        if (row.get("類型") or "") == "K8S":
            continue
        try:
            hourly = float(row.get("價格(小時)") or 0)
        except ValueError:
            continue
        if hourly <= 0:
            continue

        gpu_txt = (row.get("GPU") or "").strip()
        gpu_n = _gpu_count(gpu_txt)
        if not need_gpu and gpu_n > 0:
            continue

        try:
            vcpu = int(row.get("vCPU") or 0)
            mem = int(row.get("記憶體(GB)") or 0)
        except ValueError:
            continue
        try:
            disk = int(row.get("系統碟(GB)") or 0)
        except ValueError:
            disk = 0

        plans.append({
            "方案": row["方案"],
            "vcpu": vcpu,
            "mem": mem,
            "gpu": gpu_n,
            "gpu_txt": gpu_txt,
            "disk": disk,
            "牌價": hourly,
            "單價": hourly * disc,
        })
    return plans, pt, disc


def _disk_rate_hourly(region: str, user_id: str, disk_type: str = "SSD") -> float:
    from common import accounts

    rate_month = settings.disk_rate(region, disk_type)
    if rate_month <= 0:
        return 0.0
    if settings.storage_discount_applies(region):
        rate_month *= settings.discount_rate(region, accounts.plan_type(user_id))
    return rate_month / (24 * 30)


def _gpu_count(gpu_txt: str) -> int:
    if not gpu_txt:
        return 0
    if "*" in gpu_txt:
        try:
            return int(gpu_txt.split("*")[-1].strip())
        except ValueError:
            return 1
    return 1


def _solve(plans: list, need_vcpu: int, need_mem: int, need_gpu: int,
           budget_hours: float, budget: float, max_machines: int = _MAX_MACHINES,
           need_disk: int = 0, disk_rate_h: float = 0.0):
    disk_cost = disk_rate_h * need_disk if need_disk > 0 else 0.0
    eff_vcpu = max((p["vcpu"] / p["單價"] for p in plans if p["vcpu"] > 0), default=0)
    eff_mem = max((p["mem"] / p["單價"] for p in plans if p["mem"] > 0), default=0)
    eff_gpu = max((p["gpu"] / p["單價"] for p in plans if p["gpu"] > 0), default=0)

    def lower_bound(v, m, g) -> float:
        lbs = [0.0]
        if v > 0:
            lbs.append(v / eff_vcpu if eff_vcpu > 0 else math.inf)
        if m > 0:
            lbs.append(m / eff_mem if eff_mem > 0 else math.inf)
        if g > 0:
            lbs.append(g / eff_gpu if eff_gpu > 0 else math.inf)
        return max(lbs)

    order = sorted(plans, key=lambda p: -(p["vcpu"] + p["mem"] / 4 + p["gpu"] * 32) / p["單價"])

    cap = math.inf
    if budget and budget > 0 and budget_hours > 0:
        cap = budget / budget_hours - disk_cost

    best = {"cost": math.inf, "combo": None}
    nodes = {"n": 0}
    exhausted = {"v": True}

    def dfs(i, v, m, g, cost, machines, combo):
        nodes["n"] += 1
        if nodes["n"] > _MAX_NODES:
            exhausted["v"] = False
            return
        if v <= 0 and m <= 0 and g <= 0:
            if cost < best["cost"]:
                best["cost"] = cost
                best["combo"] = dict(combo)
            return
        if i >= len(order) or machines >= max_machines:
            return
        if cost + lower_bound(v, m, g) >= min(best["cost"], cap + 1e-9):
            return

        p = order[i]
        caps = []
        if v > 0 and p["vcpu"] > 0:
            caps.append(math.ceil(v / p["vcpu"]))
        if m > 0 and p["mem"] > 0:
            caps.append(math.ceil(m / p["mem"]))
        if g > 0 and p["gpu"] > 0:
            caps.append(math.ceil(g / p["gpu"]))
        max_k = min(max(caps) if caps else 0, max_machines - machines)

        for k in range(max_k, -1, -1):
            new_cost = cost + k * p["單價"]
            if new_cost >= min(best["cost"], cap + 1e-9):
                continue
            if k:
                combo[p["方案"]] = k
            dfs(i + 1,
                v - k * p["vcpu"], m - k * p["mem"], g - k * p["gpu"],
                new_cost, machines + k, combo)
            if k:
                combo.pop(p["方案"], None)

    t0 = time.perf_counter()
    dfs(0, need_vcpu, need_mem, need_gpu, 0.0, 0, {})
    LAST_STATS.clear()
    LAST_STATS.update({
        "nodes": nodes["n"],
        "plans": len(order),
        "max_machines": max_machines,
        "elapsed_ms": (time.perf_counter() - t0) * 1000,
        "exhausted": exhausted["v"],
        "best_cost": best["cost"],
        "disk_cost": disk_cost,
    })
    if best["combo"] is None:
        return best["cost"], None, exhausted["v"], 0.0
    return best["cost"] + disk_cost, best["combo"], exhausted["v"], float(need_disk)


def to_milp(plans: list, need_vcpu: int, need_mem: int, need_gpu: int,
            budget_hours: float, budget: float, max_machines: int,
            need_disk: int = 0, disk_rate_h: float = 0.0) -> dict:
    n = len(plans)
    has_disk = need_disk > 0 and disk_rate_h > 0
    c = [p["單價"] for p in plans]
    if has_disk:
        c = c + [disk_rate_h]
    rows, lb, ub, names = [], [], [], []

    def _row(vals_for_plans, disk_coef=0.0):
        r = list(vals_for_plans)
        if has_disk:
            r.append(disk_coef)
        return r

    for key, need, label in (("vcpu", need_vcpu, "vCPU 需求"),
                             ("mem", need_mem, "記憶體需求"),
                             ("gpu", need_gpu, "GPU 需求")):
        if need > 0:
            rows.append(_row([p[key] for p in plans]))
            lb.append(float(need)); ub.append(math.inf); names.append(label)

    if has_disk:
        rows.append(_row([0.0] * n, disk_coef=1.0))
        lb.append(float(need_disk)); ub.append(math.inf); names.append("磁碟需求")

    if budget and budget > 0 and budget_hours > 0:
        rows.append(list(c))
        lb.append(-math.inf); ub.append(budget / budget_hours); names.append("預算上限")

    rows.append(_row([1.0] * n, disk_coef=0.0))
    lb.append(-math.inf); ub.append(float(max_machines)); names.append("台數上限")

    return {
        "c": c, "A": rows, "lb": lb, "ub": ub, "names": names,
        "integrality": [1] * n + ([0] if has_disk else []),
        "var_lb": [0] * n + ([0] if has_disk else []),
        "var_ub": [max_machines] * n + ([_MAX_DISK_GB] if has_disk else []),
        "plans": [p["方案"] for p in plans],
        "has_disk": has_disk,
        "disk_rate_h": disk_rate_h if has_disk else 0.0,
    }


def _solve_milp(plans: list, need_vcpu: int, need_mem: int, need_gpu: int,
                budget_hours: float, budget: float, max_machines: int,
                need_disk: int = 0, disk_rate_h: float = 0.0):
    try:
        import numpy as np
        from scipy.optimize import milp, LinearConstraint, Bounds
    except Exception:
        return None

    model = to_milp(plans, need_vcpu, need_mem, need_gpu,
                    budget_hours, budget, max_machines, need_disk, disk_rate_h)
    try:
        t0 = time.perf_counter()
        res = milp(
            c=np.array(model["c"], dtype=float),
            constraints=LinearConstraint(np.array(model["A"], dtype=float),
                                         np.array(model["lb"], dtype=float),
                                         np.array(model["ub"], dtype=float)),
            integrality=np.array(model["integrality"]),
            bounds=Bounds(np.array(model["var_lb"], dtype=float),
                          np.array(model["var_ub"], dtype=float)),
        )
        elapsed = (time.perf_counter() - t0) * 1000
    except Exception:
        return None

    if not res.success or res.x is None:
        MILP_STATS.clear()
        MILP_STATS.update({"solver": "HiGHS", "status": getattr(res, "message", ""),
                           "elapsed_ms": elapsed, "feasible": False,
                           "n_disk_vars": 1 if model["has_disk"] else 0})
        return math.inf, None, True, 0.0

    n = len(plans)
    combo = {}
    for name, val in zip(model["plans"], res.x[:n]):
        k = int(round(float(val)))
        if k > 0:
            combo[name] = k
    disk_gb = float(res.x[n]) if model["has_disk"] else 0.0
    cost = (sum(plans[i]["單價"] * int(round(float(v))) for i, v in enumerate(res.x[:n]))
            + model["disk_rate_h"] * disk_gb)

    MILP_STATS.clear()
    MILP_STATS.update({
        "solver": "HiGHS（scipy.optimize.milp）",
        "vars": len(model["c"]),
        "constraints": len(model["A"]),
        "n_disk_vars": 1 if model["has_disk"] else 0,
        "elapsed_ms": elapsed,
        "feasible": True,
        "best_cost": cost,
    })
    return cost, (combo or None), True, disk_gb


def solve_plan_mix(plans: list, need_vcpu: int, need_mem: int, need_gpu: int,
                   budget_hours: float, budget: float, max_machines: int,
                   need_disk: int = 0, disk_rate_h: float = 0.0):
    r = _solve_milp(plans, need_vcpu, need_mem, need_gpu,
                    budget_hours, budget, max_machines, need_disk, disk_rate_h)
    if r is not None:
        cost, combo, exact, disk_gb = r
        return cost, combo, exact, MILP_STATS.get("solver", "MILP Solver"), disk_gb
    cost, combo, exact, disk_gb = _solve(plans, need_vcpu, need_mem, need_gpu,
                                         budget_hours, budget, max_machines,
                                         need_disk, disk_rate_h)
    return cost, combo, exact, "內建分支定界（無 MILP solver 可用）", disk_gb


def _baseline_single(plans: list, need_vcpu: int, need_mem: int, need_gpu: int,
                     max_machines: int, disk_cost_h: float = 0.0):
    best = None
    for p in plans:
        ks = []
        if need_vcpu > 0:
            if p["vcpu"] <= 0:
                continue
            ks.append(math.ceil(need_vcpu / p["vcpu"]))
        if need_mem > 0:
            if p["mem"] <= 0:
                continue
            ks.append(math.ceil(need_mem / p["mem"]))
        if need_gpu > 0:
            if p["gpu"] <= 0:
                continue
            ks.append(math.ceil(need_gpu / p["gpu"]))
        k = max(ks) if ks else 0
        if k <= 0 or k > max_machines:
            continue
        cost = p["單價"] * k + disk_cost_h
        if best is None or cost < best[2]:
            best = (p, k, cost)
    return best


def optimize_plan_mix(vcpu: int = 0, memory_gb: int = 0, gpu_count: int = 0,
                      budget: float = 0, hours_per_day: float = 24, days: int = 30,
                      max_machines: int = 8, region: str = None,
                      user_id: str = "default",
                      disk_gb: int = 0, disk_type: str = "SSD") -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案，請確認 data/pricing.csv 路徑正確"

    region = settings.safe_region(region)
    vcpu = max(0, int(vcpu or 0))
    memory_gb = max(0, int(memory_gb or 0))
    gpu_count = max(0, int(gpu_count or 0))
    disk_gb = max(0, min(int(disk_gb or 0), _MAX_DISK_GB))

    if vcpu == 0 and memory_gb == 0 and gpu_count == 0:
        return ("請至少提供一項資源需求（vCPU / 記憶體 GB / GPU 張數）。\n"
                "例如：「我要 64 核、256GB 記憶體、2 張 GPU，怎麼配最省？」")
    if hours_per_day <= 0 or hours_per_day > 24:
        return "每天運行時數需介於 0 到 24 小時之間"
    if days <= 0:
        return "使用天數需大於 0"
    max_machines = max(1, min(int(max_machines or 8), _MAX_MACHINES))

    total_hours = hours_per_day * days
    plans, pt, disc = _candidate_plans(region, need_gpu=gpu_count > 0, user_id=user_id)
    if not plans:
        return f"{_header(region, pt, disc)}\n此區域沒有可用的方案資料"

    disk_rate_h = _disk_rate_hourly(region, user_id, disk_type) if disk_gb else 0.0
    disk_cost_h = disk_rate_h * disk_gb

    cost_h, combo, exact, solver, disk_out = solve_plan_mix(
        plans, vcpu, memory_gb, gpu_count, total_hours, budget, max_machines,
        disk_gb, disk_rate_h)

    lines = [_header(region, pt, disc)]
    lines.append(f"需求：{_demand_txt(vcpu, memory_gb, gpu_count, disk_gb, disk_type)}"
                 f"　使用情境：{hours_per_day:g}h × {days} 天（共 {total_hours:,.0f} 小時）")
    if budget and budget > 0:
        lines.append(f"預算上限：${budget:,.0f}")
    lines.append("")

    if combo is None:
        cost_nb, combo_nb, _, _, _ = solve_plan_mix(
            plans, vcpu, memory_gb, gpu_count, total_hours, 0, max_machines,
            disk_gb, disk_rate_h)
        if combo_nb is None:
            lines.append("在此區域的方案中湊不出符合需求的組合（可能需求超出可提供的規格上限）")
        else:
            need_total = cost_nb * total_hours
            lines.append(f"預算不足：滿足此需求的最低總費用為 ${need_total:,.2f}"
                         f"（超出預算 ${need_total - budget:,.2f}）")
            if disk_gb:
                lines.append(f"　　（其中磁碟 {disk_gb:,}GB {disk_type} 佔 "
                             f"${disk_cost_h * total_hours:,.2f}）")
            lines.append("")
            lines.append("若放寬預算，最省組合為：")
            lines += _combo_lines(plans, combo_nb, total_hours,
                                  disk_gb, disk_type, disk_rate_h)
        lines.append(f"（{settings.PRICING_DISCLAIMER}）")
        return "\n".join(lines)

    total = cost_h * total_hours

    base = _baseline_single(plans, vcpu, memory_gb, gpu_count, max_machines, disk_cost_h)
    save_pct = 0.0
    if base is not None:
        base_total = base[2] * total_hours
        if base_total > 0:
            save_pct = (base_total - total) / base_total

    n_kinds = len(combo)
    demote = base is not None and n_kinds > 1 and save_pct < _MIX_MIN_SAVING

    if demote:
        bp, bk, bcost_h = base
        lines.append(f"建議：{bp['方案']} × {bk}（單一機型）")
        lines += _combo_lines(plans, {bp["方案"]: bk}, total_hours,
                              disk_gb, disk_type, disk_rate_h)
        lines.append("")
        lines.append(f"總計：${bcost_h:,.2f}/小時 × {total_hours:,.0f} 小時 "
                     f"＝ **${base[2] * total_hours:,.2f}**")
        lines.append(f"求解：{solver}")
        if budget and budget > 0:
            lines.append(f"預算餘額：${budget - base[2] * total_hours:,.2f}")
        lines.append("")
        lines.append(f"── 為什麼不推薦混搭 ──")
        lines.append(f"混 {n_kinds} 種機型的最省解為 ${total:,.2f}，"
                     f"只省 ${base[2] * total_hours - total:,.2f}（{save_pct * 100:.1f}%）")
        lines.append(f"低於 {_MIX_MIN_SAVING * 100:.0f}% 門檻 → 多管 {n_kinds - 1} 種機型的"
                     f"維運成本通常大於省下的錢，因此建議單一機型")
        lines.append("")
        lines.append(f"（{settings.PRICING_DISCLAIMER}）")
        return "\n".join(lines)

    lines.append("最省組合：")
    lines += _combo_lines(plans, combo, total_hours, disk_gb, disk_type, disk_rate_h)
    lines.append("")
    lines.append(f"總計：${cost_h:,.2f}/小時 × {total_hours:,.0f} 小時 ＝ **${total:,.2f}**")
    lines.append(f"求解：{solver}")
    if budget and budget > 0:
        lines.append(f"預算餘額：${budget - total:,.2f}")
    if not exact:
        lines.append("（註：搜尋節點達上限，此為目前找到的最佳解，未必是全域最佳）")

    lines.append("")
    lines.append(f"── 對照：現行做法（只用單一方案，最多 {max_machines} 台）──")
    if base is None:
        lines.append("單一方案湊不出此需求 → 只有混搭組合可行（現行做法在此情境下無解）")
    else:
        bp, bk, bcost_h = base
        base_total = bcost_h * total_hours
        lines.append(f"{bp['方案']} × {bk}　${bcost_h:,.2f}/小時　→ 總計 ${base_total:,.2f}")
        if base_total - total > 1e-6:
            save = base_total - total
            lines.append(f"**最佳化節省 ${save:,.2f}（{save / base_total * 100:.1f}%）**")
        else:
            lines.append("兩者相同：此需求下單一方案已是最佳解（最佳化確認沒有更省的組合）")

    lines.append("")
    lines.append(f"（{settings.PRICING_DISCLAIMER}）")
    return "\n".join(lines)


def _header(region: str, pt: str, disc: float) -> str:
    label = settings.REGION_LABELS.get(region, region)
    if disc < 1.0:
        return f"【{label}】成本最佳化（帳號身分：{pt}，差別費率 {disc * 10:.0f} 折）"
    return f"【{label}】成本最佳化（帳號身分：{pt}，牌價）"


def _demand_txt(v: int, m: int, g: int, d: int = 0, dt: str = "SSD") -> str:
    parts = []
    if v:
        parts.append(f"vCPU ≥ {v}")
    if m:
        parts.append(f"記憶體 ≥ {m}GB")
    if g:
        parts.append(f"GPU ≥ {g} 張")
    if d:
        parts.append(f"磁碟 ≥ {d:,}GB {dt}")
    return "、".join(parts)


def _combo_lines(plans: list, combo: dict, total_hours: float,
                 disk_gb: int = 0, disk_type: str = "SSD",
                 disk_rate_h: float = 0.0) -> list:
    by_name = {p["方案"]: p for p in plans}
    lines = []
    tot_v = tot_m = tot_g = 0
    for name, k in sorted(combo.items(), key=lambda kv: -by_name[kv[0]]["單價"] * kv[1]):
        p = by_name[name]
        tot_v += p["vcpu"] * k
        tot_m += p["mem"] * k
        tot_g += p["gpu"] * k
        gpu = f"GPU:{p['gpu_txt']} " if p["gpu_txt"] else ""
        sysdisk = f" 系統碟:{p['disk']}GB" if p.get("disk") else ""
        lines.append(f"  {name} × {k}　{gpu}vCPU:{p['vcpu']} 記憶體:{p['mem']}GB{sysdisk}"
                     f"　${p['單價']:,.2f}/h"
                     f"　小計 ${p['單價'] * k * total_hours:,.2f}")
    if disk_gb and disk_rate_h > 0:
        lines.append(f"  加購磁碟 {disk_gb:,}GB {disk_type}　${disk_rate_h:,.4f}/GB/h"
                     f"　小計 ${disk_rate_h * disk_gb * total_hours:,.2f}")
    lines.append(f"  規格合計：vCPU {tot_v}、記憶體 {tot_m}GB"
                 + (f"、GPU {tot_g} 張" if tot_g else "")
                 + (f"、加購磁碟 {disk_gb:,}GB" if disk_gb else ""))
    if disk_gb:
        lines.append("  （系統碟綁在各自機器上、無法跨機器合併成單一磁碟區，"
                     "因此不折抵加購量——報價偏保守不會低估）")
    return lines
