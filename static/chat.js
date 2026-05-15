'use strict';

const MODEL = document.getElementById('chat-root')?.dataset.model || 'llama3.2:1b';
const OLLAMA = document.getElementById('chat-root')?.dataset.ollama || 'http://127.0.0.1:11434';

let conv = [];
let tokenCount = 0;
let msgCount = 0;
let respTimes = [];
let userTokenLens = [];
let aiTokenLens = [];
let ragDocs = [];
let ragEnabled = true;
let currentModel = MODEL;

async function loadModels() {
  const sel = document.getElementById('model-select');
  if (!sel) return;
  try {
    const r = await fetch('/models');
    const d = await r.json();
    if (d.models && d.models.length) {
      sel.innerHTML = d.models.map(m =>
        `<option value="${m}" ${m === currentModel ? 'selected' : ''}>${m}</option>`
      ).join('');
      sel.addEventListener('change', () => {
        currentModel = sel.value;
        document.getElementById('chat-root').dataset.model = currentModel;
        document.querySelector('.model-badge').textContent = '🤖 ' + currentModel;
      });
    } else {
      sel.innerHTML = '<option value="">Sin modelos</option>';
    }
  } catch(e) {
    sel.innerHTML = '<option value="">Error cargando</option>';
  }
}
loadModels();

const chat    = document.getElementById('chat');
const input   = document.getElementById('input');
const sendBtn = document.getElementById('send');
const dot     = document.getElementById('dot');
const status  = document.getElementById('status-text');
const ragDot  = document.getElementById('rag-dot');

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

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.getElementById('rag-enabled');
  if (toggle) {
    toggle.addEventListener('change', () => { ragEnabled = toggle.checked; });
  }
});

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

let chartTokens = makeChart('chartTokens', ['—'], [0]);
let chartTime   = makeChart('chartTime', ['—'], [0]);

let MAX_BARS = 8;

function updateCharts() {
  const tData   = userTokenLens.slice(-MAX_BARS);
  const n       = tData.length;
  chartTokens.data.labels = Array.from({length:n}, (_,i)=>'M'+(userTokenLens.length-n+i+1));
  chartTokens.data.datasets[0].data = tData;
  chartTokens.update('none');

  chartTime.data.datasets[0].data = respTimes;
  chartTime.data.labels = respTimes.map((_,i)=>'R'+(i+1));
  chartTime.update('none');
}

function scrollBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function addMessage(role, content, extraClass='') {
  const div = document.createElement('div');
  div.className = 'msg ' + role + (extraClass ? ' '+extraClass : '');

  if (role === 'ai') {
    const name = document.createElement('div');
    name.className = 'name';
    name.innerHTML = '<span style="color:#c77dff">◈</span> RagBot';
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

async function sendMsg() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  input.style.height = 'auto';

  addMessage('user', text);
  conv.push({ role: 'user', content: text });
  userTokenLens.push(text.split(/\s/).length);

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
    const body = { model: currentModel, messages: conv, rag: ragEnabled, rag_context: ragDocs };

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
                aiDiv.innerHTML = '<div class="name"><span style="color:#c77dff">◈</span> RagBot</div>' + formatContent(reply);
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
  if (typeof loadRagStats === 'function') loadRagStats();
}

// ── RAG stats ─────────────────────────────────────────────────────────────────
async function loadRagStats() {
  try {
    const r = await fetch('/rag/status');
    const d = await r.json();
    document.getElementById('kpi-chunks').textContent = d.chunks || 0;
    document.getElementById('rag-panel').style.display = d.chunks > 0 ? 'block' : 'none';
    const srcEl = document.getElementById('rag-sources');
    if (d.sources && d.sources.length) {
      srcEl.innerHTML = d.sources.map(s => `<span>${s}</span>`).join('');
    } else {
      srcEl.innerHTML = '<span style="color:var(--muted)">Sin documentos</span>';
    }
  } catch(e) {}
}

// ── File upload / ingest ──────────────────────────────────────────────────────
const uploadArea = document.getElementById('upload-area');
const fileInput  = document.getElementById('file-input');
const resultEl   = document.getElementById('ingest-result');

uploadArea.addEventListener('dragover', e => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', e => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  fileInput.files = e.dataTransfer.files;
  if (fileInput.files.length) ingestFiles(fileInput.files);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files.length) ingestFiles(fileInput.files);
});

async function ingestFiles(files) {
  resultEl.innerHTML = '⏳ Subiendo…';
  const formData = new FormData();
  for (const f of files) formData.append('files', f);
  try {
    const r = await fetch('/rag/ingest', { method: 'POST', body: formData });
    const d = await r.json();
    resultEl.innerHTML = '';
    if (d.error) {
      resultEl.innerHTML = `<span style="color:var(--crit)">Error: ${d.error}</span>`;
    } else {
      const total = d.total_chunks || 0;
      resultEl.innerHTML = `<span style="color:var(--ok)">✅ ${total} chunks ingestados de ${d.files.length} archivo(s)</span>`;
      resultEl.innerHTML += '<br>' + d.files.map(f =>
        `${f.file}: ${f.status === 'ok' ? f.chunks + ' chunks' : f.status}`
      ).join('<br>');
    }
    loadRagStats();
    loadDocList();
  } catch(e) {
    resultEl.innerHTML = `<span style="color:var(--crit)">Error: ${e.message}</span>`;
  }
}

