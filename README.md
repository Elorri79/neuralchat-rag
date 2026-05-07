# NeuralChat — Chatbot RAG con Ollama

Chatbot conversacional con Retrieval Augmented Generation (RAG) usando **Ollama** como LLM local y **ChromaDB** como base de datos vectorial.

![NeuralChat RAG](img/Captura%20de%20pantalla%202026-05-07%20a%20las%2014.19.52.png)

## Características

- **Chat en streaming** — respuestas en tiempo real con efecto de "tecleado"
- **RAG (Retrieval Augmented Generation)** — el modelo responde usando solo el contexto de los documentos que subas
- **Gestión de documentos** — sube archivos `.txt`, `.md`, `.csv`, `.json`, `.html` y los ingiere automáticamente en la base vectorial
- **Retrieval semántico** — búsqueda por significado, no por palabras exactas
- **KPI en tiempo real** — tokens enviados, mensajes, tiempo de respuesta, chunks en base
- **Gráficos de actividad** — distribución de tokens, longitud de mensajes, tiempos de respuesta
- **100% local** — ningún dato sale de tu máquina (Ollama + ChromaDB + Flask)

## Tecnologías

| Componente | Tecnología |
|---|---|
| LLM | [Ollama](https://ollama.com/) — `llama3.2:1b` (configurable) |
| Embeddings | Ollama `/api/embeddings` (mismo modelo que LLM) |
| Base de datos vectorial | [ChromaDB](https://www.trychroma.com/) |
| Servidor web | Flask 3.x |
| Frontend | Vanilla JS + Chart.js |
| Tunneling (opcional) | Cloudflare Argo Tunnel |

## Estructura del proyecto

```
chatbot-app-v2/
├── app.py              # Flask: rutas HTTP, streaming SSE, gestión RAG
├── rag.py              # Módulo RAG: ingest, retrieve, embedding, ChromaDB
├── static/
│   └── chat.js         # Frontend: chat, streaming, charts, upload
├── docs/               # Documentos de prueba (no sube a git)
│   └── .chromadb/      # Base vectorial (ignorado en git)
├── .gitignore
├── README.md
└── requirements.txt
```

## Base de datos vectorial — cómo funciona

### El problema que resuelve

Un LLM normal responde con lo que aprendió durante su entrenamiento. Si le preguntas sobre algo que no conocía, inventa una respuesta (alucinación). RAG soluciona esto dando al modelo solo la información relevante de tus documentos.

### El flujo completo

```
1. INGEST (indexación)
   Documento (.txt, .md, .html...)
         ↓  Limpieza y chunking (300 palabras, 50 de solape)
   Chunks de texto
         ↓  Modelo de embedding (Ollama /api/embeddings)
   Vectores de 2048 dimensiones
         ↓  ChromaDB los almacena con su texto original
   Base vectorial

2. RETRIEVAL (búsqueda)
   Pregunta del usuario
         ↓  Modelo de embedding
   Vector de la pregunta
         ↓  ChromaDB busca los k chunks más cercanos
   Contexto relevante

3. GENERATION (respuesta)
   Pregunta + Contexto → Prompt enriquecido → Ollama → Respuesta
```

### ¿Cómo sabe el modelo qué es similar?

El modelo de embedding convierte texto → vector. Textos con significados similares producen vectores "cercanos" en el espacio vectorial. ChromaDB usa **distancia euclidiana** o **cosine similarity** para encontrar los chunks más parecidos a la pregunta.

Ejemplo:
```
Pregunta: "¿Qué es Python?"
         ↓ embedding
Vector: [0.07, -0.02, 0.10, ...]
         ↓ búsqueda en ChromaDB
Chunk más cercano: "Python is a programming language..." — distancia: 0.23
```

## Instalación

### Requisitos previos

- **Python 3.9+**
- **Ollama** instalado y corriendo (`ollama serve`)
- Modelos descargados: `ollama pull llama3.2:1b` (o el que prefieras)

### Instalación

```bash
cd chatbot-app-v2
pip3 install -r requirements.txt
```

### `requirements.txt`

```
flask>=3.0
chromadb>=1.5
requests>=2.31
```

## Arranque

```bash
# Terminal 1 — Ollama (si no está corriendo como servicio)
ollama serve

# Terminal 2 — Flask
python3 app.py
```

Abrir: [http://localhost:5051](http://localhost:5051)

## Exponer a internet (opcional)

### Con cloudflared (túnel temporal)

```bash
# Instalar cloudflared: brew install cloudflared
cloudflared tunnel --url http://localhost:5051
```

Te devuelve una URL pública temporal en `trycloudflare.com`. **Caduca al cerrar el terminal.**

### Con tunnel permanente (Cloudflare con cuenta)

```bash
cloudflared tunnel login
cloudflared tunnel create neuralchat
cloudflared tunnel route dns neuralchat chat.tudominio.com
cloudflared tunnel run --token <tu-token>
```

## Uso de RAG

1. Haz clic en el botón **📚 RAG** (header)
2. Arrastra archivos `.txt`, `.md`, `.csv`, `.json`, `.html` o selecciónalos
3. Se chunkean, embeddean y guardan automáticamente
4. Escribe tu pregunta — el modelo usa **solo** el contexto de los documentos subidos
5. Verás el contexto recuperado debajo de tu mensaje

**Nota:** Los documentos son compartidos para todos los usuarios del túnel.

## Configuración

Edita las primeras variables en `app.py` y `rag.py`:

```python
# app.py
MODEL = "llama3.2:1b"       # modelo para chat
OLLAMA_URL = "http://127.0.0.1:11434"

# rag.py
EMBED_MODEL = "llama3.2:1b"  # modelo para embeddings (debe ser el mismo)
LLM_MODEL = "llama3.2:1b"
COLLECTION = "chatbot_docs"
CHUNK_SIZE = 300             # palabras por chunk
CHUNK_OVERLAP = 50            # solape entre chunks
```

## Limitaciones y siguientes mejoras

- **Modelo pequeño** — `llama3.2:1b` a veces ignora el contexto. Un modelo mayor (`qwen3.5:4b`, `qwen3.5:9b`) mejora mucho las respuestas
- **Documentos compartidos** — no hay separación por usuario
- **Sin autenticación** — cualquiera con la URL puede acceder
- **Embedding sequencial** — lento con muchos chunks. Para producción, considerar embedder paralelo o servicio dedicado
- **Sin historial persistente** — el historial de chat se pierde al cerrar

## Licencia

MIT