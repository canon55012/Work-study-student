"""端到端自動化 smoke test。"""
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import settings  # noqa: E402

_PASS = 0
_FAIL = 0


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


SMOKE_USERS = ["_smoke_alice", "_smoke_bob", "_smoke_live", "_smoke_region", "_smoke_disc"]


def _cleanup_users():
    for u in SMOKE_USERS:
        shutil.rmtree(settings.user_dir(u), ignore_errors=True)


def test_provider_state_machine():
    section("供應商切換狀態機 + 錯誤分類")
    from agent import providers as P

    enabled = [p["id"] for p in settings.LLM_PROVIDERS if p["enabled"]]
    ok_all = True
    for pid in enabled:
        okk, _ = P.set_active(pid)
        ok_all = ok_all and okk and P.active_id() == pid
    check("啟用中的供應商都能切換且 active_id 正確", ok_all)

    disabled = [p["id"] for p in settings.LLM_PROVIDERS if not p["enabled"]]
    if disabled:
        okk, msg = P.set_active(disabled[0])
        check("切換到未啟用供應商被拒絕", (not okk) and "未啟用" in msg, msg)
    okk, msg = P.set_active("____bogus____")
    check("切換到未知供應商被拒絕", (not okk) and "未知" in msg, msg)

    if disabled:
        r = P.probe(disabled[0])
        check("未啟用供應商 probe 回 disabled", r["status"] == P.DISABLED, r)

    def ex(status_code=None, msg="", name="Exception"):
        e = type(name, (Exception,), {})(msg)
        if status_code is not None:
            e.status_code = status_code
        return e

    cases = [
        (ImportError("No module named 'openai'"), P.NO_SDK, "缺套件"),
        (ex(name="APIConnectionError"), P.UNREACHABLE, "連線錯誤"),
        (ex(name="APITimeoutError"), P.UNREACHABLE, "逾時"),
        (ex(status_code=401), P.AUTH, "401"),
        (ex(status_code=429, msg="insufficient_quota"), P.QUOTA, "額度用罄"),
        (ex(status_code=429, msg="too many requests"), P.RATE, "速率"),
        (ex(status_code=503), P.UNREACHABLE, "5xx"),
    ]
    all_ok = True
    for e, expect, label in cases:
        got = P._classify(e)
        if got != expect:
            all_ok = False
            print(f"     · {label}: 期望 {expect} 得到 {got}")
    check("錯誤分類（缺套件/連線/逾時/401/額度/速率/5xx）全部正確", all_ok)

    if enabled:
        P.set_active(enabled[0])


def test_vm_lifecycle_and_billing():
    section("VM 生命週期 + 計費")
    from datetime import datetime, timedelta
    from mcp_server.tools import vm_lifecycle as vm

    U, B = "_smoke_alice", "_smoke_bob"
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)
    shutil.rmtree(settings.user_dir(B), ignore_errors=True)

    r1 = vm.create_vm("H100.small", "alice-gpu", user_id=U)
    check("建立 VM 成功", "vm-0001" in r1 and "運行中" in r1)
    vm.create_vm("Basic.small", "", user_id=U)

    check("找不到的方案被拒絕", "找不到方案" in vm.create_vm("NoSuchPlan", "", user_id=U))
    check("跨區找不到方案被拒絕（H100 不在 AI-Cloud）",
          "找不到方案" in vm.create_vm("H100.small", "", region="AI-Cloud", user_id=U))

    check("使用者隔離：bob 看不到 alice 的 VM", "沒有任何 VM" in vm.list_vms(user_id=B))

    with vm.storage.file_lock(vm._vm_csv(U)):
        rows = vm._read_vms(U)
        rows[0]["計費起點"] = (datetime.now() - timedelta(hours=2)).strftime(vm._FMT)
        vm._write_vms(U, rows)
    bill = vm.get_vm_bill("vm-0001", U)
    hours, cost, _ = vm._current_bill(vm._find_vm(vm._read_vms(U), "vm-0001"))
    check("運行中即時計費 ≈ 2h × $174.96", 349.5 < cost < 351.0, f"cost={cost:.2f}")

    stop_msg = vm.stop_vm("vm-0001", U)
    check("關機成功且顯示累計費用", "已關機" in stop_msg and "$349" in stop_msg, stop_msg.replace("\n", " "))
    row = vm._find_vm(vm._read_vms(U), "vm-0001")
    check("關機後計費起點已清空（停止計費）", not (row.get("計費起點") or "").strip())
    _, cost_stopped, _ = vm._current_bill(row)
    check("關機後費用鎖定（不再成長）", 349.5 < cost_stopped < 351.0, f"cost={cost_stopped:.2f}")

    check("對已關機再關機 → 擋下", "已是" in vm.stop_vm("vm-0001", U))
    check("操作不存在的 VM → 清楚錯誤", "找不到 VM" in vm.delete_vm("vm-9999", U))

    vm.start_vm("vm-0001", U)
    row = vm._find_vm(vm._read_vms(U), "vm-0001")
    check("重新開機後有新的計費起點", bool((row.get("計費起點") or "").strip()))

    vm.maintain_vm("vm-0001", U)
    del_msg = vm.delete_vm("vm-0001", U)
    check("刪除顯示不可復原與總費用", "不可復原" in del_msg and "總費用" in del_msg)

    acct = vm.get_account_bill(U)
    check("帳戶總覽有總費用行", "總費用" in acct)
    s = vm.account_summary(U)
    check("account_summary 結構正確", set(["vm_count", "running", "total_cost", "vms"]) <= set(s), s.keys())


