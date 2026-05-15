import os
import uuid
import logging
from datetime import datetime

from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import requests

import rag
import db

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

db.init_db()

def require_auth():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.get_user_by_id(user_id)
    return user

# ── Auth routes ─────────────────────────────────────────────────────────────

@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or len(username) < 3:
        return jsonify({"error": "El usuario debe tener al menos 3 caracteres"}), 400
    if not password or len(password) < 4:
        return jsonify({"error": "La contraseña debe tener al menos 4 caracteres"}), 400

    existing = db.get_user(username)
    if existing:
        return jsonify({"error": "El usuario ya existe"}), 409

    is_first = db.count_users() == 0
    admin_user = None
    if not is_first:
        admin_user = require_auth()
        if not admin_user or not admin_user.get("is_admin"):
            return jsonify({"error": "Solo el administrador puede crear usuarios"}), 403

    pw_hash = generate_password_hash(password)
    user_id = db.create_user(username, pw_hash, is_admin=is_first)
    if not user_id:
        return jsonify({"error": "Error al crear el usuario"}), 500

    is_admin_val = bool(is_first)
    if is_first:
        session["user_id"] = user_id
        session["username"] = username
    else:
        return jsonify({"status": "ok", "user": {"id": user_id, "username": username, "is_admin": is_admin_val}})

    return jsonify({"status": "ok", "user": {"id": user_id, "username": username, "is_admin": is_admin_val}})