async function resetRag() {
  if (!confirm('¿Borrar toda la knowledge base?')) return;
  try {
    const r = await fetch('/rag/reset', { method: 'POST' });
    const d = await r.json();
    resultEl.innerHTML = `<span style="color:var(--ok)">${d.status}</span>`;
    loadRagStats();
    loadDocList();
  } catch(e) { resultEl.innerHTML = `<span style="color:var(--crit)">${e.message}</span>`; }
}

// ── File Browser ───────────────────────────────────────────────────────────────
const SUPPORTED_EXTS = new Set(['.txt','.md','.csv','.json','.html','.htm','.py','.pdf']);

let fbCurrentPath = '';
let fbHome = '';
let fbEntries = [];
let fbSelected = new Set();

function fileIcon(name) {
  if (name === '..') return '↩️';
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
  if (ext === '.txt') return '📄';
  if (ext === '.md')  return '📝';
  if (ext === '.csv') return '📊';
  if (ext === '.json') return '🔗';
  if (ext === '.html' || ext === '.htm') return '🌐';
  if (ext === '.py')  return '🐍';
  if (ext === '.pdf') return '📕';
  return '📄';
}
function extColor(name) {
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
  if (ext === '.txt') return 'var(--accent)';
  if (ext === '.md')  return '#4d96ff';
  if (ext === '.csv') return '#3fb950';
  if (ext === '.json') return '#d29922';
  if (ext === '.html' || ext === '.htm') return '#f778ba';
  if (ext === '.py')  return '#ffd93d';
  if (ext === '.pdf') return '#f85149';
  return 'var(--muted)';
}

function formatSize(bytes) {
  if (bytes === 0) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1024/1024).toFixed(1) + ' MB';
}

async function loadDir(path) {
  const browser = document.getElementById('file-browser');
  browser.innerHTML = '<div class="fb-loading">⏳ Cargando…</div>';
  try {
    const r = await fetch('/rag/browse?path=' + encodeURIComponent(path));
    const d = await r.json();
    fbCurrentPath = d.path;
    fbHome = d.home;
    fbEntries = d.entries || [];
    if (d.error) {
      browser.innerHTML = `<div class="fb-empty">⚠️ ${d.error}</div>`;
      return;
    }
    renderBrowser();
    renderPathBar();
  } catch(e) {
    browser.innerHTML = `<div class="fb-empty">⚠️ Error: ${e.message}</div>`;
  }
}

function renderBrowser() {
  const browser = document.getElementById('file-browser');
  if (fbEntries.length === 0) {
    browser.innerHTML = '<div class="fb-empty">Carpeta vacía</div>';
    return;
  }
  browser.innerHTML = fbEntries.map((e, i) => {
    const icon = e.is_dir ? '📁' : fileIcon(e.name);
    const checked = fbSelected.has(e.path) ? 'checked' : '';
    const ext = e.name.slice(e.name.lastIndexOf('.')).toLowerCase();
    const supported = e.is_dir || SUPPORTED_EXTS.has(ext);
    const dimmed = !e.is_dir && !supported ? 'opacity:.45' : '';
    return `<div class="fb-row ${e.is_dir ? 'dir' : 'file'}" data-index="${i}" style="${dimmed}">
      <input type="checkbox" ${checked} ${e.is_dir ? 'disabled' : ''} onclick="event.stopPropagation(); toggleFile('${e.path.replace(/'/g,"\\'")}')">
      <span class="fb-icon">${icon}</span>
      <span class="fb-name" style="${!e.is_dir ? 'color:'+extColor(e.name) : ''}">${e.name}</span>
      ${e.is_dir ? '' : `<span class="fb-size">${formatSize(e.size)}</span>`}
    </div>`;
  }).join('');

  browser.querySelectorAll('.fb-row').forEach(row => {
    row.addEventListener('click', e => {
      if (e.target.type === 'checkbox') return;
      const idx = parseInt(row.dataset.index);
      const entry = fbEntries[idx];
      if (entry.is_dir) {
        fbSelected.delete(entry.path);
        updateIngestBtn();
        loadDir(entry.path);
      } else {
        const ext = entry.name.slice(entry.name.lastIndexOf('.')).toLowerCase();
        if (SUPPORTED_EXTS.has(ext)) {
          toggleFile(entry.path);
        }
      }
    });
  });
}

function renderPathBar() {
  const bar = document.getElementById('fb-path-bar');
  const parts = fbCurrentPath.replace(fbHome, '~').split('/').filter(Boolean);
  let html = `<span class="fb-path-segment" onclick="loadDir(fbHome)">~</span>`;
  let built = fbHome;
  for (const p of parts) {
    built = built + '/' + p;
    html += `<span class="fb-path-sep">/</span><span class="fb-path-segment" onclick="loadDir('${built.replace(/'/g,"\\'")}')">${p}</span>`;
  }
  bar.innerHTML = html;
}