def test_region_pricing():
    section("雲端區域（Region）分區價格與計費")
    from datetime import datetime, timedelta
    from mcp_server.tools import pricing as P
    from mcp_server.tools import vm_lifecycle as vm

    check("預設區域為 AI-Trust", settings.DEFAULT_REGION == "AI-Trust")
    cloud = P._find_plan("H200.small", "AI-Cloud")
    trust = P._find_plan("H200.small", "AI-Trust")
    check("同方案兩區都有、價格不同",
          bool(cloud) and bool(trust) and cloud["價格(小時)"] != trust["價格(小時)"],
          f"{cloud and cloud['價格(小時)']} vs {trust and trust['價格(小時)']}")
    check("H100 只在 AI-Trust（AI-Cloud 查無）",
          P._find_plan("H100.small", "AI-Cloud") is None
          and P._find_plan("H100.small", "AI-Trust") is not None)
    check("query_pricing 帶區域標頭與免責聲明",
          "AI-Cloud Region" in P.query_pricing("GPU", "AI-Cloud")
          and "暫定價格" in P.query_pricing("", "AI-Cloud"))

    U = "_smoke_region"
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)
    out = vm.create_vm("H200.small", "r", region="AI-Cloud", user_id=U)
    check("create_vm 記錄區域", "AI-Cloud" in out)
    with vm.storage.file_lock(vm._vm_csv(U)):
        rows = vm._read_vms(U)
        rows[0]["計費起點"] = (datetime.now() - timedelta(hours=1)).strftime(vm._FMT)
        vm._write_vms(U, rows)
    _, cost, hourly = vm._current_bill(vm._read_vms(U)[0])
    check("AI-Cloud VM 以該區費率計費（$245.94/h）", abs(hourly - 245.94) < 0.01, f"hourly={hourly}")
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)


def test_account_discount():
    section("帳號身分（計畫別）＋ 差別費率折扣")
    from common import accounts
    from mcp_server.tools import pricing as P

    U = "_smoke_disc"
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)
    check("預設身分為個人（牌價）",
          accounts.plan_type(U) == "個人" and accounts.discount_for(U, "AI-Trust") == 1.0)
    accounts.set_profile(U, "國科會")
    check("設定身分後折扣生效（國科會 AI-Trust 5折）",
          accounts.plan_type(U) == "國科會" and accounts.discount_for(U, "AI-Trust") == 0.5)
    check("同身分兩區折扣不同（學術：AI-Cloud 7折 / AI-Trust 5折）",
          settings.discount_rate("AI-Cloud", "學術") == 0.7
          and settings.discount_rate("AI-Trust", "學術") == 0.5)
    check("非法計畫別退回預設",
          accounts.set_profile(U, "亂填")["plan_type"] == settings.DEFAULT_PLAN_TYPE)

    accounts.set_profile(U, "國科會")
    out = P.estimate_cost("H100.small", 1, 1, "AI-Trust", U)
    check("estimate_cost 依身分套折扣（牌價 174.96 → 實收 87.48）",
          "87.48" in out and "5 折" in out, out.replace(chr(10), " "))
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)