@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    user = db.get_user(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    db.update_last_login(user["id"])
    return jsonify({"status": "ok", "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user.get("is_admin"))}})

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route("/auth/me")
def auth_me():
    user = require_auth()
    if not user:
        return jsonify({"authenticated": False}), 200
    return jsonify({
        "authenticated": True,
        "user": {"id": user["id"], "username": user["username"], "is_admin": bool(user.get("is_admin"))}
    })

@app.route("/auth/users", methods=["GET"])
def auth_list_users():
    admin = require_auth()
    if not admin or not admin.get("is_admin"):
        return jsonify({"error": "Solo el administrador"}), 403
    users = db.list_users()
    return jsonify({"users": users})

@app.route("/auth/users", methods=["POST"])
def auth_admin_create_user():
    admin = require_auth()
    if not admin or not admin.get("is_admin"):
        return jsonify({"error": "Solo el administrador"}), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    if not username or len(username) < 3:
        return jsonify({"error": "El usuario debe tener al menos 3 caracteres"}), 400
    if not password or len(password) < 4:
        return jsonify({"error": "La contraseña debe tener al menos 4 caracteres"}), 400
    if db.get_user(username):
        return jsonify({"error": "El usuario ya existe"}), 409
    pw_hash = generate_password_hash(password)
    user_id = db.create_user(username, pw_hash)
    return jsonify({"status": "ok", "user": {"id": user_id, "username": username, "is_admin": False}}), 201

@app.route("/auth/users/<int:user_id>", methods=["DELETE"])
def auth_admin_delete_user(user_id):
    admin = require_auth()
    if not admin or not admin.get("is_admin"):
        return jsonify({"error": "Solo el administrador"}), 403
    if user_id == admin["id"]:
        return jsonify({"error": "No puedes eliminarte a ti mismo"}), 400
    db.delete_user_by_id(user_id)
    return jsonify({"status": "deleted"})

# ── Session routes ──────────────────────────────────────────────────────────

@app.route("/sessions")
def list_sessions():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    sessions = db.get_sessions(user["id"])
    return jsonify({"sessions": sessions})

@app.route("/sessions", methods=["POST"])
def create_session():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip() or "Nueva conversación"
    session_id = db.create_session(user["id"], title)
    return jsonify({"session": {"id": session_id, "title": title}}), 201

@app.route("/sessions/<int:session_id>", methods=["DELETE"])
def delete_session_route(session_id):
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    db.delete_session(session_id)
    return jsonify({"status": "deleted"})

@app.route("/sessions/<int:session_id>/messages")
def get_session_messages(session_id):
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    messages = db.get_messages(session_id)
    return jsonify({"messages": messages})

# ── Chat routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", model=MODEL)

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400

    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "messages field required"}), 400

    model = data.get("model", MODEL)
    use_rag = data.get("rag", True)
    rag_context = data.get("rag_context", [])
    session_id = data.get("session_id")

    def generate():
        try:
            if rag_context and use_rag:
                last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
                if last_user:
                    rag_prompt = rag.build_rag_prompt(last_user["content"], rag_context)
                    new_messages = list(messages[:-1])
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

@app.route("/chat/save", methods=["POST"])
def save_message():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    session_id = data.get("session_id")
    role = data.get("role")
    content = data.get("content", "")
    tokens = data.get("tokens", 0)
    if not session_id or not role:
        return jsonify({"error": "session_id and role required"}), 400
    msg_id = db.add_message(session_id, role, content, tokens)
    db.touch_session(session_id)
    if role == "user":
        msgs = db.get_messages(session_id)
        user_msgs = [m for m in msgs if m["role"] == "user"]
        if len(user_msgs) <= 1:
            title = content[:60] + ("…" if len(content) > 60 else "")
            db.update_session_title(session_id, title)
    return jsonify({"id": msg_id})

# ── RAG routes ─────────────────────────────────────────────────────────────

@app.route("/rag/status")
def rag_status():
    user = require_auth()
    if not user:
        return jsonify({"chunks": 0, "sources": [], "error": "No autenticado"}), 401
    try:
        stats = rag.collection_stats(user_id=user["id"])
        storage = db.get_user_storage_info(user["id"])
        stats["storage"] = storage
        return jsonify(stats)
    except Exception as e:
        logger.error("rag_status error: %s", e)
        return jsonify({"chunks": 0, "sources": [], "error": str(e)})

@app.route("/rag/ingest", methods=["POST"])
def rag_ingest():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    results = {"files": [], "total_chunks": 0}
    try:
        files = request.files.getlist("files")
        if not files:
            return jsonify({"error": "No se enviaron archivos"}), 400

        storage = db.get_user_storage_info(user["id"])
        if storage and storage["available"] <= 0:
            return jsonify({"error": "Límite de chunks alcanzado. Elimina documentos para liberar espacio."}), 413

        import tempfile
        tmpdir = tempfile.mkdtemp()
        for f in files:
            fname = os.path.join(tmpdir, f.filename)
            f.save(fname)
            try:
                r = rag.ingest_file(fname, user_id=user["id"])
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
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    query = data.get("query", "")
    top_k = data.get("top_k", 4)
    try:
        docs = rag.retrieve(query, top_k=top_k, user_id=user["id"])
        return jsonify({"docs": docs})
    except Exception as e:
        logger.error("rag_retrieve error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/rag/reset", methods=["POST"])
def rag_reset():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    msg = rag.reset_collection()
    return jsonify({"status": "ok" if msg is True else msg})

@app.route("/rag/documents", methods=["GET"])
def rag_documents():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    try:
        docs = rag.list_documents(user_id=user["id"])
        return jsonify({"documents": docs})
    except Exception as e:
        logger.error("rag_documents error: %s", e)
        return jsonify({"documents": [], "error": str(e)})

@app.route("/rag/document-content", methods=["GET"])
def rag_document_content():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    source = request.args.get("source", "")
    if not source:
        return jsonify({"error": "source required"}), 400
    try:
        content = rag.get_document_content(source, user_id=user["id"])
        return jsonify({"source": source, "content": content})
    except Exception as e:
        logger.error("rag_document_content error: %s", e)
        return jsonify({"error": str(e)}), 500

@app.route("/rag/delete", methods=["POST"])
def rag_delete():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    source = data.get("source", "")
    if not source:
        return jsonify({"error": "source required"}), 400
    ok = rag.delete_document(source, user_id=user["id"])
    if ok:
        return jsonify({"status": "deleted", "source": source})
    return jsonify({"error": "No se pudo eliminar el documento"}), 500

@app.route("/rag/ingest-paths", methods=["POST"])
def rag_ingest_paths():
    user = require_auth()
    if not user:
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body required"}), 400
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": "No se enviaron rutas"}), 400

    storage = db.get_user_storage_info(user["id"])
    results = {"files": [], "total_chunks": 0}
    for fpath in paths:
        if not os.path.isfile(fpath):
            results["files"].append({"file": fpath, "status": "not_found"})
            continue
        if storage and storage["available"] <= 0:
            results["files"].append({"file": os.path.basename(fpath), "status": "error", "error": "Límite de chunks"})
            continue
        try:
            r = rag.ingest_file(fpath, user_id=user["id"])
            results["files"].append({"file": os.path.basename(fpath), **r})
            results["total_chunks"] += r.get("chunks", 0)
        except Exception as e:
            logger.error("Error ingesting path %s: %s", fpath, e)
            results["files"].append({"file": os.path.basename(fpath), "status": "error", "error": str(e)})
    return jsonify(results)

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
