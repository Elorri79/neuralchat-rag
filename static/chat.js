'use strict';

// ── Config from data attributes ──────────────────────────────────────────────
const MODEL = document.getElementById('chat-root')?.dataset.model || 'llama3.2:1b';
const OLLAMA = document.getElementById('chat-root')?.dataset.ollama || 'http://127.0.0.1:11434';

// ── State ─────────────────────────────────────────────────────────────────────
let conv = []; // {role:'user'|'assistant', content}
let tokenCount = 0;
let msgCount = 0;
let respTimes = [];
let userTokenLens = [];
let aiTokenLens = [];
let ragDocs = [];       // último resultado de retrieval
let ragEnabled = true;  // toggle RAG

// ── DOM ─────────────────────────────────────────────────────────────────────
const chat    = document.getElementById('chat');
const input   = document.getElementById('input');
const sendBtn = document.getElementById('send');
const dot     = document.getElementById('dot');
const status  = document.getElementById('status-text');
const ragDot  = document.getElementById('rag-dot');

// ── Auto-resize textarea ─────────────────────────────────────────────────────
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 140) + 'px';
});
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMsg();
  }
});

// ── RAG toggle ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('rag-enabled');
  if (toggle) {
    toggle.addEventListener('change', () => { ragEnabled = toggle.checked; });
  }
});

// ── Charts ───────────────────────────────────────────────────────────────────
const COLORS = ['#ff6b6b','#ffd93d','#6bcb77','#4d96ff','#c77dff','#ff9f43','#39c5bb','#f778ba'];
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = 'rgba(48,54,61,.8)';

function makeChart(id, labels, data, maxBars=8) {
  return new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{ data, backgroundColor: COLORS.slice(0, data.length), borderWidth: 0, borderRadius: 4 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      animation: { duration: 400 },
      scales: {
        x: { grid: { color: 'rgba(48,54,61,.6)' }, ticks: { color: '#8b949e', font: { size: 9 } } },
        y: { grid: { color: 'rgba(48,54,61,.6)' }, ticks: { color: '#8b949e', font: { size: 9 } }, beginAtZero: true }
      }
    }
  });
}

// chartTokens → tokens por mensaje (barras verticales)
let chartTokens = makeChart('chartTokens', ['—'], [0]);
// chartTime → tiempo de respuesta en segundos (barras)
let chartTime   = makeChart('chartTime', ['—'], [0]);

let MAX_BARS = 8;

