"""論文 MILP 實驗
E1  以論文 §4.2 例子重現其報告的 makespan
E2  以完整模型求全域最佳（附錄 F binary search on T）
E3  化簡後模型與上線實作 optimize.to_milp() 逐項比對
E4  以實測 h(c,w) 與累積 f_w 代入同一組式子求解
"""
import argparse
import csv
import datetime
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import workload

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RULE = "=" * 78














class Config:

    def __init__(self, name, v, s, h):
        self.name = name
        self.v = v
        self.s = s
        self.h = h

    def cost(self, prices):
        """o_c = Σ_n ( d_n(c) × p_n )"""
        return sum(k * prices[n] for n, k in self.v.items())

    def gpus(self):
        return sum(self.v.values())

    def mem(self, mems):
        """附錄 D 記憶體檢查用：Σ_n ( d_n(c) × m_n )"""
        return sum(k * mems[n] for n, k in self.v.items())


def build_full_milp(configs, prices, avails, f, budget, T_hat):
    C, W, N = len(configs), len(f), len(prices)
    nv = C + C * W

    def xi(c, w):
        return C + c * W + w

    rows, lb, ub, names = [], [], [], []

    for w in range(W):
        r = [0.0] * nv
        for c in range(C):
            r[xi(c, w)] = 1.0
        rows.append(r); lb.append(1.0); ub.append(1.0)
        names.append(f"(2) 負載 w{w+1} 須 100% 被服務")

    for c, cfg in enumerate(configs):
        r = [0.0] * nv
        r[c] = -float(T_hat)
        for w in range(W):
            r[xi(c, w)] = f[w] / cfg.h[w]
        rows.append(r); lb.append(-math.inf); ub.append(0.0)
        names.append(f"(3) 配置 {cfg.name} 的完成時間 ≤ T̂")

    for c, cfg in enumerate(configs):
        for w in range(W):
            r = [0.0] * nv
            r[xi(c, w)] = 1.0
            r[c] = -1.0
            rows.append(r); lb.append(-math.inf); ub.append(0.0)
            names.append(f"(4) {cfg.name} 未啟用則不可分派 w{w+1}")

    r = [0.0] * nv
    for c, cfg in enumerate(configs):
        r[c] = cfg.cost(prices)
    rows.append(r); lb.append(-math.inf); ub.append(float(budget))
    names.append("(5) 預算上限 B")

    for n in range(N):
        r = [0.0] * nv
        for c, cfg in enumerate(configs):
            r[c] = float(cfg.v.get(n, 0))
        rows.append(r); lb.append(-math.inf); ub.append(float(avails[n]))
        names.append(f"(6) GPU 型號 t{n+1} 庫存 ≤ {avails[n]}")

    return {
        "A": rows, "lb": lb, "ub": ub, "names": names,
        "c": [cfg.cost(prices) for cfg in configs] + [0.0] * (C * W),
        "integrality": [1] * C + [0] * (C * W),
        "var_lb": [0.0] * nv,
        "var_ub": [float(max(avails))] * C + [1.0] * (C * W),
        "n_y": C, "n_x": C * W,
    }


def solve_feasibility(model):
    try:
        import numpy as np
        from scipy.optimize import milp, LinearConstraint, Bounds
    except Exception:
        return None, None, None

    res = milp(
        c=np.array(model["c"], dtype=float),
        constraints=LinearConstraint(np.array(model["A"], dtype=float),
                                     np.array(model["lb"], dtype=float),
                                     np.array(model["ub"], dtype=float)),
        integrality=np.array(model["integrality"]),
        bounds=Bounds(np.array(model["var_lb"], dtype=float),
                      np.array(model["var_ub"], dtype=float)),
    )
    if not res.success or res.x is None:
        return False, None, None
    ny = model["n_y"]
    return True, [int(round(v)) for v in res.x[:ny]], list(res.x[ny:])


def binary_search_T(configs, prices, avails, f, budget, tol=0.01):
    lo = 0.0
    hi = sum(f[w] / min(cfg.h[w] for cfg in configs) for w in range(len(f)))
    for _ in range(40):
        m = build_full_milp(configs, prices, avails, f, budget, hi)
        ok, _, _ = solve_feasibility(m)
        if ok:
            break
        hi *= 2
    else:
        return None, None, None

    best = None
    while hi - lo > tol:
        mid = (lo + hi) / 2
        m = build_full_milp(configs, prices, avails, f, budget, mid)
        ok, y, x = solve_feasibility(m)
        if ok:
            hi = mid
            best = (mid, y, x)
        else:
            lo = mid
    return best if best else (None, None, None)