def test_cost_advisor():
    section("成本顧問（磁碟加購 / 預算試算 / 跨區比價 / 成本健檢 / 價目監測）")
    from datetime import datetime, timedelta
    from common import accounts
    from mcp_server.tools import pricing as P
    from mcp_server.tools import vm_lifecycle as vm

    U = "_smoke_disc"
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)

    accounts.set_profile(U, "國科會")
    s_trust = P.estimate_storage_cost(500, "SSD", 1, "AI-Trust", U)
    check("加 500GB SSD（AI-Trust 單一價，國科會也不折）",
          "770.00" in s_trust and "單一價" in s_trust, s_trust.replace(chr(10), " "))
    s_cloud = P.estimate_storage_cost(500, "SSD", 1, "AI-Cloud", U)
    check("加 500GB SSD（AI-Cloud 儲存亦適用折扣，國科會 5 折 $695）",
          "695.00" in s_cloud and "1390.00" in s_cloud, s_cloud.replace(chr(10), " "))
    check("不支援的磁碟類型被擋", "不支援" in P.estimate_storage_cost(100, "NVMe", 1, "AI-Trust", U))

    ec = P.estimate_cost("H100.small", 24, 30, "AI-Trust", U, disk_gb=100, disk_type="HDD")
    check("estimate_cost 帶磁碟會列出加購磁碟與合計",
          "加購磁碟" in ec and "合計實收" in ec, ec.replace(chr(10), " "))

    pb = P.plan_budget(50000, "H100.small", "AI-Trust", 24, U)
    check("plan_budget：5 萬預算能跑 H100 約 23.8 天（國科會折後）",
          "23.8 天" in pb and "87.48" in pb, pb.replace(chr(10), " "))
    check("plan_budget 預算需大於 0", "大於 0" in P.plan_budget(0, "H100.small", "AI-Trust", 24, U))

    accounts.set_profile(U, "個人")
    cr = P.compare_regions("H200.small", 24, 30, U)
    check("compare_regions：H200 兩區並列且指出最省一區",
          "最省" in cr and "AI-Cloud" in cr and "AI-Trust" in cr, cr.replace(chr(10), " "))
    check("compare_regions：只在一區的方案給提示",
          "只在" in P.compare_regions("H100.small", 24, 30, U))

    accounts.set_profile(U, "個人")
    vm.create_vm("Basic.small", "idle-box", region="AI-Trust", user_id=U)
    with vm.storage.file_lock(vm._vm_csv(U)):
        rows = vm._read_vms(U)
        rows[0]["計費起點"] = (datetime.now() - timedelta(hours=48)).strftime(vm._FMT)
        vm._write_vms(U, rows)
    ss = vm.suggest_savings(U, business_hours=8)
    check("suggest_savings 給出每月可省金額與連續運行旗標",
          "月省" in ss and "可省" in ss and "連續運行" in ss, ss.replace(chr(10), " "))
    check("suggest_savings：無運行機器時回沒有可優化",
          "沒有運行中" in vm.suggest_savings("_smoke_bob", 8))
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)

    import pricing_watch as pw
    html1 = ('<html><body><p>暫定價格</p>'
             '<img src="data:image/png;base64,AAAABBBBCCCC"></body></html>')
    html2 = ('<html><body><p>正式公告價格</p>'
             '<img src="data:image/png;base64,ZZZZYYYYXXXX"></body></html>')
    fp1, fp2 = pw._extract(html1), pw._extract(html2)
    check("pricing_watch 能抽出 base64 圖片並算 hash",
          fp1["image_count"] == 1 and len(fp1["image_hashes"]) == 1)
    check("pricing_watch 偵測到圖片與文字變動", len(pw._diff(fp1, fp2)) >= 2)
    check("pricing_watch 相同內容無變動", pw._diff(fp1, fp1) == [])

    from mcp_server.tools.optimize import optimize_plan_mix
    from mcp_server.tools import optimize as OPT
    accounts.set_profile(U, "個人")
    out = optimize_plan_mix(vcpu=32, memory_gb=64, days=30, region="AI-Trust", user_id=U)
    check("optimize_plan_mix 回覆含最省組合與單一方案對照",
          "最省組合" in out and "對照" in out, out.replace(chr(10), " ")[:100])
    check("回覆標明求解器（MILP Solver 或內建分支定界）", "求解：" in out,
          out.replace(chr(10), " ")[:120])
    milp = OPT._solve_milp(
        OPT._candidate_plans("AI-Trust", False, U)[0], 32, 64, 0, 720, 0, 8)
    if milp is not None:
        check("MILP Solver 求得可行解且與內建分支定界一致",
              milp[1] is not None
              and abs(milp[0] - OPT._solve(
                  OPT._candidate_plans("AI-Trust", False, U)[0],
                  32, 64, 0, 720, 0, 8)[0]) < 1e-6,
              (milp[0], OPT.MILP_STATS))
    else:
        check("無 MILP solver 時退回內建分支定界（完整搜尋）",
              OPT._solve(OPT._candidate_plans("AI-Trust", False, U)[0],
                         32, 64, 0, 720, 0, 8)[2] is True)
    check("未給任何需求時friendly 擋下",
          "請至少提供一項資源需求" in optimize_plan_mix(user_id=U))
    out_d = optimize_plan_mix(vcpu=32, memory_gb=64, disk_gb=500,
                              region="AI-Trust", user_id=U)
    check("帶 disk_gb 時回覆含磁碟需求與加購明細",
          "磁碟 ≥ 500GB" in out_d and "加購磁碟" in out_d,
          out_d.replace(chr(10), " ")[:140])
    check("磁碟為連續變數（模型成為真正的 Mixed-Integer）",
          OPT.to_milp(OPT._candidate_plans("AI-Trust", False, U)[0],
                      32, 64, 0, 720, 0, 8, 500, 0.002)["integrality"][-1] == 0)
    out_thr = optimize_plan_mix(vcpu=64, memory_gb=256, region="AI-Trust", user_id=U)
    check("混搭省不到 3% 時改推單一機型並說明原因",
          "單一機型" in out_thr and "為什麼不推薦混搭" in out_thr,
          out_thr.replace(chr(10), " ")[:140])
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)


