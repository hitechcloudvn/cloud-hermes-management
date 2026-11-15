# Changelog

**Tiếng Việt** | **English**

Tất cả thay đổi đáng chú ý của dự án được ghi lại trong tệp này.
All notable changes to this project are documented in this file.

---

## 🇻🇳 Tiếng Việt

### [0.1.0] - 2026-11-15

Bản phát hành công khai đầu tiên.

- **Management API FastAPI đầy đủ** — 73 endpoint: health/info, xác thực, điều
  khiển dịch vụ, cấu hình/nhà cung cấp, kênh nhắn tin, cron, nhật ký + luồng
  SSE, biến môi trường, CLI passthrough, proxy sidecar Zalo, OpenViking, Codex
  OAuth, vai trò & quy tắc.
- **Dịch vụ RAG MCP tùy chọn** — embedding fastembed chạy cục bộ + vector store
  SQLite, cung cấp các công cụ `rag_search` / `rag_stats` cho Hermes
  (`install.sh --with-rag`).
- **Triển khai bare-metal Ubuntu 24.04** — `install.sh` / `bootstrap.sh` thiết
  lập systemd `hermes.target` + reverse proxy Caddy + tường lửa UFW.
- **CI/CD** — GitHub Actions + GitLab CI build và phát hành bản release khi có
  tag `v*`.
- **Tài liệu song ngữ Việt–Anh** — `README.md` chứa đầy đủ cả hai ngôn ngữ
  (`## 🇻🇳 Tiếng Việt` / `## 🇬🇧 English`), theo chuẩn tổ chức `hitechcloudvn`.
- **Chuẩn hoá tác giả lịch sử git** về Nguyễn Thanh An kèm trailer đồng tác giả.

---

## 🇬🇧 English

### [0.1.0] - 2026-11-15

First public release.

- **Full FastAPI Management API** — 73 endpoints: health/info, auth, service
  control, config/providers, channels, cron, logs + SSE streaming, env, CLI
  passthrough, Zalo sidecar proxy, OpenViking, Codex OAuth, roles & rules.
- **Optional RAG MCP service** — local fastembed embeddings + SQLite vector
  store, exposing the `rag_search` / `rag_stats` tools to Hermes
  (`install.sh --with-rag`).
- **Bare-metal Ubuntu 24.04 deployment** — `install.sh` / `bootstrap.sh` set up
  systemd `hermes.target` + Caddy reverse proxy + UFW firewall.
- **CI/CD** — GitHub Actions + GitLab CI build and publish releases on `v*` tags.
- **Bilingual VN–EN documentation** — `README.md` carries both languages in full
  (`## 🇻🇳 Tiếng Việt` / `## 🇬🇧 English`), following the `hitechcloudvn` org
  convention.
- **Git history authorship** normalized to Nguyễn Thanh An with co-author
  trailers.
