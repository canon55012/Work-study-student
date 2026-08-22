import csv
import os

from config import settings

_PLANS_CACHE = {}
_PLANS_MTIME = None


def _all_by_region() -> dict:
    global _PLANS_CACHE, _PLANS_MTIME
    try:
        mtime = os.path.getmtime(settings.PRICING_CSV)
    except OSError:
        mtime = None
    if _PLANS_MTIME == mtime and _PLANS_CACHE:
        return _PLANS_CACHE

    cache = {}
    with open(settings.PRICING_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            region = (row.get("Region") or "").strip() or settings.DEFAULT_REGION
            name = (row.get("方案") or "").strip()
            if name:
                cache.setdefault(region, {})[name] = row
    _PLANS_CACHE, _PLANS_MTIME = cache, mtime
    return cache


def _load_plans(region: str = None) -> dict:
    region = settings.safe_region(region)
    return _all_by_region().get(region, {})


def _find_plan(name: str, region: str = None):
    all_rows = _load_plans(region)
    name = (name or "").strip()
    if name in all_rows:
        return all_rows[name]
    for k, v in all_rows.items():
        if k.lower() == name.lower():
            return v
    for k, v in all_rows.items():
        if name.lower() in k.lower():
            return v
    return None


def _region_header(region: str) -> str:
    region = settings.safe_region(region)
    disk = settings.DISK_RATES.get(region, {})
    return (f"【{settings.REGION_LABELS.get(region, region)}】"
            f"（系統碟{disk.get('系統碟', '')}；磁碟 SSD ${disk.get('SSD')}／HDD "
            f"${disk.get('HDD')} 每GB/月）")


def query_pricing(keyword: str = "", region: str = None) -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案，請確認 data/pricing.csv 路徑正確"
    region = settings.safe_region(region)
    rows = []
    for r in _load_plans(region).values():
        if keyword and keyword.lower() not in r["方案"].lower() \
                and keyword.lower() not in (r.get("類型") or "").lower():
            continue
        if not r["價格(小時)"]:
            continue
        rows.append(r)
    if not rows:
        return f"{_region_header(region)}\n查無符合的方案"
    lines = [_region_header(region)]
    for r in rows:
        gpu = f"GPU:{r['GPU']} " if r["GPU"] else ""
        lines.append(f"{r['方案']} | {gpu}vCPU:{r['vCPU']} | 記憶體:{r['記憶體(GB)']}GB | "
                     f"系統碟:{r['系統碟(GB)']}GB | ${r['價格(小時)']}/小時")
    lines.append(f"（{settings.PRICING_DISCLAIMER}）")
    return "\n".join(lines)


def recommend_server(vcpu: int = 0, memory_gb: int = 0, need_gpu: bool = False,
                     region: str = None) -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案"
    region = settings.safe_region(region)
    matched = []
    for r in _load_plans(region).values():
        if not r["價格(小時)"]:
            continue
        if (r.get("類型") or "") == "K8S":
            continue
        try:
            r_vcpu = int(r["vCPU"]) if r["vCPU"] else 0
            r_mem = int(r["記憶體(GB)"]) if r["記憶體(GB)"] else 0
            r_gpu = bool(r["GPU"])
            if need_gpu and not r_gpu:
                continue
            if not need_gpu and r_gpu:
                continue
            if vcpu and r_vcpu < vcpu:
                continue
            if memory_gb and r_mem < memory_gb:
                continue
            matched.append(r)
        except Exception:
            continue
    if not matched:
        return f"{_region_header(region)}\n沒有符合條件的方案"
    matched.sort(key=lambda x: float(x["價格(小時)"]))
    lines = [_region_header(region), "符合條件的方案（價格由低到高）："]
    for r in matched[:5]:
        gpu = f"GPU:{r['GPU']} " if r["GPU"] else ""
        lines.append(f"{r['方案']} | {gpu}vCPU:{r['vCPU']} | 記憶體:{r['記憶體(GB)']}GB | "
                     f"${r['價格(小時)']}/小時")
    return "\n".join(lines)


def compare_plans(plan_a: str, plan_b: str, region: str = None) -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案"
    region = settings.safe_region(region)

    a = _find_plan(plan_a, region)
    b = _find_plan(plan_b, region)
    if not a:
        return f"在 {settings.REGION_LABELS.get(region, region)} 找不到方案：{plan_a}，請用 query_pricing 確認"
    if not b:
        return f"在 {settings.REGION_LABELS.get(region, region)} 找不到方案：{plan_b}，請用 query_pricing 確認"

    def fmt(row, field, unit=""):
        val = row.get(field, "") or "—"
        return f"{val}{unit}" if val != "—" else "—"

    lines = [
        _region_header(region),
        f"方案比較：{a['方案']} vs {b['方案']}",
        "",
        f"GPU        ：{fmt(a,'GPU') or '無'} vs {fmt(b,'GPU') or '無'}",
        f"vCPU       ：{fmt(a,'vCPU')} vs {fmt(b,'vCPU')}",
        f"記憶體     ：{fmt(a,'記憶體(GB)','GB')} vs {fmt(b,'記憶體(GB)','GB')}",
        f"系統碟     ：{fmt(a,'系統碟(GB)','GB')} vs {fmt(b,'系統碟(GB)','GB')}",
        f"每小時費用 ：${fmt(a,'價格(小時)')} vs ${fmt(b,'價格(小時)')}",
    ]

    try:
        pa = float(a.get("價格(小時)", 0) or 0)
        pb = float(b.get("價格(小時)", 0) or 0)
        if pa > 0 and pb > 0:
            if pb > pa:
                lines.append(f"\n{b['方案']} 比 {a['方案']} 貴 {pb/pa:.1f} 倍")
            else:
                lines.append(f"\n{a['方案']} 比 {b['方案']} 貴 {pa/pb:.1f} 倍")
            lines.append(f"月費估算（24hr×30天）：{a['方案']} ${pa*24*30:.2f} / "
                         f"{b['方案']} ${pb*24*30:.2f}")
    except Exception:
        pass

    return "\n".join(lines)


def _storage_estimate(region: str, disk_gb: float, disk_type: str,
                      months: float, disc: float) -> dict:
    region = settings.safe_region(region)
    rate = settings.disk_rate(region, disk_type)
    gross_month = rate * disk_gb
    gross_total = gross_month * months
    if settings.storage_discount_applies(region):
        net_total = gross_total * disc
        discounted = disc < 1.0
    else:
        net_total = gross_total
        discounted = False
    return {"rate": rate, "gross_month": gross_month, "gross_total": gross_total,
            "net_total": net_total, "discounted": discounted}


def estimate_cost(plan: str, hours_per_day: float = 24, days: int = 30,
                  region: str = None, user_id: str = "default",
                  disk_gb: float = 0, disk_type: str = "SSD") -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案"
    region = settings.safe_region(region)

    row = _find_plan(plan, region)
    if not row:
        return f"在 {settings.REGION_LABELS.get(region, region)} 找不到方案：{plan}，請用 query_pricing 確認"

    try:
        hourly = float(row.get("價格(小時)", 0) or 0)
    except ValueError:
        hourly = 0
    if hourly <= 0:
        return f"{row['方案']} 沒有可用的價格資料，無法估算"

    if hours_per_day <= 0 or hours_per_day > 24:
        return "每天使用時數需介於 0 到 24 小時之間"
    if days <= 0:
        return "使用天數需大於 0"

    daily = hourly * hours_per_day
    total = daily * days
    full_month = hourly * 24 * 30

    from common import accounts
    pt = accounts.plan_type(user_id)
    disc = settings.discount_rate(region, pt)
    compute_net = total * disc

    lines = [
        _region_header(region),
        f"費用估算：{row['方案']}（${hourly:.2f}/小時）",
        f"使用情境：每天 {hours_per_day:g} 小時 × {days} 天",
        f"每日費用：${daily:.2f}",
    ]
    if disc < 1.0:
        lines += [
            f"計算資源牌價：${total:.2f}",
            f"帳號身分：{pt}（差別費率 {disc*10:.0f} 折）",
            f"計算資源實收：${compute_net:.2f}",
        ]
    else:
        lines += [
            f"計算資源費用：${total:.2f}",
            f"帳號身分：{pt}（牌價，無折扣）",
        ]

    grand_net = compute_net
    if disk_gb and disk_gb > 0:
        se = _storage_estimate(region, disk_gb, disk_type, days / 30.0, disc)
        if se["rate"] <= 0:
            lines.append(f"（磁碟類型 {disk_type} 不支援，僅估算計算資源；磁碟請填 SSD 或 HDD）")
        else:
            grand_net += se["net_total"]
            dt = (disk_type or "SSD").strip().upper()
            lines.append(f"加購磁碟：{disk_gb:g}GB {dt}（${se['rate']}/GB/月 × "
                         f"{days/30.0:.2f} 月＝${se['gross_total']:.2f} 牌價）")
            if se["discounted"]:
                lines.append(f"　磁碟實收：${se['net_total']:.2f}（此區儲存亦適用差別費率）")
            elif not settings.storage_discount_applies(region):
                lines.append("　磁碟實收：同牌價（此區儲存為單一價、不隨身分折扣）")
            lines.append(f"合計實收（計算＋磁碟）：${grand_net:.2f}")

    lines.append(f"參考：24 小時全天運轉一個月約 ${full_month:.2f}（牌價，未含磁碟）")
    return "\n".join(lines)


def estimate_storage_cost(disk_gb: float, disk_type: str = "SSD", months: float = 1,
                          region: str = None, user_id: str = "default") -> str:
    region = settings.safe_region(region)
    if disk_gb is None or disk_gb <= 0:
        return "請提供要加購的磁碟容量（GB，需大於 0）"
    if months <= 0:
        return "使用月數需大於 0"

    rate = settings.disk_rate(region, disk_type)
    if rate <= 0:
        return f"不支援的磁碟類型：{disk_type}（請填 SSD 或 HDD）"

    from common import accounts
    pt = accounts.plan_type(user_id)
    disc = settings.discount_rate(region, pt)
    se = _storage_estimate(region, disk_gb, disk_type, months, disc)
    dt = (disk_type or "SSD").strip().upper()
    disk_info = settings.DISK_RATES.get(region, {})

    lines = [
        _region_header(region),
        f"磁碟加購估算：{disk_gb:g}GB {dt}（${rate}/GB/月，含 5% 稅）",
        f"系統碟：{disk_info.get('系統碟', '')}（此為額外加購容量）",
        f"使用月數：{months:g} 個月",
    ]
    if se["discounted"]:
        lines += [
            f"牌價：${se['gross_total']:.2f}",
            f"帳號身分：{pt}（此區儲存適用差別費率 {disc*10:.0f} 折）",
            f"實收：${se['net_total']:.2f}",
        ]
    else:
        lines.append(f"費用：${se['gross_total']:.2f}")
        if not settings.storage_discount_applies(region):
            lines.append(f"（{settings.REGION_LABELS.get(region, region)} 儲存為單一價，"
                         f"不隨帳號身分折扣；帳號身分：{pt}）")
        else:
            lines.append(f"帳號身分：{pt}（牌價，無折扣）")
    lines.append(f"（{settings.PRICING_DISCLAIMER}）")
    return "\n".join(lines)


def plan_budget(budget: float, plan: str, region: str = None,
                hours_per_day: float = 24, user_id: str = "default") -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案"
    region = settings.safe_region(region)
    if budget is None or budget <= 0:
        return "請提供大於 0 的預算金額"
    if hours_per_day <= 0 or hours_per_day > 24:
        return "每天運行時數需介於 0 到 24 小時之間"

    row = _find_plan(plan, region)
    if not row:
        return f"在 {settings.REGION_LABELS.get(region, region)} 找不到方案：{plan}，請用 query_pricing 確認"
    try:
        hourly = float(row.get("價格(小時)", 0) or 0)
    except ValueError:
        hourly = 0
    if hourly <= 0:
        return f"{row['方案']} 沒有可用的價格資料，無法試算"

    from common import accounts
    pt = accounts.plan_type(user_id)
    disc = settings.discount_rate(region, pt)
    net_hourly = hourly * disc
    total_hours = budget / net_hourly
    days = total_hours / hours_per_day

    lines = [
        _region_header(region),
        f"預算試算：{row['方案']}　預算 ${budget:,.0f}",
    ]
    if disc < 1.0:
        lines.append(f"單價：牌價 ${hourly:.2f}/小時 → {pt} {disc*10:.0f} 折後 ${net_hourly:.2f}/小時")
    else:
        lines.append(f"單價：${hourly:.2f}/小時（{pt}，牌價）")
    lines += [
        f"可運行總時數：約 {total_hours:,.1f} 小時",
        f"以每天 {hours_per_day:g} 小時計：約可跑 {days:,.1f} 天",
    ]
    if hours_per_day >= 24:
        lines.append(f"（等於約 {days/30.0:,.1f} 個月全天運轉）")
    else:
        full = total_hours / 24
        lines.append(f"（若改 24 小時全天運轉：約 {full:,.1f} 天）")
    lines.append(f"（{settings.PRICING_DISCLAIMER}）")
    return "\n".join(lines)


def compare_regions(plan: str, hours_per_day: float = 24, days: int = 30,
                    user_id: str = "default") -> str:
    if not os.path.exists(settings.PRICING_CSV):
        return "找不到報價檔案"
    if hours_per_day <= 0 or hours_per_day > 24:
        return "每天使用時數需介於 0 到 24 小時之間"
    if days <= 0:
        return "使用天數需大於 0"

    from common import accounts
    pt = accounts.plan_type(user_id)

    found = []
    for region in settings.REGIONS:
        row = _find_plan(plan, region)
        if not row:
            continue
        try:
            hourly = float(row.get("價格(小時)", 0) or 0)
        except ValueError:
            hourly = 0
        if hourly <= 0:
            continue
        disc = settings.discount_rate(region, pt)
        net_hourly = hourly * disc
        total_net = net_hourly * hours_per_day * days
        found.append({"region": region, "方案": row["方案"], "hourly": hourly,
                      "disc": disc, "net_hourly": net_hourly, "total_net": total_net})

    if not found:
        return f"兩區都找不到方案：{plan}，請用 query_pricing 確認名稱"
    if len(found) == 1:
        f0 = found[0]
        return (f"方案「{f0['方案']}」只在 {settings.REGION_LABELS.get(f0['region'], f0['region'])} 提供，"
                f"無跨區可比。折扣後 ${f0['net_hourly']:.2f}/小時"
                f"（身分：{pt}），{hours_per_day:g}h×{days}天約 ${f0['total_net']:.2f}。")

    found.sort(key=lambda x: x["total_net"])
    cheap, other = found[0], found[1]
    lines = [
        f"跨區比價：{plan}（帳號身分：{pt}；使用情境 {hours_per_day:g}h×{days}天）",
        "",
    ]
    for f in found:
        tag = "  ← 最省" if f is cheap else ""
        disc_txt = f"{f['disc']*10:.0f}折後 " if f["disc"] < 1.0 else ""
        lines.append(f"{settings.REGION_LABELS.get(f['region'], f['region'])}："
                     f"牌價 ${f['hourly']:.2f}/h → {disc_txt}${f['net_hourly']:.2f}/h"
                     f" | 區間總計 ${f['total_net']:.2f}{tag}")
    save = other["total_net"] - cheap["total_net"]
    if save > 0.005:
        pct = save / other["total_net"] * 100
        lines += ["", f"建議：選 {settings.REGION_LABELS.get(cheap['region'], cheap['region'])}，"
                  f"此情境可省 ${save:.2f}（約 {pct:.0f}%）。"]
    else:
        lines += ["", "兩區折扣後費用相同，可依其他因素（規格供應、延遲）擇一。"]
    lines.append(f"（{settings.PRICING_DISCLAIMER}）")
    return "\n".join(lines)