def test_wallet():
    section("錢包（餘額 / 儲值 / 扣抵 / burn rate 剩餘天數）")
    from datetime import datetime, timedelta
    from common import accounts, wallet
    from mcp_server.tools import vm_lifecycle as vm
    from mcp_server.tools import wallet as wt

    U = "_smoke_disc"
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)
    accounts.set_profile(U, "國科會")

    check("空錢包餘額為 0", wallet.balance(U) == 0.0)
    check("空錢包交易明細友善提示", "沒有任何交易" in wt.list_transactions(20, U))

    out = wt.top_up_wallet(50000, U)
    check("儲值 5 萬後餘額 $50,000", "50,000.00" in out and wallet.balance(U) == 50000.0,
          out.replace(chr(10), " "))
    check("儲值金額需大於 0", "大於 0" in wt.top_up_wallet(0, U))

    vm.create_vm("H100.small", "wallet-box", region="AI-Trust", user_id=U)
    with vm.storage.file_lock(vm._vm_csv(U)):
        rows = vm._read_vms(U)
        rows[0]["計費起點"] = (datetime.now() - timedelta(hours=10)).strftime(vm._FMT)
        vm._write_vms(U, rows)

    bal_view = wt.get_wallet_balance(U)
    check("餘額檢視含每日燃燒率與預估可用天數（pending≈$874.80）",
          "每日燃燒率" in bal_view and "預估可用" in bal_view and "874" in bal_view,
          bal_view.replace(chr(10), " "))

    stop_msg = vm.stop_vm("wallet-box", U)
    check("關機時把運行費用從錢包扣抵",
          "從錢包扣抵" in stop_msg and "874" in stop_msg, stop_msg.replace(chr(10), " "))
    check("扣抵後餘額 ≈ $49,125.20", 49124.0 < wallet.balance(U) < 49126.5,
          f"bal={wallet.balance(U)}")

    txns = wt.list_transactions(20, U)
    check("交易明細含儲值與扣抵兩筆",
          "儲值" in txns and "扣抵" in txns and "50,000.00" in txns,
          txns.replace(chr(10), " "))

    idle_view = wt.get_wallet_balance(U)
    check("無運行機器時餘額檢視標示無燃燒",
          "無燃燒" in idle_view or "不會減少" in idle_view, idle_view.replace(chr(10), " "))

    acct = vm.get_account_bill(U)
    check("get_account_bill 帳單尾顯示錢包餘額", "錢包餘額" in acct, acct.replace(chr(10), " "))

    shutil.rmtree(settings.user_dir(U), ignore_errors=True)


_SMOKE_PROJECTS = """\
project_id,計畫名稱,類別代碼,狀態,核定額度,起始日,結束日,管理者,成員,\
quota_gpu,quota_vcpu,quota_memory_gb,quota_storage_gb,quota_vm
SMK-MST-001,冒煙測試國科會計畫,MST,active,100000,2026-01-01,2026-12-31,\
_smoke_alice,"_smoke_alice,_smoke_bob",1,96,512,240,2
SMK-ACD-002,冒煙測試學術計畫,ACD,active,50000,2026-01-01,2026-12-31,\
_smoke_alice,_smoke_alice,4,384,2048,960,4
SMK-ENT-003,冒煙測試到期計畫,ENT,expired,10000,2025-01-01,2025-12-31,\
_smoke_bob,_smoke_bob,4,384,2048,960,4
"""


