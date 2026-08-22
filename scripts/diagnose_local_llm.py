import json
import os
import platform
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from config import settings  # noqa: E402

TIMEOUT = 5.0


def _host_port(base_url: str):
    rest = base_url.split("://", 1)[-1]
    hostport = rest.split("/", 1)[0]
    if ":" in hostport:
        h, p = hostport.rsplit(":", 1)
        return h, int(p)
    return hostport, 443 if base_url.startswith("https") else 80


def line(t=""):
    print(t)


def head(t):
    print("\n" + t)
    print("-" * 58)


def main():
    base = settings.LOCAL_LLM_BASE_URL
    model = settings.LOCAL_LLM_MODEL
    key = settings.LOCAL_LLM_API_KEY
    host, port = _host_port(base)
    results = {}

    print("=" * 58)
    print("  本地 LLM 連線診斷")
    print("=" * 58)
    print(f"  端點　：{base}")
    print(f"  主機　：{host}　連接埠：{port}")
    print(f"  模型　：{model}")
    print(f"  金鑰　：{'已設定（%d 字元）' % len(key) if key else '未設定'}")
    print(f"  本機　：{platform.node()}　{platform.system()} {platform.release()}")

    head("L0 本機網路位址")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        print(f"  對外介面位址：{local_ip}")
        same = local_ip.split(".")[0] == host.split(".")[0]
        print(f"  與目標同一個 A 段（{host.split('.')[0]}.x.x.x）：{'是' if same else '否'}")
        results["local_ip"] = local_ip
    except Exception as e:
        print(f"  取得失敗：{e}")

    head("L2 ICMP（ping）")
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        r = subprocess.run(["ping", flag, "2", host], capture_output=True,
                           text=True, timeout=20)
        ok = r.returncode == 0
        print(f"  {'✅ 有回應' if ok else '❌ 無回應（逾時或不可達）'}")
        results["icmp"] = ok
        tail = [x for x in r.stdout.strip().splitlines() if x.strip()][-2:]
        for t in tail:
            print("   ", t.strip())
    except Exception as e:
        print(f"  ⚠ 無法執行 ping：{e}")
        results["icmp"] = None
    print("  註：部分環境會擋 ICMP，ping 不通不代表服務一定壞，看下一層。")

    head(f"L3 TCP（連接埠 {port} 是否可連）")
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            ms = (time.time() - t0) * 1000
            print(f"  ✅ 連得上（{ms:.0f} ms）→ 路由沒問題，且有服務在聽這個埠")
            results["tcp"] = True
    except socket.timeout:
        print(f"  ❌ 逾時（{TIMEOUT:.0f}s）→ 封包送不到：多半是**沒有路由／VPN 未連／防火牆擋**")
        results["tcp"] = False
    except ConnectionRefusedError:
        print("  ❌ 連線被拒 → 路由「通得到主機」，但**該埠沒有服務在聽**（服務沒開或換埠）")
        results["tcp"] = "refused"
    except Exception as e:
        print(f"  ❌ {type(e).__name__}: {e}")
        results["tcp"] = False

    head("L4 HTTP（GET /v1/models — 此 server 本來就沒有這個端點）")
    if results.get("tcp") is not True:
        print("  ⏭ 跳過：TCP 不通，上層不用測")
        results["http"] = None
    else:
        try:
            req = urllib.request.Request(base.rstrip("/") + "/models")
            if key:
                req.add_header("Authorization", f"Bearer {key}")
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                body = resp.read(400).decode("utf-8", "replace")
                print(f"  ✅ HTTP {resp.status}")
                print(f"     {body[:200]}")
                results["http"] = resp.status
        except urllib.error.HTTPError as e:
            note = "（此 server 沒有 models 端點，404 代表服務活著、屬正常）" \
                if e.code == 404 else "（服務有回應，但這個路徑或金鑰有問題）"
            print(f"  ⚠ HTTP {e.code}{note}")
            results["http"] = e.code
        except Exception as e:
            print(f"  ❌ {type(e).__name__}: {e}")
            results["http"] = False

    head("L5 API（POST /v1/chat/completions）")
    if results.get("tcp") is not True:
        print("  ⏭ 跳過：TCP 不通")
        results["api"] = None
    else:
        payload = json.dumps({
            "model": model, "max_tokens": 8,
            "messages": [{"role": "user", "content": "ping"}],
        }).encode()
        try:
            req = urllib.request.Request(
                base.rstrip("/") + "/chat/completions", data=payload,
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {key}" if key else ""})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
                msg = body.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"  ✅ 生成成功：{msg[:80]!r}")
                results["api"] = True
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            print(f"  ❌ HTTP {e.code}：{detail}")
            print("     401/403 → 金鑰無效或過期；404 → 路徑或模型名不對")
            results["api"] = e.code
        except Exception as e:
            print(f"  ❌ {type(e).__name__}: {e}")
            results["api"] = False

    print("\n" + "=" * 58)
    print("  結論")
    print("=" * 58)
    tcp = results.get("tcp")
    if results.get("api") is True:
        verdict = "✅ 本地 LLM 完全可用——端點、金鑰、模型都正確。"
        action = "可直接跑 python main.py，回答標頭應顯示「由 本地LLM 生成」。"
    elif tcp is True:
        verdict = "⚠ 網路通得到，但服務層有問題（以 L5 為準，L4 的 404 屬正常）。"
        action = "把 L5 的狀態碼回報給提供端點的人：金鑰是否過期、模型名是否改了。"
    elif tcp == "refused":
        verdict = "⚠ 連線被拒（RST）：可能是該埠沒有服務，也可能是防火牆 reject。"
        action = ("拿同主機的其他埠當對照組來分辨——例如 22（SSH）："
                  "若 22 連得上，代表主機活著、防火牆沒全擋，那就是 9000 沒服務；"
                  "若連 22 也被拒，就是 ACL 在擋整台。")
    else:
        verdict = "❌ 封包根本送不到目標（TCP 逾時）。"
        action = ("這台機器沒有到該位址的路由。請確認：(1) 是否需要先連 VPN；"
                  "(2) 這台機器是否被允許存取該網段；(3) 端點位址是否仍有效。")
    print(f"  {verdict}")
    print(f"  建議：{action}")

    print("\n  ── 可直接貼給對方的摘要 ──")
    print(f"  機器 {platform.node()}（{results.get('local_ip','?')}）"
          f" → {host}:{port}")
    print(f"  ICMP={results.get('icmp')}　TCP={results.get('tcp')}"
          f"　HTTP={results.get('http')}　API={results.get('api')}")
    print(f"  端點 {base}　模型 {model}")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
