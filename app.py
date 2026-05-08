from flask import Flask, render_template_string, request, jsonify, session
import requests
import uuid, os, mimetypes
from datetime import datetime

import rag  # our RAG module

app = Flask(__name__)
app.secret_key = 'intelpulse-chatbot-v2-rag'

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3.5:4b"

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NeuralChat v3 — Panel Conversacional RAG</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:#0d1117; --surface:#161b22; --border:#30363d;
    --accent:#58a6ff; --ok:#3fb950; --warn:#d29922; --crit:#f85149;
    --txt:#e6edf3; --muted:#8b949e;
    --purple:#c77dff; --orange:#ff9f43; --cyan:#39c5bb; --pink:#f778ba;
  }
* { box-sizing: border-box; margin: 0; padding: 0 }
  html, body { height: 100dvh; overflow: hidden }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--txt);
    height: 100dvh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  header{
    background:linear-gradient(135deg,#0d1117 0%,#1a2332 50%,#0d1117 100%);
    border-bottom:1px solid var(--border);padding:20px 36px;
    display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
  }
  header h1{font-size:1.6rem;letter-spacing:2px;text-transform:uppercase}
  header h1 span{color:var(--accent)}
  header small{font-size:.4em;color:var(--muted);margin-left:8px}
  .model-badge{
    background:rgba(88,166,255,.15);border:1px solid rgba(88,166,255,.3);
    color:var(--accent);padding:4px 14px;border-radius:20px;font-size:.8rem;
  }
  .rag-badge{
    background:rgba(199,125,255,.15);border:1px solid rgba(199,125,255,.3);
    color:var(--purple);padding:4px 14px;border-radius:20px;font-size:.8rem;
    cursor:pointer;transition:opacity .2s;
  }
  .rag-badge:hover{opacity:.8}

  .kpi-bar{
    display:grid;grid-template-columns:repeat(5,1fr);
    gap:14px;padding:20px 36px;flex-shrink:0;
  }
  .kpi{
    background:var(--surface);border:1px solid var(--border);border-radius:10px;
    padding:14px 18px;display:flex;align-items:center;gap:12px;
  }
  .kpi-icon{font-size:1.5rem}
  .kpi-info{}
  .kpi-label{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
  .kpi-value{font-size:1.3rem;font-weight:700}
  .kpi.crit .kpi-value{color:var(--crit)}
  .kpi.ok   .kpi-value{color:var(--ok)}
  .kpi.warn .kpi-value{color:var(--warn)}
  .kpi.cyan .kpi-value{color:var(--cyan)}
  .kpi.purple .kpi-value{color:var(--purple)}

  /* ── Responsive ─────────────────────────────────────────────────── */
  @media (max-width: 900px) {
    .kpi-bar { grid-template-columns: repeat(3, 1fr) !important; padding: 12px 16px !important; gap: 8px !important; }
    .kpi { padding: 10px 12px !important; }
    header { padding: 14px 16px !important; }
    .input-bar { padding: 12px 16px !important; }
    .sidebar { display: none !important; }          /* hide charts on small screens */
    .main-layout { display: block !important; }
    .chat-header { padding: 10px 16px !important; }
    #chat { padding: 16px !important; }
    footer { padding: 8px !important; font-size: .65rem !important; }
  }
  @media (max-width: 540px) {
    .kpi-bar { grid-template-columns: repeat(2, 1fr) !important; }
    .kpi-icon { display: none !important; }
    .msg { max-width: 90% !important; }
  }

  .main-layout{display:flex;flex:1;overflow:hidden;min-height:0}

  /* Charts sidebar */
  .sidebar{
    width:280px;flex-shrink:0;border-right:1px solid var(--border);
    padding:16px;display:flex;flex-direction:column;gap:10px;overflow-y:auto;
  }
  .sidebar h3{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:2px}
  .chart-card{
    background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px;
  }
  .chart-card .chart-label{font-size:.7rem;color:var(--muted);margin-bottom:4px}
  .chart-card canvas{width:100%!important;max-height:80px}

  /* RAG Panel */
  .rag-panel{
    background:var(--surface);border:1px solid rgba(199,125,255,.3);
    border-radius:10px;padding:14px;
  }
  .rag-panel h4{font-size:.8rem;color:var(--purple);margin-bottom:8px;display:flex;align-items:center;gap:6px}
  .rag-sources{font-size:.75rem;color:var(--muted);margin-top:6px}
  .rag-sources span{
    display:inline-block;background:rgba(199,125,255,.12);
    color:var(--purple);padding:2px 8px;border-radius:10px;margin:2px;font-size:.7rem;
  }
  .rag-toggle{margin-top:8px;display:flex;align-items:center;gap:8px;font-size:.8rem;color:var(--muted);cursor:pointer}
  .rag-toggle input{accent-color:var(--purple)}

  /* Chat area */
  .chat-area{flex:1;display:flex;flex-direction:column;min-width:0}
  .chat-header{
    padding:14px 24px;border-bottom:1px solid var(--border);
    display:flex;align-items:center;justify-content:space-between;flex-shrink:0;
  }
  .chat-status{display:flex;align-items:center;gap:8px;font-size:.82rem;color:var(--muted)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--ok)}
  .dot.offline{background:var(--crit)}
  .rag-dot{width:8px;height:8px;border-radius:50%;background:var(--purple);display:none}
  .rag-dot.active{display:inline-block}

  #chat{flex:1;overflow-y:auto;padding:16px 24px 100px 24px;display:flex;flex-direction:column;gap:14px}
  .msg{max-width:75%;padding:12px 16px;border-radius:14px;font-size:.92rem;line-height:1.55;white-space:pre-wrap;word-break:break-word}
  .msg.user{align-self:flex-end;background:linear-gradient(135deg,#1a3a5c,#0d2744);border:1px solid rgba(88,166,255,.3);color:var(--txt);border-bottom-right-radius:4px}
  .msg.ai{align-self:flex-start;background:var(--surface);border:1px solid var(--border);color:var(--txt);border-bottom-left-radius:4px}
  .msg.ai .name{font-size:.7rem;color:var(--accent);font-weight:700;margin-bottom:6px;display:flex;align-items:center;gap:6px}
  .msg.code{background:#0d1117;border:1px solid var(--border);font-family:'Courier New',monospace;font-size:.85rem;padding:12px 16px;white-space:pre;overflow-x:auto;border-radius:8px}
  .msg.error{background:rgba(248,81,73,.1);border-color:rgba(248,81,73,.3);color:var(--crit)}
  .msg.thinking{background:var(--surface);border:1px solid var(--border);color:var(--muted);font-style:italic}
  .msg.rag-context{
    background:rgba(199,125,255,.08);border-color:rgba(199,125,255,.25);
    font-size:.78rem;color:var(--muted);max-width:90%;
  }
  .rag-context-label{color:var(--purple);font-weight:700;margin-bottom:4px;font-size:.7rem;display:flex;align-items:center;gap:4px}
  .typing-dots{display:inline-flex;gap:4px;align-items:center;margin-left:8px}
  .typing-dots span{width:6px;height:6px;border-radius:50%;background:var(--accent);animation:bounce 1.2s infinite}
  .typing-dots span:nth-child(2){animation-delay:.2s}
  .typing-dots span:nth-child(3){animation-delay:.4s}
  @keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}

  /* Input bar */
  .input-bar{
    position:fixed;bottom:32px;left:0;right:0;
    padding:12px 24px;border-top:1px solid var(--border);
    display:flex;gap:12px;align-items:flex-end;flex-shrink:0;
    background:var(--surface);z-index:10;
  }
  #input{
    flex:1;background:var(--bg);border:1px solid var(--border);border-radius:10px;
    color:var(--txt);font-size:.92rem;padding:12px 16px;resize:none;outline:none;
    font-family:inherit;min-height:48px;max-height:140px;transition:border-color .2s;
  }
  #input:focus{border-color:var(--accent)}
  #input::placeholder{color:var(--muted)}
  button{
    background:var(--accent);border:none;border-radius:10px;color:#fff;
    font-size:.88rem;font-weight:600;padding:0 22px;cursor:pointer;
    height:48px;transition:opacity .2s;flex-shrink:0;
  }
  button:hover{opacity:.85}
  button:disabled{opacity:.4;cursor:not-allowed}
  .btn-clear{background:var(--surface);border:1px solid var(--border);color:var(--muted);font-size:.8rem;padding:0 14px}
  .btn-rag{background:rgba(199,125,255,.2);border:1px solid rgba(199,125,255,.4);color:var(--purple)}

  footer{position:fixed;bottom:0;left:0;right:0;text-align:center;padding:8px 16px;color:var(--muted);font-size:.65rem;background:var(--bg);border-top:1px solid var(--border);z-index:10}

  /* Modal overlay */
  .modal-overlay{
    position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;
    display:none;align-items:center;justify-content:center;
  }
  .modal-overlay.open{display:flex}
  .modal{
    background:var(--surface);border:1px solid var(--border);border-radius:14px;
    padding:28px;width:480px;max-width:95vw;
  }
  .modal h2{font-size:1.1rem;color:var(--txt);margin-bottom:16px;display:flex;align-items:center;gap:8px}
  .modal input[type="text"], .modal textarea{
    width:100%;background:var(--bg);border:1px solid var(--border);border-radius:8px;
    color:var(--txt);font-size:.88rem;padding:10px 14px;margin-bottom:10px;outline:none;font-family:inherit;
  }
  .modal input[type="text"]:focus, .modal textarea:focus{border-color:var(--accent)}
  .modal-actions{display:flex;gap:10px;justify-content:flex-end;margin-top:14px}
  .modal-actions button{padding:8px 20px;height:auto;font-size:.85rem}
  .btn-cancel{background:var(--bg)!important;border:1px solid var(--border)!important;color:var(--muted)!important}
  .btn-upload{background:rgba(199,125,255,.2)!important;border:1px solid rgba(199,125,255,.4)!important;color:var(--purple)!important}
  .upload-area{
    border:2px dashed rgba(199,125,255,.3);border-radius:10px;padding:20px;text-align:center;
    cursor:pointer;transition:border-color .2s;margin-bottom:10px;
  }
  .upload-area:hover{border-color:var(--purple)}
  .upload-area.dragover{border-color:var(--purple);background:rgba(199,125,255,.05)}
  .upload-area input{display:none}
  .upload-hint{font-size:.8rem;color:var(--muted)}
  #ingest-result{margin-top:10px;font-size:.82rem;max-height:150px;overflow-y:auto;color:var(--ok)}

  /* File browser */
  .file-browser{
    border:1px solid var(--border);border-radius:8px;overflow:hidden;
    max-height:320px;overflow-y:auto;margin-bottom:10px;
  }
  .file-browser::-webkit-scrollbar{width:6px}
  .file-browser::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
  .fb-row{
    display:flex;align-items:center;gap:8px;padding:8px 12px;
    cursor:pointer;border-bottom:1px solid rgba(48,54,61,.5);
    transition:background .1s;font-size:.82rem;user-select:none;
  }
  .fb-row:last-child{border-bottom:none}
  .fb-row:hover{background:rgba(88,166,255,.06)}
  .fb-row.dir:hover{background:rgba(199,125,255,.08)}
  .fb-row input[type=checkbox]{accent-color:var(--purple);flex-shrink:0}
  .fb-icon{font-size:1.1rem;flex-shrink:0;width:20px;text-align:center}
  .fb-name{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .fb-size{font-size:.7rem;color:var(--muted);flex-shrink:0}
  .fb-path-bar{
    display:flex;align-items:center;gap:6px;margin-bottom:8px;
    background:var(--bg);border:1px solid var(--border);border-radius:6px;
    padding:6px 10px;font-size:.75rem;min-height:34px;flex-wrap:wrap;
  }
  .fb-path-segment{
    color:var(--accent);cursor:pointer;padding:2px 4px;border-radius:4px;
  }
  .fb-path-segment:hover{background:rgba(88,166,255,.12)}
  .fb-path-sep{color:var(--muted)}
  .fb-loading{text-align:center;padding:20px;color:var(--muted);font-size:.82rem}
  .fb-empty{text-align:center;padding:20px;color:var(--muted);font-size:.82rem}
  .fb-actions{
    display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap;
  }
  .fb-count{font-size:.78rem;color:var(--muted);flex:1}
  .btn-ingest{
    background:var(--purple)!important;color:#fff!important;
    font-size:.82rem!important;padding:0 16px!important;height:38px!important;
  }
  .btn-ingest:disabled{opacity:.4!important;cursor:not-allowed!important}
  .btn-select-all{
    background:rgba(88,166,255,.15)!important;border:1px solid rgba(88,166,255,.3)!important;
    color:var(--accent)!important;font-size:.78rem!important;padding:0 12px!important;height:34px!important;
  }
  .btn-back{
    background:var(--surface)!important;border:1px solid var(--border)!important;
    color:var(--muted)!important;font-size:.78rem!important;padding:0 12px!important;height:34px!important;
  }
  .ext-txt,.ext-md{color:#4d96ff}
  .ext-csv{color:#3fb950}
  .ext-json{color:#d29922}
  .ext-html,.ext-htm{color:#f778ba}
  .ext-py{color:#ffd93d}
  .ext-pdf{color:#f85149}
</style>
</head>
<body>

<header>
  <h1>Neural<span>Chat</span><small>v3 · RAG</small></h1>
  <div style="display:flex;gap:10px;align-items:center">
      <select id="model-select" style="background:var(--surface);border:1px solid var(--border);border-radius:20px;color:var(--accent);font-size:.8rem;padding:4px 12px;cursor:pointer">
        <option value="">Cargando…</option>
      </select>
      <div class="rag-badge" onclick="openIngestModal()" title="Gestionar documentos RAG">📚 RAG</div>
      <div class="model-badge">🤖 {{ model }}</div>
    </div>
</header>

<!-- KPI bar -->
<div class="kpi-bar" id="chat-root" data-model="{{ model }}" data-ollama="{{ ollama_url }}">
  <div class="kpi crit">
    <div class="kpi-icon">🧠</div>
    <div class="kpi-info">
      <div class="kpi-label">Tokens enviados</div>
      <div class="kpi-value" id="kpi-tokens">0</div>
    </div>
  </div>
  <div class="kpi ok">
    <div class="kpi-icon">💬</div>
    <div class="kpi-info">
      <div class="kpi-label">Mensajes</div>
      <div class="kpi-value" id="kpi-msgs">0</div>
    </div>
  </div>
  <div class="kpi warn">
    <div class="kpi-icon">⏱️</div>
    <div class="kpi-info">
      <div class="kpi-label">Tiempo resp.</div>
      <div class="kpi-value" id="kpi-time">—</div>
    </div>
  </div>
  <div class="kpi purple">
    <div class="kpi-icon">📚</div>
    <div class="kpi-info">
      <div class="kpi-label">Chunks</div>
      <div class="kpi-value" id="kpi-chunks">—</div>
    </div>
  </div>
  <div class="kpi cyan">
    <div class="kpi-icon">📊</div>
    <div class="kpi-info">
      <div class="kpi-label">Sesión</div>
      <div class="kpi-value">{{ session_id[:8] }}…</div>
    </div>
  </div>
</div>

<div class="main-layout">

  <!-- Sidebar -->
  <div class="sidebar">
    <h3>📈 Actividad del modelo</h3>
    <div class="chart-card">
      <div class="chart-label">Tokens por mensaje</div>
      <div style="height:80px;position:relative"><canvas id="chartTokens"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-label">Tiempo resp. (s)</div>
      <div style="height:80px;position:relative"><canvas id="chartTime"></canvas></div>
    </div>

    <!-- RAG panel -->
    <div class="rag-panel" id="rag-panel" style="display:none">
      <h4>📚 Contexto RAG</h4>
      <div id="rag-sources" class="rag-sources"></div>
      <label class="rag-toggle">
        <input type="checkbox" id="rag-enabled" checked>
        Usar RAG en esta conversación
      </label>
    </div>
  </div>

  <!-- Chat -->
  <div class="chat-area">
    <div class="chat-header">
      <div class="chat-status">
        <div class="dot" id="dot"></div>
        <div class="rag-dot" id="rag-dot"></div>
        <span id="status-text">Conectado a Ollama</span>
      </div>
      <span style="font-size:.78rem;color:var(--muted)">{{ model }}</span>
    </div>

    <div id="chat"></div>

    <div class="input-bar">
      <textarea id="input" placeholder="Escribe tu mensaje… (Enter = enviar, Shift+Enter = nueva línea)" rows="1"></textarea>
      <button type="button" id="send" onclick="sendMsg()">Enviar</button>
      <button type="button" class="btn-clear" onclick="clearChat()">Limpiar</button>
    </div>
  </div>
</div>

<!-- Ingest modal -->
<div class="modal-overlay" id="ingest-modal">
  <div class="modal">
    <h2>📚 Gestionar Knowledge Base</h2>

    <!-- File browser -->
    <div class="fb-path-bar" id="fb-path-bar">
      <span style="color:var(--muted);font-size:.7rem">Cargando…</span>
    </div>
    <div class="file-browser" id="file-browser">
      <div class="fb-loading">⏳ Cargando directorio…</div>
    </div>

    <div class="fb-actions">
      <button class="btn-select-all" onclick="toggleSelectAll()">☑️ Sel. todos</button>
      <span class="fb-count" id="fb-count">0 archivos seleccionados</span>
      <button class="btn-ingest" id="btn-ingest" onclick="ingestSelected()" disabled>📥 Ingestar</button>
    </div>

    <div style="margin:10px 0;border-top:1px solid var(--border);padding-top:10px">
      <div class="upload-area" id="upload-area" onclick="document.getElementById('file-input').click()">
        <input type="file" id="file-input" multiple accept=".txt,.md,.csv,.json,.html,.htm">
        <div style="font-size:1.4rem;margin-bottom:6px">📄</div>
        <div class="upload-hint">Arrastra archivos aquí o haz clic para seleccionar<br><small>.txt .md .csv .json .html .htm</small></div>
      </div>
    </div>
    <div id="ingest-result"></div>
    <div class="modal-actions">
      <button class="btn-cancel" onclick="closeIngestModal()">Cerrar</button>
      <button class="btn-upload" onclick="resetRag()">🗑️ Reset KB</button>
    </div>
  </div>
</div>

<footer>
  NeuralChat v3 · RAG con Ollama · ChromaDB · {{ model }}
</footer>

<script src="{{ url_for('static', filename='chat.js') }}"></script>
<script>
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
loadRagStats();

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
  } catch(e) {
    resultEl.innerHTML = `<span style="color:var(--crit)">Error: ${e.message}</span>`;
  }
}

// ── Reset RAG ──────────────────────────────────────────────────────────────────
async function resetRag() {
  if (!confirm('¿Borrar toda la knowledge base?')) return;
  try {
    const r = await fetch('/rag/reset', { method: 'POST' });
    const d = await r.json();
    resultEl.innerHTML = `<span style="color:var(--ok)">${d.status}</span>`;
    loadRagStats();
  } catch(e) { resultEl.innerHTML = `<span style="color:var(--crit)">${e.message}</span>`; }
}

// ── File Browser ───────────────────────────────────────────────────────────────
const SUPPORTED_EXTS = new Set(['.txt','.md','.csv','.json','.html','.htm','.py','.pdf']);

let fbCurrentPath = '';
let fbHome = '';
let fbEntries = [];       // [{name, path, is_dir, size}]
let fbSelected = new Set();

const FILE_ICONS = {
  dir:  '📁',
  txt:  '📄', md:  '📝', csv: '📊', json: '🔗',
  html: '🌐', htm: '🌐', py:  '🐍', pdf: '📕',
};
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

  // Click row → enter dir or toggle checkbox
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
  btn.disabled = true;
  countEl.textContent = '⏳ Ingestando…';
  try {
    const r = await fetch('/rag/ingest-paths', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paths })
    });
    const d = await r.json();
    resultEl.innerHTML = '';
    if (d.error) {
      resultEl.innerHTML = `<span style="color:var(--crit)">Error: ${d.error}</span>`;
    } else {
      const total = d.total_chunks || 0;
      resultEl.innerHTML = `<span style="color:var(--ok)">✅ ${total} chunks de ${d.files.length} archivo(s)</span><br>` +
        d.files.map(f => `${f.file}: ${f.status === 'ok' ? f.chunks + ' chunks' : f.status}`).join('<br>');
      fbSelected.clear();
      updateIngestBtn();
      renderBrowser();
    }
    loadRagStats();
  } catch(e) {
    resultEl.innerHTML = `<span style="color:var(--crit)">Error: ${e.message}</span>`;
  }
  btn.disabled = false;
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
}
function closeIngestModal() {
  document.getElementById('ingest-modal').classList.remove('open');
}
</script>
</body>
</html>
"""

# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    session_id = session.get('session_id') or str(uuid.uuid4())
    session['session_id'] = session_id
    return render_template_string(
        TEMPLATE,
        model=MODEL,
        ollama_url=OLLAMA_URL,
        session_id=session_id,
    )

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data        = request.get_json()
    messages    = data.get("messages", [])
    model       = data.get("model", MODEL)
    use_rag     = data.get("rag", True)

    # Si hay contexto RAG, enriquecer system prompt
    rag_context = data.get("rag_context", [])

    def generate():
        try:
            # Si hay docs RAG, alterar el último mensaje de usuario
            if rag_context and use_rag:
                last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
                if last_user:
                    rag_prompt = rag.build_rag_prompt(last_user["content"], rag_context)
                    new_messages = []
                    for m in messages[:-1]:
                        new_messages.append(m)
                    new_messages.append({"role": "user", "content": rag_prompt})
                    messages_to_send = new_messages
                else:
                    messages_to_send = messages
            else:
                messages_to_send = messages

            r = requests.post(
                OLLAMA_URL,
                json={"model": model, "messages": messages_to_send, "stream": True, "think": False},
                stream=True,
                timeout=120
            )
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    yield b"data:" + line + b"\n"
            yield b"data:{\"done\":true}\n"
        except Exception as e:
            yield f"data:{{\"error\":\"{str(e)}\"}}".encode()

    return app.response_class(generate(), mimetype='text/event-stream')

# ── RAG Routes ────────────────────────────────────────────────────────────────

@app.route("/rag/status")
def rag_status():
    try:
        stats = rag.collection_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"chunks": 0, "sources": [], "error": str(e)})

@app.route("/rag/ingest", methods=["POST"])
def rag_ingest():
    """Recibe archivos y los ingiere en ChromaDB."""
    results = {"files": [], "total_chunks": 0}
    try:
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No se enviaron archivos"}), 400

        import tempfile, os as _os
        tmpdir = tempfile.mkdtemp()
        for f in files:
            fname  = _os.path.join(tmpdir, f.filename)
            f.save(fname)
            try:
                r = rag.ingest_file(fname)
                results["files"].append({"file": f.filename, **r})
                results["total_chunks"] += r.get("chunks", 0)
            except Exception as e:
                results["files"].append({"file": f.filename, "status": "error", "error": str(e)})
            finally:
                _os.unlink(fname)
        _os.rmdir(tmpdir)
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/rag/retrieve", methods=["POST"])
def rag_retrieve():
    """Busca chunks relevantes para una query. Devuelve JSON."""
    data = request.get_json()
    query = data.get("query", "")
    top_k = data.get("top_k", 4)
    try:
        docs = rag.retrieve(query, top_k=top_k)
        return jsonify({"docs": docs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/rag/reset", methods=["POST"])
def rag_reset():
    msg = rag.reset_collection()
    return jsonify({"status": "ok" if msg is True else msg})

@app.route("/models", methods=["GET"])
def list_models():
    """Devuelve los modelos disponibles en Ollama."""
    try:
        r = requests.get(f"{OLLAMA_URL.replace('/api/chat', '')}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        return jsonify({"models": [m["name"] for m in models]})
    except Exception as e:
        return jsonify({"models": [], "error": str(e)}), 500

@app.route("/rag/browse")
def rag_browse():
    """Lista el contenido de un directorio. path GET = ruta a explorar."""
    import os as _os
    requested = request.args.get("path", "")
    # Seguridad: solo permitir rutas dentro del home del usuario
    home = _os.path.expanduser("~")
    # Normalizar y resolver
    if requested:
        requested = _os.path.normpath(requested)
        # Evitar path traversal
        if not requested.startswith(home):
            requested = home
    else:
        requested = home

    try:
        entries = []
        # Añadir ".." para volver al directorio padre si no estamos en home
        if requested != home:
            entries.append({"name": "..", "path": _os.path.dirname(requested), "is_dir": True, "size": 0})
        for name in sorted(_os.listdir(requested)):
            if name.startswith("."):
                continue
            fpath = _os.path.join(requested, name)
            try:
                stat = _os.stat(fpath)
                is_dir = _os.path.isdir(fpath)
                size = stat.st_size if not is_dir else 0
                entries.append({
                    "name": name,
                    "path": fpath,
                    "is_dir": is_dir,
                    "size": size,
                })
            except PermissionError:
                pass
        # Ordenar: dirs primero, luego archivos, ambos alfabético
        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return jsonify({"path": requested, "home": home, "entries": entries})
    except PermissionError:
        return jsonify({"path": requested, "home": home, "entries": [], "error": "Permiso denegado"})
    except Exception as e:
        return jsonify({"path": requested, "home": home, "entries": [], "error": str(e)})

@app.route("/rag/ingest-paths", methods=["POST"])
def rag_ingest_paths():
    """Recibe rutas de archivo locales y las ingiere en ChromaDB."""
    import os as _os
    data = request.get_json()
    paths = data.get("paths", []) if data else []
    if not paths:
        return jsonify({"error": "No se enviaron rutas"}), 400

    results = {"files": [], "total_chunks": 0}
    for fpath in paths:
        if not _os.path.isfile(fpath):
            results["files"].append({"file": fpath, "status": "not_found"})
            continue
        try:
            r = rag.ingest_file(fpath)
            results["files"].append({"file": _os.path.basename(fpath), **r})
            results["total_chunks"] += r.get("chunks", 0)
        except Exception as e:
            results["files"].append({"file": _os.path.basename(fpath), "status": "error", "error": str(e)})
    return jsonify(results)

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
print("\n  ╔══════════════════════════════════════╗")
    print("  ║   NeuralChat v3 — RAG + Ollama       ║")
    print("  ╚══════════════════════════════════════╝")
    print(f"  → http://localhost:5051")
    print(f"  → Modelo: {MODEL}")
    print(f"  → Embedding: {rag.EMBED_MODEL}")
    app.run(host="0.0.0.0", port=5051, debug=False, threaded=True)
