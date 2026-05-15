import os, hashlib, re, uuid, html, logging
from threading import Lock
import chromadb
from chromadb.config import Settings
import requests

logger = logging.getLogger(__name__)

OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL  = os.getenv("EMBED_MODEL", "llama3.2:1b")
LLM_MODEL    = os.getenv("LLM_MODEL", "qwen3.5:4b")
COLLECTION   = "chatbot_docs"
CHUNK_SIZE   = 300
CHUNK_OVERLAP = 50

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

def get_embeddings_sequential(texts: list[str]) -> list[list[float]]:
    return [get_embedding(t) for t in texts]

def chunk_text(text: str) -> list[str]:
    words = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        end   = start + CHUNK_SIZE
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk.strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks

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

def ingest_file(filepath: str, metadata: dict = None) -> dict:
    filename = os.path.basename(filepath)
    text = extract_text(filepath)
    if not text.strip():
        return {"chunks": 0, "status": "empty"}

    chunks = chunk_text(text)
    n = len(chunks)

    logger.info("Generando %d embeddings para '%s'…", n, filename)
    embeddings = get_embeddings_sequential(chunks)

    with _chroma_lock:
        col = get_collection()
        ids = [f"{filename}#{i}" for i in range(n)]
        metadatas = [{"source": filename, "chunk": i, **(metadata or {})} for i in range(n)]
        col.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)

    return {"chunks": n, "status": "ok"}

def ingest_directory(directory: str, extensions: tuple = (".txt", ".md", ".csv", ".json", ".html", ".htm", ".pdf")) -> dict:
    total_chunks = 0
    files_processed = []
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.lower().endswith(extensions):
                fpath = os.path.join(root, fname)
                try:
                    result = ingest_file(fpath)
                    total_chunks += result["chunks"]
                    files_processed.append({"file": fname, **result})
                except Exception as e:
                    logger.error("Error ingesting %s: %s", fname, e)
                    files_processed.append({"file": fname, "status": "error", "error": str(e)})
    return {"total_chunks": total_chunks, "files": files_processed}

def retrieve(query: str, top_k: int = 4) -> list[dict]:
    try:
        q_embedding = get_embedding(query)
    except Exception as e:
        logger.error("Embedding query error: %s", e)
        return []

    with _chroma_lock:
        col = get_collection()
        try:
            results = col.query(
                query_embeddings=[q_embedding],
                n_results=top_k,
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
        "Eres un asistente RAG. Responde la pregunta del usuario usando "
        "ÚNICAMENTE la información proporcionada en la sección de contexto inferior. "
        "Si la respuesta no está en el contexto, di claramente que no tienes esa información. "
        "No inventes nada. Sé conciso y responde en español.\n\n"
        f"=== CONTEXTO ===\n{context_block}\n"
        f"=== PREGUNTA ===\n{user_query}\n\n"
        "=== RESPUESTA ==="
    )

def collection_stats() -> dict:
    with _chroma_lock:
        col = get_collection()
        count = col.count()
        if count == 0:
            return {"chunks": 0, "sources": []}
        try:
            results = col.get(include=["metadatas"])
            sources = list({m["source"] for m in results.get("metadatas", []) if m})
        except Exception:
            sources = []
        return {"chunks": count, "sources": sources}

def reset_collection():
    try:
        with _chroma_lock:
            chroma_client.delete_collection(COLLECTION)
            chroma_client.get_or_create_collection(name=COLLECTION, metadata={"description": "Documentos del chatbot RAG"})
        return True
    except Exception as e:
        return str(e)

def list_documents() -> list[dict]:
    with _chroma_lock:
        col = get_collection()
        count = col.count()
        if count == 0:
            return []
        try:
            results = col.get(include=["metadatas"])
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

def get_document_content(source: str) -> str:
    with _chroma_lock:
        col = get_collection()
        try:
            results = col.get(where={"source": source}, include=["documents"])
            docs = results.get("documents", [])
            if docs:
                return "\n\n---\n\n".join(docs)
            return ""
        except Exception as e:
            logger.error("get_document_content error: %s", e)
            return ""

def delete_document(source: str) -> bool:
    with _chroma_lock:
        col = get_collection()
        try:
            col.delete(where={"source": source})
            return True
        except Exception as e:
            logger.error("delete_document error: %s", e)
            return False
