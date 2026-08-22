import itertools
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import settings                                    # noqa: E402
from mcp_server.tools import optimize as OPT                   # noqa: E402
from mcp_server.tools.optimize import optimize_plan_mix        # noqa: E402

_PASS = 0
_FAIL = 0


def _solved(out: str) -> bool:
    """輸出是否代表求得可行解（不依賴顯示用的裝飾符號）。"""
    return ("最省組合：" in out or "（單一機型）" in out) and "預算不足" not in out


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ✅ {name}")
    else:
        _FAIL += 1
        print(f"  ❌ {name}　{detail}")
    return bool(cond)


def section(title):
    print(f"\n── {title} " + "─" * max(0, 48 - len(title)))


def _total_from_text(text: str):
    m = re.search(r"＝ \*\*\$([\d,]+\.\d{2})\*\*", text)
    return float(m.group(1).replace(",", "")) if m else None


def _brute_force(plans, v, m, g, max_machines):
    best = math.inf
    names = list(range(len(plans)))
    for k in range(0, max_machines + 1):
        for combo in itertools.combinations_with_replacement(names, k):
            sv = sum(plans[i]["vcpu"] for i in combo)
            sm = sum(plans[i]["mem"] for i in combo)
            sg = sum(plans[i]["gpu"] for i in combo)
            if sv >= v and sm >= m and sg >= g:
                best = min(best, sum(plans[i]["單價"] for i in combo))
    return best


def test_coverage():
    section("求解正確性：組合規格 ≥ 需求")
    cases = [(64, 256, 0), (96, 512, 2), (32, 64, 0), (8, 32, 0), (24, 128, 1)]
    for v, m, g in cases:
        plans, _, _ = OPT._candidate_plans(settings.DEFAULT_REGION, g > 0, "default")
        cost, combo, _, _ = OPT._solve(plans, v, m, g, 720, 0, 8)
        if combo is None:
            check(f"需求 {v}c/{m}G/{g}gpu 有解", False, "找不到組合")
            continue
        by = {p["方案"]: p for p in plans}
        sv = sum(by[n]["vcpu"] * k for n, k in combo.items())
        sm = sum(by[n]["mem"] * k for n, k in combo.items())
        sg = sum(by[n]["gpu"] * k for n, k in combo.items())
        check(f"需求 {v}c/{m}G/{g}gpu → 得到 {sv}c/{sm}G/{sg}gpu 覆蓋成立",
              sv >= v and sm >= m and sg >= g, f"{sv},{sm},{sg}")


def test_optimality():
    section("最佳性：與窮舉結果一致")
    plans, _, _ = OPT._candidate_plans(settings.DEFAULT_REGION, False, "default")
    for v, m, cap in [(16, 32, 3), (32, 64, 4), (24, 96, 4)]:
        cost, combo, _, _ = OPT._solve(plans, v, m, 0, 720, 0, cap)
        brute = _brute_force(plans, v, m, 0, cap)
        check(f"需求 {v}c/{m}G（≤{cap}台）求解 ${cost:.2f} ＝ 窮舉 ${brute:.2f}",
              abs(cost - brute) < 1e-6, f"solver={cost} brute={brute}")


def test_budget():
    section("預算約束")
    out = optimize_plan_mix(vcpu=8, memory_gb=32, budget=1000, days=30)
    check("預算不足時明確回報不足", "預算不足" in out and "最省組合" not in out.split("若放寬")[0])

    full = optimize_plan_mix(vcpu=8, memory_gb=32, days=30)
    need = _total_from_text(full)
    check("同需求在不設預算時可解", need is not None, out[:80])

    if need:
        ok = optimize_plan_mix(vcpu=8, memory_gb=32, budget=need + 1, days=30)
        check("預算剛好足夠時可解", "最省組合：" in ok and "預算不足" not in ok)
        no = optimize_plan_mix(vcpu=8, memory_gb=32, budget=need - 1, days=30)
        check("預算差一元時判定不足", "預算不足" in no)


