import hashlib
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings

QA_URL = ("https://iservice.nchc.org.tw/nchc_service/"
          "nchc_service_qa_single.php?qa_code=839")
BASELINE_FILE = str(settings.DATA_DIR / "pricing_watch_baseline.json")
_UA = "Mozilla/5.0 (pricing-watch; NCHC price monitor)"
_TIMEOUT = 20


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def _extract(html: str) -> dict:
    imgs = re.findall(r"data:image/[a-zA-Z.+-]+;base64,([A-Za-z0-9+/=]+)", html)
    img_hashes = sorted(_sha(b) for b in imgs)

    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "image_count": len(imgs),
        "image_hashes": img_hashes,
        "text_hash": _sha(text),
        "text_len": len(text),
    }


def _load_baseline() -> dict:
    if not os.path.exists(BASELINE_FILE):
        return {}
    try:
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_baseline(fp: dict, url: str):
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    data = dict(fp)
    data["url"] = url
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _diff(old: dict, new: dict) -> list:
    changes = []
    if old.get("image_count") != new.get("image_count"):
        changes.append(f"圖片數量：{old.get('image_count')} → {new.get('image_count')}")
    if set(old.get("image_hashes", [])) != set(new.get("image_hashes", [])):
        changes.append("價目表圖片內容有變（base64 圖片 hash 不同）")
    if old.get("text_hash") != new.get("text_hash"):
        changes.append(f"說明文字有變（長度 {old.get('text_len')} → {new.get('text_len')}）")
    return changes


def main():
    argv = sys.argv[1:]
    url = QA_URL
    if "--url" in argv:
        i = argv.index("--url")
        if i + 1 < len(argv):
            url = argv[i + 1]

    if "--show" in argv:
        bl = _load_baseline()
        if not bl:
            print("尚無基準線。先執行 python pricing_watch.py 建立。")
            return 0
        print("目前基準線：")
        print(f"  URL        ：{bl.get('url')}")
        print(f"  圖片數量   ：{bl.get('image_count')}")
        print(f"  圖片 hash  ：{len(bl.get('image_hashes', []))} 個")
        print(f"  文字長度   ：{bl.get('text_len')}")
        print(f"  文字 hash  ：{(bl.get('text_hash') or '')[:16]}…")
        print(f"  基準線檔案 ：{BASELINE_FILE}")
        return 0

    try:
        html = _fetch(url)
    except Exception as e:  # noqa: BLE001 — 監測腳本要把任何抓取失敗都收成訊息
        print(f"❌ 抓取失敗：{type(e).__name__}: {e}")
        print(f"   （目標：{url}）")
        return 1

    try:
        fp = _extract(html)
    except Exception as e:  # noqa: BLE001
        print(f"❌ 解析失敗：{type(e).__name__}: {e}")
        return 1

    print(f"抓取完成：圖片 {fp['image_count']} 張、文字 {fp['text_len']} 字元")

    if "--update" in argv:
        _save_baseline(fp, url)
        print(f"✅ 已（無條件）更新基準線 → {BASELINE_FILE}")
        return 0

    baseline = _load_baseline()
    if not baseline:
        _save_baseline(fp, url)
        print(f"ℹ️ 首次執行，已建立基準線 → {BASELINE_FILE}")
        print("   之後再執行本腳本即可偵測價目表是否改版。")
        return 0

    changes = _diff(baseline, fp)
    if not changes:
        print("✅ 價目頁與基準線一致，無變動。")
        return 0

    print("⚠️ 偵測到價目頁變動：")
    for c in changes:
        print(f"   · {c}")
    print("\n請人工回到該頁核對，並視情況更新 data/pricing.csv 與相關設定；")
    print("核對無誤後執行 python pricing_watch.py --update 讓基準線跟上。")
    print(f"（頁面：{url}）")
    return 2


if __name__ == "__main__":
    sys.exit(main())
