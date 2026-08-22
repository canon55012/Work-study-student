import asyncio
import time

from flask import Blueprint, jsonify

from config import settings
from agent import providers
from common import observability
from mcp_client.client import get_client
from mcp_server.tools import vm_lifecycle

admin_bp = Blueprint("admin", __name__)

_TOOLS_CACHE = {"at": 0.0, "tools": [], "error": ""}
_TOOLS_MAX_AGE = 60.0


def _list_tools() -> dict:
    now = time.time()
    fresh = now - _TOOLS_CACHE["at"] < _TOOLS_MAX_AGE
    if fresh and (_TOOLS_CACHE["tools"] or _TOOLS_CACHE["error"]):
        return _TOOLS_CACHE

    async def go():
        async with get_client() as c:
            return await c.list_tools()

    try:
        tools = asyncio.run(go())
        _TOOLS_CACHE.update(at=now, error="", tools=[{
            "name": t.name,
            "desc": (getattr(t, "description", "") or "").strip().split("\n")[0],
        } for t in tools])
    except Exception as e:
        _TOOLS_CACHE.update(at=now, tools=[], error=f"{type(e).__name__}: {e}")
    return _TOOLS_CACHE


def _tool_stats(calls: list) -> dict:
    stats = {}
    for c in calls:
        st = stats.setdefault(c.get("tool", ""), {"n": 0, "ok": 0, "ms": 0.0})
        st["n"] += 1
        st["ok"] += 1 if c.get("ok") else 0
        st["ms"] += float(c.get("latency_ms") or 0)
    for st in stats.values():
        st["avg_ms"] = round(st["ms"] / st["n"], 1) if st["n"] else 0.0
    return stats