def test_projects_and_quota():
    section("計畫 / Quota（身分從計畫讀 + 額度控管）")
    from common import accounts, projects
    from mcp_server.tools import projects as pj
    from mcp_server.tools import vm_lifecycle as vm

    saved_csv = settings.PROJECTS_CSV
    tmp_csv = os.path.join(tempfile.mkdtemp(prefix="smoke_proj_"), "projects.csv")
    with open(tmp_csv, "w", encoding="utf-8") as f:
        f.write(_SMOKE_PROJECTS)
    settings.PROJECTS_CSV = tmp_csv

    A, B, N = "_smoke_alice", "_smoke_bob", "_smoke_disc"
    for u in (A, B, N):
        shutil.rmtree(settings.user_dir(u), ignore_errors=True)

    try:
        check("計畫載入且成員關係正確（alice 2 個 / bob 2 個）",
              [p["project_id"] for p in projects.for_user(A)] == ["SMK-MST-001", "SMK-ACD-002"]
              and len(projects.for_user(B)) == 2,
              [p["project_id"] for p in projects.for_user(A)])

        prof = accounts.get_profile(A)
        check("身分來源＝計畫（MST → 國科會，非自選）",
              prof["plan_source"] == "project" and prof["plan_type"] == "國科會"
              and prof["project_id"] == "SMK-MST-001", prof)
        accounts.set_profile(A, "企業")
        check("有計畫時自選身分不覆蓋計畫類別", accounts.plan_type(A) == "國科會",
              accounts.plan_type(A))

        accounts.set_profile(N, "學術")
        pn = accounts.get_profile(N)
        check("無計畫帳號退回自選身分（相容）",
              pn["plan_source"] == "self" and pn["plan_type"] == "學術", pn)

        check("切換計畫改變折扣（AI-Cloud 國科會 0.5）",
              accounts.discount_for(A, "AI-Cloud") == 0.5)
        okk, _ = accounts.set_current_project(A, "SMK-ACD-002")
        check("切換到自己的計畫成功且折扣改為學術 7 折",
              okk and accounts.plan_type(A) == "學術"
              and accounts.discount_for(A, "AI-Cloud") == 0.7)
        okk, msg = accounts.set_current_project(B, "SMK-ACD-002")
        check("切換到非成員計畫被拒絕", (not okk) and "不是計畫" in msg, msg)
        accounts.set_current_project(A, "SMK-MST-001")

        out = vm.create_vm("H100.small", "quota-box", region="AI-Trust", user_id=A)
        check("建立 VM 掛在計畫底下並顯示額度",
              "SMK-MST-001" in out and "計畫額度" in out, out.replace(chr(10), " "))
        snap = vm.project_snapshot("SMK-MST-001")
        check("額度用量由 VM 規格即時加總（GPU 1 / vCPU 96）",
              snap["usage"]["gpu"] == 1 and snap["usage"]["vcpu"] == 96, snap["usage"])

        blocked = vm.create_vm("H100.small", "over-quota", region="AI-Trust", user_id=A)
        check("Quota 不足時擋下建立並指出不足項目",
              "無法建立" in blocked and "GPU" in blocked and "Quota 不足" in blocked,
              blocked.replace(chr(10), " "))

        vm.stop_vm("quota-box", A)
        check("已關機的機器仍佔用額度",
              vm.project_snapshot("SMK-MST-001")["usage"]["gpu"] == 1)
        vm.delete_vm("quota-box", A)
        check("刪除後額度釋放",
              vm.project_snapshot("SMK-MST-001")["usage"]["gpu"] == 0)

        accounts.set_current_project(B, "SMK-ENT-003")
        exp = vm.create_vm("Basic.small", "x", region="AI-Trust", user_id=B)
        check("到期計畫無法開立新資源", "無法建立" in exp and "expired" in exp,
              exp.replace(chr(10), " "))

        vm.create_vm("H100.small", "warn-box", region="AI-Trust", user_id=A)
        q = pj.get_quota("", A)
        check("get_quota 顯示用罄警示與剩餘", "已用罄" in q and "剩餘" in q,
              q.replace(chr(10), " ")[:120])
        check("非成員查別人的計畫額度被拒絕",
              "不是計畫" in pj.get_quota("SMK-ACD-002", B))
        check("list_projects 標示目前使用中的計畫",
              "★" in pj.list_projects(A) and "SMK-MST-001" in pj.list_projects(A))
        check("無計畫者查額度得到清楚說明",
              "沒有參與任何計畫" in pj.get_quota("", N))
    finally:
        settings.PROJECTS_CSV = saved_csv
        shutil.rmtree(os.path.dirname(tmp_csv), ignore_errors=True)
        for u in (A, B, N):
            shutil.rmtree(settings.user_dir(u), ignore_errors=True)


