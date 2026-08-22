import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from rag import faq

def load_eval():
    rows = []
    with open(settings.DATA_DIR / "faq_eval.csv", "r", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((r["測試問題"].strip(), r["應命中關鍵字"].strip()))
    return rows


def run(retrieve_fn, name, top_k, strip_keywords=False):
    items = faq._load_faq()
    if strip_keywords:
        items = [{**it, "keywords": []} for it in items]
    rows = load_eval()
    correct = 0
    fails = []
    for q, expect in rows:
        hits = retrieve_fn(q, items, top_k)
        if expect == "(無)":
            ok = len(hits) == 0
        else:
            ok = any(expect in h["answer"] or expect in h["question"] for h in hits)
        correct += ok
        if not ok:
            top = hits[0]["question"][:20] if hits else "（無命中）"
            fails.append(f"    x {q}  -> 期望「{expect}」, top1「{top}」")
    print(f"[{name}] 命中率 {correct}/{len(rows)} = {correct/len(rows)*100:.0f}%")
    for line in fails:
        print(line)
    return correct, len(rows)


def run_production():
    rows = load_eval()
    correct = 0
    for q, expect in rows:
        hits = faq.retrieve(q, top_k=2)
        ok = (len(hits) == 0) if expect == "(無)" \
            else any(expect in h["answer"] or expect in h["question"] for h in hits)
        correct += ok
    print(f">>> 線上實際設定（retrieve top_k=2）命中率："
          f"{correct}/{len(rows)} = {correct/len(rows)*100:.0f}%  <<<")
    return correct, len(rows)


def run_faithfulness():
    ctx = faq.search_faq("H100 適合什麼用途")
    grounded = "H100 是高階 GPU 方案，適合大型語言模型訓練與深度學習推論。"
    halluc = "H100 每小時只要 5 元，還免費附贈 100GB 流量與技術客服專線。"
    g1 = faq.check_grounding(grounded, ctx)
    g2 = faq.check_grounding(halluc, ctx)
    print(f"照知識庫回答：支持度 {g1['score']}，通過={g1['ok']}")
    print(f"自行杜撰回答：支持度 {g2['score']}，通過={g2['ok']}  ← 應被標記")
    if g2["flagged"]:
        print("   標記出的可疑內容：", g2["flagged"][0])


if __name__ == "__main__":
    print("最高可用後端：", faq.active_backend())
    print("=" * 56)
    run_production()
    print("實際服務後端（last_backend）：", faq.last_backend(),
          "（embedding 連不上會自動退回 tfidf/keyword）")
    print("=" * 56)
    print("### 忠實度檢核（生成端）")
    run_faithfulness()
    print("=" * 56)
    print("（以下為 top_k=1 嚴格診斷，用來觀察排序與兩後端差異，非線上設定）")

    print("\n### 情境 A：keyword 欄完整（人工仔細維護）top_k=1")
    run(faq._keyword_retrieve, "Tier 2 舊：關鍵字+bigram", 1)
    print("-" * 56)
    run(faq._tfidf_retrieve, "Tier 1 新：TF-IDF 餘弦", 1)

    print("\n### 情境 B：keyword 欄清空（模擬無人力維護）top_k=1")
    print("    這才看得出差距：舊方法只剩 bigram，新方法靠 TF-IDF 仍站得住")
    run(faq._keyword_retrieve, "Tier 2 舊：關鍵字+bigram", 1, strip_keywords=True)
    print("-" * 56)
    run(faq._tfidf_retrieve, "Tier 1 新：TF-IDF 餘弦", 1, strip_keywords=True)