@admin_bp.route("/api/admin/overview")
def overview():
    users = []
    grand_total = 0.0
    grand_net = 0.0
    for uid in settings.list_users():
        s = vm_lifecycle.account_summary(uid)
        grand_total += s["total_cost"]
        grand_net += s.get("total_net", s["total_cost"])
        users.append(s)

    calls = observability.read_tool_calls(2000)
    tools = _list_tools()

    return jsonify({
        "llm": {
            "active": providers.active_id(),
            "providers": providers.probe_all(),
        },
        "users": users,
        "grand_total": round(grand_total, 2),
        "grand_net": round(grand_net, 2),
        "tools": tools["tools"],
        "tools_error": tools["error"],
        "tool_stats": _tool_stats(calls),
        "tool_calls": list(reversed(calls[-200:])),
        "faq_misses": list(reversed(observability.read_faq_misses(200))),
    })


ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>管理介面 · 可信賴雲</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:20px;font-size:13px}
  h1{font-size:18px;margin-bottom:4px}
  .sub{color:#64748b;font-size:12px;margin-bottom:16px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .card{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:14px;margin-bottom:16px}
  .card h2{font-size:14px;margin-bottom:10px;color:#93c5fd;display:flex;align-items:center;gap:8px}
  .full{grid-column:1 / -1}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #24324a;vertical-align:top}
  th{color:#64748b;font-weight:600;position:sticky;top:0;background:#1e293b}
  .scroll{max-height:280px;overflow-y:auto}
  .pill{padding:1px 7px;border-radius:10px;font-size:11px;color:#fff}
  .mono{font-family:monospace;color:#a78bfa}
  .muted{color:#64748b}
  .big{font-size:22px;font-weight:700;color:#5eead4}
  button{background:#1d4ed8;color:#fff;border:none;border-radius:6px;padding:6px 12px;cursor:pointer;font-size:12px}
  a{color:#93c5fd}
  .ok{background:#0d9488}.warn{background:#d97706}.err{background:#dc2626}.off{background:#475569}
  .row{display:flex;gap:16px;flex-wrap:wrap;align-items:center}
</style>
</head>
<body>
<h1>管理介面</h1>
<div class="sub">可信賴雲 AI Agent · 系統運作總覽　<a href="/">← 回聊天</a>　<button onclick="load()">重新整理</button>　<span id="ts" class="muted"></span></div>

<div class="grid">
  <div class="card">
    <h2>LLM 供應商狀態</h2>
    <table><thead><tr><th>供應商</th><th>模型</th><th>狀態</th><th>延遲</th></tr></thead>
    <tbody id="llm-body"></tbody></table>
  </div>
  <div class="card">
    <h2>帳單總覽</h2>
    <div class="row">
      <div><div class="muted">使用者數</div><div class="big" id="user-count">-</div></div>
      <div><div class="muted">運行中 VM</div><div class="big" id="running-count">-</div></div>
      <div><div class="muted">牌價總額</div><div class="big" id="grand-total">-</div></div>
      <div><div class="muted">折扣後實收</div><div class="big" id="grand-net" style="color:#fbbf24">-</div></div>
    </div>
  </div>
</div>

<div class="card full">
  <h2>可用工具　<span class="muted" id="tools-count"></span></h2>
  <div class="muted" id="tools-err" style="color:#fca5a5"></div>
  <div class="scroll">
  <table><thead><tr><th>工具</th><th>說明</th><th>呼叫次數</th><th>成功率</th><th>平均耗時</th></tr></thead>
  <tbody id="tools-body"></tbody></table>
  </div>
</div>

<div class="card full">
  <h2>各使用者 VM 與計費</h2>
  <div class="scroll">
  <table><thead><tr><th>使用者</th><th>身分</th><th>VM</th><th>名稱</th><th>區域</th><th>方案</th><th>狀態</th><th>運行時數</th><th>牌價</th><th>實收</th></tr></thead>
  <tbody id="vm-body"></tbody></table>
  </div>
</div>

<div class="grid">
  <div class="card">
    <h2>工具呼叫記錄</h2>
    <div class="scroll">
    <table><thead><tr><th>時間</th><th>使用者</th><th>工具</th><th>成敗</th><th>耗時</th></tr></thead>
    <tbody id="tool-body"></tbody></table>
    </div>
  </div>
  <div class="card">
    <h2>FAQ 未命中</h2>
    <div class="scroll">
    <table><thead><tr><th>時間</th><th>使用者</th><th>問題</th><th>後端</th></tr></thead>
    <tbody id="miss-body"></tbody></table>
    </div>
  </div>
</div>

<script>
const STATUS_ZH = {ok:'可用', unreachable:'無法連線', auth_error:'金鑰無效', quota_exceeded:'額度不足', rate_limited:'速率受限', disabled:'未啟用', no_sdk:'套件未安裝', error:'錯誤'};
const STATUS_CLS = {ok:'ok', unreachable:'err', auth_error:'err', quota_exceeded:'warn', rate_limited:'warn', disabled:'off', no_sdk:'off', error:'err'};
function esc(s){ return (s==null?'':String(s)).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function load(){
  fetch('/api/admin/overview').then(r=>r.json()).then(d=>{
    // LLM
    document.getElementById('llm-body').innerHTML = d.llm.providers.map(p=>{
      const cls = STATUS_CLS[p.status]||'off';
      const act = p.active ? ' ★' : '';
      const lat = p.latency_ms!=null ? p.latency_ms+' ms' : '-';
      return `<tr><td>${esc(p.label)}${act}</td><td class="mono">${esc(p.model)}</td>`+
             `<td><span class="pill ${cls}">${esc(p.detail||STATUS_ZH[p.status])}</span></td><td class="muted">${lat}</td></tr>`;
    }).join('');

    // 帳單彙總
    let running=0; d.users.forEach(u=> running+=u.running);
    document.getElementById('user-count').textContent = d.users.length;
    document.getElementById('running-count').textContent = running;
    document.getElementById('grand-total').textContent = '$'+d.grand_total.toFixed(2);
    document.getElementById('grand-net').textContent = '$'+(d.grand_net!=null?d.grand_net:d.grand_total).toFixed(2);

    // 各使用者 VM
    let rows='';
    d.users.forEach(u=>{
      // 身分後面標所屬計畫：W5 起計畫別是「從計畫讀」的，標出來才看得出來源
      const pt = esc(u.plan_type||'') + (u.project_id ? `<br><span class="muted mono">${esc(u.project_id)}</span>` : '');
      if(!u.vms.length){ rows += `<tr><td>${esc(u.user_id)}</td><td>${pt}</td><td colspan="8" class="muted">（無 VM）</td></tr>`; return; }
      u.vms.forEach((v,i)=>{
        const net = v.net!=null ? v.net : v.cost;
        const netCell = net<v.cost ? `<span style="color:#fbbf24">$${net.toFixed(2)}</span>` : `$${net.toFixed(2)}`;
        rows += `<tr><td>${i===0?esc(u.user_id):''}</td><td>${i===0?pt:''}</td><td class="mono">${esc(v.vm_id)}</td>`+
                `<td>${esc(v['名稱'])}</td><td>${esc(v['區域'])}</td><td>${esc(v['方案'])}</td><td>${esc(v['狀態中文'])}</td>`+
                `<td>${v.hours.toFixed(4)}</td><td class="muted">$${v.cost.toFixed(2)}</td><td>${netCell}</td></tr>`;
      });
    });
    document.getElementById('vm-body').innerHTML = rows || '<tr><td colspan="10" class="muted">尚無使用者資料</td></tr>';

    // 可用工具（清單來自 MCP Server 實際註冊的工具，不是寫死的）
    const st = d.tool_stats || {};
    document.getElementById('tools-count').textContent =
      d.tools.length ? '共 ' + d.tools.length + ' 個（由 MCP Server 實際回報）' : '';
    document.getElementById('tools-err').textContent =
      d.tools_error ? '無法取得工具清單：' + d.tools_error + '（MCP Server 可能沒啟動）' : '';
    document.getElementById('tools-body').innerHTML = d.tools.map(t=>{
      const s = st[t.name];
      if(!s) return `<tr><td class="mono">${esc(t.name)}</td><td class="muted">${esc(t.desc)}</td>`+
                    `<td class="muted">0</td><td class="muted">—</td><td class="muted">—</td></tr>`;
      const rate = Math.round(s.ok / s.n * 100);
      const cls = rate===100 ? 'ok' : (rate>=80 ? 'warn' : 'err');
      return `<tr><td class="mono">${esc(t.name)}</td><td class="muted">${esc(t.desc)}</td>`+
             `<td>${s.n}</td><td><span class="pill ${cls}">${rate}%</span></td>`+
             `<td class="muted">${s.avg_ms} ms</td></tr>`;
    }).join('') || '<tr><td colspan="5" class="muted">取不到工具清單</td></tr>';

    // 工具呼叫
    document.getElementById('tool-body').innerHTML = d.tool_calls.map(t=>{
      const cls = t.ok ? 'ok' : 'err';
      const txt = t.ok ? '成功' : '失敗';
      return `<tr><td class="muted">${esc(t.ts)}</td><td>${esc(t.user_id)}</td>`+
             `<td class="mono" title="${esc(JSON.stringify(t.params))}">${esc(t.tool)}</td>`+
             `<td><span class="pill ${cls}">${txt}</span></td><td class="muted">${t.latency_ms} ms</td></tr>`;
    }).join('') || '<tr><td colspan="5" class="muted">尚無記錄</td></tr>';

    // FAQ 未命中
    document.getElementById('miss-body').innerHTML = d.faq_misses.map(m=>
      `<tr><td class="muted">${esc(m.ts)}</td><td>${esc(m.user_id)}</td><td>${esc(m.question)}</td><td class="mono">${esc(m.backend)}</td></tr>`
    ).join('') || '<tr><td colspan="4" class="muted">目前沒有未命中</td></tr>';

    document.getElementById('ts').textContent = '更新於 ' + new Date().toLocaleTimeString();
  });
}
load();
setInterval(load, 10000);
</script>
</body>
</html>"""


@admin_bp.route("/admin")
def admin_page():
    from flask import render_template_string
    return render_template_string(ADMIN_HTML)