def test_user_behavior_isolation():
    section("查詢歷史（使用者隔離）")
    from mcp_server.tools import user_behavior as ub

    U, B = "_smoke_alice", "_smoke_bob"
    ub.log_query("報價查詢", "H100", "H100.small", "smoke", U)
    ha, hb = ub.get_user_history(user_id=U), ub.get_user_history(user_id=B)
    check("alice 的歷史寫入成功", "H100" in ha)
    check("使用者隔離：bob 看不到 alice 的歷史", "尚無查詢記錄" in hb)
    check("get_recommendations 反映 alice 記錄", "H100" in ub.get_recommendations(U))

    import csv as _csv
    from agent import providers as _prov
    from common import workload as _wl

    check("負載分桶符合論文 3×3 結構",
          _wl.bucket(2455, 18) == "長輸入/短輸出"
          and _wl.bucket(496, 510) == "短輸入/長輸出"
          and _wl.bucket(824, 253) == "中輸入/中輸出",
          (_wl.bucket(2455, 18), _wl.bucket(496, 510), _wl.bucket(824, 253)))

    _old = getattr(_prov, "LAST_USAGE", (0, 0))
    _prov.LAST_USAGE = (2455, 18)
    ub.log_query("報價查詢", "H200", "H200.small", "tok", U)
    _prov.LAST_USAGE = _old
    with open(settings.user_history_csv(U), "r", encoding="utf-8") as _f:
        _rows = list(_csv.DictReader(_f))
    check("log_query 自動寫入 token 數與負載類型",
          _rows[-1].get("輸入tokens") == "2455"
          and _rows[-1].get("負載類型") == "長輸入/短輸出",
          _rows[-1])

    C = "_smoke_carol"
    _p = settings.user_history_csv(C)
    os.makedirs(os.path.dirname(_p), exist_ok=True)
    with open(_p, "w", newline="", encoding="utf-8") as _f:
        _w = _csv.writer(_f)
        _w.writerow(["時間", "查詢類型", "關鍵字", "選擇方案", "備註"])
        _w.writerow(["2026-01-01 00:00:00", "報價查詢", "舊資料", "CPU.small", "old"])
    ub.log_query("方案推薦", "新資料", "CPU.large", "new", C)
    with open(_p, "r", encoding="utf-8") as _f:
        _cr = list(_csv.reader(_f))
    check("舊格式歷史檔就地升級為 8 欄且保留原資料",
          _cr[0] == ub._HEADER and len(_cr) == 3
          and _cr[1][2] == "舊資料" and len(_cr[1]) == 8,
          (_cr[0], _cr[1] if len(_cr) > 1 else None))
    shutil.rmtree(settings.user_dir(C), ignore_errors=True)


def test_knowledge_base():
    section("知識客服（KB 擴充 / 多類別檢索 / 匯入冪等 / 命中率不降）")
    import csv as _csv
    from rag import faq

    items = faq._load_faq()
    check("知識庫已明顯擴充（≥60 條）", len(items) >= 60, f"faq.csv={len(items)} 條")

    cases = [
        ("計畫快到期想延長使用", "續用"),
        ("我報帳需要發票怎麼拿", "發票"),
        ("我要申購更多運算額度怎麼下訂單", "訂單"),
        ("台灣杉三號的硬碟空間怎麼算錢", "100GB"),
        ("平台上怎麼載入我要的軟體套件", "module"),
        ("要怎麼 ssh 進去運算主機", "SSH"),
        ("登入密碼忘記了要怎麼重設", "重設"),
        ("服務有沒有服務水準保障", "SLA"),
    ]
    ok_all = True
    for q, kw in cases:
        hits = faq.retrieve(q, top_k=2)
        hit = any(kw in h["answer"] or kw in h["question"] for h in hits)
        ok_all = ok_all and hit
        if not hit:
            check(f"新類別檢索：{q[:12]}… →「{kw}」", False)
    check("9 大新類別各抽一題皆檢索得到", ok_all)

    check("庫外問題仍回退（不亂塞）", faq.retrieve("推薦台南好吃的牛肉湯", top_k=2) == [])

    seed_path = str(settings.DATA_DIR / "faq_seed_nchc.csv")
    with open(seed_path, encoding="utf-8") as f:
        seed = list(_csv.DictReader(f))
    have = {it["question"] for it in items}
    mergeable = [r for r in seed
                 if "圖片型" not in (r.get("關鍵字") or "")
                 and (r.get("問題") or "").strip()]
    dup = sum(1 for r in mergeable if (r.get("問題") or "").strip() in have)
    check("匯入冪等：種子可併題已全部在庫（重跑不重複）", dup == len(mergeable),
          f"{dup}/{len(mergeable)} 已在庫")
    img = sum(1 for r in seed if "圖片型" in (r.get("關鍵字") or ""))
    check("圖片型條目未併入（待人工）", img >= 1 and all(
        r["問題"].strip() not in have for r in seed if "圖片型" in (r.get("關鍵字") or "")),
          f"圖片型 {img} 條")