def paper_example():
    return {
        "prices": [4.0, 2.0, 2.0],
        "avails": [2, 2, 2],
        "mems": [80, 48, 24],
        "f": [80.0, 20.0],
        "budget": 8.0,
        "configs": [
            Config("c1 = 1×t1",     {0: 1}, (1,), [1.0, 1.2]),
            Config("c2 = 1×t2",     {1: 1}, (1,), [0.9, 0.9]),
            Config("c3 = 1×t3",     {2: 1}, (1,), [0.3, 0.5]),
            Config("c4 = TP(2×t2)", {1: 2}, (2,), [2.4, 1.5]),
        ],
    }














_IN_REP = {"短": 496, "中": 824, "長": 2455}
_OUT_REP = {"短": 18, "中": 253, "長": 510}


def load_profile(path):
    if not os.path.exists(path):
        return None, f"找不到 {path}——請先在能連到 vLLM 的機器上跑 paper/profile_vllm.py --run"
    with open(path, "r", encoding="utf-8") as fh:
        d = json.load(fh)
    if d.get("contaminated"):
        return d, "這份量測期間偵測到其他請求，**不可用於正式引用**"
    return d, None


def load_fw(path):
    if not os.path.exists(path):
        return None
    counts = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                i, o = int(row.get("輸入tokens") or 0), int(row.get("輸出tokens") or 0)
                if not i and not o:
                    continue
                label = workload.bucket(i, o)
                a, b = label.split("/")
                key = (_IN_REP[a[0]], _OUT_REP[b[0]])
                counts[key] = counts.get(key, 0) + 1
    except Exception as e:
        print(f"  讀 {path} 失敗：{e}")
        return None
    return counts or None


def load_fw_json(path):
    if not path or not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        counts = {}
        for k, v in (d.get("f_w") or {}).items():
            i, o = (int(x) for x in k.split(","))
            counts[(i, o)] = float(v)
        return (counts or None), d
    except Exception as e:
        print(f"  ⚠️ 讀 {path} 失敗：{e}")
        return None, None




DEFAULT_PROFILES = ["paper/vllm_profile_sat.json", "paper/vllm_profile.json"]


def profile_provenance(path=None):
    path = path or find_profile()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        return None
    sn = d.get("snapshot") or {}
    meta = d.get("h_c_w_meta") or {}
    at = (sn.get("measured_at") or "")[:10] or "時間未記錄"
    return {
        "path": os.path.relpath(path, os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))).replace(os.sep, "/"),
        "measured_at": at,
        "endpoint": sn.get("endpoint", "?"),
        "model": sn.get("model_served") or sn.get("model_requested") or "?",
        "n_measured": len(d.get("h_c_w") or {}),
        "saturated": bool(d.get("all_saturated")),
        "lower_bound": any(m.get("is_lower_bound") for m in meta.values()),
        "refit": bool(d.get("refit")),
        "refit_at": datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat(),
    }


def find_profile():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for rel in DEFAULT_PROFILES:
        full = os.path.join(base, rel)
        if os.path.exists(full):
            return full
    return None



# ---- 實驗 --------------------------------------------------------
RESULTS = []
PAPER_T = 28.67          # 論文 §4.2 Case 3 報告值


def head(tag, title):
    print("\n[%s] %s" % (tag, title))
    print(RULE)


def result(tag, ok, detail=""):
    RESULTS.append((tag, ok))
    print("  %s  %s" % ("PASS" if ok else "FAIL", detail))


def e1_reproduce(ex):
    """E1：以論文 §4.2 例子重現其報告的 makespan。"""
    prices, f, configs = ex["prices"], ex["f"], ex["configs"]
    W, C = len(f), len(configs)
    head("E1", "論文 §4.2 例子重現")
    print("  N=%d W=%d |C|=%d B=%s" % (len(prices), W, C, ex["budget"]))
    print("  p_n=%s  a_n=%s  m_n=%s  f_w=%s" % (prices, ex["avails"], ex["mems"], f))
    for c in configs:
        print("    %-14s o_c=%4.0f  h_c,w=%s" % (c.name, c.cost(prices), c.h))
    m = build_full_milp(configs, prices, ex["avails"], f, ex["budget"], T_hat=30.0)
    print("  變數 %d  約束 %d" % (C + C * W + 1, len(m["A"])))

    y = [1, 0, 0, 1]
    x = [[0.15, 1.0], [0, 0], [0, 0], [0.85, 0.0]]
    T = max(sum(x[c][w] * f[w] / (y[c] * configs[c].h[w]) for w in range(W))
            for c in range(C) if y[c])
    cost = sum(y[c] * configs[c].cost(prices) for c in range(C))
    print("  代入論文 Case 3 方案  T=%.2fs  成本=%.0f  論文報告值=%ss" % (T, cost, PAPER_T))
    result("E1", abs(T - PAPER_T) < 0.01, "delta=%.4fs" % abs(T - PAPER_T))


