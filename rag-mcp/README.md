# hermes-rag — Local RAG over MCP for Hermes Agent

[English](README.md) | [Tiếng Việt](README.vi.md)

A small, dependency-light Retrieval-Augmented-Generation service for the
[hermes-vps](../README.md) stack. It ingests your own documents, embeds them
locally with [fastembed](https://github.com/qdrant/fastembed) (CPU, no API key),
and exposes retrieval to Hermes as MCP tools over StreamableHTTP.

Generation stays in Hermes — this service only does **retrieval** (embed +
search), so your chat LLM (DeepSeek, Nous, OpenAI, …) is unchanged.

## Architecture

```
docs/ (md, txt, pdf)
   │  hermes-rag ingest
   ▼
chunk (recursive, overlap) ─► embed (fastembed, multilingual) ─► SQLite store
                                                                     │
Hermes ──MCP rag_search──► embed query ─► cosine top-k ◄────────────┘
```

- **Embeddings:** local fastembed model, default
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-d, good for
  Vietnamese + English). Set `RAG_EMBED_MODEL=intfloat/multilingual-e5-large`
  for higher quality if you have ~2GB RAM to spare.
- **Vector store:** plain SQLite with float32 BLOBs + numpy brute-force cosine.
  No native extension (sqlite-vec / FAISS). Fine up to ~tens of thousands of
  chunks; swap in an ANN index beyond that.
- **Transport:** MCP StreamableHTTP at `http://127.0.0.1:9998/mcp`.

## CLI

```bash
hermes-rag ingest [PATH]     # ingest a file or dir (default: RAG_DOCS_DIR)
hermes-rag search "query"    # one-off retrieval, prints ranked passages
hermes-rag stats             # documents / chunks / model in the store
hermes-rag reset             # wipe the store (e.g. before changing models)
hermes-rag serve             # run the MCP server (used by systemd)
```

Ingestion is idempotent — unchanged files (by content hash) are skipped.

## MCP tools exposed to Hermes

| Tool | Purpose |
|------|---------|
| `rag_search(query, top_k=5)` | Return the most relevant passages with source path + score |
| `rag_stats()` | Report knowledge-base size and the embedding model in use |

## Configuration (env, read by `config.py`)

| Var | Default | Meaning |
|-----|---------|---------|
| `RAG_DATA_DIR` | `/opt/hermes-rag/data` | SQLite store location |
| `RAG_DOCS_DIR` | `/opt/hermes-rag/docs` | Default ingest source |
| `RAG_MODEL_CACHE` | `/opt/hermes-rag/models` | fastembed model cache (persistent) |
| `RAG_EMBED_MODEL` | multilingual MiniLM | Embedding model name |
| `RAG_HOST` / `RAG_PORT` | `127.0.0.1` / `9998` | MCP server bind |
| `RAG_TOP_K` | `5` | Default results per query |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `1000` / `150` | Chunking (chars) |
| `RAG_MAX_CONTEXT_CHARS` | `6000` | Max chars returned per search |
| `RAG_EMBED_PREFIX` | auto (`e5` models) | Force `query:`/`passage:` prefixes on/off |

## Hermes registration

Add to `~/.hermes/config.yaml` (the installer does this with `--with-rag`):

```yaml
mcp_servers:
  rag:
    url: "http://127.0.0.1:9998/mcp"
    timeout: 180
    connect_timeout: 30
```

Hermes auto-reloads `mcp_servers` on config change.
