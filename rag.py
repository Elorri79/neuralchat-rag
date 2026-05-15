import os, hashlib, re, uuid, html, logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import chromadb
from chromadb.config import Settings
import requests

logger = logging.getLogger(__name__)

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL  = os.getenv("EMBED_MODEL", "nomic-embed-text")
LLM_MODEL    = os.getenv("LLM_MODEL", "qwen3.5:4b")
COLLECTION   = "chatbot_docs"
CHUNK_SIZE   = 500
MAX_WORKERS  = 4

db_dir = os.path.join(os.path.dirname(__file__), ".chromadb")
os.makedirs(db_dir, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=db_dir)
_chroma_lock = Lock()

def get_collection():
    return chroma_client.get_or_create_collection(
        name=COLLECTION,
        metadata={"description": "Documentos del chatbot RAG"}
    )

def get_embedding(text: str) -> list[float]:
    r = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60
    )
    r.raise_for_status()
    return r.json()["embedding"]

def get_embeddings_parallel(texts: list[str], max_workers: int = MAX_WORKERS) -> list[list[float]]:
    if len(texts) <= 1:
        return [get_embedding(t) for t in texts]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(get_embedding, t): i for i, t in enumerate(texts)}
        results = [None] * len(texts)
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
        return results

def chunk_text(text: str) -> list[str]:
    paragraphs = re.split(r'\n\s*\n', text.strip())
    chunks = []
    buffer = []
    buffer_len = 0

    def flush_buffer():
        nonlocal buffer, buffer_len
        if buffer:
            chunks.append(" ".join(buffer))
            buffer = []
            buffer_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        words = para.split()
        para_len = len(words)

        if para_len >= CHUNK_SIZE:
            flush_buffer()
            for i in range(0, para_len, CHUNK_SIZE):
                chunks.append(" ".join(words[i:i + CHUNK_SIZE]))
        elif buffer_len + para_len <= CHUNK_SIZE:
            buffer.append(para)
            buffer_len += para_len
        else:
            flush_buffer()
            buffer.append(para)
            buffer_len = para_len

    flush_buffer()
    return chunks if chunks else [text]