def e2_optimum(ex):
    """E2：以完整模型求全域最佳 makespan（附錄 F binary search on T）。"""
    prices, f, configs = ex["prices"], ex["f"], ex["configs"]
    W = len(f)
    head("E2", "完整模型全域最佳")
    T, y, x = binary_search_T(configs, prices, ex["avails"], f, ex["budget"])
    if T is None:
        result("E2", False, "scipy 不可用")
        return
    print("  T*=%.2fs  容差 0.01" % T)
    for c, cfg in enumerate(configs):
        if y[c]:
            frac = " ".join("w%d=%.0f%%" % (w + 1, x[c * W + w] * 100)
                            for w in range(W) if x[c * W + w] > 1e-6)
            print("    y[%s]=%d  %s" % (cfg.name.split()[0], y[c], frac))
    used = sum(y[c] * configs[c].cost(prices) for c in range(len(configs)))
    print("  成本=%.0f <= B=%.0f" % (used, ex["budget"]))
    result("E2", used <= ex["budget"] + 1e-9, "T*=%.2fs" % T)


def e3_equivalence():
    """E3：化簡後模型與上線實作 optimize.to_milp() 是否逐項相同。"""
    import shutil
    from config import settings
    from common import accounts
    from mcp_server.tools import optimize as OPT

    head("E3", "化簡模型 vs 上線實作（optimize.to_milp）")
    U = "_milp_check"
    accounts.set_profile(U, "個人")
    need_v, need_m, need_g, K, B, T = 96, 512, 2, 8, 300000, 720
    plans, _, _ = OPT._candidate_plans(settings.DEFAULT_REGION, need_gpu=True, user_id=U)
    actual = OPT.to_milp(plans, need_v, need_m, need_g, T, B, K)

    N = len(plans)
    exp_c = [q["單價"] for q in plans]
    rows, lb, ub = [], [], []
    for key, need in (("vcpu", need_v), ("mem", need_m), ("gpu", need_g)):
        if need > 0:
            rows.append([q[key] for q in plans])
            lb.append(float(need))
            ub.append(math.inf)
    if B > 0 and T > 0:
        rows.append(list(exp_c))
        lb.append(-math.inf)
        ub.append(B / T)
    rows.append([1.0] * N)
    lb.append(-math.inf)
    ub.append(float(K))

    checks = [
        ("變數個數", len(actual["c"]) == N),
        ("目標係數", actual["c"] == exp_c),
        ("約束矩陣 A", actual["A"] == rows),
        ("下界 lb", actual["lb"] == lb),
        ("上界 ub", actual["ub"] == ub),
        ("整數性", actual["integrality"] == [1] * N),
        ("變數下界", actual["var_lb"] == [0] * N),
        ("變數上界", actual["var_ub"] == [K] * N),
    ]
    print("  情境 %d核/%dGB/%dGPU  K=%d  B=%s/%gh  N=%d  約束 %d"
          % (need_v, need_m, need_g, K, format(B, ","), T, N, len(actual["A"])))
    for label, okk in checks:
        print("    %s  %s" % ("ok  " if okk else "DIFF", label))
    shutil.rmtree(settings.user_dir(U), ignore_errors=True)
    passed = sum(1 for _, o in checks if o)
    result("E3", passed == len(checks), "%d/%d 相同" % (passed, len(checks)))


