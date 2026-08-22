import argparse
import json
import os
import random
import re
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RULE = "=" * 78
THIN = "-" * 78

WORKLOADS_FULL = [(i, o) for i in (496, 824, 2455) for o in (18, 253, 510)]
WORKLOADS_QUICK = [(496, 18), (824, 253), (2455, 510)]

SATURATION_GAIN = 0.10


def load_env():
    base = os.getenv("LOCAL_LLM_BASE_URL", "")
    key = os.getenv("LOCAL_LLM_API_KEY", "")
    model = os.getenv("LOCAL_LLM_MODEL", "")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    envf = os.path.join(root, ".env")
    if os.path.exists(envf):
        for line in open(envf, encoding="utf-8", errors="replace"):
            line = line.strip().lstrip("﻿")
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k == "LOCAL_LLM_BASE_URL" and not base:
                base = v
            elif k == "LOCAL_LLM_API_KEY" and not key:
                key = v
            elif k == "LOCAL_LLM_MODEL" and not model:
                model = v
    return (base or "http://140.110.160.178:8000/v1").rstrip("/"), key, \
           (model or "google/gemma-4-31b-it")


def _req(url, key, data=None, timeout=120, stream=False):
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    if key:
        req.add_header("Authorization", "Bearer " + key)
    return urllib.request.urlopen(req, timeout=timeout)