def test_prompt_covers_tools():
    section("工具可達性（註冊表 vs system prompt 不得漂移）")
    import asyncio
    import mcp_server.server as S
    from prompt.system_prompt import SYSTEM_PROMPT
    from agent.tools import USER_SCOPED_TOOLS, REGION_SCOPED_TOOLS

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    registered = [t.name for t in asyncio.run(S.mcp.list_tools())]

    undocumented = [t for t in registered if t not in SYSTEM_PROMPT]
    check("每個註冊的工具都寫進 system prompt（否則 LLM 看不到）",
          not undocumented, f"漏掉：{undocumented}")

    import re
    mentioned = set(re.findall(r"^- (\w+)\(", SYSTEM_PROMPT, re.M))
    ghost = sorted(mentioned - set(registered))
    check("system prompt 沒有提到不存在的工具", not ghost, f"幽靈工具：{ghost}")

    stale = sorted((USER_SCOPED_TOOLS | REGION_SCOPED_TOOLS) - set(registered))
    check("USER/REGION_SCOPED_TOOLS 沒有指向不存在的工具", not stale, f"殘留：{stale}")


def test_observability():
    section("可觀測性（工具呼叫記錄 + FAQ 未命中）")
    from common import observability as ob
    from rag import faq

    ob.log_tool_call("_smoke_alice", "create_vm", {"plan": "H100.small"}, True, 12.3, "ok")
    ob.log_tool_call("_smoke_bob", "delete_vm", {"vm_id": "x"}, False, 5.0, "失敗")
    rows = ob.read_tool_calls(10)
    check("工具呼叫已記錄（含成敗/耗時）",
          len(rows) >= 2 and rows[-1]["ok"] is False and rows[-2]["ok"] is True)

    before = len(ob.read_faq_misses())
    out = faq.search_faq("請問今天午餐吃什麼比較好", user_id="_smoke_alice")
    after_miss = ob.read_faq_misses()
    check("FAQ 查無相關 → 記錄未命中（含後端）",
          "查無相關" in out and len(after_miss) == before + 1
          and after_miss[-1]["backend"], after_miss[-1] if after_miss else None)

    n_before = len(ob.read_faq_misses())
    faq.search_faq("H100 適合什麼用途", user_id="_smoke_alice")
    check("FAQ 命中 → 不記錄未命中", len(ob.read_faq_misses()) == n_before)

    hit_ctx = "以下是知識庫中最相關的說明。Q1：什麼是可信賴雲？"
    n0 = len(ob.read_faq_misses())
    logged = ob.maybe_log_weak_faq_miss("你們有 K8s 代管嗎", hit_ctx,
                                        {"ok": False, "score": 0.0}, "_smoke_alice")
    check("弱相關+接不了地 → 補記未命中", logged and len(ob.read_faq_misses()) == n0 + 1)
    n1 = len(ob.read_faq_misses())
    ob.maybe_log_weak_faq_miss("x", hit_ctx, {"ok": True}, "_smoke_alice")
    ob.maybe_log_weak_faq_miss("x", "知識庫中查無相關說明…", {"ok": False}, "_smoke_alice")
    ob.maybe_log_weak_faq_miss("x", None, None, "_smoke_alice")
    check("接地／查無相關／未走 FAQ → 不重複記", len(ob.read_faq_misses()) == n1)


def test_flask_endpoints():
    section("Flask 端點（web + admin）")
    import web

    c = web.app.test_client()
    check("GET / 回 200", c.get("/").status_code == 200)
    st = c.get("/status").get_json()
    check("GET /status 有 llm 與 kind", "llm" in st and "kind" in st, st)
    check("GET /admin 回 200", c.get("/admin").status_code == 200)

    prov = c.get("/api/llm/providers").get_json()
    keys_ok = all(set(["id", "label", "status", "detail"]) <= set(p) for p in prov["providers"])
    check("GET /api/llm/providers 結構正確且含全部供應商",
          keys_ok and len(prov["providers"]) == len(settings.LLM_PROVIDERS))

    enabled = [p["id"] for p in settings.LLM_PROVIDERS if p["enabled"]]
    if enabled:
        sw = c.post("/api/llm/switch", json={"id": enabled[0]}).get_json()
        check("POST /api/llm/switch 有效供應商成功", sw["ok"] and "status" in sw)
    bad = c.post("/api/llm/switch", json={"id": "____bogus____"}).get_json()
    check("POST /api/llm/switch 無效供應商被拒絕", not bad["ok"])

    prof = c.post("/api/profile", json={"plan_type": "學術"},
                  headers={"X-User-Id": "_smoke_alice"}).get_json()
    prof2 = c.get("/api/profile", headers={"X-User-Id": "_smoke_alice"}).get_json()
    check("POST/GET /api/profile 設定並讀回帳號身分",
          prof.get("ok") and prof2.get("plan_type") == "學術")

    pj = c.get("/api/projects", headers={"X-User-Id": "_smoke_alice"}).get_json()
    check("GET /api/projects 結構正確（計畫清單＋目前選用）",
          isinstance(pj.get("projects"), list) and "current" in pj, pj)
    bad_pj = c.post("/api/project", json={"project_id": "____nope____"},
                    headers={"X-User-Id": "_smoke_alice"})
    check("POST /api/project 無效計畫被拒絕（400）",
          bad_pj.status_code == 400 and not bad_pj.get_json()["ok"])
    check("首頁含計畫選擇器（身分由計畫決定）",
          "project-select" in c.get("/").get_data(as_text=True))

    ov = c.get("/api/admin/overview").get_json()
    struct = set(["llm", "users", "grand_total", "tool_calls", "faq_misses"]) <= set(ov)
    check("GET /api/admin/overview 結構正確", struct, list(ov.keys()))
    uids = [u["user_id"] for u in ov["users"]]
    check("admin 總覽含測試使用者的隔離資料", "_smoke_alice" in uids, uids)