function toggleFile(path) {
  if (fbSelected.has(path)) fbSelected.delete(path);
  else fbSelected.add(path);
  updateIngestBtn();
  renderBrowser();
}

function toggleSelectAll() {
  const files = fbEntries.filter(e => !e.is_dir && SUPPORTED_EXTS.has(e.name.slice(e.name.lastIndexOf('.')).toLowerCase()));
  if (fbSelected.size === files.length) {
    fbSelected.clear();
  } else {
    files.forEach(f => fbSelected.add(f.path));
  }
  updateIngestBtn();
  renderBrowser();
}

function updateIngestBtn() {
  const count = fbSelected.size;
  document.getElementById('fb-count').textContent = count === 0
    ? '0 archivos seleccionados'
    : `${count} archivo${count !== 1 ? 's' : ''} seleccionado${count !== 1 ? 's' : ''}`;
  document.getElementById('btn-ingest').disabled = count === 0;
}

async function ingestSelected() {
  const paths = Array.from(fbSelected);
  if (paths.length === 0) return;
  const btn = document.getElementById('btn-ingest');
  const countEl = document.getElementById('fb-count');
  const prog = document.getElementById('ingest-progress');
  const progBar = document.getElementById('prog-bar');
  const progLabel = document.getElementById('prog-label');

  btn.disabled = true;
  countEl.textContent = '⏳ Ingestando…';
  prog.classList.add('active');
  progBar.value = 0;
  progLabel.textContent = `0/${paths.length} archivos procesados…`;

  let completed = 0;
  const total = paths.length;

  for (const fpath of paths) {
    progLabel.textContent = `${completed+1}/${total} — ${fpath.split('/').pop()}`;
    try {
      const r = await fetch('/rag/ingest-paths', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paths: [fpath] })
      });
      const d = await r.json();
      completed++;
      progBar.value = (completed / total) * 100;
      if (d.error) {
        resultEl.innerHTML += `<div style="color:var(--crit)">⚠ ${fpath.split('/').pop()}: ${d.error}</div>`;
      }
    } catch(e) {
      completed++;
      progBar.value = (completed / total) * 100;
      resultEl.innerHTML += `<div style="color:var(--crit)">⚠ ${fpath.split('/').pop()}: ${e.message}</div>`;
    }
  }

  progLabel.textContent = `✅ ${completed} archivos procesados`;
  fbSelected.clear();
  updateIngestBtn();
  renderBrowser();
  loadRagStats();
  loadDocList();
  btn.disabled = false;
}

// ── Document list & preview ──────────────────────────────────────────────────
async function loadDocList() {
  const section = document.getElementById('doc-list-section');
  const listEl = document.getElementById('doc-list');
  try {
    const r = await fetch('/rag/documents');
    const d = await r.json();
    if (d.documents && d.documents.length > 0) {
      section.style.display = 'block';
      listEl.innerHTML = d.documents.map(doc =>
        `<div class="doc-row">
          <span class="doc-name" onclick="previewDoc('${doc.source.replace(/'/g,"\\'")}')">📄 ${doc.source}</span>
          <span class="doc-chunks">${doc.chunks} chunks</span>
          <button class="doc-delete" onclick="deleteDoc('${doc.source.replace(/'/g,"\\'")}')">🗑</button>
        </div>`
      ).join('');
    } else {
      section.style.display = 'none';
    }
  } catch(e) {}
}

async function previewDoc(source) {
  const preview = document.getElementById('doc-preview');
  try {
    const r = await fetch('/rag/document-content?source=' + encodeURIComponent(source));
    const d = await r.json();
    if (d.content) {
      preview.textContent = d.content.slice(0, 2000) + (d.content.length > 2000 ? '\n\n… (truncado)' : '');
      preview.style.display = 'block';
    } else {
      preview.textContent = '(documento vacío)';
      preview.style.display = 'block';
    }
  } catch(e) {
    preview.textContent = 'Error: ' + e.message;
    preview.style.display = 'block';
  }
}

async function deleteDoc(source) {
  if (!confirm(`¿Eliminar "${source}" de la knowledge base?`)) return;
  try {
    const r = await fetch('/rag/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source })
    });
    const d = await r.json();
    loadRagStats();
    loadDocList();
    document.getElementById('doc-preview').style.display = 'none';
  } catch(e) {}
}

// ── Modal open/close ───────────────────────────────────────────────────────────
let modalOpened = false;
function openIngestModal() {
  document.getElementById('ingest-modal').classList.add('open');
  if (!modalOpened) {
    modalOpened = true;
    loadDir('');
  }
  loadRagStats();
  loadDocList();
}
function closeIngestModal() {
  document.getElementById('ingest-modal').classList.remove('open');
}

// ── Init ─────────────────────────────────────────────────────────────────────
loadRagStats();
