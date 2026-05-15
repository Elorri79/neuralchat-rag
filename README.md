# NeuralChat v3.1 — Chatbot RAG con Ollama

Chatbot conversacional con Retrieval Augmented Generation (RAG) usando **Ollama** como LLM local y **ChromaDB** como base de datos vectorial. 100% local.

![NeuralChat RAG](img/Captura%20de%20pantalla%202026-05-07%20a%20las%2014.19.52.png)

## Modelo actual

- **LLM**: `qwen3.5:4b` (4.7B parámetros) — rápido, sin thinking, respuesta directa en español
- **Embeddings**: `llama3.2:1b` — generación de vectores para ChromaDB

## Características

- **Chat en streaming** — respuestas en tiempo real con efecto de "tecleado"
- **RAG (Retrieval Augmented Generation)** — el modelo responde usando solo el contexto de los documentos que subas
- **Selector de modelo** — elige entre cualquier modelo Ollama instalado y cambialo en tiempo real sin reiniciar
- **Explorador de archivos** — navega por tu sistema de archivos, selecciona y ingiere documentos directamente desde carpetas locales
- **Soporte PDF** — extracción de texto de documentos PDF mediante `pypdf`
- **Gestión de documentos** — sube archivos `.txt`, `.md`, `.csv`, `.json`, `.html`, `.pdf` y los ingiere automáticamente en la base vectorial
- **Borrado selectivo** — elimina documentos individuales de la knowledge base sin tener que resetearla entera
- **Previsualización de documentos** — haz clic en cualquier documento ingerido para ver su contenido
- **Retrieval semántico** — búsqueda por significado, no por palabras exactas
- **KPI en tiempo real** — tokens enviados, mensajes, tiempo de respuesta, chunks en base
- **Gráficos de actividad** — distribución de tokens y tiempos de respuesta
- **Barra de progreso en ingest** — feedback visual al ingerir múltiples archivos
- **100% local** — ningún dato sale de tu máquina (Ollama + ChromaDB + Flask)

## Tecnologías

| Componente | Tecnología |
|---|---|
| LLM | [Ollama](https://ollama.com/) — `qwen3.5:4b` (configurable) |
| Embeddings | Ollama `/api/embeddings` — `llama3.2:1b` |
| Base de datos vectorial | [ChromaDB](https://www.trychroma.com/) |
| Servidor web | Flask 3.x |
| Frontend | Vanilla JS + Chart.js |
| Tunneling (opcional) | Cloudflare Argo Tunnel |

## Estructura del proyecto

```
chatbot-app-v2/
├── app.py                 # Flask: rutas HTTP, streaming SSE, gestión RAG
├── rag.py                 # Módulo RAG: ingest, retrieve, embedding, ChromaDB
├── requirements.txt       # Dependencias Python
├── templates/
│   └── index.html         # Template Jinja2 de la UI
├── static/
│   ├── chat.js            # Frontend: chat, streaming, charts, file browser
│   └── style.css          # Estilos CSS
├── docs/                  # Documentos de prueba (no sube a git)
├── .chromadb/             # Base vectorial (ignorado en git)
├── .gitignore
└── README.md
```

## Base de datos vectorial — cómo funciona

### El problema que resuelve

Un LLM normal responde con lo que aprendió durante su entrenamiento. Si le preguntas sobre algo que no conocía, inventa una respuesta (alucinación). RAG soluciona esto dando al modelo solo la información relevante de tus documentos.

### El flujo completo

```
1. INGEST (indexación)
   Documento (.txt, .md, .html, .pdf...)
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

## Instalación

### Requisitos previos

- **Python 3.9+**
- **Ollama** instalado y corriendo (`ollama serve`)
- Modelos descargados: `ollama pull llama3.2:1b` (embedding) y `ollama pull qwen3.5:4b` (chat)

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
pypdf>=4.0
python-dotenv>=1.0
```

## Arranque

```bash
# Terminal 1 — Ollama (si no está corriendo como servicio)
ollama serve

# Terminal 2 — Flask (con virtualenv recomendado)
python3 app.py
```

Abrir: [http://localhost:5051](http://localhost:5051)

### Variables de entorno (opcional)

| Variable | Default | Descripción |
|---|---|---|
| `MODEL` | `qwen3.5:4b` | Modelo para chat |
| `EMBED_MODEL` | `llama3.2:1b` | Modelo para embeddings |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | URL base de Ollama |
| `PORT` | `5051` | Puerto del servidor Flask |
| `SECRET_KEY` | (aleatorio) | Clave secreta de Flask |

Ejemplo:
```bash
MODEL="llama3.2:1b" PORT=8080 python3 app.py
```

## Exponer a internet (opcional)

### Con cloudflared (túnel temporal)

```bash
cloudflared tunnel --url http://localhost:5051
```

Te devuelve una URL pública temporal en `trycloudflare.com`.

## Uso de RAG

1. Haz clic en el botón **📚 RAG** (header)
2. Navega por el explorador de archivos o arrastra archivos al área de upload
3. Se chunkean, embeddean y guardan automáticamente
4. Escribe tu pregunta — el modelo usa **solo** el contexto de los documentos subidos
5. Verás el contexto recuperado debajo de tu mensaje

**Formatos soportados:** `.txt`, `.md`, `.csv`, `.json`, `.html`, `.htm`, `.pdf`

## Configuración

Toda la configuración se hace mediante variables de entorno (ver tabla arriba).
Los parámetros de chunking se editan directamente en `rag.py`:

```python
COLLECTION = "chatbot_docs"
CHUNK_SIZE = 300        # palabras por chunk
CHUNK_OVERLAP = 50       # solape entre chunks
```

## Mejoras en v3.1

- **Template HTML separado** — el HTML/CSS/JS ya no está embebido en `app.py`. Uso de `templates/index.html`, `static/style.css` y `static/chat.js`
- **Soporte PDF** — extracción de texto con `pypdf`
- **Borrado selectivo de documentos** — elimina documentos uno a uno desde el modal RAG
- **Previsualización de documentos** — clic para ver el contenido ingerido
- **Barra de progreso en ingest** — feedback visual al procesar archivos
- **Variables de entorno** — configuración mediante `MODEL`, `OLLAMA_URL`, `PORT`, `SECRET_KEY`
- **Logging estructurado** — logs con timestamp y nivel
- **Thread safety** — lock para acceso concurrente a ChromaDB
- **Validación de requests** — los endpoints devuelven 400 si faltan campos
- **Path traversal fix** — el explorador de archivos usa `realpath` para prevenir symlink escapes
- **Secret key dinámica** — generada aleatoriamente si no se define en entorno

## Limitaciones

- **Embedding secuencial** — lento con muchos chunks
- **Documentos compartidos** — no hay separación por usuario
- **Sin autenticación** — cualquiera con la URL puede acceder
- **Sin historial persistente** — el historial de chat se pierde al cerrar

## Licencia

MIT
