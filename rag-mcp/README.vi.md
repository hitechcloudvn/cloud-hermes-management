# hermes-rag — RAG cục bộ qua MCP cho Hermes Agent

[English](README.md) | [Tiếng Việt](README.vi.md)

Một dịch vụ Retrieval-Augmented-Generation nhỏ, gọn phụ thuộc cho stack
[hermes-vps](../README.vi.md). Dịch vụ nạp tài liệu của riêng bạn, tạo embedding
cục bộ với [fastembed](https://github.com/qdrant/fastembed) (CPU, không cần API
key), và cung cấp khả năng truy xuất cho Hermes dưới dạng các công cụ MCP qua
StreamableHTTP.

Phần sinh câu trả lời (generation) vẫn nằm ở Hermes — dịch vụ này chỉ làm
**truy xuất** (embed + tìm kiếm), nên mô hình chat của bạn (DeepSeek, Nous,
OpenAI, …) không thay đổi.

## Kiến trúc

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

## CLI

```bash
hermes-rag ingest [PATH]     # ingest a file or dir (default: RAG_DOCS_DIR)
hermes-rag search "query"    # one-off retrieval, prints ranked passages
hermes-rag stats             # documents / chunks / model in the store
hermes-rag reset             # wipe the store (e.g. before changing models)
hermes-rag serve             # run the MCP server (used by systemd)
```

Quá trình ingest idempotent — tệp không thay đổi (theo content hash) sẽ bị bỏ qua.

## Các công cụ MCP cung cấp cho Hermes

| Công cụ | Mục đích |
|------|---------|
| `rag_search(query, top_k=5)` | Trả về các đoạn văn liên quan nhất kèm đường dẫn nguồn + điểm |
| `rag_stats()` | Báo cáo kích thước cơ sở tri thức và mô hình embedding đang dùng |

## Cấu hình (env, đọc bởi `config.py`)

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

## Đăng ký với Hermes

Thêm vào `~/.hermes/config.yaml` (trình cài đặt tự làm việc này với `--with-rag`):

```yaml
mcp_servers:
  rag:
    url: "http://127.0.0.1:9998/mcp"
    timeout: 180
    connect_timeout: 30
```

Hermes tự động nạp lại `mcp_servers` khi cấu hình thay đổi.
