'use strict';

const MODEL = document.getElementById('chat-root')?.dataset.model || 'qwen3.5:4b';

let conv = [];
let tokenCount = 0;
let msgCount = 0;
let respTimes = [];
let userTokenLens = [];
let aiTokenLens = [];
let ragDocs = [];
let ragEnabled = true;
let currentModel = MODEL;
let currentUser = null;
let currentSessionId = null;
let sessions = [];
let loadingHistory = false;

// ── Auth ────────────────────────────────────────────────────────────────────

function showAuth() {
  document.getElementById('auth-error').style.display = 'none';
  document.getElementById('auth-error').textContent = '';
  document.getElementById('auth-username').value = '';
  document.getElementById('auth-password').value = '';
  document.getElementById('auth-overlay').classList.add('open');
}
function hideAuth() {
  document.getElementById('auth-overlay').classList.remove('open');
}

let authMode = 'login';
const authTitle = document.getElementById('auth-title');
const authSubmit = document.getElementById('auth-submit');
const authToggle = document.getElementById('auth-toggle');
const authError = document.getElementById('auth-error');
const authUser = document.getElementById('auth-username');
const authPass = document.getElementById('auth-password');

authToggle.addEventListener('click', () => {
  authMode = authMode === 'login' ? 'register' : 'login';
  authTitle.textContent = authMode === 'login' ? '🔐 Iniciar sesión' : '📝 Crear cuenta';
  authSubmit.textContent = authMode === 'login' ? 'Entrar' : 'Crear cuenta';
  authToggle.textContent = authMode === 'login' ? '¿No tienes cuenta? Registrarse' : '¿Ya tienes cuenta? Iniciar sesión';
  authError.style.display = 'none';
});