def test_live_mcp():
    section("Live：MCP Client → Server 實際呼叫工具")
    import asyncio
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from mcp_client.client import get_client
    from agent import tools as agent_tools

    U = "_smoke_live"
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)

    async def run():
        async with get_client() as client:
            tools = await client.list_tools()
            check("list_tools 回傳 30 個工具", len(tools) == 30, f"實際 {len(tools)}")

            ok, r = await agent_tools.call_tool(client, "create_vm",
                                                {"plan": "H100.small", "name": "live-gpu"}, U)
            check("透過 MCP 建立 VM 成功", ok and "vm-0001" in r, r[:60])

            ok, r = await agent_tools.call_tool(client, "list_vms", {}, U)
            check("透過 MCP 列出 VM（隔離到 _smoke_live）", ok and "live-gpu" in r)

            ok, r = await agent_tools.call_tool(client, "get_account_bill", {}, U)
            check("透過 MCP 查帳單", ok and "總費用" in r)

            ok, r = await agent_tools.call_tool(client, "delete_vm", {"vm_id": "vm-0001"}, U)
            check("透過 MCP 刪除 VM", ok and "不可復原" in r)

    try:
        asyncio.run(run())
    except Exception as e:
        check("連上 MCP Server", False, f"{type(e).__name__}: {e}（請先啟動 uvicorn mcp_server.server:app）")


def test_live_llm():
    section("Live：實際向目前選用的 LLM 送一次生成")
    from agent import providers as P
    try:
        txt = P.chat([
            {"role": "system", "content": "你是測試助手，只回一個字。"},
            {"role": "user", "content": "請回覆：OK"},
        ])
        used = P.LAST_USED[1] if P.LAST_USED else "?"
        check(f"LLM 生成成功（實際由 {used} 回答）", bool(txt and txt.strip()), repr(txt)[:60])
    except Exception as e:
        check("至少一家 LLM 可用", False, f"{type(e).__name__}: {e}")


def main():
    argv = sys.argv[1:]
    do_live = "--live" in argv
    do_llm = "--llm" in argv

    print("=" * 56)
    print("  可信賴雲 AI Agent — 自動化 smoke test")
    print(f"  模式：離線" + ("＋Live-MCP" if do_live else "") + ("＋Live-LLM" if do_llm else ""))
    print("=" * 56)

    tmp = tempfile.mkdtemp(prefix="smoke_")
    saved = (settings.TOOL_CALL_LOG, settings.FAQ_MISS_LOG, settings.LLM_STATE_FILE)
    settings.TOOL_CALL_LOG = os.path.join(tmp, "tool_calls.jsonl")
    settings.FAQ_MISS_LOG = os.path.join(tmp, "faq_misses.jsonl")
    settings.LLM_STATE_FILE = os.path.join(tmp, "llm_state.json")

    try:
        _cleanup_users()
        test_provider_state_machine()
        test_vm_lifecycle_and_billing()
        test_region_pricing()
        test_account_discount()
        test_cost_advisor()
        test_wallet()
        test_projects_and_quota()
        test_knowledge_base()
        test_user_behavior_isolation()
        test_prompt_covers_tools()
        test_observability()
        test_flask_endpoints()
        if do_live:
            test_live_mcp()
        if do_llm:
            test_live_llm()
    finally:
        _cleanup_users()
        settings.TOOL_CALL_LOG, settings.FAQ_MISS_LOG, settings.LLM_STATE_FILE = saved
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 56)
    print(f"  結果：通過 {_PASS}　失敗 {_FAIL}")
    print("=" * 56)
    if not do_live:
        print("  提示：加 --live 可測 MCP Client→Server；加 --llm 可測真實 LLM 生成")
    sys.exit(1 if _FAIL else 0)


if __name__ == "__main__":
    main()
