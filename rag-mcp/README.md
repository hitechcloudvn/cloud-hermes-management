<div align="center">

# hermes-rag

**Dịch vụ RAG cục bộ qua MCP cho Hermes Agent**

**Local RAG over MCP for Hermes Agent**

**Tiếng Việt** | **English**

</div>

---

## 🇻🇳 Tiếng Việt

Một dịch vụ Retrieval-Augmented-Generation nhỏ, gọn phụ thuộc cho stack
[hermes-cloud-server](../README.md). Dịch vụ nạp tài liệu của riêng bạn, tạo embedding
cục bộ với [fastembed](https://github.com/qdrant/fastembed) (CPU, không cần API
key), và cung cấp khả năng truy xuất cho Hermes dưới dạng các công cụ MCP qua
StreamableHTTP.

Phần sinh câu trả lời (generation) vẫn nằm ở Hermes — dịch vụ này chỉ làm
**truy xuất** (embed + tìm kiếm), nên mô hình chat của bạn (DeepSeek, Nous,
OpenAI, …) không thay đổi.

### Kiến trúc

```
docs/ (md, txt, pdf)
   │  hermes-rag ingest
   ▼
chunk (recursive, overlap) ─► embed (fastembed, multilingual) ─► SQLite store
                                                                     │
Hermes ──MCP rag_search──► embed query ─► cosine top-k ◄────────────┘
```

- **Embedding:** mô hình fastembed cục bộ, mặc định
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-d, tốt cho
  tiếng Việt + tiếng Anh). Đặt `RAG_EMBED_MODEL=intfloat/multilingual-e5-large`
  để chất lượng cao hơn nếu bạn còn dư ~2GB RAM.
- **Vector store:** SQLite thuần với BLOB float32 + numpy cosine vét cạn.
  Không có extension native (sqlite-vec / FAISS). Hoạt động tốt tới vài chục
  nghìn chunk; cần chuyển sang ANN index nếu lớn hơn.
- **Transport:** MCP StreamableHTTP tại `http://127.0.0.1:9998/mcp`.

### CLI

```bash
hermes-rag ingest [PATH]     # nạp một tệp hoặc thư mục (mặc định: RAG_DOCS_DIR)
hermes-rag search "query"    # truy xuất một lần, in các đoạn được xếp hạng
hermes-rag stats             # số tài liệu / chunk / mô hình trong store
hermes-rag reset             # xóa store (vd. trước khi đổi mô hình)
hermes-rag serve             # chạy MCP server (systemd dùng lệnh này)
```

Quá trình ingest idempotent — tệp không thay đổi (theo content hash) sẽ bị bỏ qua.

### Các công cụ MCP cung cấp cho Hermes

| Công cụ | Mục đích |
|------|---------|
| `rag_search(query, top_k=5)` | Trả về các đoạn văn liên quan nhất kèm đường dẫn nguồn + điểm |
| `rag_stats()` | Báo cáo kích thước cơ sở tri thức và mô hình embedding đang dùng |

### Cấu hình (env, đọc bởi `config.py`)

| Biến | Mặc định | Ý nghĩa |
|-----|---------|---------|
| `RAG_DATA_DIR` | `/opt/hermes-rag/data` | Vị trí SQLite store |
| `RAG_DOCS_DIR` | `/opt/hermes-rag/docs` | Nguồn ingest mặc định |
| `RAG_MODEL_CACHE` | `/opt/hermes-rag/models` | Cache mô hình fastembed (lâu dài) |
| `RAG_EMBED_MODEL` | multilingual MiniLM | Tên mô hình embedding |
| `RAG_HOST` / `RAG_PORT` | `127.0.0.1` / `9998` | Địa chỉ bind của MCP server |
| `RAG_TOP_K` | `5` | Số kết quả mặc định mỗi truy vấn |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `1000` / `150` | Cắt chunk (theo ký tự) |
| `RAG_MAX_CONTEXT_CHARS` | `6000` | Số ký tự tối đa trả về mỗi lần tìm |
| `RAG_EMBED_PREFIX` | auto (`e5` models) | Bật/tắt tiền tố `query:`/`passage:` |

### Đăng ký với Hermes

Thêm vào `~/.hermes/config.yaml` (trình cài đặt tự làm việc này với `--with-rag`):

```yaml
mcp_servers:
  rag:
    url: "http://127.0.0.1:9998/mcp"
    timeout: 180
    connect_timeout: 30
```

Hermes tự động nạp lại `mcp_servers` khi cấu hình thay đổi.

---

## 🇬🇧 English

A small, dependency-light Retrieval-Augmented-Generation service for the
[hermes-cloud-server](../README.md) stack. It ingests your own documents, embeds them
locally with [fastembed](https://github.com/qdrant/fastembed) (CPU, no API key),
and exposes retrieval to Hermes as MCP tools over StreamableHTTP.

Generation stays in Hermes — this service only does **retrieval** (embed +
search), so your chat LLM (DeepSeek, Nous, OpenAI, …) is unchanged.

### Architecture

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

### CLI

```bash
hermes-rag ingest [PATH]     # ingest a file or dir (default: RAG_DOCS_DIR)
hermes-rag search "query"    # one-off retrieval, prints ranked passages
hermes-rag stats             # documents / chunks / model in the store
hermes-rag reset             # wipe the store (e.g. before changing models)
hermes-rag serve             # run the MCP server (used by systemd)
```

Ingestion is idempotent — unchanged files (by content hash) are skipped.

### MCP tools exposed to Hermes

| Tool | Purpose |
|------|---------|
| `rag_search(query, top_k=5)` | Return the most relevant passages with source path + score |
| `rag_stats()` | Report knowledge-base size and the embedding model in use |

### Configuration (env, read by `config.py`)

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

### Hermes registration

Add to `~/.hermes/config.yaml` (the installer does this with `--with-rag`):

```yaml
mcp_servers:
  rag:
    url: "http://127.0.0.1:9998/mcp"
    timeout: 180
    connect_timeout: 30
```

Hermes auto-reloads `mcp_servers` on config change.