authSubmit.addEventListener('click', async () => {
  const username = authUser.value.trim();
  const password = authPass.value.trim();
  if (!username || !password) {
    authError.textContent = 'Completa todos los campos';
    authError.style.display = 'block';
    return;
  }
  authError.style.display = 'none';
  try {
    const r = await fetch(`/auth/${authMode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const d = await r.json();
    if (d.error) {
      authError.textContent = d.error;
      authError.style.display = 'block';
      return;
    }
    currentUser = d.user;
    hideAuth();
    onLogin();
  } catch(e) {
    console.error('Auth fetch error:', e);
    authError.textContent = 'Error al conectar con el servidor. ¿Está Flask corriendo?';
    authError.style.display = 'block';
  }
});

authUser.addEventListener('keydown', e => { if (e.key === 'Enter') authSubmit.click(); });
authPass.addEventListener('keydown', e => { if (e.key === 'Enter') authSubmit.click(); });

async function checkAuth() {
  try {
    const r = await fetch('/auth/me');
    const d = await r.json();
    if (d.authenticated && d.user) {
      currentUser = d.user;
      onLogin();
    } else {
      showAuth();
    }
  } catch(e) {
    showAuth();
  }
}

async function logout() {
  await fetch('/auth/logout', { method: 'POST' });
  currentUser = null;
  currentSessionId = null;
  sessions = [];
  conv = [];
  document.getElementById('chat').innerHTML = '';
  document.getElementById('sessions-list').innerHTML = '';
  document.getElementById('user-menu').style.display = 'none';
  document.getElementById('user-dropdown').classList.remove('open');
  document.getElementById('kpi-chunks').textContent = '—';
  document.getElementById('kpi-storage').textContent = '—';
  document.getElementById('session-title').textContent = '';
  document.getElementById('docs-list').innerHTML = '<div class="panel-empty">Sin documentos todavía.<br>Haz clic en 📚 RAG para añadir.</div>';
  document.getElementById('docs-preview').style.display = 'none';
  showAuth();
}

// ── Model selector ────────────────────────────────────────────────────────────
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
    sel.innerHTML = '<option value="">Modelos no disponibles</option>';
  }
}

// ── Sessions ─────────────────────────────────────────────────────────────────

function onLogin() {
  const menu = document.getElementById('user-menu');
  const badge = document.getElementById('user-badge');
  const info = document.getElementById('dropdown-info');
  menu.style.display = 'block';
  badge.className = 'user-badge' + (currentUser.is_admin ? ' admin' : '');
  badge.textContent = currentUser.is_admin ? '👑 ' + currentUser.username : '👤 ' + currentUser.username;
  info.innerHTML = `<span class="uname">${currentUser.username}</span><span class="urole">${currentUser.is_admin ? 'Administrador' : 'Usuario'}</span>`;
  loadModels();
  loadSessions();
  loadRagStats();
  loadDocsPanel();
}

// User dropdown toggle
document.addEventListener('DOMContentLoaded', () => {
  const badge = document.getElementById('user-badge');
  const dropdown = document.getElementById('user-dropdown');
  if (badge) {
    badge.addEventListener('click', (e) => {
      e.stopPropagation();
      dropdown.classList.toggle('open');
    });
    document.addEventListener('click', () => dropdown.classList.remove('open'));
  }
});

async function loadSessions() {
  try {
    const r = await fetch('/sessions');
    const d = await r.json();
    sessions = d.sessions || [];
    renderSessions();
    if (sessions.length > 0 && !currentSessionId) {
      switchSession(sessions[0].id);
    } else if (sessions.length === 0) {
      newSession();
    }
  } catch(e) {}
}

function renderSessions() {
  const list = document.getElementById('sessions-list');
  list.innerHTML = sessions.map(s =>
    `<div class="session-item ${s.id === currentSessionId ? 'active' : ''}"
          onclick="switchSession(${s.id})">
       <span class="session-title">${s.title}</span>
       <button class="session-del" onclick="event.stopPropagation();deleteSession(${s.id})">×</button>
     </div>`
  ).join('');
}

async function newSession() {
  try {
    const r = await fetch('/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
    const d = await r.json();
    sessions.unshift(d.session);
    renderSessions();
    switchSession(d.session.id);
  } catch(e) {}
}

async function switchSession(sessionId) {
  if (loadingHistory) return;
  currentSessionId = sessionId;
  renderSessions();
  document.getElementById('session-title').textContent = '';
  loadingHistory = true;
  try {
    const r = await fetch(`/sessions/${sessionId}/messages`);
    const d = await r.json();
    const msgs = d.messages || [];
    const chatEl = document.getElementById('chat');
    chatEl.innerHTML = '';
    conv = [];
    tokenCount = 0;
    msgCount = 0;
    respTimes = [];
    userTokenLens = [];
    aiTokenLens = [];

    for (const m of msgs) {
      if (m.role === 'user') {
        addMessage('user', m.content);
        conv.push({ role: 'user', content: m.content });
        userTokenLens.push(m.content.split(/\s/).length);
      } else if (m.role === 'assistant') {
        addMessage('ai', m.content);
        conv.push({ role: 'assistant', content: m.content });
        const words = m.content.split(/\s/).length;
        aiTokenLens.push(words);
        tokenCount += m.content.length;
        msgCount++;
      }
    }

    const s = sessions.find(s => s.id === sessionId);
    if (s) document.getElementById('session-title').textContent = s.title;

    document.getElementById('kpi-tokens').textContent = tokenCount;
    document.getElementById('kpi-msgs').textContent = msgCount;
    document.getElementById('kpi-time').textContent = respTimes.length > 0 ? respTimes[respTimes.length-1] + 's' : '—';
  } catch(e) {}
  loadingHistory = false;
}

async function deleteSession(sessionId) {
  if (!confirm('¿Eliminar esta conversación?')) return;
  try {
    await fetch(`/sessions/${sessionId}`, { method: 'DELETE' });
    sessions = sessions.filter(s => s.id !== sessionId);
    if (currentSessionId === sessionId) {
      currentSessionId = null;
      if (sessions.length > 0) switchSession(sessions[0].id);
      else newSession();
    } else {
      renderSessions();
    }
  } catch(e) {}
}

// ── DOM ─────────────────────────────────────────────────────────────────────
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

async function saveMessage(role, content, tokens) {
  if (!currentSessionId) return;
  try {
    await fetch('/chat/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: currentSessionId, role, content, tokens: tokens || 0 })
    });
  } catch(e) {}
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
  saveMessage('user', text);

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
    const body = { model: currentModel, messages: conv, rag: ragEnabled, rag_context: ragDocs, session_id: currentSessionId };

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

                ragDot.classList.remove('active');

                saveMessage('assistant', reply, reply.length);
                loadSessions();
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
  if (!confirm('¿Limpiar la conversación actual?')) return;
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
  if (typeof loadRagStats === 'function') loadRagStats();
}

// ── Panel toggles ──────────────────────────────────────────────────────────────
function togglePanel(name) {
  const el = document.getElementById('panel-' + name);
  const btn = document.getElementById('toggle-' + name);
  if (!el) return;
  const wasOpen = !el.classList.contains('closed');
  el.classList.toggle('closed');
  btn.classList.toggle('active');
  btn.title = wasOpen
    ? (name === 'sessions' ? 'Abrir conversaciones' : 'Abrir documentos')
    : (name === 'sessions' ? 'Cerrar conversaciones' : 'Cerrar documentos');
  btn.textContent = wasOpen
    ? (name === 'sessions' ? '▶' : '◀')
    : (name === 'sessions' ? '◀' : '▶');
  setTimeout(() => window.dispatchEvent(new Event('resize')), 220);
}

// ── RAG stats ─────────────────────────────────────────────────────────────────
async function loadRagStats() {
  if (!currentUser) return;
  try {
    const r = await fetch('/rag/status');
    const d = await r.json();
    document.getElementById('kpi-chunks').textContent = d.chunks || 0;
    if (d.storage) {
      document.getElementById('kpi-storage').textContent = `${d.storage.used}/${d.storage.max}`;
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
      resultEl.innerHTML = `<span style="color:var(--ok)">✅ ${total} chunks de ${d.files.length} archivo(s)</span>`;
      resultEl.innerHTML += '<br>' + d.files.map(f =>
        `${f.file}: ${f.status === 'ok' ? f.chunks + ' chunks' : f.status}`
      ).join('<br>');
    }
    loadRagStats();
    loadDocList();
    loadDocsPanel();
  } catch(e) {
    resultEl.innerHTML = `<span style="color:var(--crit)">Error: ${e.message}</span>`;
  }
}

async function resetRag() {
  if (!confirm('¿Borrar toda tu knowledge base?')) return;
  try {
    const r = await fetch('/rag/reset', { method: 'POST' });
    const d = await r.json();
    resultEl.innerHTML = `<span style="color:var(--ok)">${d.status}</span>`;
    loadRagStats();
    loadDocList();
    loadDocsPanel();
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
  loadDocsPanel();
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
  if (!confirm(`¿Eliminar "${source}" de tu knowledge base?`)) return;
  try {
    await fetch('/rag/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source })
    });
    loadRagStats();
    loadDocList();
    loadDocsPanel();
    document.getElementById('doc-preview').style.display = 'none';
  } catch(e) {}
}

// ── Documents panel (right) ────────────────────────────────────────────────────
async function loadDocsPanel() {
  const listEl = document.getElementById('docs-list');
  if (!listEl) return;
  try {
    const r = await fetch('/rag/documents');
    const d = await r.json();
    const docs = d.documents || [];
    if (docs.length === 0) {
      listEl.innerHTML = '<div class="panel-empty">Sin documentos todavía.<br>Haz clic en 📚 Menú para añadir.</div>';
      return;
    }
    listEl.innerHTML = docs.map(doc =>
      `<div class="doc-item" onclick="previewDocPanel('${doc.source.replace(/'/g,"\\'")}')">
        <span class="doc-icon">📄</span>
        <span class="doc-name">${doc.source}</span>
        <span class="doc-chunks">${doc.chunks}</span>
        <button class="doc-del" onclick="event.stopPropagation();deleteDocPanel('${doc.source.replace(/'/g,"\\'")}')">×</button>
      </div>`
    ).join('');
  } catch(e) { console.error('loadDocsPanel error:', e); }
}

async function previewDocPanel(source) {
  const preview = document.getElementById('docs-preview');
  if (!preview) return;
  document.querySelectorAll('.doc-item').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.doc-item').forEach(el => {
    if (el.querySelector('.doc-name')?.textContent === source) el.classList.add('active');
  });
  try {
    const r = await fetch('/rag/document-content?source=' + encodeURIComponent(source));
    const d = await r.json();
    if (d.content) {
      preview.innerHTML = '<pre>' + d.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').slice(0, 3000) + (d.content.length > 3000 ? '\n\n… (truncado)' : '') + '</pre>';
      preview.style.display = 'block';
    } else {
      preview.innerHTML = '<pre style="color:var(--muted)">(documento vacío)</pre>';
      preview.style.display = 'block';
    }
  } catch(e) {
    preview.innerHTML = '<pre style="color:var(--crit)">Error</pre>';
    preview.style.display = 'block';
  }
}

async function deleteDocPanel(source) {
  if (!confirm(`¿Eliminar "${source}" de tu knowledge base?`)) return;
  try {
    await fetch('/rag/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source })
    });
    document.getElementById('docs-preview').style.display = 'none';
    loadDocsPanel();
    loadRagStats();
    loadDocList();
  } catch(e) {}
}

// ── Modal open/close ───────────────────────────────────────────────────────────
let modalOpened = false;
async function loadAdminUsers() {
  const section = document.getElementById('admin-section');
  const listEl = document.getElementById('user-list');
  if (!currentUser?.is_admin) {
    section.style.display = 'none';
    return;
  }
  section.style.display = 'block';
  try {
    const r = await fetch('/auth/users');
    const d = await r.json();
    listEl.innerHTML = (d.users || []).map(u =>
      `<div class="doc-row">
        <span class="doc-name">${u.is_admin ? '👑 ' : '👤 '}${u.username}</span>
        <span class="doc-chunks">${u.last_login ? new Date(u.last_login).toLocaleDateString() : 'nunca'}</span>
        ${u.id !== currentUser.id
          ? `<button class="doc-delete" onclick="adminDeleteUser(${u.id})">×</button>`
          : '<span style="font-size:.65rem;color:var(--muted)">(tú)</span>'}
      </div>`
    ).join('');
  } catch(e) {}
}

async function adminCreateUser() {
  const username = document.getElementById('admin-new-user').value.trim();
  const password = document.getElementById('admin-new-pass').value.trim();
  if (!username || !password) return;
  try {
    const r = await fetch('/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const d = await r.json();
    if (d.error) {
      document.getElementById('ingest-result').innerHTML = `<span style="color:var(--crit)">${d.error}</span>`;
    } else {
      document.getElementById('admin-new-user').value = '';
      document.getElementById('admin-new-pass').value = '';
      document.getElementById('ingest-result').innerHTML = `<span style="color:var(--ok)">✅ Usuario "${username}" creado</span>`;
      loadAdminUsers();
    }
  } catch(e) {}
}

async function adminDeleteUser(userId) {
  if (!confirm('¿Eliminar este usuario y todas sus conversaciones?')) return;
  try {
    await fetch(`/auth/users/${userId}`, { method: 'DELETE' });
    loadAdminUsers();
  } catch(e) {}
}

function openIngestModal() {
  document.getElementById('ingest-modal').classList.add('open');
  if (!modalOpened) {
    modalOpened = true;
    loadDir('');
  }
  loadRagStats();
  loadDocList();
  loadAdminUsers();
}
function closeIngestModal() {
  document.getElementById('ingest-modal').classList.remove('open');
}

// ── Init ─────────────────────────────────────────────────────────────────────
checkAuth();