def test_discount():
    section("身分折扣（國科會 5 折）")
    import shutil
    from common import accounts

    uid_base, uid_disc = "_opt_test_base", "_opt_test_disc"
    accounts.set_profile(uid_base, "個人")
    accounts.set_profile(uid_disc, "國科會")
    assert accounts.plan_type(uid_base) == "個人"
    assert accounts.plan_type(uid_disc) == "國科會"

    base = optimize_plan_mix(vcpu=32, memory_gb=64, days=30, user_id=uid_base)
    disc = optimize_plan_mix(vcpu=32, memory_gb=64, days=30, user_id=uid_disc)
    b, d = _total_from_text(base), _total_from_text(disc)
    if b and d:
        check(f"國科會總價 ${d:,.2f} ＝ 牌價 ${b:,.2f} 的 5 折",
              abs(d - b * 0.5) < 1.0, f"{d} vs {b*0.5}")
    else:
        check("折扣案例可解", False, f"{b} / {d}")
    for u in (uid_base, uid_disc):
        shutil.rmtree(settings.user_dir(u), ignore_errors=True)


def test_vs_baseline():
    section("對照：最佳化不會比單一方案更貴")
    for v, m, g in [(64, 256, 0), (96, 512, 2), (32, 64, 0), (48, 192, 0)]:
        plans, _, _ = OPT._candidate_plans(settings.DEFAULT_REGION, g > 0, "default")
        cost, combo, _, _ = OPT._solve(plans, v, m, g, 720, 0, 8)
        base = OPT._baseline_single(plans, v, m, g, 8)
        if base is None:
            check(f"需求 {v}c/{m}G/{g}gpu：單一方案無解，混搭有解", combo is not None)
            continue
        check(f"需求 {v}c/{m}G/{g}gpu：最佳化 ${cost:.2f}/h ≤ 單一方案 ${base[2]:.2f}/h",
              cost <= base[2] + 1e-6)


def test_edges():
    section("邊界輸入")
    check("空需求給提示", "請至少提供一項資源需求" in optimize_plan_mix())
    check("時數 0 被擋下", "每天運行時數" in optimize_plan_mix(vcpu=8, hours_per_day=0))
    check("時數 25 被擋下", "每天運行時數" in optimize_plan_mix(vcpu=8, hours_per_day=25))
    check("天數 0 被擋下", "使用天數" in optimize_plan_mix(vcpu=8, days=0))
    out = optimize_plan_mix(vcpu=999999, memory_gb=999999, days=1)
    check("超大需求不會拋例外", isinstance(out, str) and len(out) > 0)
    check("兩區都可解",
          _solved(optimize_plan_mix(vcpu=16, memory_gb=32, region="AI-Cloud"))
          and _solved(optimize_plan_mix(vcpu=16, memory_gb=32, region="AI-Trust")))


