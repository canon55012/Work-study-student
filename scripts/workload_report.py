import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import settings          # noqa: E402
from common import workload          # noqa: E402

RULE = "=" * 74
MIN_USEFUL = 100


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true", help="額外輸出 CSV 格式")
    args = ap.parse_args()

    d = workload.distribution()
    print(RULE)
    print("  負載分布 f_w —— 各類請求各佔多少")
    print(RULE)
    print(f"  資料來源：{os.path.relpath(settings.WORKLOAD_CSV, settings.BASE_DIR)}")

    if d["total"] == 0:
        print("\n  尚無紀錄。")
        print("  紀錄會在每次 LLM 生成成功後自動寫入（agent.providers.chat）——")
        print("  跑幾輪 python main.py 或 web 介面之後再回來看。")
        return 0

    print(f"  總筆數 {d['total']:,}　可用 {d['counted']:,}"
          f"　未知 token {d['unknown']:,}"
          + ("（供應商未回 usage）" if d["unknown"] else ""))

    print(f"\n  {'負載類型':<18}{'筆數':>8}{'佔比 f_w':>12}"
          f"{'平均輸入':>12}{'平均輸出':>12}")
    print("  " + "-" * 60)
    order = sorted(d["buckets"].items(), key=lambda kv: -kv[1]["n"])
    for label, b in order:
        print(f"  {label:<18}{b['n']:>8,}{b['ratio'] * 100:>11.1f}%"
              f"{b['in_avg']:>12,.0f}{b['out_avg']:>12,.0f}")

    print("\n  分桶邊界（沿用論文 Figure 3/4 的 3×3 結構，改用區間容納真實流量）")
    print("    輸入　短 <512　中 512–1536　長 ≥1536 tokens")
    print("    輸出　短 <64 　中 64–384 　 長 ≥384  tokens")

    print("\n  解讀")
    print("    長輸入/短輸出 → prefill 吃算力　　短輸入/長輸出 → decode 吃記憶體頻寬")
    print("    論文的核心洞察就是：這兩類該送到不同的 GPU 配置上。")

    if d["counted"] < MIN_USEFUL:
        print(f"\n  樣本只有 {d['counted']} 筆（建議 ≥ {MIN_USEFUL} 筆再引用）。")
        print("     現在的分布還會隨每一筆大幅跳動，不要拿來下結論。")
    else:
        print(f"\n  樣本 {d['counted']:,} 筆，分布已可作為 f_w 的初步估計。")
    if d["unknown"]:
        print(f"  有 {d['unknown']} 筆取不到 token 數（未計入分布）——"
              "通常是供應商回應沒有 usage 欄位。")

    if args.csv:
        print("\n" + RULE)
        print("  CSV（可貼進簡報或試算表）")
        print(RULE)
        print("負載類型,筆數,佔比,平均輸入tokens,平均輸出tokens")
        for label, b in order:
            print(f"{label},{b['n']},{b['ratio']:.4f},"
                  f"{b['in_avg']:.0f},{b['out_avg']:.0f}")

    print("\n  下一步：拿到 h(c,w)（paper/profile_vllm.py）之後，"
          "f_w 與 h(c,w) 一起填進")
    print("          paper/milp.py，論文完整模型就能用真實係數求解。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