def get_json(url, key, timeout=15):
    try:
        with _req(url, key, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def get_text(url, key, timeout=15):
    try:
        with _req(url, key, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return ""


def parse_metrics(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^([a-zA-Z_:][\w:]*)(\{[^}]*\})?\s+([-\d.eE+]+|NaN)$', line)
        if m:
            try:
                out.setdefault(m.group(1), []).append((m.group(2) or "", float(m.group(3))))
            except ValueError:
                pass
    return out


def metric(metrics, name, default=0.0):
    rows = metrics.get(name)
    return rows[0][1] if rows else default


def sh(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def snapshot(base, key, model):
    root = base[:-3].rstrip("/") if base.endswith("/v1") else base
    metrics_txt = get_text(root + "/metrics", key)
    m = parse_metrics(metrics_txt)

    served, model_meta = None, {}
    models = get_json(base + "/models", key)
    if models and models.get("data"):
        served = models["data"][0].get("id")
        model_meta = {k: v for k, v in models["data"][0].items()
                      if k in ("max_model_len", "root", "owned_by", "created")}

    info = {}
    for name, rows in m.items():
        if name.endswith("_info") or "config" in name:
            for labels, _ in rows:
                for k, v in re.findall(r'(\w+)="([^"]*)"', labels or ""):
                    info.setdefault(name, {})[k] = v

    gpus = []
    smi = sh(["nvidia-smi",
              "--query-gpu=index,name,memory.total,driver_version,compute_cap",
              "--format=csv,noheader"])
    for line in smi.splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 4:
            gpus.append({"index": p[0], "name": p[1], "memory_total": p[2],
                         "driver": p[3], "compute_cap": p[4] if len(p) > 4 else ""})

    return {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "endpoint": base,
        "model_requested": model,
        "model_served": served,
        "model_meta": model_meta,
        "gpus": gpus,
        "gpu_count": len(gpus),
        "gpu_types": sorted({g["name"] for g in gpus}),
        "vllm_version": get_json(root + "/version", key) or
                        info.get("vllm:cache_config_info", {}).get("version", "unknown"),
        "vllm_info": info,
        "host": sh(["uname", "-a"]) or sh(["hostname"]),
        "python": sys.version.split()[0],
        "cuda_smi": sh(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]),
        "metrics_available": sorted(m.keys())[:60],
    }


def busy(base, key):
    root = base[:-3].rstrip("/") if base.endswith("/v1") else base
    m = parse_metrics(get_text(root + "/metrics", key, timeout=8))
    if not m:
        return None, None
    return metric(m, "vllm:num_requests_running"), metric(m, "vllm:num_requests_waiting")


_WORDS = ("resource allocation cluster scheduling throughput latency inference "
          "batch memory bandwidth tensor pipeline parallel budget optimization "
          "constraint variable objective solver integer linear program").split()


def count_tokens(base, key, text, model):
    root = base[:-3].rstrip("/") if base.endswith("/v1") else base
    try:
        body = json.dumps({"model": model, "prompt": text}).encode()
        with _req(root + "/tokenize", key, body, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        return d.get("count") or len(d.get("tokens") or [])
    except Exception:
        return None


def make_prompt(base, key, model, target_tokens, rng):
    def build(n_words):
        return " ".join(rng.choice(_WORDS) for _ in range(n_words))

    lo, hi = 1, max(8, target_tokens * 3)
    best, best_txt = None, build(target_tokens)
    for _ in range(18):
        mid = (lo + hi) // 2
        txt = build(mid)
        n = count_tokens(base, key, txt, model)
        if n is None:
            return build(int(target_tokens * 0.78)), None
        if best is None or abs(n - target_tokens) < abs(best - target_tokens):
            best, best_txt = n, txt
        if n < target_tokens:
            lo = mid + 1
        elif n > target_tokens:
            hi = mid - 1
        else:
            return txt, n
    return best_txt, best


def one_request(base, key, model, prompt, out_tokens, allow_cache, rng):
    head = "" if allow_cache else f"[{rng.randrange(10**9)}] "
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": head + prompt}],
        "max_tokens": out_tokens,
        "min_tokens": out_tokens,
        "temperature": 0,
        "stream": True,
        "ignore_eos": True,
    }
    for attempt in (0, 1):
        t0 = time.perf_counter()
        ttft, n_out = None, 0
        try:
            with _req(base + "/chat/completions", key,
                      json.dumps(payload).encode(), timeout=600) as r:
                for raw in r:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        d = json.loads(chunk)
                    except Exception:
                        continue
                    delta = (d.get("choices") or [{}])[0].get("delta") or {}
                    if delta.get("content"):
                        if ttft is None:
                            ttft = time.perf_counter() - t0
                        n_out += 1
            return True, ttft, time.perf_counter() - t0, n_out, None
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:200]
            if attempt == 0 and ("min_tokens" in msg or "ignore_eos" in msg):
                payload.pop("min_tokens", None)
                payload.pop("ignore_eos", None)
                continue
            return False, None, None, 0, f"HTTP {e.code}: {msg}"
        except Exception as e:
            return False, None, None, 0, f"{type(e).__name__}: {e}"
    return False, None, None, 0, "unreachable"


def measure(base, key, model, prompt, out_tokens, conc, n_req, allow_cache, rng):
    results, lock = [], threading.Lock()
    idx = {"i": 0}

    def worker():
        local = random.Random(rng.randrange(10**9))
        while True:
            with lock:
                if idx["i"] >= n_req:
                    return
                idx["i"] += 1
            r = one_request(base, key, model, prompt, out_tokens, allow_cache, local)
            with lock:
                results.append(r)

    t0 = time.perf_counter()
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(conc)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0

    ok = [r for r in results if r[0]]
    if not ok:
        err = next((r[4] for r in results if r[4]), "unknown")
        return {"ok": 0, "error": err}

    ttfts = [r[1] for r in ok if r[1] is not None]
    totals = [r[2] for r in ok]
    outs = [r[3] for r in ok]

    def pct(xs, q):
        if not xs:
            return 0.0
        s = sorted(xs)
        return s[min(len(s) - 1, int(q * len(s)))]

    tok_out = sum(outs)
    return {
        "ok": len(ok), "failed": len(results) - len(ok), "wall_s": wall,
        "throughput_rps": len(ok) / wall if wall > 0 else 0.0,
        "out_tok_per_s": tok_out / wall if wall > 0 else 0.0,
        "ttft_p50": pct(ttfts, 0.50), "ttft_p95": pct(ttfts, 0.95),
        "e2e_p50": pct(totals, 0.50), "e2e_p95": pct(totals, 0.95),
        "tpot_mean": (statistics.mean(
            [(t - f) / max(1, n - 1) for t, f, n in zip(totals, ttfts, outs) if n > 1])
            if len(ttfts) == len(totals) and any(n > 1 for n in outs) else 0.0),
        "out_tokens_mean": statistics.mean(outs) if outs else 0,
    }


def preflight(base, key, model, snap):
    print(RULE)
    print("  Preflight（不送任何負載）")
    print(RULE)
    print(f"  endpoint  {base}")
    print(f"  模型（設定）{model}")
    print(f"  模型（實際）{snap.get('model_served') or '取不到 /v1/models'}")
    if snap["gpus"]:
        for g in snap["gpus"]:
            print(f"  GPU {g['index']}：{g['name']}　{g['memory_total']}　driver {g['driver']}")
        print(f"  → {snap['gpu_count']} 張、{len(snap['gpu_types'])} 種型號")
    else:
        print("  這台看不到 GPU（nvidia-smi 不存在或無輸出）")
        print("     vLLM 可能跑在別台——要量 h(c,w) 請到實際跑模型那台上執行")

    run, wait = busy(base, key)
    if run is None:
        print("\n  取不到 /metrics —— 無法判斷是否有人在用，也拿不到延遲直方圖")
        return False
    print(f"\n  目前負載：執行中 {run:.0f}、排隊 {wait:.0f}")
    if run or wait:
        print("  **有人在用**。此時量測會互相干擾，數字不可信。")
        print("     請等閒置時段，或先協調一個獨佔窗口。")
        return False
    print("  目前閒置")

    tk = count_tokens(base, key, "hello world", model)
    print(f"  /tokenize：{'可用（可精確控制輸入長度）' if tk else '不可用（長度只能估算，精度下降）'}")

    print("\n  判定：")
    if snap["gpu_count"] >= 2 and len(snap["gpu_types"]) >= 2:
        print("    多型號多張 → 論文維度①（異質 GPU 組成）可量")
    elif snap["gpu_count"] >= 2:
        print("    單型號多張 → 維度①不可量；維度②（TP/PP）需能自行啟動 vLLM")
    elif snap["gpu_count"] == 1:
        print("    單張 GPU → 只能量到「這一個配置」的 h(w)，是一欄不是矩陣")
        print("       但這仍是專案第一個外部量測值，足以把效能係數從假設變成量測")
    else:
        print("    本機看不到 GPU（vLLM 在遠端）→ 仍可量「這個 endpoint 這一套部署」的 h(w)")
        print("       量測是對 endpoint 送受控負載、在本機端計時，不需要登入 GPU 那台。")
        print("       但配置數 |C| = 1，拿到的是一欄不是矩陣；要矩陣得能自行啟動 vLLM。")
    print("\n  確認可以量測後，加 --run 開始。建議先 --quick。")
    return True


def fit_latency_model(records, concurrency):
    pts = [r for r in records if r.get("concurrency") == concurrency and r.get("ok")
           and r.get("in_tokens") and r.get("throughput_rps")]
    if not pts:
        return None
    a_s = [r["ttft_p50"] * 1000.0 / r["in_tokens"] for r in pts if r.get("ttft_p50")]
    b_s = [r["tpot_mean"] * 1000.0 for r in pts if r.get("tpot_mean")]
    if not a_s or not b_s:
        return None
    a, b = statistics.fmean(a_s), statistics.fmean(b_s)

    errs = []
    for r in pts:
        pred = interpolate_h({"ms_per_in_token": a, "ms_per_out_token": b,
                              "concurrency": concurrency}, r["in_tokens"], r["out_tokens"])
        if pred:
            errs.append(abs(pred - r["throughput_rps"]) / r["throughput_rps"] * 100)
    return {
        "form": "h = concurrency / (a*in_tokens + b*(out_tokens-1))",
        "concurrency": concurrency,
        "ms_per_in_token": a, "ms_per_out_token": b,
        "a_spread_pct": (max(a_s) - min(a_s)) / a * 100 if len(a_s) > 1 else 0.0,
        "b_spread_pct": (max(b_s) - min(b_s)) / b * 100 if len(b_s) > 1 else 0.0,
        "n_points": len(pts), "max_err_pct": max(errs) if errs else None,
        "note": f"由併發 {concurrency} 的 TTFT/TPOT 拆解；內插值僅供補格子，不等同飽和量測",
    }


def fit_service_rate_model(hcw, hcw_meta):
    pts = []
    for k, h in hcw.items():
        m = hcw_meta.get(k) or {}
        if not m.get("saturated"):
            continue
        i, o = (int(x) for x in k.split(","))
        pts.append((i, o, h))
    if len(pts) < 2:
        return None

    sii = sio = soo = sy1 = sy2 = 0.0
    for i, o, h in pts:
        y = 1.0 / h
        w = 1.0 / (y * y)
        sii += w * i * i; sio += w * i * o; soo += w * o * o
        sy1 += w * i * y; sy2 += w * o * y
    det = sii * soo - sio * sio
    if det <= 0:
        return None
    a = (sy1 * soo - sy2 * sio) / det
    b = (sii * sy2 - sio * sy1) / det
    if a <= 0 or b <= 0:
        return None

    errs = [abs(1.0 / (a * i + b * o) / h - 1) * 100 for i, o, h in pts]
    return {
        "form": "h = 1 / (alpha*in_tokens + beta*out_tokens)   [saturated service rate]",
        "regime": "saturated",
        "ms_per_in_token": a * 1000.0,
        "ms_per_out_token": b * 1000.0,
        "max_out_tok_per_s": 1.0 / b,
        "max_in_tok_per_s": 1.0 / a,
        "n_points": len(pts), "max_err_pct": max(errs),
        "note": "飽和服務率模型；h 與併發度無關（飽和後併發再加只會排隊）",
    }


def predict_h(model, in_tok, out_tok):
    if not model:
        return None
    a = model["ms_per_in_token"]
    b = model["ms_per_out_token"]
    if model.get("regime") == "saturated":
        t = a * in_tok + b * out_tok
        return 1000.0 / t if t > 0 else None
    lat = a * in_tok + b * max(out_tok - 1, 0)
    return model.get("concurrency", 1) * 1000.0 / lat if lat > 0 else None


def interpolate_h(model, in_tok, out_tok):
    return predict_h(model, in_tok, out_tok)


def enforce_monotone(grid, ins, outs):
    moved, conflict = [], []
    for _ in range(len(ins) * len(outs)):
        changed = False
        for i in ins:
            for o in outs:
                cell = grid[f"{i},{o}"]
                lo, hi = 0.0, float("inf")
                for i2 in ins:
                    for o2 in outs:
                        if (i2, o2) == (i, o):
                            continue
                        h2 = grid[f"{i2},{o2}"]["h"]
                        if i2 >= i and o2 >= o:
                            lo = max(lo, h2)
                        if i2 <= i and o2 <= o:
                            hi = min(hi, h2)
                if lo > hi + 1e-12:
                    if cell["source"] == "measured":
                        conflict.append(f"({i},{o})")
                    continue
                if cell["source"] != "measured":
                    new = min(max(cell["h"], lo), hi)
                    if abs(new - cell["h"]) > 1e-9:
                        moved.append((f"({i},{o})", cell["h"], new))
                        cell["h"] = new
                        cell["monotone_adjusted"] = True
                        changed = True
        if not changed:
            break
    return moved, sorted(set(conflict))


def build_h_grid(hcw, hcw_meta, model):
    grid = [(i, o) for i in (496, 824, 2455) for o in (18, 253, 510)]
    out = {}
    for (i, o) in grid:
        key = f"{i},{o}"
        m = hcw_meta.get(key)
        if key in hcw and m:
            out[key] = {"h": hcw[key], "source": "measured",
                        "concurrency": m.get("concurrency"),
                        "saturated": m.get("saturated", False)}
        else:
            h = predict_h(model, i, o)
            if h is None:
                return None
            out[key] = {"h": h, "source": "interpolated",
                        "saturated": bool(model.get("regime") == "saturated"),
                        "err_pct": model.get("max_err_pct")}
    moved, conflict = enforce_monotone(out, (496, 824, 2455), (18, 253, 510))
    for k, before, after in moved:
        print(f"  · 單調性修正 {k}：{before:.3f} → {after:.3f} req/s "
              f"（{abs(after / before - 1) * 100:.1f}%，在模型誤差帶內）")
    if conflict:
        print(f"  ⚠️ 實測格彼此矛盾：{'、'.join(conflict)} —— 這要重量，補值救不了")
    return out


def derive(records, loads, concs, verbose=True):
    if verbose:
        print("\n" + RULE)
        print("  h(c,w)　配置 c = 目前這一套部署；w = 負載類型")
        print(RULE)
        print(f"  {'負載 (in, out)':<20}{'最高併發':>10}{'h (req/s)':>12}{'輸出 tok/s':>12}"
              f"{'TTFT p95':>11}　飽和")
    hcw, hcw_meta, unsaturated = {}, {}, []
    for (in_tok, out_tok) in loads:
        rs = [r for r in records
              if r["in_tokens"] == in_tok and r["out_tokens"] == out_tok]
        if not rs:
            continue
        best = max(rs, key=lambda r: r["throughput_rps"])
        last = max(rs, key=lambda r: r["concurrency"])
        g = last.get("gain_vs_prev")
        sat = g is not None and g < SATURATION_GAIN
        if not sat:
            unsaturated.append(f"({in_tok},{out_tok})")
        key = f"{in_tok},{out_tok}"
        hcw[key] = best["throughput_rps"]
        hcw_meta[key] = {"concurrency": best["concurrency"], "saturated": sat,
                         "is_lower_bound": not sat,
                         "out_tok_per_s": best["out_tok_per_s"],
                         "ttft_p95_ms": best["ttft_p95"] * 1000}
        if verbose:
            print(f"  ({in_tok:>4}, {out_tok:>3}){'':<8}{best['concurrency']:>10}"
                  f"{best['throughput_rps']:>12.3f}{best['out_tok_per_s']:>12.1f}"
                  f"{best['ttft_p95'] * 1000:>10.0f}ms　{'✅' if sat else '❌ 下界'}")

    if unsaturated and verbose:
        print(f"\n  下列負載未達飽和：{'、'.join(unsaturated)}")
        print(f"     這些 h 是**下界**，不是論文附錄 L 說的 batched processing capacity。")
        print(f"     填進模型會低估副本能力 → 高估要開幾份 → 報價偏高。")
        print(f"     建議：--concurrency {','.join(str(c * 2) for c in concs)} 重跑到吞吐持平。")

    ref_conc = concs[-1] if concs else None
    if not unsaturated:
        model = fit_service_rate_model(hcw, hcw_meta)
        if verbose and model:
            print(f"\n  飽和服務率模型（h 與併發度無關）")
            print(f"    1 ÷ h = {model['ms_per_in_token']:.4f}×in ＋ "
                  f"{model['ms_per_out_token']:.3f}×out  [ms]")
            print(f"    → decode 上限 {model['max_out_tok_per_s']:.0f} out-tok/s、"
                  f"prefill 上限 {model['max_in_tok_per_s']:.0f} in-tok/s")
            print(f"    重現實測點最大誤差 {model['max_err_pct']:.1f}%"
                  f"（論文附錄 L 原文：estimation errors range from 4% to 7%）")
    else:
        model = fit_latency_model(records, ref_conc)
        if verbose and model:
            print(f"\n  延遲兩參數模型（綁定併發 {ref_conc}，**未飽和**）")
            print(f"    h = {ref_conc} ÷ ({model['ms_per_in_token']:.4f}×in ＋ "
                  f"{model['ms_per_out_token']:.2f}×(out−1))  [ms]")
            print(f"    重現實測點最大誤差 {model['max_err_pct']:.1f}%")

    h_grid = build_h_grid(hcw, hcw_meta, model)
    if h_grid and verbose and model:
        n_meas = sum(1 for v in h_grid.values() if v["source"] == "measured")
        print(f"\n  論文 3×3 九格已補滿：實測 {n_meas} 格、內插 {9 - n_meas} 格"
              f"（內插格誤差約 {model['max_err_pct']:.0f}%，僅供補格）")
    return hcw, hcw_meta, model, h_grid, unsaturated, ref_conc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="真的送負載（預設只做 preflight）")
    ap.add_argument("--quick", action="store_true", help="只跑 3 種負載類型")
    ap.add_argument("--concurrency", default="1,2,4", help="併發度，逗號分隔")
    ap.add_argument("--requests", type=int, default=16,
                    help="每組發幾個請求（至少要 4 × 最高併發，才跑得滿 4 輪）")
    ap.add_argument("--refit", metavar="PATH",
                    help="不量測，直接用既有 JSON 的 records 重算 h/模型/九宮格")
    ap.add_argument("--warmup", type=int, default=2, help="暖身請求數（不計入）")
    ap.add_argument("--allow-cache", action="store_true",
                    help="不加隨機前綴（用來量 prefix caching 的效果）")
    ap.add_argument("--out", default="paper/vllm_profile.json")
    ap.add_argument("--seed", type=int, default=20260814)
    args = ap.parse_args()

    if args.refit:
        return refit(args.refit)

    concs = [int(c) for c in args.concurrency.split(",") if c.strip()]
    top = max(concs)
    if args.requests < top:
        print(f"\n  --requests {args.requests} < 最高併發 {top}")
        print(f"     會有 {top - args.requests} 條執行緒分不到工作，實際併發低於標稱值，")
        print(f"     量出來的 h 會被貼上**錯的併發標籤**。")
        print(f"\n     改成：--requests {4 * top}")
        print("\n（沒有送出任何負載）")
        return 2
    if args.requests < 4 * top:
        print(f"\n  --requests {args.requests} ÷ 最高併發 {top} "
              f"= 只有 {args.requests / top:.1f} 輪；頭尾的爬升與收尾佔比過高，"
              f"吞吐會被低估。建議 --requests {4 * top}。")

    base, key, model = load_env()
    rng = random.Random(args.seed)

    print(RULE)
    print("  vLLM 吞吐量 profiling —— 量出論文的 h(c,w)")
    print(RULE)
    snap = snapshot(base, key, model)
    if not preflight(base, key, model, snap) or not args.run:
        if not args.run:
            print("\n（未加 --run，到此為止，沒有送出任何負載）")
        return 0

    loads = WORKLOADS_QUICK if args.quick else WORKLOADS_FULL

    print("\n" + RULE)
    print(f"  開始量測：{len(loads)} 種負載 × {len(concs)} 個併發度"
          f"　每組 {args.requests} 請求（另暖身 {args.warmup}）")
    print(f"  prefix cache：{'允許命中' if args.allow_cache else '每次加隨機前綴避開'}")
    print(RULE)

    records, contaminated = [], False
    for (in_tok, out_tok) in loads:
        prompt, actual = make_prompt(base, key, model, in_tok, rng)
        print(f"\n── 負載 w = (輸入 {in_tok}, 輸出 {out_tok})"
              f"　實際輸入 {actual if actual else '估算'} tokens")

        for i in range(args.warmup):
            one_request(base, key, model, prompt, out_tok, args.allow_cache, rng)

        prev_rps, saturated_at = None, None
        for conc in concs:
            run, wait = busy(base, key)
            if run and run > conc:
                print(f"   ⚠️ 偵測到 {run:.0f} 個執行中請求（>本次併發 {conc}）→ 數據可能被污染")
                contaminated = True
            r = measure(base, key, model, prompt, out_tok, conc,
                        args.requests, args.allow_cache, rng)
            if not r.get("ok"):
                print(f"   併發 {conc:>2}：❌ {r.get('error')}")
                continue

            gain = None if prev_rps is None else (r["throughput_rps"] / prev_rps - 1)
            mark = ""
            if gain is not None:
                mark = f"　(+{gain * 100:.0f}%)"
                if gain < SATURATION_GAIN and saturated_at is None:
                    saturated_at = conc
                    mark += "　← 增幅 < %d%%，視為已飽和" % (SATURATION_GAIN * 100)
            prev_rps = r["throughput_rps"]

            print(f"   併發 {conc:>2}：吞吐 {r['throughput_rps']:.3f} req/s"
                  f"　輸出 {r['out_tok_per_s']:.1f} tok/s"
                  f"　TTFT p50 {r['ttft_p50'] * 1000:.0f}ms / p95 {r['ttft_p95'] * 1000:.0f}ms"
                  f"　TPOT {r['tpot_mean'] * 1000:.1f}ms{mark}")
            records.append({"in_tokens": in_tok, "out_tokens": out_tok,
                            "actual_in_tokens": actual, "concurrency": conc,
                            "gain_vs_prev": gain, **r})

        if saturated_at is None and len(concs) > 1:
            print(f"   ⚠️ 到最高併發 {concs[-1]} 仍未飽和 → 這一列的 h 是**下界**，"
                  f"建議加大 --concurrency 重跑")

    hcw, hcw_meta, model_, h_grid, unsaturated, ref_conc = derive(records, loads, concs)

    out = {"snapshot": snap, "args": vars(args), "records": records, "h_c_w": hcw,
           "h_c_w_meta": hcw_meta, "latency_model": model_,
           "reference_concurrency": ref_conc, "h_grid": h_grid,
           "all_saturated": not unsaturated, "contaminated": contaminated}
    write_profile(args.out, out)

    if contaminated:
        print("  量測期間偵測到其他請求")
    return 0