def _clean_html(text: str) -> str:
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_text(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".txt", ".md", ".csv"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    elif ext in (".html", ".htm"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return _clean_html(f.read())
    elif ext == ".json":
        import json
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        texts = []
        def flatten(obj):
            if isinstance(obj, str):
                texts.append(obj)
            elif isinstance(obj, list):
                for v in obj: flatten(v)
            elif isinstance(obj, dict):
                for v in obj.values(): flatten(v)
        flatten(data)
        return "\n".join(texts)
    elif ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        reader = PdfReader(filepath)
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t)
        return "\n".join(pages)
    return ""

def _ensure_dimension(col, dim: int):
    if dim == 0:
        return
    try:
        count = col.count()
        if count > 0:
            existing = col.get(limit=1, include=["embeddings"])
            emb = existing.get("embeddings") if existing else None
            if emb is not None and len(emb) > 0:
                existing_dim = len(emb[0])
                if existing_dim != dim:
                    logger.warning("Dimensión cambiada %d→%d, reseteando colección", existing_dim, dim)
                    chroma_client.delete_collection(COLLECTION)
                    new_col = chroma_client.get_or_create_collection(
                        name=COLLECTION,
                        metadata={"description": "Documentos del chatbot RAG"}
                    )
                    return new_col
    except Exception as e:
        logger.error("Error checking dimensions: %s", e)

def ingest_file(filepath: str, user_id: int = None, metadata: dict = None) -> dict:
    filename = os.path.basename(filepath)
    text = extract_text(filepath)
    if not text.strip():
        return {"chunks": 0, "status": "empty"}

    chunks = chunk_text(text)
    n = len(chunks)

    logger.info("Generando %d embeddings para '%s' (user=%s)…", n, filename, user_id)
    embeddings = get_embeddings_parallel(chunks)

    dim = len(embeddings[0]) if embeddings else 0
    with _chroma_lock:
        col = get_collection()
        col = _ensure_dimension(col, dim) or col

        ids = []
        metadatas = []
        for i in range(n):
            ids.append(f"{filename}#{i}#u{user_id or 0}")
            meta = {"source": filename, "chunk": i, **(metadata or {})}
            if user_id:
                meta["user_id"] = user_id
            metadatas.append(meta)
        col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    return {"chunks": n, "status": "ok"}

def retrieve(query: str, top_k: int = 4, user_id: int = None) -> list[dict]:
    try:
        q_embedding = get_embedding(query)
    except Exception as e:
        logger.error("Embedding query error: %s", e)
        return []

    with _chroma_lock:
        col = get_collection()
        try:
            where = {"user_id": user_id} if user_id else None
            results = col.query(
                query_embeddings=[q_embedding],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.error("Query error: %s", e)
            return []

    docs = []
    for i in range(len(results.get("ids", [[]])[0])):
        docs.append({
            "content":   results["documents"][0][i],
            "source":    results["metadatas"][0][i].get("source", "?"),
            "chunk":     results["metadatas"][0][i].get("chunk", 0),
            "distance":  results["distances"][0][i],
        })
    return docs

def build_rag_prompt(user_query: str, docs: list[dict]) -> str:
    if not docs:
        context_block = "(No se ha encontrado contexto relevante en la base de conocimiento.)"
    else:
        blocks = []
        for j, d in enumerate(docs, 1):
            blocks.append(f"[Documento {j} — {d['source']}]\n{d['content']}")
        context_block = "\n\n".join(blocks)

    return (
        "Eres un asistente RAG experto en documentación técnica. "
        "Los documentos de contexto pueden estar en inglés u otros idiomas. "
        "Responde SIEMPRE en español, usando ÚNICAMENTE la información "
        "proporcionada en la sección de contexto inferior. "
        "Si es necesario, traduce la información del inglés al español antes de responder. "
        "Si la respuesta no está en el contexto, di claramente que no tienes esa información. "
        "No inventes nada. Sé conciso, preciso y útil.\n\n"
        f"=== CONTEXTO ===\n{context_block}\n"
        f"=== PREGUNTA ===\n{user_query}\n\n"
        "=== RESPUESTA ==="
    )

def collection_stats(user_id: int = None) -> dict:
    with _chroma_lock:
        col = get_collection()
        where = {"user_id": user_id} if user_id else None
        try:
            results = col.get(where=where, include=["metadatas"])
            metadatas = results.get("metadatas", [])
            count = len(metadatas)
            sources = list({m["source"] for m in metadatas if m}) if metadatas else []
        except Exception:
            count = 0
            sources = []
        return {"chunks": count, "sources": sources}

def get_user_chunks(user_id: int) -> int:
    with _chroma_lock:
        col = get_collection()
        try:
            results = col.get(where={"user_id": user_id}, include=["metadatas"])
            return len(results.get("metadatas", []))
        except Exception:
            return 0

def reset_collection():
    try:
        with _chroma_lock:
            chroma_client.delete_collection(COLLECTION)
            chroma_client.get_or_create_collection(name=COLLECTION, metadata={"description": "Documentos del chatbot RAG"})
        return True
    except Exception as e:
        return str(e)

def list_documents(user_id: int = None) -> list[dict]:
    with _chroma_lock:
        col = get_collection()
        where = {"user_id": user_id} if user_id else None
        try:
            results = col.get(where=where, include=["metadatas"])
            source_map = {}
            for m in results.get("metadatas", []):
                if m:
                    src = m.get("source", "?")
                    source_map.setdefault(src, 0)
                    source_map[src] += 1
            return [{"source": src, "chunks": n} for src, n in sorted(source_map.items())]
        except Exception as e:
            logger.error("list_documents error: %s", e)
            return []

def get_document_content(source: str, user_id: int = None) -> str:
    with _chroma_lock:
        col = get_collection()
        where = {"$and": [{"source": source}]}
        if user_id is not None:
            where["$and"].append({"user_id": user_id})
        try:
            results = col.get(where=where, include=["documents"])
            docs = results.get("documents", [])
            return "\n\n---\n\n".join(docs) if docs else ""
        except Exception as e:
            logger.error("get_document_content error: %s", e)
            return ""

def delete_document(source: str, user_id: int = None) -> bool:
    with _chroma_lock:
        col = get_collection()
        where = {"$and": [{"source": source}]}
        if user_id is not None:
            where["$and"].append({"user_id": user_id})
        try:
            col.delete(where=where)
            return True
        except Exception as e:
            logger.error("delete_document error: %s", e)
            return False
