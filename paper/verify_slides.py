import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROFILE = "paper/vllm_profile_sat.json"
TOL = 0.0015

SLIDE_CONC = {
    (496, 18):   {16: 7.693, 32: 8.396, 64: 8.385},
    (824, 253):  {16: 0.945, 32: 0.941, 64: 0.940},
    (2455, 510): {16: 0.379, 32: 0.379, 64: 0.379},
}
SLIDE_GRID = {
    (496, 18): (8.396, "measured"),      (496, 253): (0.945, "interpolated"),
    (496, 510): (0.456, "interpolated"), (824, 18): (6.695, "interpolated"),
    (824, 253): (0.945, "measured"),     (824, 510): (0.450, "interpolated"),
    (2455, 18): (3.391, "interpolated"), (2455, 253): (0.778, "interpolated"),
    (2455, 510): (0.379, "measured"),
}
SLIDE_LOWER_BOUND = [4.00, 0.383, 0.180]
SLIDE_RATIO = 2.1
SLIDE_TOK_RANGE = (150, 240)
SLIDE_MAX_ERR = 11.4


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, PROFILE)
    if not os.path.exists(path):
        print(f"找不到 {PROFILE}")
        return 1
    d = json.load(open(path, encoding="utf-8"))
    recs = {(r["in_tokens"], r["out_tokens"], r["concurrency"]): r
            for r in d["records"]}
    bad = []

    print(f"量測檔 {PROFILE}")
    print(f"  measured_at {d['snapshot'].get('measured_at')}"
          f"　飽和 {d.get('all_saturated')}　refit {d.get('refit')}")

    print("\n① 併發表")
    for (i, o), row in SLIDE_CONC.items():
        for conc, said in row.items():
            r = recs.get((i, o, conc))
            got = r["throughput_rps"] if r else None
            ok = got is not None and abs(got - said) < TOL
            if not ok:
                bad.append(f"併發表 ({i},{o})@{conc}：講稿 {said} vs 檔案 {got}")
            print(f"   ({i:>4},{o:>3}) 併發{conc:>2}　{said:6.3f}　"
                  f"{'✅' if ok else '❌ 檔案為 ' + str(got)}")

    print("\n② 九宮格")
    for (i, o), (said, src) in SLIDE_GRID.items():
        g = d["h_grid"].get(f"{i},{o}", {})
        got, gsrc = g.get("h"), g.get("source")
        ok = got is not None and abs(got - said) < TOL and gsrc == src
        if not ok:
            bad.append(f"九宮格 ({i},{o})：講稿 {said}/{src} vs 檔案 {got}/{gsrc}")
        print(f"   ({i:>4},{o:>3})　{said:6.3f} {src:12}　"
              f"{'✅' if ok else '❌ 檔案為 ' + str(got) + '/' + str(gsrc)}")

    print("\n③ 衍生數字")
    h = d["h_c_w"]
    sat = [h["496,18"], h["824,253"], h["2455,510"]]
    ratio = sum(sat) / sum(SLIDE_LOWER_BOUND)
    ok = abs(ratio - SLIDE_RATIO) < 0.05
    bad += [] if ok else [f"倍數：講稿 {SLIDE_RATIO} vs 算出 {ratio:.2f}"]
    print(f"   平均倍數（平均值之比）　講稿 {SLIDE_RATIO}　算出 {ratio:.2f}　"
          f"{'✅' if ok else '❌'}")

    tok = []
    for k, m in d["h_c_w_meta"].items():
        i, o = map(int, k.split(","))
        r = recs.get((i, o, m["concurrency"]))
        if r:
            tok.append(r["out_tok_per_s"])
    lo, hi = min(tok), max(tok)
    ok = SLIDE_TOK_RANGE[0] - 3 <= lo and hi <= SLIDE_TOK_RANGE[1] + 3
    bad += [] if ok else [f"輸出速率：講稿 {SLIDE_TOK_RANGE} vs 飽和點 {lo:.0f}～{hi:.0f}"]
    print(f"   輸出速率（飽和點）　　講稿 {SLIDE_TOK_RANGE[0]}～{SLIDE_TOK_RANGE[1]}　"
          f"算出 {lo:.0f}～{hi:.0f}　{'✅' if ok else '❌'}")

    err = d["latency_model"].get("max_err_pct")
    ok = err is not None and abs(err - SLIDE_MAX_ERR) < 0.05
    bad += [] if ok else [f"補格誤差：講稿 {SLIDE_MAX_ERR}% vs 檔案 {err}"]
    print(f"   補格模型誤差　　　　　講稿 {SLIDE_MAX_ERR}%　檔案 "
          f"{err:.4f}%　{'✅' if ok else '❌'}")

    print()
    if bad:
        print(f"❌ {len(bad)} 項對不上：")
        for b in bad:
            print(f"   ・{b}")
        return 1
    print("✅ 講稿引用的數字全部與量測檔一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