function updateCharts() {
  // Tokens: últimas MAX_BARS interacciones de usuario
  const tData   = userTokenLens.slice(-MAX_BARS);
  const n       = tData.length;
  chartTokens.data.labels = Array.from({length:n}, (_,i)=>'M'+(userTokenLens.length-n+i+1));
  chartTokens.data.datasets[0].data = tData;
  chartTokens.update('none');

  // Tiempo de respuesta
  chartTime.data.datasets[0].data = respTimes;
  chartTime.data.labels = respTimes.map((_,i)=>'R'+(i+1));
  chartTime.update('none');
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function scrollBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function addMessage(role, content, extraClass='') {
  const div = document.createElement('div');
  div.className = 'msg ' + role + (extraClass ? ' '+extraClass : '');

  if (role === 'ai') {
    const name = document.createElement('div');
    name.className = 'name';
    name.innerHTML = '<span style="color:#c77dff">◈</span> NeuroGPT';
    div.appendChild(name);
    content = formatContent(content);
  }

  div.innerHTML += content;
  chat.appendChild(div);
  scrollBottom();
  return div;
}

function formatContent(text) {
  let t = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  t = t.replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre class="msg-code"><code>$2</code></pre>');
  t = t.replace(/(^|[^`])`([^`]+)`([^`]|$)/g, '$1<code style="background:rgba(88,166,255,.12);color:#58a6ff;padding:1px 5px;border-radius:4px">$2</code>$3');
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  t = t.replace(/\n/g, '<br>');
  return t;
}

function setThinking(on) {
  if (on) {
    const div = document.createElement('div');
    div.id = 'thinking';
    div.className = 'msg ai thinking';
    div.innerHTML = 'Pensando<span class="typing-dots"><span></span><span></span><span></span></span>';
    chat.appendChild(div);
    scrollBottom();
  } else {
    const t = document.getElementById('thinking');
    if (t) t.remove();
  }
}

// ── Show RAG context in chat ──────────────────────────────────────────────────
function showRagContext(docs) {
  if (!docs || docs.length === 0) return;
  const div = document.createElement('div');
  div.className = 'msg ai rag-context';
  let html = '<div class="rag-context-label">📚 Contexto RAG recuperado</div>';
  docs.forEach((d, i) => {
    const src = d.source || '?';
    const snippet = d.content.length > 200 ? d.content.slice(0, 200) + '…' : d.content;
    html += `<details style="margin-top:6px"><summary style="cursor:pointer;font-size:.75rem;color:var(--purple)">${src} [chunk ${i+1}] — distancia: ${d.distance?.toFixed(3)}</summary><div style="margin-top:4px;font-size:.75rem;color:var(--muted);white-space:pre-wrap">${formatContent(snippet)}</div></details>`;
  });
  div.innerHTML = html;
  chat.appendChild(div);
  scrollBottom();
}

// ── Retrieve RAG context ───────────────────────────────────────────────────────
async function retrieveRag(query) {
  try {
    const r = await fetch('/rag/retrieve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: 4 })
    });
    const d = await r.json();
    return d.docs || [];
  } catch(e) {
    return [];
  }
}

// ── Send ─────────────────────────────────────────────────────────────────────
async function sendMsg() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';

  addMessage('user', text);
  conv.push({ role: 'user', content: text });
  userTokenLens.push(text.split(/\s/).length);

  // ── RAG retrieval (antes de enviar al modelo) ─────────────────────────────
  ragDocs = [];
  if (ragEnabled) {
    ragDocs = await retrieveRag(text);
    if (ragDocs.length > 0) {
      ragDot.classList.add('active');
      showRagContext(ragDocs);
    } else {
      ragDot.classList.remove('active');
    }
  }

  setThinking(true);
  sendBtn.disabled = true;

  const t0 = Date.now();

  try {
    const body = { model: MODEL, messages: conv, rag: ragEnabled, rag_context: ragDocs };

    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    setThinking(false);

    if (!res.ok) throw new Error('HTTP ' + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let reply = '';
    let done = false;

    const aiDiv = addMessage('ai', '');

    while (!done) {
      const { value, done: d } = await reader.read();
      done = d;
      if (value) {
        const chunk = decoder.decode(value, { stream: !d });
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data:')) {
            try {
              const obj = JSON.parse(line.slice(5));
              if (obj.message?.content) {
                reply += obj.message.content;
                aiDiv.innerHTML = '<div class="name"><span style="color:#c77dff">◈</span> NeuroGPT</div>' + formatContent(reply);
                scrollBottom();
              }
              if (obj.done) {
                conv.push({ role: 'assistant', content: reply });
                msgCount++;
                const elapsed = ((Date.now()-t0)/1000).toFixed(1);
                respTimes.push(parseFloat(elapsed));
                aiTokenLens.push(reply.split(/\s/).length);
                tokenCount += reply.length;

                document.getElementById('kpi-tokens').textContent = tokenCount;
                document.getElementById('kpi-msgs').textContent = msgCount;
                document.getElementById('kpi-time').textContent = elapsed + 's';

                updateCharts();

                ragDot.classList.remove('active');
              }
            } catch(e) {}
          }
        }
      }
    }

  } catch(err) {
    setThinking(false);
    addMessage('ai', '⚠ Error: ' + err.message + ' — ¿Está Ollama corriendo?', 'error');
    dot.classList.add('offline');
    status.textContent = 'Ollama desconectado';
    ragDot.classList.remove('active');
  }

  sendBtn.disabled = false;
  input.focus();
}

function clearChat() {
  chat.innerHTML = '';
  conv = [];
  tokenCount = 0;
  msgCount = 0;
  respTimes = [];
  userTokenLens = [];
  aiTokenLens = [];
  ragDocs = [];
  document.getElementById('kpi-tokens').textContent = '0';
  document.getElementById('kpi-msgs').textContent = '0';
  document.getElementById('kpi-time').textContent = '—';
  document.getElementById('kpi-chunks').textContent = '—';
  chartTokens.data.datasets[0].data = [0];
  chartTokens.data.labels = ['—'];
  chartTokens.update('none');
  chartTime.data.datasets[0].data = [];
  chartTime.data.labels = ['—'];
  chartTime.update('none');
  // reload rag stats
  if (typeof loadRagStats === 'function') loadRagStats();
}
