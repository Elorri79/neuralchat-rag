import os
import uuid
import logging
import mimetypes
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session
import requests

import rag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24).hex())

OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_URL = OLLAMA_BASE_URL + "/api/chat"
MODEL = os.getenv("MODEL", "qwen3.5:4b")

# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    session_id = session.get("session_id") or str(uuid.uuid4())
    session["session_id"] = session_id
    return render_template(
        "index.html",
        model=MODEL,
        ollama_url=OLLAMA_URL,
        session_id=session_id,
    )

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "messages field required"}), 400

    model = data.get("model", MODEL)
    use_rag = data.get("rag", True)
    rag_context = data.get("rag_context", [])

    def generate():
        try:
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
                timeout=120,
            )
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    yield b"data:" + line + b"\n"
            yield b"data:{\"done\":true}\n"
        except Exception as e:
            logger.error("chat_stream error: %s", e)
            yield f"data:{{\"error\":\"{str(e)}\"}}".encode()

    return app.response_class(generate(), mimetype="text/event-stream")

# ── RAG Routes ────────────────────────────────────────────────────────────────

@app.route("/rag/status")
def rag_status():
    try:
        stats = rag.collection_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error("rag_status error: %s", e)
        return jsonify({"chunks": 0, "sources": [], "error": str(e)})

@app.route("/rag/ingest", methods=["POST"])
def rag_ingest():
    results = {"files": [], "total_chunks": 0}
    try:
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No se enviaron archivos"}), 400

        import tempfile
        tmpdir = tempfile.mkdtemp()
        for f in files:
            fname = os.path.join(tmpdir, f.filename)
            f.save(fname)
            try:
                r = rag.ingest_file(fname)
                results["files"].append({"file": f.filename, **r})
                results["total_chunks"] += r.get("chunks", 0)
            except Exception as e:
                logger.error("Error ingesting uploaded %s: %s", f.filename, e)
                results["files"].append({"file": f.filename, "status": "error", "error": str(e)})
            finally:
                os.unlink(fname)
        os.rmdir(tmpdir)
        return jsonify(results)
    except Exception as e:
        logger.error("rag_ingest error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/rag/retrieve", methods=["POST"])
def rag_retrieve():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    query = data.get("query", "")
    top_k = data.get("top_k", 4)
    try:
        docs = rag.retrieve(query, top_k=top_k)
        return jsonify({"docs": docs})
    except Exception as e:
        logger.error("rag_retrieve error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/rag/reset", methods=["POST"])
def rag_reset():
    msg = rag.reset_collection()
    return jsonify({"status": "ok" if msg is True else msg})

@app.route("/rag/documents", methods=["GET"])
def rag_documents():
    try:
        docs = rag.list_documents()
        return jsonify({"documents": docs})
    except Exception as e:
        logger.error("rag_documents error: %s", e)
        return jsonify({"documents": [], "error": str(e)})

@app.route("/rag/document-content", methods=["GET"])
def rag_document_content():
    source = request.args.get("source", "")
    if not source:
        return jsonify({"error": "source required"}), 400
    try:
        content = rag.get_document_content(source)
        return jsonify({"source": source, "content": content})
    except Exception as e:
        logger.error("rag_document_content error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/rag/delete", methods=["POST"])
def rag_delete():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    source = data.get("source", "")
    if not source:
        return jsonify({"error": "source required"}), 400
    ok = rag.delete_document(source)
    if ok:
        return jsonify({"status": "deleted", "source": source})
    return jsonify({"error": "No se pudo eliminar el documento"}), 500

@app.route("/models", methods=["GET"])
def list_models():
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        return jsonify({"models": [m["name"] for m in models]})
    except Exception as e:
        logger.error("list_models error: %s", e)
        return jsonify({"models": [], "error": str(e)}), 500

@app.route("/rag/browse")
def rag_browse():
    import os as _os
    requested = request.args.get("path", "")
    home = _os.path.expanduser("~")
    if requested:
        requested = _os.path.realpath(_os.path.normpath(requested))
        if not requested.startswith(_os.path.realpath(home)):
            requested = home
    else:
        requested = home

    try:
        entries = []
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
                entries.append({"name": name, "path": fpath, "is_dir": is_dir, "size": size})
            except PermissionError:
                pass
        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return jsonify({"path": requested, "home": home, "entries": entries})
    except PermissionError:
        return jsonify({"path": requested, "home": home, "entries": [], "error": "Permiso denegado"})
    except Exception as e:
        logger.error("rag_browse error: %s", e)
        return jsonify({"path": requested, "home": home, "entries": [], "error": str(e)})

@app.route("/rag/ingest-paths", methods=["POST"])
def rag_ingest_paths():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": "No se enviaron rutas"}), 400

    results = {"files": [], "total_chunks": 0}
    for fpath in paths:
        if not os.path.isfile(fpath):
            results["files"].append({"file": fpath, "status": "not_found"})
            continue
        try:
            r = rag.ingest_file(fpath)
            results["files"].append({"file": os.path.basename(fpath), **r})
            results["total_chunks"] += r.get("chunks", 0)
        except Exception as e:
            logger.error("Error ingesting path %s: %s", fpath, e)
            results["files"].append({"file": os.path.basename(fpath), "status": "error", "error": str(e)})
    return jsonify(results)

# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5051))
    print("\n  ╔══════════════════════════════════════╗")
    print("  ║   NeuralChat v3 — RAG + Ollama       ║")
    print("  ╚══════════════════════════════════════╝")
    print(f"  → http://localhost:{port}")
    print(f"  → Modelo: {MODEL}")
    print(f"  → Embedding: {rag.EMBED_MODEL}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
