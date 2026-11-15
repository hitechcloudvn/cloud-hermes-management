<div align="center">

# hermes-mgmt

**API quản trị VPS cho Hermes Agent**

**VPS Management API for Hermes Agent**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Made in Vietnam](https://img.shields.io/badge/Made%20in-Vietnam-DA251D?style=flat-square)](https://hitechcloud.vn)

**Tiếng Việt** | **English**

</div>

---

## 🇻🇳 Tiếng Việt

### Giới thiệu

Gói Python `hermes_mgmt` — FastAPI Management API cho cụm Hermes Agent trên VPS Ubuntu 24.04. Chạy tại cổng `:9997`, cung cấp 73 endpoint quản trị: trạng thái hệ thống, điều khiển systemd, cấu hình provider/model, kênh nhắn tin, cron, nhật ký (SSE), biến môi trường, chuyển tiếp CLI, Zalo, OpenViking, Codex OAuth và vai trò agent.

Tài liệu đầy đủ (cài đặt, kiến trúc, danh mục endpoint, kiểm thử API): xem [README.md](https://github.com/hitechcloudvn/cloud-hermes-management) ở repo gốc.

### Cài đặt & kiểm thử

```bash
# Cài đặt trong venv
pip install -e .

# Chạy test (159 test)
python -m pytest tests/ -q
```

Yêu cầu Python ≥ 3.11. Phản hồi API dùng envelope thống nhất `{ok, data, error}`; xác thực qua `Authorization: Bearer <HERMES_MGMT_API_KEY>` hoặc session cookie từ `POST /api/auth/login`.

## 🇬🇧 English

### Introduction

The `hermes_mgmt` Python package — a FastAPI Management API for the Hermes Agent stack on Ubuntu 24.04 VPS. It serves 73 admin endpoints on port `:9997`: system status, systemd control, provider/model config, messaging channels, cron, logs (SSE), environment variables, CLI passthrough, Zalo, OpenViking, Codex OAuth and agent roles.

Full documentation (install, architecture, endpoint catalog, API test results): see the [root README.md](https://github.com/hitechcloudvn/cloud-hermes-management).

### Install & test

```bash
# Install into a venv
pip install -e .

# Run the tests (159 tests)
python -m pytest tests/ -q
```

Requires Python ≥ 3.11. API responses use a uniform `{ok, data, error}` envelope; authenticate with `Authorization: Bearer <HERMES_MGMT_API_KEY>` or a session cookie from `POST /api/auth/login`.