def e4_measured(profile_path, workload_path, price, hours, budget, max_replicas,
                fw_path=None):
    """E4：以實測 h(c,w) 與累積 f_w 代入同一組式子求解。"""
    head("E4", "實測係數代入完整模型")
    prof, warn = load_profile(profile_path)
    if prof is None:
        result("E4", False, warn)
        return
    if warn:
        print("  %s" % warn)

    pv = profile_provenance(profile_path)
    sat = bool(prof.get("all_saturated"))
    if pv:
        refit = ("  refit=" + pv["refit_at"]) if pv["refit"] else ""
        print("  來源 %s  measured_at=%s%s" % (pv["path"], pv["measured_at"], refit))
        print("  模型 %s  飽和=%s  實測點 %d" % (pv["model"], sat, pv["n_measured"]))

    grid = [(i, o) for i in (496, 824, 2455) for o in (18, 253, 510)]
    hg = prof.get("h_grid")
    if not hg:
        result("E4", False, "profile 無 h_grid（舊格式）")
        return
    h_vec, src = [], []
    for w in grid:
        cell = hg.get("%d,%d" % w)
        if not cell:
            result("E4", False, "缺負載類型 %s" % (w,))
            return
        h_vec.append(cell["h"])
        src.append("m" if cell["source"] == "measured" else "i")

    print("  h(c,w)  |C|=1  實測 %d / 內插 %d" % (src.count("m"), src.count("i")))
    for w, h, sc in zip(grid, h_vec, src):
        print("    (%4d,%3d)  %9.4f req/s  %s" % (w[0], w[1], h, sc))
    lm = prof.get("latency_model")
    if lm:
        print("    補值模型 regime=%s  max_err=%.1f%%" % (lm.get("regime"), lm["max_err_pct"]))

    counts = load_fw(workload_path)
    fw_meta = None
    if not counts:
        counts, fw_meta = load_fw_json(fw_path)
    if counts:
        f = [float(counts.get(w, 0)) for w in grid]
        srcname = fw_path if fw_meta else workload_path
    else:
        f = [1.0] * len(grid)
        srcname = "（無資料，各類型等量代入）"
    n = sum(f)
    print("  f_w  來源 %s  n=%s" % (srcname, format(int(n), ",")))
    for w, fw in zip(grid, f):
        if fw:
            pct = ("  %5.1f%%" % (fw / n * 100)) if n else ""
            print("    (%4d,%3d)  %8.0f%s" % (w[0], w[1], fw, pct))
    if fw_meta:
        print("    註：由邊際分布與獨立性假設推得，非量測之聯合分布")
    elif counts and n < 100:
        print("    註：樣本 %.0f 筆，分布尚未穩定" % n)

    budget_h = budget / hours if hours else budget
    print("  p_n=%s $/h  B=%s/%gh=%.2f $/h  副本上限=%d"
          % (price, format(int(budget), ","), hours, budget_h, max_replicas))

    configs = [Config("c1", {0: 1}, (1,), h_vec)]
    T, y, x = binary_search_T(configs, [price], [max_replicas], f, budget_h)
    if T is None:
        result("E4", False, "預算內無可行解")
        return
    avg = ("  平均 %.0f ms/req" % (T / n * 1000)) if n else ""
    print("  解  y=%.0f  成本=%.2f $/h  T=%.1fs%s" % (y[0], y[0] * price, T, avg))
    result("E4", True, "T=%.1fs，|C|=1（論文維度①②需多配置，未涵蓋）" % T)


def main():
    ap = argparse.ArgumentParser(description="論文 MILP 實驗（arXiv:2502.00722 式 1-7）")
    ap.add_argument("--profile", metavar="JSON",
                    help="量測檔；不給則自動尋找 " + " 或 ".join(DEFAULT_PROFILES))
    ap.add_argument("--no-profile", action="store_true", help="略過 E4")
    ap.add_argument("--workload", default="data/workload_log.csv", help="f_w 來源")
    ap.add_argument("--price", type=float, default=174.96, help="p_n（$/h）")
    ap.add_argument("--hours", type=float, default=720, help="預算涵蓋時數")
    ap.add_argument("--budget", type=float, default=300000, help="總預算")
    ap.add_argument("--max-replicas", type=int, default=8, help="式 6 的 a_n")
    ap.add_argument("--fw", metavar="PATH", help="f_w 備援來源")
    args = ap.parse_args()

    print(RULE)
    print("  論文 MILP 實驗　arXiv:2502.00722 式 1-7 ＋ 附錄 D/F")
    print("  " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print(RULE)

    ex = paper_example()
    e1_reproduce(ex)
    e2_optimum(ex)
    e3_equivalence()

    profile = None if args.no_profile else (args.profile or find_profile())
    if profile:
        e4_measured(profile, args.workload, args.price, args.hours,
                    args.budget, args.max_replicas, fw_path=args.fw)
    else:
        why = "--no-profile" if args.no_profile else "找不到量測檔"
        print("\n[E4] 略過（%s）" % why)

    print("\n" + RULE)
    print("  " + "  ".join("%s=%s" % (t, "PASS" if o else "FAIL") for t, o in RESULTS))
    print(RULE)
    return 0 if all(o for _, o in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
