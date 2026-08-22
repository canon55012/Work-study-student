import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper.profile_vllm import load_env, get_text, parse_metrics  # noqa: E402


def get(url, key, timeout=10):
    """取回文字內容，回傳 (狀態碼, 內容)；取不到回 (0, "")。"""
    body = get_text(url, key, timeout=timeout)
    return (200, body) if body else (0, "")


def first(metrics: dict, name: str):
    """取某個指標的第一個樣本值；不存在回 None。"""
    rows = metrics.get(name)
    return rows[0][1] if rows else None

RULE = "=" * 78

IN_EDGES = (512, 1536)
OUT_EDGES = (64, 384)
IN_REP = (496, 824, 2455)
OUT_REP = (18, 253, 510)


def histogram(metrics, name):
    rows = metrics.get(name + "_bucket")
    if not rows:
        return None
    pairs = []
    for labels, v in rows:
        le = None
        for part in labels.strip("{}").split(","):
            if part.strip().startswith("le="):
                le = part.split("=", 1)[1].strip().strip('"')
        if le is None:
            continue
        pairs.append((float("inf") if le in ("+Inf", "Inf") else float(le), v))
    if not pairs:
        return None
    pairs.sort(key=lambda x: x[0])

    bins, prev_le, prev_cum = [], 0.0, 0.0
    for le, cum in pairs:
        n = cum - prev_cum
        if n < 0:
            n = 0.0
        bins.append((prev_le, le, n))
        prev_le, prev_cum = le, cum
    return bins


def split_by_edges(bins, edges):
    out = [0.0, 0.0, 0.0]
    cuts = [0.0, float(edges[0]), float(edges[1]), float("inf")]
    for lo, hi, n in bins:
        if n <= 0:
            continue
        if hi == float("inf"):
            idx = 2 if lo >= cuts[2] else (1 if lo >= cuts[1] else 0)
            out[idx] += n
            continue
        width = hi - lo
        for k in range(3):
            a, b = max(lo, cuts[k]), min(hi, cuts[k + 1])
            if b > a:
                out[k] += n * ((b - a) / width if width > 0 else 1.0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="寫出 f_w JSON（給 paper/milp.py --fw 吃）")
    args = ap.parse_args()

    base, key, model = load_env()
    root = base[:-3].rstrip("/") if base.endswith("/v1") else base

    print(RULE)
    print("  由 /metrics 直方圖推 f_w（唯讀，不送任何負載）")
    print(RULE)
    print(f"  endpoint  {root}/metrics")

    st, body = get(root + "/metrics", key, timeout=10)
    if st != 200 or not body:
        print(f"  取不到 /metrics（HTTP {st}）")
        return 2
    m = parse_metrics(body)

    hin = histogram(m, "vllm:request_prompt_tokens")
    hout = histogram(m, "vllm:request_generation_tokens")
    if not hin or not hout:
        missing = [n for n, h in (("request_prompt_tokens", hin),
                                  ("request_generation_tokens", hout)) if not h]
        print(f"  缺直方圖：{'、'.join(missing)}")
        print("     這版 vLLM 沒開這些指標 → 這條路走不通，只能靠 Agent 實際跑來累積")
        return 2

    n_in, n_out = sum(b[2] for b in hin), sum(b[2] for b in hout)
    s_in = first(m, "vllm:request_prompt_tokens_sum")
    s_out = first(m, "vllm:request_generation_tokens_sum")
    print(f"\n  累積請求數　輸入直方圖 {n_in:,.0f} 筆｜輸出直方圖 {n_out:,.0f} 筆")
    if s_in and n_in:
        print(f"  平均形狀　　輸入 {s_in / n_in:,.0f} tokens、輸出 {s_out / n_out:,.0f} tokens")

    mi = split_by_edges(hin, IN_EDGES)
    mo = split_by_edges(hout, OUT_EDGES)

    def pct(xs):
        t = sum(xs) or 1.0
        return [x / t for x in xs]

    pi, po = pct(mi), pct(mo)
    print(f"\n  輸入邊際分布（切點 {IN_EDGES[0]} / {IN_EDGES[1]}）")
    for lbl, rep, n, p in zip(("短", "中", "長"), IN_REP, mi, pi):
        print(f"    {lbl}輸入（代表點 {rep:>4}）　{n:>10,.0f} 筆　{p * 100:5.1f}%")
    print(f"  輸出邊際分布（切點 {OUT_EDGES[0]} / {OUT_EDGES[1]}）")
    for lbl, rep, n, p in zip(("短", "中", "長"), OUT_REP, mo, po):
        print(f"    {lbl}輸出（代表點 {rep:>4}）　{n:>10,.0f} 筆　{p * 100:5.1f}%")

    total = sum(mi)
    fw = {}
    print(f"\n  九格 f_w（輸入機率 × 輸出機率 × 總筆數）")
    print(f"  {'':>16}{'輸出短':>12}{'輸出中':>12}{'輸出長':>12}")
    for a, (li, rep_i) in enumerate(zip(("短", "中", "長"), IN_REP)):
        row = []
        for b, rep_o in enumerate(OUT_REP):
            n = pi[a] * po[b] * total
            fw[f"{rep_i},{rep_o}"] = n
            row.append(f"{n:>12,.0f}")
        print(f"  {li}輸入 ({rep_i:>4}){''.join(row)}")


    if args.out:
        payload = {
            "source": "vllm_metrics_histogram",
            "endpoint": root,
            "model": model,
            "total_requests": total,
            "in_marginal": dict(zip([str(r) for r in IN_REP], mi)),
            "out_marginal": dict(zip([str(r) for r in OUT_REP], mo)),
            "f_w": fw,
            "assumptions": [
                "輸入長度與輸出長度獨立（vLLM 只有邊際直方圖，無聯合分布）",
                "跨界桶按桶內均勻分布切開",
                "為 vLLM 啟動至今的累積值，非特定時間區間",
            ],
        }
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = args.out if os.path.isabs(args.out) else os.path.join(root_dir, args.out)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print(f"\n  已寫入 {args.out}")
        print(f"  下一步：python paper/milp.py "
              f"--profile paper/vllm_profile_sat.json --fw {args.out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中止（Ctrl-C）。")
        sys.exit(130)