def test_storage():
    print("\n[storage 維度]")
    from common import accounts
    import shutil

    U = "_opt_disk_user"
    accounts.set_profile(U, "個人")
    plans_t, _, _ = OPT._candidate_plans("AI-Trust", False, U)
    n = len(plans_t)

    m0 = OPT.to_milp(plans_t, 32, 64, 0, 720, 0, 8, 0, 0.0)
    check("disk_gb=0 時變數數 = 方案數（沒有多出磁碟變數）",
          len(m0["c"]) == n and m0["has_disk"] is False, len(m0["c"]))
    m1 = OPT.to_milp(plans_t, 32, 64, 0, 720, 0, 8, 500, 0.002)
    check("disk_gb>0 時變數數 = 方案數 + 1",
          len(m1["c"]) == n + 1 and m1["has_disk"] is True, len(m1["c"]))

    check("有磁碟時每列約束長度都等於變數數",
          all(len(r) == n + 1 for r in m1["A"]),
          [len(r) for r in m1["A"]])

    check("磁碟為連續變數（integrality 最後一位為 0）",
          m1["integrality"] == [1] * n + [0])

    _, _, _, _, dg = OPT.solve_plan_mix(plans_t, 8, 16, 0, 720, 0, 4, 100, 0.002)
    check("系統碟不折抵加購量（需求 100GB → 加購 100GB，不因系統碟 120GB 而歸零）",
          abs(dg - 100) < 1e-6, dg)

    check("磁碟覆蓋約束成立（s ≥ D）", dg >= 100 - 1e-9, dg)

    a = OPT._solve_milp(plans_t, 32, 64, 0, 720, 0, 8, 500, 0.002)
    b = OPT._solve(plans_t, 32, 64, 0, 720, 0, 8, 500, 0.002)
    check("含磁碟時 HiGHS 與內建 B&B 總成本一致",
          a is not None and abs(a[0] - b[0]) < 1e-6, (a[0] if a else None, b[0]))

    m_only = OPT._solve_milp(plans_t, 32, 64, 0, 720, 0, 8, 0, 0.0)
    check("含磁碟成本 = 純機器成本 + 費率×GB",
          abs((a[0] - m_only[0]) - 0.002 * 500) < 1e-6,
          (a[0], m_only[0], a[0] - m_only[0]))

    accounts.set_profile(U, "國科會")
    cloud_list = settings.disk_rate("AI-Cloud", "SSD") / (24 * 30)
    trust_list = settings.disk_rate("AI-Trust", "SSD") / (24 * 30)
    cloud_r = OPT._disk_rate_hourly("AI-Cloud", U, "SSD")
    trust_r = OPT._disk_rate_hourly("AI-Trust", U, "SSD")
    check("AI-Cloud 國科會：磁碟費率 = 牌價 × 5 折",
          abs(cloud_r - cloud_list * 0.5) < 1e-12, (cloud_r, cloud_list))
    check("AI-Trust 國科會：磁碟費率 = 牌價（儲存不打折）",
          abs(trust_r - trust_list) < 1e-12, (trust_r, trust_list))

    check("disk_type=HDD 走到不同費率",
          OPT._disk_rate_hourly("AI-Trust", U, "HDD")
          < OPT._disk_rate_hourly("AI-Trust", U, "SSD"))

    accounts.set_profile(U, "個人")
    base = optimize_plan_mix(vcpu=8, memory_gb=16, days=30, budget=9000,
                             region="AI-Trust", user_id=U)
    withd = optimize_plan_mix(vcpu=8, memory_gb=16, days=30, budget=9000,
                              disk_gb=5000, region="AI-Trust", user_id=U)
    check("磁碟計入預算約束（同預算下加磁碟會變成預算不足）",
          _solved(base) and "預算不足" in withd,
          (base[:60], withd[:60]))

    out = optimize_plan_mix(vcpu=32, memory_gb=64, disk_gb=500, days=30,
                            region="AI-Trust", user_id=U)
    check("輸出含磁碟需求與加購明細",
          "磁碟 ≥ 500GB" in out and "加購磁碟" in out, out[:200])

    shutil.rmtree(settings.user_dir(U), ignore_errors=True)


def test_mix_threshold():
    print("\n[混搭門檻]")
    from common import accounts
    import shutil

    U = "_opt_thr_user"
    accounts.set_profile(U, "個人")

    out = optimize_plan_mix(vcpu=64, memory_gb=256, days=30,
                            region="AI-Trust", user_id=U)
    check("低於門檻時改推單一機型", "單一機型" in out and "為什麼不推薦混搭" in out,
          out[:160])
    check("低於門檻時仍誠實揭露混搭的數字", "只省" in out, out[:160])

    out2 = optimize_plan_mix(vcpu=96, memory_gb=512, gpu_count=2, days=30,
                             region="AI-Trust", user_id=U)
    check("高於門檻時維持混搭建議",
          "最省組合" in out2 and "最佳化節省" in out2, out2[:160])

    out3 = optimize_plan_mix(vcpu=64, memory_gb=512, days=30,
                             region="AI-Trust", user_id=U)
    check("單一方案無解時不受門檻影響（仍給混搭）", _solved(out3), out3[:160])

    shutil.rmtree(settings.user_dir(U), ignore_errors=True)


def main():
    print("成本最佳化工具（optimize_plan_mix）離線驗證")
    test_coverage()
    test_optimality()
    test_budget()
    test_discount()
    test_vs_baseline()
    test_storage()
    test_mix_threshold()
    test_edges()
    print(f"\n結果：通過 {_PASS}　失敗 {_FAIL}")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