def write_profile(rel_out, payload):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        rel_out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"\n  已寫入 {rel_out}（含完整環境快照，供重現用）")





def refit(path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = path if os.path.isabs(path) else os.path.join(root, path)
    with open(full, encoding="utf-8") as fh:
        old = json.load(fh)
    records = old.get("records") or []
    if not records:
        print(f"  {path} 裡沒有 records，無法重算")
        return 2

    loads, seen = [], set()
    for r in records:
        k = (r["in_tokens"], r["out_tokens"])
        if k not in seen:
            seen.add(k); loads.append(k)
    concs = sorted({r["concurrency"] for r in records})

    print(RULE)
    print("  重算（--refit）：沒有送出任何負載，只重跑推導")
    print(RULE)
    print(f"  來源 {path}：{len(records)} 筆 records、"
          f"{len(loads)} 種負載、併發 {','.join(map(str, concs))}")

    hcw, hcw_meta, model_, h_grid, unsaturated, ref_conc = derive(records, loads, concs)
    old.update({"h_c_w": hcw, "h_c_w_meta": hcw_meta, "latency_model": model_,
                "reference_concurrency": ref_conc, "h_grid": h_grid,
                "all_saturated": not unsaturated, "refit": True})
    write_profile(path, old)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中止（Ctrl-C）。")
        sys.exit(130)
