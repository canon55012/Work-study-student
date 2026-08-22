import asyncio
import sys
import json
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from flask import (
    Flask, request, jsonify, render_template_string, Response, stream_with_context
)

from config import settings
from agent import providers
from agent.llm import init_llm
from agent.core import build_messages, call_and_parse
from agent import tools as agent_tools
from mcp_client.client import get_client
from admin import admin_bp

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

init_llm()


HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>可信賴雲 AI Agent</title>
<style>
  :root{
    --bg:#0b1020; --surface:#141b2e; --surface-2:#1b2439; --line:#26314b;
    --line-soft:#1e2740;
    --text:#e6ebf5; --text-dim:#9aa8c2; --text-mute:#657089;
    --accent:#5b8def; --accent-soft:#1e2c4d;
    --think:#7c93b8; --tool:#a78bfa; --result:#4ade80; --error:#f87171;
    --llm:#fbbf24; --wait:#64748b; --note:#38bdf8; --warn:#fb923c;
    --radius:10px; --radius-lg:14px;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{
    font-family:"Segoe UI","Noto Sans TC","Microsoft JhengHei",system-ui,-apple-system,sans-serif;
    background:var(--bg);color:var(--text);height:100vh;
    display:flex;flex-direction:column;
    font-size:14px;line-height:1.7;-webkit-font-smoothing:antialiased;
  }

  /* ── 頂列 ───────────────────────────────────────────── */
  header{
    background:var(--surface);border-bottom:1px solid var(--line);
    padding:10px 18px;display:flex;align-items:center;gap:7px;flex-wrap:wrap;
  }
  .brand{font-size:15px;font-weight:600;letter-spacing:.02em;display:flex;align-items:center;gap:9px}
  .brand::before{
    content:"";width:3px;height:16px;border-radius:2px;
    background:linear-gradient(180deg,var(--accent),#8b5cf6);
  }
  header .grow{flex:1}
  .tag{
    font-size:11px;padding:2px 9px;border-radius:999px;color:#fff;
    font-weight:500;letter-spacing:.02em;
  }
  header label{font-size:11px;color:var(--text-dim);margin-left:4px;letter-spacing:.03em}
  /* 計畫名稱可能很長，不限寬會把整列擠到換行 */
  #project-select{max-width:180px}
  #llm-select{max-width:190px}
  #plan-badge{font-size:11px;color:var(--text-dim);white-space:nowrap}
  header select,header input{
    background:var(--bg);color:var(--text);border:1px solid var(--line);
    border-radius:8px;padding:6px 9px;font-size:12px;font-family:inherit;
    transition:border-color .15s;
  }
  header select:hover,header input:hover{border-color:#33405f}
  header select:focus,header input:focus{outline:none;border-color:var(--accent)}
  .btn{
    background:var(--bg);color:var(--text-dim);border:1px solid var(--line);
    border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer;
    font-family:inherit;text-decoration:none;transition:all .15s;
  }
  .btn:hover{color:var(--text);border-color:#3c4a6b;background:var(--surface-2)}
  #switch-msg{font-size:11px;padding:3px 10px;border-radius:999px;transition:background .2s}

  /* ── 對話區 ─────────────────────────────────────────── */
  #chat{flex:1;overflow-y:auto;padding:22px 20px 24px;display:flex;flex-direction:column;gap:12px}
  #chat::-webkit-scrollbar{width:10px}
  #chat::-webkit-scrollbar-thumb{background:#243052;border-radius:6px;border:3px solid var(--bg)}
  #chat::-webkit-scrollbar-thumb:hover{background:#2f3d63}

  .msg{max-width:74%;padding:13px 17px;border-radius:var(--radius-lg);white-space:pre-wrap;word-break:break-word}
  .user{
    background:linear-gradient(135deg,var(--accent),#4776d8);color:#fff;
    align-self:flex-end;border-bottom-right-radius:4px;
    box-shadow:0 2px 10px rgba(91,141,239,.22);
  }
  .agent{
    background:var(--surface);border:1px solid var(--line);
    align-self:flex-start;border-bottom-left-radius:4px;
  }

  /* ── 推理過程：左色條 + 文字標籤，不用圖示 ────────────── */
  .step{
    align-self:flex-start;max-width:88%;
    display:flex;gap:11px;align-items:baseline;
    background:var(--surface-2);border-left:2px solid var(--wait);
    padding:8px 14px;border-radius:0 var(--radius) var(--radius) 0;
    font-size:12.5px;color:var(--text-dim);
    opacity:0;transform:translateY(3px);transition:opacity .25s,transform .25s;
  }
  .step.show{opacity:1;transform:none}
  .step__tag{
    flex:none;width:42px;text-align:right;
    font-size:11px;font-weight:600;letter-spacing:.02em;color:var(--wait);
  }
  .step__body{flex:1;word-break:break-word;font-family:inherit}
  /* 輪次／工具名放在內文開頭，標籤那一欄才能維持等寬對齊 */
  .step__label{
    font-family:"Cascadia Mono",Consolas,monospace;font-size:11.5px;
    color:var(--text);background:rgba(255,255,255,.06);
    padding:1px 7px;border-radius:5px;margin-right:8px;
  }
  .step__body code{
    font-family:"Cascadia Mono",Consolas,monospace;font-size:11.5px;
    background:rgba(255,255,255,.05);padding:1px 6px;border-radius:4px;
  }
  .step--think{border-left-color:var(--think)} .step--think .step__tag{color:var(--think)}
  .step--tool {border-left-color:var(--tool)}  .step--tool  .step__tag{color:var(--tool)}
  .step--result{border-left-color:var(--result)}.step--result .step__tag{color:var(--result)}
  .step--error{border-left-color:var(--error)} .step--error .step__tag{color:var(--error)}
  .step--error .step__body{color:#fca5a5}
  .step--llm  {border-left-color:var(--llm)}   .step--llm   .step__tag{color:var(--llm)}
  .step--note {border-left-color:var(--note)}  .step--note  .step__tag{color:var(--note)}
  .step--warn {border-left-color:var(--warn)}  .step--warn  .step__tag{color:var(--warn)}
  .step--wait {border-left-color:var(--wait);background:transparent}

  .thinking{
    align-self:flex-start;display:flex;align-items:center;gap:9px;
    padding:9px 15px;font-size:12.5px;color:var(--text-dim);
  }
  .dots{display:inline-flex;gap:3px}
  .dots i{width:4px;height:4px;border-radius:50%;background:var(--text-dim);animation:pulse 1.3s infinite}
  .dots i:nth-child(2){animation-delay:.18s} .dots i:nth-child(3){animation-delay:.36s}
  @keyframes pulse{0%,70%,100%{opacity:.25;transform:scale(.8)}35%{opacity:1;transform:scale(1)}}

  /* ── 起始畫面 ───────────────────────────────────────── */
  .welcome-screen{
    flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:14px;padding:20px;text-align:center;
  }
  .welcome-title{
    font-size:26px;font-weight:600;letter-spacing:.06em;color:var(--text);
    background:linear-gradient(135deg,#e6ebf5 20%,#8fb0f0);
    -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  }
  .welcome-rule{width:44px;height:2px;border-radius:2px;background:linear-gradient(90deg,var(--accent),#8b5cf6)}
  .welcome-desc{font-size:13px;color:var(--text-dim);max-width:430px;line-height:1.8}
  .welcome-hint{font-size:10.5px;color:#55627e;letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
  .examples{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:580px}
  .ex-item{
    padding:8px 15px;border-radius:999px;background:var(--surface);
    border:1px solid var(--line);color:var(--text-dim);font-size:12.5px;
    cursor:pointer;transition:all .18s;
  }
  .ex-item:hover{
    background:var(--accent-soft);border-color:var(--accent);color:var(--text);
    transform:translateY(-1px);
  }

  /* ── 輸入列 ─────────────────────────────────────────── */
  #footer{
    padding:13px 18px;background:var(--surface);border-top:1px solid var(--line);
    display:flex;gap:9px;align-items:center;
  }
  #inp{
    flex:1;padding:12px 16px;border-radius:var(--radius);
    border:1px solid var(--line);background:var(--bg);color:var(--text);
    font-size:14px;font-family:inherit;outline:none;transition:border-color .15s;
  }
  #inp::placeholder{color:#55627e}
  #inp:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(91,141,239,.12)}
  #send-btn{
    padding:12px 24px;background:var(--accent);color:#fff;border:none;
    border-radius:var(--radius);cursor:pointer;font-size:14px;font-weight:500;
    font-family:inherit;transition:background .15s;
  }
  #send-btn:hover:not(:disabled){background:#4776d8}
  #send-btn:disabled{background:#2a3550;color:#55627e;cursor:not-allowed}
  #clear-btn{padding:12px 15px}
</style>
</head>
<body>
<header>
  <span class="brand">可信賴雲</span>
  <span class="tag" id="llm-tag" style="background:#0d9488">載入中</span>
  <span id="switch-msg"></span>
  <span class="grow"></span>
  <label>LLM</label>
  <select id="llm-select" title="切換 LLM 供應商"></select>
  <button id="probe-btn" class="btn">測試連線</button>
  <label>區域</label>
  <select id="region-select" title="切換雲端區域（兩區價格不同）">
    <option value="AI-Trust">AI-Trust</option>
    <option value="AI-Cloud">AI-Cloud</option>
  </select>
  <label>使用者</label>
  <input id="user-input" style="width:100px" title="切換使用者（資料隔離）" />
  <label>計畫</label>
  <select id="project-select" title="目前使用中的計畫（資源開在計畫底下、扣計畫額度）"></select>
  <select id="plan-select" title="帳號計畫別（決定差別費率折扣）">
    <option>企業</option><option>個人</option><option>學術</option><option>政府法人</option><option>國科會</option>
  </select>
  <span id="plan-badge" title="計畫別由所屬計畫的類別決定"></span>
  <a href="/admin" target="_blank" class="btn">管理介面</a>
</header>
<div id="chat">
  <div class="welcome-screen">
    <p class="welcome-title">可信賴雲</p>
    <div class="welcome-rule"></div>
    <p class="welcome-desc">雲端資源查詢、試算與管理。會記住您的查詢偏好與機器；右上角可切換供應商、區域與使用者，資料各自隔離。</p>
    <p class="welcome-hint">點選範例快速開始</p>
    <div class="examples">
      <span class="ex-item">我要一台跑深度學習的 GPU 機器</span>
      <span class="ex-item">幫我開一台 H100.small</span>
      <span class="ex-item">列出我的機器</span>
      <span class="ex-item">vm-0001 花了多少錢</span>
      <span class="ex-item">我總共花多少</span>
      <span class="ex-item">我還剩多少錢、還能用幾天</span>
      <span class="ex-item">我有哪些計畫</span>
      <span class="ex-item">我的計畫額度還剩多少</span>
      <span class="ex-item">計畫要怎麼申請？</span>
    </div>
  </div>
</div>
<div id="footer">
  <button id="clear-btn" class="btn" title="清除對話記憶">清除</button>
  <input id="inp" placeholder="請輸入您的需求..." />
  <button id="send-btn">送出</button>
</div>
<script>
const chat = document.getElementById('chat');
const inp  = document.getElementById('inp');
const sendBtn = document.getElementById('send-btn');
const llmSelect = document.getElementById('llm-select');
const regionSelect = document.getElementById('region-select');
const planSelect = document.getElementById('plan-select');
const projectSelect = document.getElementById('project-select');
const planBadge = document.getElementById('plan-badge');
const userInput = document.getElementById('user-input');
const switchMsg = document.getElementById('switch-msg');

// 使用者身分（無密碼，僅用於資料隔離）；存 localStorage，隨每個請求帶到後端
let USER = localStorage.getItem('cloud_user') || 'default';
userInput.value = USER;
// 雲端區域（價格不同）；存 localStorage，隨每個請求以 X-Region 帶到後端
let REGION = localStorage.getItem('cloud_region') || 'AI-Trust';
regionSelect.value = REGION;
function headers(json){ const h = {'X-User-Id': USER, 'X-Region': REGION}; if(json) h['Content-Type']='application/json'; return h; }

userInput.addEventListener('change', function(){
  USER = (userInput.value.trim() || 'default').replace(/[^a-zA-Z0-9_-]/g,'');
  userInput.value = USER;
  localStorage.setItem('cloud_user', USER);
  setSwitch('已切換使用者：'+USER, '#0d9488');
  loadProfile();   // 每個帳號有自己的身分
});

regionSelect.addEventListener('change', function(){
  REGION = regionSelect.value;
  localStorage.setItem('cloud_region', REGION);
  setSwitch('已切換區域：'+REGION+'（價格不同）', '#7c3aed');
});

// 帳號身分（計畫別）：W5 起有計畫者一律「從計畫讀」，自選下拉只留給沒有計畫的個人用戶。
// 兩個控制項擇一顯示：有計畫 → 計畫下拉 + 唯讀身分標籤；無計畫 → 自選身分下拉。
function renderProfile(d){
  const fromProject = d.plan_source === 'project';
  projectSelect.style.display = fromProject ? '' : 'none';
  planBadge.style.display     = fromProject ? '' : 'none';
  planSelect.style.display    = fromProject ? 'none' : '';
  if(fromProject){
    projectSelect.value = d.project_id || '';
    planBadge.textContent = '身分：'+d.plan_type+'（依計畫）';
  } else if(d.plan_type){
    planSelect.value = d.plan_type;
  }
}
function loadProfile(){
  fetch('/api/projects', {headers: headers()}).then(r=>r.json()).then(pj=>{
    projectSelect.innerHTML = pj.projects.map(function(p){
      return '<option value="'+p.project_id+'">'+p.project_id+'｜'+p.名稱
           + (p.active ? '' : '（'+p.狀態+'）')+'</option>';
    }).join('');
    return fetch('/api/profile', {headers: headers()}).then(r=>r.json());
  }).then(renderProfile);
}
projectSelect.addEventListener('change', function(){
  fetch('/api/project', {method:'POST', headers: headers(true),
    body: JSON.stringify({project_id: projectSelect.value})})
    .then(r=>r.json()).then(d=>{
      if(!d.ok){ setSwitch(d.msg || '切換計畫失敗', '#dc2626'); return; }
      renderProfile(d);
      setSwitch(d.msg+'　身分：'+d.plan_type+'（折扣與額度依此計畫）', '#7c3aed');
    });
});
planSelect.addEventListener('change', function(){
  fetch('/api/profile', {method:'POST', headers: headers(true),
    body: JSON.stringify({plan_type: planSelect.value})})
    .then(r=>r.json()).then(d=>{
      renderProfile(d);
      setSwitch('帳號身分：'+d.plan_type+'（估算/計費將依此套折扣）', '#7c3aed');
    });
});
loadProfile();

function setSwitch(text, color){
  switchMsg.textContent = text;
  switchMsg.style.background = color || '#334155';
  switchMsg.style.color = '#fff';
  if(text) setTimeout(function(){ if(switchMsg.textContent===text){ switchMsg.textContent=''; switchMsg.style.background='transparent'; } }, 4000);
}

const STATUS_COLOR = {ok:'#0d9488', unreachable:'#dc2626', auth_error:'#dc2626', quota_exceeded:'#d97706', rate_limited:'#d97706', disabled:'#475569', no_sdk:'#475569', error:'#dc2626'};

// 載入供應商清單 + 目前狀態
function loadProviders(){
  fetch('/api/llm/providers', {headers: headers()}).then(r=>r.json()).then(d=>{
    llmSelect.innerHTML = '';
    d.providers.forEach(function(p){
      const opt = document.createElement('option');
      // 狀態用文字表達（p.detail 就是「可用／無法連線／額度不足…」），
      opt.value = p.id;
      opt.textContent = p.label + '（' + p.detail + '）';
      opt.disabled = (p.status==='disabled');
      if(p.active) opt.selected = true;
      llmSelect.appendChild(opt);
    });
    const active = d.providers.find(p=>p.active);
    const tag = document.getElementById('llm-tag');
    if(active){ tag.textContent = active.label; tag.style.background = STATUS_COLOR[active.status] || '#0d9488'; }
  });
}

llmSelect.addEventListener('change', function(){
  const id = llmSelect.value;
  setSwitch('切換中…', '#334155');
  fetch('/api/llm/switch', {method:'POST', headers: headers(true), body: JSON.stringify({id})})
    .then(r=>r.json()).then(d=>{
      if(d.ok){
        const s = d.status;
        const color = STATUS_COLOR[s.status] || '#0d9488';
        setSwitch(d.msg + '｜' + s.detail, color);
      } else {
        setSwitch('切換失敗：' + d.msg, '#dc2626');
      }
      loadProviders();
    }).catch(()=> setSwitch('切換失敗', '#dc2626'));
});

document.getElementById('probe-btn').addEventListener('click', function(){
  setSwitch('測試連線中…', '#334155');
  fetch('/api/llm/providers', {headers: headers()}).then(r=>r.json()).then(d=>{
    const parts = d.providers.map(p=> p.label+'='+p.detail);
    setSwitch(parts.join('　'), '#334155');
    loadProviders();
  });
});

loadProviders();

document.querySelectorAll('.ex-item').forEach(function(item){
  item.addEventListener('click', function(){ inp.value = item.textContent.trim(); doSend(); });
});
inp.addEventListener('keydown', function(e){ if(e.key === 'Enter') doSend(); });
sendBtn.addEventListener('click', doSend);

document.getElementById('clear-btn').addEventListener('click', async function(){
  await fetch('/clear', {method:'POST', headers: headers()});
  chat.innerHTML = '';
  addMsg('對話記憶已清除，請重新開始。', 'agent');
});

function addMsg(text, cls){
  const d = document.createElement('div');
  d.className = 'msg ' + cls;
  d.textContent = text;
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight; return d;
}
// 推理步驟的分類由後端以 kind 欄位明講，前端只負責上色與標籤。
// 舊做法是比對訊息裡的 emoji 來猜類別，訊息文字一改就會失準。
const STEP_TAG = {
  think:'推理', tool:'工具', result:'回傳', error:'錯誤',
  llm:'模型', note:'記錄', warn:'注意', wait:'等待'
};
function addStep(text, kind, label){
  const k = STEP_TAG[kind] ? kind : 'wait';
  const d = document.createElement('div');
  d.className = 'step step--' + k;
  const tag = document.createElement('span');
  tag.className = 'step__tag';
  tag.textContent = STEP_TAG[k];
  const body = document.createElement('span');
  body.className = 'step__body';
  if(label){
    const lb = document.createElement('span');
    lb.className = 'step__label';
    lb.textContent = label;
    body.appendChild(lb);
  }
  body.appendChild(document.createTextNode(text));
  d.appendChild(tag); d.appendChild(body);
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
  setTimeout(function(){ d.classList.add('show'); }, 30);
}
function addThinking(){
  const d = document.createElement('div');
  d.className='thinking'; d.id='thinking';
  d.innerHTML = '<span>處理中</span><span class="dots"><i></i><i></i><i></i></span>';
  chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
}
function removeThinking(){ const el=document.getElementById('thinking'); if(el) el.remove(); }

async function doSend(){
  const q = inp.value.trim(); if(!q) return;
  // 送出第一則訊息後就把起始畫面收掉，否則範例膠囊會一直卡在對話上方
  const w = chat.querySelector('.welcome-screen');
  if(w) w.remove();
  inp.value=''; sendBtn.disabled=true;
  addMsg(q, 'user'); addThinking();
  try{
    const res = await fetch('/ask_stream', {method:'POST', headers: headers(true), body: JSON.stringify({query:q})});
    const reader = res.body.getReader(); const decoder = new TextDecoder(); let first=true;
    // 真串流下事件是一小塊一小塊到的：一筆 data: 可能被切在兩個 chunk 中間，
    // 一個中文字的 UTF-8 位元組也可能被切開。所以要 (1) 用 stream:true 解碼，
    // (2) 留一個 buffer，只處理已收到換行的完整事件，其餘留到下一輪再拼。
    let buf = '';
    while(true){
      const {done, value} = await reader.read(); if(done) break;
      buf += decoder.decode(value, {stream:true});
      const lines = buf.split('\\n');
      buf = lines.pop();                      // 最後一段可能只有半筆，留著
      for(const line of lines){
        if(!line.startsWith('data:')) continue;
        try{
          const data = JSON.parse(line.slice(5));
          if(data.type==='step'){ if(first){removeThinking(); first=false;} addStep(data.text, data.kind, data.label); await new Promise(r=>setTimeout(r,60)); }
          else if(data.type==='answer'){ removeThinking(); addMsg(data.text, 'agent'); }
          else if(data.type==='error'){ removeThinking(); addStep(data.text, 'error'); }
        }catch(e){}
      }
    }
  }catch(e){ removeThinking(); addMsg('發生錯誤，請稍後再試', 'agent'); }
  sendBtn.disabled=false; inp.focus();
}
</script>
</body>
</html>"""


def send_event(data: dict) -> str:
    return f"data:{json.dumps(data, ensure_ascii=False)}\n\n"


HEARTBEAT_SECONDS = 5.0


async def think(fn, queue, label="推理"):
    task = asyncio.create_task(asyncio.to_thread(fn))
    t0 = time.monotonic()
    next_tick = HEARTBEAT_SECONDS
    while True:
        done, _ = await asyncio.wait({task}, timeout=0.5)
        if done:
            return task.result()
        elapsed = time.monotonic() - t0
        if elapsed >= next_tick:
            chars = providers.PROGRESS.get("chars", 0)
            wrote = f"，已產出 {chars} 字" if chars else ""
            await queue.put({"type": "step", "kind": "wait",
                             "text": f"{label}中，已等 {int(elapsed)} 秒{wrote}"})
            next_tick += HEARTBEAT_SECONDS


_histories = {}


def _history_for(user_id: str) -> list:
    return _histories.setdefault(settings.safe_user(user_id), [])


async def run_agent_stream(user_input, queue, user_id, region=None):
    history = _history_for(user_id)
    messages = build_messages(user_input, history)
    faq_context = None
    selected_label = providers.active_label()

    try:
        async with get_client() as client:
            for i in range(1, 8):
                try:
                    d = await think(lambda: call_and_parse(messages), queue,
                                    f"第{i}輪推理")
                except Exception as e:
                    await queue.put({"type": "error", "text": f"推理失敗：{e}"})
                    return

                used = providers.LAST_USED
                if used and used[1] != selected_label:
                    why = "；".join(providers.LAST_ERRORS) or "原因不明"
                    await queue.put({"type": "step", "kind": "llm", "text": (
                        f"選用的 {selected_label} 這次沒用上，已自動改用 {used[1]}"
                        f"　原因：{why}")})
                    selected_label = used[1]
                    await asyncio.sleep(0.05)

                thought = d.get("thought", "")
                action = d.get("action", "")
                params = d.get("params", {})

                await queue.put({"type": "step", "kind": "think",
                                 "label": f"第 {i} 輪", "text": thought})
                await asyncio.sleep(0.1)

                if action == "FINISH":
                    answer = d.get("answer", "")
                    if faq_context:
                        from agent.core import enforce_grounding
                        answer, g, attempts = await think(
                            lambda: enforce_grounding(messages, d, faq_context),
                            queue, "忠實度檢核")
                        if attempts:
                            await queue.put({"type": "step", "kind": "note", "text": (
                                f"忠實度檢核未過，已自動依知識庫重答 {attempts} 次"
                                f"（支持度回到 {g['score']}）")})
                            await asyncio.sleep(0.1)
                        elif not g["ok"]:
                            await queue.put({"type": "step", "kind": "warn", "text": (
                                f"忠實度檢核：支持度 {g['score']}，部分內容可能超出知識庫")})
                            await asyncio.sleep(0.1)
                        from common.observability import maybe_log_weak_faq_miss
                        if maybe_log_weak_faq_miss(user_input, faq_context, g, user_id):
                            await queue.put({"type": "step", "kind": "note", "text": (
                                "已記錄 FAQ 未命中：知識庫無法支持此題，供後續補題")})
                            await asyncio.sleep(0.05)
                    history.append({"role": "user", "content": user_input})
                    history.append({"role": "assistant", "content": answer})
                    if len(history) > 20:
                        history[:] = history[-20:]
                    await queue.put({"type": "step", "kind": "llm",
                                     "text": f"由 {selected_label} 生成回答"})
                    await asyncio.sleep(0.05)
                    await queue.put({"type": "answer", "text": answer})
                    return

                await queue.put({"type": "step", "kind": "tool", "label": action,
                                 "text": f"參數 {params}"})
                await asyncio.sleep(0.1)

                ok, result = await agent_tools.call_tool(client, action, params, user_id, region)
                short = result[:150] + ('...' if len(result) > 150 else '')
                if ok:
                    await queue.put({"type": "step", "kind": "result", "text": short})
                    if action == "search_faq":
                        faq_context = result
                else:
                    await queue.put({"type": "step", "kind": "error", "text": result})
                await asyncio.sleep(0.1)

                messages += [
                    {"role": "assistant", "content": json.dumps(d, ensure_ascii=False)},
                    {"role": "user", "content": f"Tool {action} 回傳：\n{result}\n請繼續推理。"},
                ]

        await queue.put({"type": "answer", "text": "已達最大推理輪數，請換個方式描述需求"})
    except Exception as e:
        await queue.put({"type": "error", "text": str(e)})
    finally:
        await queue.put(None)


app = Flask(__name__)
app.register_blueprint(admin_bp)


def current_user() -> str:
    return request.headers.get("X-User-Id", settings.DEFAULT_USER)


def current_region() -> str:
    return settings.safe_region(request.headers.get("X-Region"))


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/status")
def status():
    return jsonify({"llm": providers.active_label(), "kind": providers.active_kind()})


@app.route("/api/llm/providers")
def api_llm_providers():
    return jsonify({"providers": providers.probe_all(), "active": providers.active_id()})


@app.route("/api/llm/switch", methods=["POST"])
def api_llm_switch():
    data = request.get_json(silent=True) or {}
    pid = data.get("id", "")
    ok, msg = providers.set_active(pid)
    status_info = providers.probe(pid) if ok else {}
    return jsonify({"ok": ok, "msg": msg, "status": status_info})


@app.route("/ask_stream", methods=["POST"])
def ask_stream():
    data = request.get_json()
    query = data.get("query", "")
    user_id = current_user()
    region = current_region()

    def generate():
        yield ":" + " " * 2048 + "\n\n"
        yield send_event({"type": "step", "kind": "wait", "text": "已收到，開始處理"})

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        producer = None
        try:
            queue = asyncio.Queue()
            producer = loop.create_task(
                run_agent_stream(query, queue, user_id, region))
            while True:
                item = loop.run_until_complete(queue.get())
                if item is None:
                    break
                yield send_event(item)
            loop.run_until_complete(producer)
        finally:
            if producer is not None and not producer.done():
                producer.cancel()
                try:
                    loop.run_until_complete(producer)
                except BaseException:
                    pass
            loop.close()
            asyncio.set_event_loop(None)

    return Response(stream_with_context(generate()),
                    mimetype='text/event-stream',
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/api/profile", methods=["GET"])
def api_profile_get():
    from common import accounts
    return jsonify(accounts.get_profile(current_user()))


@app.route("/api/profile", methods=["POST"])
def api_profile_set():
    from common import accounts
    data = request.get_json(silent=True) or {}
    return jsonify({"ok": True, **accounts.set_profile(current_user(), data.get("plan_type", ""))})


@app.route("/api/projects", methods=["GET"])
def api_projects():
    from common import accounts, projects
    uid = current_user()
    cur = accounts.current_project(uid)
    return jsonify({
        "projects": [{
            "project_id": p["project_id"], "名稱": p["名稱"], "類別": p["類別"],
            "計畫別": p["計畫別"], "狀態": p["狀態"], "active": projects.is_active(p),
        } for p in projects.for_user(uid)],
        "current": cur["project_id"] if cur else "",
    })


@app.route("/api/project", methods=["POST"])
def api_project_set():
    from common import accounts
    data = request.get_json(silent=True) or {}
    ok, res = accounts.set_current_project(current_user(), data.get("project_id", ""))
    if not ok:
        return jsonify({"ok": False, "msg": res}), 400
    return jsonify({"ok": True, "msg": f"已切換計畫：{res['project_id']}（{res['名稱']}）",
                    **accounts.get_profile(current_user())})


@app.route("/clear", methods=["POST"])
def clear():
    _history_for(current_user()).clear()
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    print("   可信賴雲 AI Agent (Web版)")
    print("   瀏覽器開啟 http://127.0.0.1:5000")
    print("   管理介面   http://127.0.0.1:5000/admin")
    app.run(host=settings.WEB_HOST, port=settings.WEB_PORT, debug=False, threaded=True)
