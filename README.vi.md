# hermes-cloud-server — Triển khai VPS bare-metal cho Hermes Agent

[English](README.md) | [Tiếng Việt](README.vi.md)

Trình cài đặt một lệnh + FastAPI Management REST API + systemd + reverse proxy Caddy cho [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) trên **Ubuntu 24.04**.

Lấy cảm hứng từ mô hình triển khai OpenClaw, viết lại trên nền Python của Hermes.

## Tính năng

- **Cài đặt một lệnh** — `curl … | bash` thiết lập Hermes + dashboard + mgmt API trong ~3 phút
- **Không Docker** — chạy trực tiếp trên hệ điều hành qua systemd, tiết kiệm 200-500 MB RAM
- **FastAPI Management API** — 73 endpoint cho status/config/channels/cron/logs/CLI/Zalo/OpenViking/Codex/Roles (đã smoke-test 34/34 PASS, xem [#kết-quả-kiểm-thử-api](#kết-quả-kiểm-thử-api))
- **15 mẫu nhà cung cấp** — Anthropic, OpenAI, Google, xAI, DeepSeek, Groq, Mistral, Together, Nous Portal, OpenRouter, HuggingFace, Kimi, MiMo, MiniMax, z.ai
- **6 kênh nhắn tin** — Telegram, Discord, Slack, Signal, WhatsApp, Email
- **SSL tự động** — Let's Encrypt qua Caddy, dự phòng chứng chỉ tự ký khi DNS chưa sẵn sàng
- **Cổng xác thực dashboard** — Caddy yêu cầu tham số `?token=<HERMES_AUTH_TOKEN>` rồi đặt cookie HTTP-only hạn 30 ngày; ai không có token sẽ nhận 403
- **Tự động phát hiện hostname** — dùng `hostname -f`, dự phòng `<IP>.sslip.io`

## Hướng dẫn nhanh

```bash
curl -fsSL https://raw.githubusercontent.com/hitechcloudvn/cloud-hermes-management/main/install.sh | \
  bash -s --
```

Sau ~3 phút:

```
Dashboard URL (first visit, sets a 30d cookie then strips token):
  https://<HOSTNAME>/?token=<AUTH_TOKEN>

Management API: http://<IP>:9997     (port-only, not proxied via Caddy)

AUTH_TOKEN:     <48-char hex — dashboard gate>
MGMT_API_KEY:   <64-char hex — mgmt API bearer>
GATEWAY_TOKEN:  <64-char hex — hermes gateway>
```

Mở URL dashboard một lần trên mỗi trình duyệt; Caddy sẽ đặt cookie
`hermes_auth` (`HttpOnly; Secure; SameSite=Lax; Max-Age=2592000`)
rồi chuyển hướng 302 về `/` để token không nằm trong lịch sử trình duyệt.
Các lần truy cập sau tới `https://<HOSTNAME>/` được tự động xác thực bằng
cookie. Khách không có token nhận `403 Forbidden`.

## Cơ sở tri thức RAG (tùy chọn)

Cho Hermes khả năng truy xuất trên **chính tài liệu của bạn**. Cài đặt với cờ
`--with-rag` để thêm dịch vụ thứ 4 (`hermes-rag`) nạp các tệp cục bộ và cung cấp
công cụ MCP `rag_search` mà agent gọi trong lúc trò chuyện:

```bash
curl -fsSL https://raw.githubusercontent.com/hitechcloudvn/cloud-hermes-management/main/install.sh | \
  bash -s -- --with-rag
```

Rồi nạp tài liệu và lập chỉ mục:

```bash
cp ~/my-docs/*.{md,txt,pdf} /opt/hermes-rag/docs/
hermes-rag ingest        # chunk + embed + store
hermes-rag stats         # documents / chunks / model
hermes-rag search "câu hỏi của bạn"   # one-off test query
```

- **Embedding chạy cục bộ** qua fastembed (CPU, không cần API key, ngoại tuyến).
  Mô hình mặc định đa ngôn ngữ và hoạt động tốt với tiếng Việt. DeepSeek/mô hình
  chat của bạn không bị ảnh hưởng — nó vẫn trả lời; RAG chỉ làm phần truy xuất.
- **Không phụ thuộc native**: SQLite thuần + numpy cosine. Hoạt động tốt tới vài
  chục nghìn chunk; xem [rag-mcp/README.vi.md](rag-mcp/README.vi.md) để tinh chỉnh
  và tùy chọn mô hình lớn hơn `multilingual-e5-large`.
- Cổng `9998` **chỉ loopback** (không mở trong UFW); Hermes kết nối qua
  localhost và tự động nạp lại mục `mcp_servers.rag` mà trình cài đặt thêm vào
  `config.yaml`.

## Kiến trúc

```
Internet
  │
  ├── :80/:443 ── Caddy (systemd, Let's Encrypt)
  │                 │
  │                 ├── ?token=<AUTH_TOKEN>  → 302 + Set-Cookie hermes_auth (30d)
  │                 ├── cookie hermes_auth   → reverse_proxy 127.0.0.1:9119
  │                 │                          (Host header rewritten to localhost:9119
  │                 │                          to satisfy Hermes' strict Host check)
  │                 └── neither              → 403 Forbidden
  │
  └── :9997 (direct, UFW-allowed) ── Mgmt API (Bearer auth)
```

Dashboard của Hermes sở hữu toàn bộ vùng `/api/*` (status, sessions,
env, providers, logs, …). Management API **không** được proxy qua
Caddy vì không gian `/api/*` của nó chồng lấn với của Hermes; nó nằm trên
cổng `9997` và được truy cập trực tiếp.

| Dịch vụ | Nhị phân | Cổng | Mục đích |
|---------|--------|------|---------|
| `hermes-gateway.service` | `hermes gateway run` | — | Cầu nối nhắn tin |
| `hermes-dashboard.service` | `hermes dashboard --host 127.0.0.1 --port 9119` | 9119 | Giao diện web (FastAPI) |
| `hermes-mgmt.service` | `uvicorn hermes_mgmt.main:app` | 9997 | Management REST API |
| `caddy.service` | `caddy` | 80, 443 | Reverse proxy + SSL |

## Bố cục hệ thống tệp

```
/opt/hermes/                       Install root
├── .env                           Service tokens + domain (systemd EnvironmentFile)
├── data/                          Runtime data
├── Caddyfile                      Caddy config (uses env vars from .env)
└── hermes-agent/                  Upstream Hermes source (git clone, uv venv)

/root/.hermes/                     HERMES_HOME — Hermes's own store
├── config.yaml                    Model, terminal, display, ... config
├── .env                           Provider API keys (ANTHROPIC_API_KEY, ...)
├── sessions/, logs/, skills/      Runtime data
└── auth.json                      OAuth tokens

/opt/hermes-mgmt/                  Management API
├── pyproject.toml
├── hermes_mgmt/                   Python package
└── .venv/                         uv-managed venv

/etc/hermes/config/                Provider + channel JSON templates (15+6)
├── anthropic.json    deepseek.json    google.json       groq.json
├── huggingface.json  kimi.json        mimo.json         minimax.json
├── mistral.json      nous-portal.json openai.json       openrouter.json
├── together.json     xai.json         zai.json
└── channels/
    ├── discord.json  email.json       signal.json
    ├── slack.json    telegram.json    whatsapp.json

/etc/systemd/system/
├── hermes.target
├── hermes-gateway.service
├── hermes-dashboard.service
├── hermes-mgmt.service
└── caddy.service.d/override.conf
```

## Vận hành hằng ngày

```bash
MGMT_KEY=$(grep ^HERMES_MGMT_API_KEY /opt/hermes/.env | cut -d= -f2)

# Status
systemctl status hermes-gateway hermes-dashboard hermes-mgmt caddy
curl -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/status

# Logs
journalctl -u hermes-gateway -f
journalctl -u hermes-mgmt -f
curl -H "Authorization: Bearer $MGMT_KEY" "http://localhost:9997/api/logs?service=hermes-gateway&lines=100"

# Configure messaging + model (first time)
hermes gateway setup
hermes model

# Via API
curl -X PUT -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"provider":"anthropic","model":"anthropic/claude-sonnet-4-6"}' \
  http://localhost:9997/api/config/provider

curl -X PUT -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"token":"<telegram-bot-token>"}' \
  http://localhost:9997/api/channels/telegram

# Restart
curl -X POST -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/restart

# Upgrade Hermes Agent (git pull + reinstall + restart gateway+dashboard)
curl -X POST -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/upgrade

# Upgrade management API itself (re-pulls /opt/hermes-mgmt sources + restart hermes-mgmt)
curl -X POST -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/upgrade-mgmt

# Get one-click dashboard URL (with ?token= for first visit, sets cookie)
curl -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/info \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['dashboard_url'])"
```

## Management API — tham chiếu đầy đủ

URL gốc: `http://<VPS-IP>:9997` (mở qua UFW, không nằm sau Caddy).
OpenAPI spec trực tiếp: `GET $BASE/openapi.json`.

### Xác thực

Tất cả các route trừ `GET /health`, `POST /api/auth/login` và `POST /api/auth/logout`
yêu cầu **một** trong hai:

- **Bearer token** — `Authorization: Bearer $HERMES_MGMT_API_KEY` (lâu dài, lấy từ `.env`)
- **Session cookie** — được đặt bởi `POST /api/auth/login` (mật khẩu bcrypt, phiên ký HMAC)

Giới hạn tốc độ: **10 lần đăng nhập thất bại mỗi IP / 15 phút → HTTP 429**.

### Envelope phản hồi

Mọi phản hồi JSON dùng cùng một cấu trúc:

```json
{ "ok": true,  "data": { ... }, "error": null }
{ "ok": false, "data": null,    "error": "Description of failure" }
```

Lỗi kiểm tra dữ liệu trả về `422` chuẩn của FastAPI với `{ "detail": [...] }`.

### Danh mục endpoint (73 route)

#### 1) Health & info (công khai + bearer)

| Phương thức | Đường dẫn | Xác thực | Mô tả |
|---|---|---|---|
| GET | `/health` | none | Kiểm tra liveness — trả về `{"ok": true, "version": "0.1.0"}` |
| GET | `/api/info` | bearer | Domain, IP công khai, phiên bản Hermes + mgmt, **`dashboard_url` một chạm kèm `?token=`**, `auth_token` thô |
| GET | `/api/status` | bearer | Trạng thái active/inactive của systemd cho từng dịch vụ Hermes |
| GET | `/api/version` | bearer | Toàn bộ output của `hermes version` |
| GET | `/api/system` | bearer | CPU%, bộ nhớ, đĩa, uptime, load avg (qua `psutil`) |
| GET | `/api/domain` | bearer | `DOMAIN` hiện tại trong `.env` |

```bash
curl -s -H "Authorization: Bearer $MGMT_KEY" http://<VPS-IP>:9997/api/info
# { "ok": true, "data": {
#     "domain":         "wxfparstk.hitechcloud.zone",
#     "ip":             "103.142.27.98",     # resolved live, not 127.0.0.1
#     "hermes_version": "Hermes Agent v0.13.0 (2026.5.7) ...",
#     "mgmt_version":   "0.1.0",
#     "dashboard_url":  "https://wxfparstk.hitechcloud.zone/?token=<AUTH_TOKEN>",
#     "auth_token":     "<AUTH_TOKEN>"       # null if HERMES_AUTH_TOKEN unset
# }, "error": null }
```

Các hệ thống provisioning (Hostbill, n8n, ...) có thể truyền thẳng
`dashboard_url` cho khách hàng cuối như một liên kết một chạm; Caddy đặt
cookie `hermes_auth` trong lần truy cập đầu và token bị loại khỏi lịch sử
trình duyệt nhờ chuyển hướng 302.

```bash
curl -s -H "Authorization: Bearer $MGMT_KEY" http://<VPS-IP>:9997/api/system
# { "ok": true, "data": {
#     "cpu_percent": 0.0,
#     "memory": {"total": 4105515008, "available": 3371732992, "percent": 17.9},
#     "disk":   {"total": 50884108288, "used": 4532400128, "percent": 8.9},
#     "uptime_seconds": 280146.58,
#     "load_avg": [0.28, 0.10, 0.03]
# }, "error": null }
```

#### 2) Xác thực (6)

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| POST | `/api/auth/login` | `{username, password}` | Trả về session cookie. 401 nếu sai mật khẩu, 429 sau 10 lần thất bại |
| POST | `/api/auth/logout` | — | Idempotent; xóa session cookie |
| GET | `/api/auth/user` | — | Người dùng đã xác thực hiện tại |
| POST | `/api/auth/create-user` | `{username, password}` | Tạo thêm tài khoản admin |
| PUT | `/api/auth/change-password` | `{old_password, new_password}` | Đổi mật khẩu |
| DELETE | `/api/auth/user` | — | Xóa tài khoản người dùng hiện tại |

#### 3) Điều khiển dịch vụ (7) — **có tính phá hủy**

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| POST | `/api/restart` | — | `systemctl restart hermes.target` |
| POST | `/api/stop` | — | Dừng toàn bộ dịch vụ Hermes |
| POST | `/api/start` | — | Khởi động toàn bộ dịch vụ Hermes |
| POST | `/api/rebuild` | — | `cd web && npm install && npm run build`, sau đó khởi động lại dashboard |
| POST | `/api/upgrade` | — | `git pull` Hermes Agent + `uv pip install -e '.[…]'` + khởi động lại gateway/dashboard. Trả về 202 Accepted; chạy nền |
| POST | `/api/upgrade-mgmt` | — | **Tự cập nhật**: tải lại toàn bộ nguồn `/opt/hermes-mgmt/` từ raw GitHub (hoặc `git pull` nếu đã checkout), cài lại qua `uv pip install -e .`, khởi động lại `hermes-mgmt.service`. Trả về 202 trước khi uvicorn khởi động lại |
| POST | `/api/reset` | `{"confirm":"RESET"}` | Xóa cấu hình + phiên (cần chuỗi confirm tường minh) |
| PUT | `/api/domain` | `{domain}` | Đổi `DOMAIN` trong `.env`, render lại Caddyfile, khởi động lại Caddy |

```bash
# Bootstrap the upgrade endpoint itself the first time (mgmt-api was installed
# before /api/upgrade-mgmt existed). All subsequent upgrades can use the API.
ssh root@<VPS> 'curl -fsSL https://raw.githubusercontent.com/hitechcloudvn/cloud-hermes-management/main/scripts/upgrade-mgmt.sh | bash'

# Once /api/upgrade-mgmt is live, upgrade in place via API:
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" \
  http://<VPS-IP>:9997/api/upgrade-mgmt
# { "ok": true, "data": {"message": "Management API upgrade started in background"} }
```

#### 4) Cấu hình (5)

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| GET | `/api/config` | — | Nội dung `config.yaml` hiện tại (API key được che thành `sk-****<last4>`) |
| GET | `/api/providers` | — | Liệt kê toàn bộ template `*.json` trong `/etc/hermes/config/` (mặc định 15) |
| PUT | `/api/config/provider` | `{provider, model}` | Đặt `model.default` (`<provider>/<bare-model>`) và `model.provider` trong `config.yaml`. Loại bỏ tiền tố `<provider>/` trùng lặp nếu người gọi đã thêm sẵn |
| PUT | `/api/config/api-key` | `{provider, api_key}` | Ghi `<PROVIDER>_API_KEY` vào `.env`, khởi động lại gateway |
| DELETE | `/api/config/api-key?provider=<p>` | — | Xóa API key khỏi `.env` |
| POST | `/api/config/test-key` | `{provider, api_key}` | `GET <base_url>/v1/models` (hoặc đường dẫn riêng của nhà cung cấp) — **không** lưu khóa |

```bash
# Test a key without saving
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"provider":"openai","api_key":"sk-..."}' \
  http://localhost:9997/api/config/test-key
# { "ok": true, "data": {"status_code": 200, "provider": "openai"}, "error": null }

# Set the active model (both forms are accepted and produce the same result)
curl -X PUT -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"provider":"deepseek","model":"deepseek-v4-flash"}' \
  http://localhost:9997/api/config/provider
# Equivalent:
#   -d '{"provider":"deepseek","model":"deepseek/deepseek-v4-flash"}'
```

#### 5) Kênh nhắn tin (3)

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| GET | `/api/channels` | — | Liệt kê các kênh nhắn tin đã cấu hình |
| PUT | `/api/channels/{channel}` | theo nhà cung cấp (vd. `{token, chat_id}` với Telegram) | Upsert cấu hình kênh trong `config.yaml` |
| DELETE | `/api/channels/{channel}` | — | Xóa kênh. Trả về 404 nếu chưa cấu hình |

Các `{channel}` được hỗ trợ: `telegram`, `discord`, `slack`, `signal`, `whatsapp`, `email`.

#### 6) Cron (6)

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| GET | `/api/cron` | — | Liệt kê mọi job `hermes cron` |
| GET | `/api/cron/status` | — | Trạng thái tổng hợp (số lượng đang chạy, tạm dừng, thất bại) |
| POST | `/api/cron` | `{name, schedule, prompt, ...}` | Tạo job mới |
| POST | `/api/cron/{job_id}/pause` | — | Tạm dừng job |
| POST | `/api/cron/{job_id}/resume` | — | Tiếp tục job đang tạm dừng |
| POST | `/api/cron/{job_id}/run` | — | Chạy job ngay lập tức |
| DELETE | `/api/cron/{job_id}` | — | Xóa job |

#### 7) Nhật ký (3)

| Phương thức | Đường dẫn | Query | Mô tả |
|---|---|---|---|
| GET | `/api/logs` | `service`, `lines`, `priority` | journalctl tail cho một dịch vụ |
| GET | `/api/logs/stream` | `service` | Luồng **SSE** — phát các dòng mới khi chúng xuất hiện |
| GET | `/api/logs/files` | — | Liệt kê tệp trong `/var/log/{caddy,hermes-install.log,…}` |

```bash
# Tail gateway logs (last 200)
curl -s -H "Authorization: Bearer $MGMT_KEY" \
  "http://localhost:9997/api/logs?service=hermes-gateway&lines=200"

# Live stream (SSE)
curl -N -H "Authorization: Bearer $MGMT_KEY" \
  "http://localhost:9997/api/logs/stream?service=hermes-gateway"
```

#### 8) Biến môi trường (3)

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| GET | `/api/env` | — | Toàn bộ khóa trong `/opt/hermes/.env` (giá trị nhạy cảm được che) |
| PUT | `/api/env/{key}` | `{value}` | Upsert một biến môi trường, ghi nguyên tử |
| DELETE | `/api/env/{key}` | — | Xóa một biến môi trường |

Các khóa khớp `/(_KEY|_TOKEN|_SECRET|_PASSWORD|_HASH)$/i` được trả về dạng
`sk-****<last4>` trong phản hồi GET.

#### 9) Chuyển tiếp Hermes CLI (1)

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| POST | `/api/cli` | `{subcommand, args}` | Chạy lệnh `hermes <sub>` trong whitelist và trả về stdout/stderr/exit code |

Whitelist: `version, status, doctor, config, model, cron, gateway, logs, skills, sessions, memory, tools, insights, auth`. Lệnh khác trả về `400`.

```bash
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"subcommand":"version","args":[]}' \
  http://localhost:9997/api/cli
# { "ok": true, "data": {"exit_code": 0, "stdout": "Hermes Agent v0.13.0 …", "stderr": ""}, "error": null }
```

#### 10) Kết nối Zalo cá nhân (6)

Plugin Zalo đi kèm một sidecar Node.js (zca-js) bind tại `127.0.0.1:3838` —
**không thể truy cập từ ngoài VPS**. Các route này proxy sidecar qua
Management API để người dùng ít chuyên môn kết nối Zalo hoàn toàn từ dashboard:
**quét QR → nhập số điện thoại của sếp → xong**. Không cần SSH, không `curl`,
không phải săn UID.

**Bot so với chủ (quan trọng):** tài khoản quét QR là **BOT** (một số phụ
gửi/nhắn thay mặt bot). **Chủ** là **sếp** — một tài khoản Zalo *khác*, nhắn
cho bot để ra lệnh quản trị. Vì vậy sau khi đăng nhập QR bạn phải cho API biết
chủ là ai, bằng **số điện thoại** (API phân giải thành UID qua sidecar). Plugin
Hermes sẽ không chạy nền tảng cho tới khi `ZALO_PERSONAL_OWNER_UID` được đặt;
việc đặt chủ sẽ kích hoạt plugin và khởi động lại gateway, từ đó gateway quản
lý sidecar (phiên đăng nhập được lưu trên đĩa).

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| POST | `/api/zalo/connect` | — | Bắt đầu đăng nhập QR. Khởi tạo sidecar nếu cần. `{status:"pending", qr_url:"/api/zalo/qr"}` (hoặc `{status:"connected", bot_uid}` nếu đã đăng nhập). `503` nếu sidecar không khởi động được |
| GET | `/api/zalo/qr` | — | Bytes **PNG** QR thô (dùng làm `<img src>`). `404` khi QR còn đang tạo; thử lại sau 1–2 giây kể từ `/connect` |
| GET | `/api/zalo/status` | — | Gọi polling endpoint này. `data`: `status` ∈ `disconnected/pending/scanned/connected/error`, `bot_uid` (tài khoản bot đã quét — **không** phải chủ), `name`, `sidecar` (bool), `owner_set` (bool — UID của sếp đã được cấu hình chưa) |
| POST | `/api/zalo/set-owner` | `{phone}` hoặc `{uid}` | Đặt sếp làm chủ. `phone` được phân giải thành UID qua sidecar đã kết nối (`/users/by-phones`); `uid` đặt trực tiếp. Sau đó kích hoạt plugin + khởi động lại gateway. `409` nếu bot chưa đăng nhập, `404` nếu số không có tài khoản Zalo |
| GET | `/api/zalo/owner` | — | Chủ hiện tại: `{owner_uid, owner_set}` |
| POST | `/api/zalo/disconnect` | — | Đăng xuất + xóa phiên Zalo |

Luồng trên dashboard:

```
[Kết nối Zalo]  → POST /api/zalo/connect
                → poll GET /api/zalo/status every ~2s
   pending      → show <img src="/api/zalo/qr"> + "Quét bằng app Zalo (số phụ)"
   connected, owner_set=false
                → ask: "Nhập số Zalo của SẾP (người điều khiển bot)"
                → POST /api/zalo/set-owner {phone}
   owner_set=true → "✅ Bot sẵn sàng. Sếp nhắn bot để ra lệnh; khách nhắn được tiếp."
```

```bash
# 1. Start QR login (spawns sidecar), then render /api/zalo/qr; scan with the
#    SECONDARY Zalo number that will be the bot.
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/zalo/connect

# 2. Poll until connected (bot_uid = the bot account, NOT the owner)
curl -s -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/zalo/status
# { "ok": true, "data": {"status":"connected","bot_uid":"555","sidecar":true,"owner_set":false}, ... }

# 3. Set the boss as owner by their phone number (resolved to a UID by the bot)
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"phone":"0901234567"}' http://localhost:9997/api/zalo/set-owner
# { "ok": true, "data": {"owner_uid":"boss123","owner_set":true}, "error": null }
```

> ⚠️ Zalo Web API không chính thức. **Dùng số phụ cho bot** — các thao tác
> kết bạn/gửi tin hàng loạt có nguy cơ bị khóa tài khoản. Được cài và bật theo
> mặc định (`--skip-zalo` để không cài). Bất kỳ ai cũng có thể nhắn cho bot
> không cần duyệt từng người (`ZALO_PERSONAL_ALLOW_ALL_USERS=true`); chủ sở hữu
> có các lệnh quản trị. Xem `/root/.hermes/plugins/zalo-personal/README.md`.

#### 11) Backend bộ nhớ OpenViking (12)

[OpenViking](https://github.com/volcengine/OpenViking) là một backend ngữ cảnh /
bộ nhớ tùy chọn — **không cài theo mặc định** (cần thêm RAM + khóa LLM cho
embedding/VLM). Dashboard điều khiển toàn bộ vòng đời theo yêu cầu, nên từng
khách hàng tự quyết định có cài hay không. Chạy trong venv cách ly tại
`/opt/hermes-openviking` với service riêng `hermes-openviking.service` trên
`127.0.0.1:1933`, nối vào Hermes qua `OPENVIKING_ENDPOINT`.

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| GET | `/api/openviking/status` | — | Trạng thái vòng đời: `installed`, `config_ready`, `service_active`, `healthy`, `wired_into_hermes`, `endpoint` |
| POST | `/api/openviking/install` | — | Chạy trình cài đặt ở chế độ nền (venv + `pip install openviking` + unit systemd). `202`; tái sử dụng `OPENAI_API_KEY` hiện có trong `.env` |
| GET | `/api/openviking/config` | — | `ov.conf` hiện tại (embedding + VLM), `api_key` được che. `{configured:false}` nếu chưa thiết lập |
| POST | `/api/openviking/config` | `{api_key, api_base?, embedding_model?, vlm_model?, provider?, dimension?}` | Ghi `~/.openviking/ov.conf` (embedding + VLM). Một `api_key` duy nhất được áp cho cả hai |
| POST | `/api/openviking/test-key` | `{api_key, api_base?}` | Kiểm tra khóa LLM (GET `<api_base>/models`) trước khi lưu. Không ghi bền lâu |
| POST | `/api/openviking/enable` | — | Khởi động service + đặt `OPENVIKING_ENDPOINT` + khởi động lại gateway. `409` nếu chưa cài hoặc chưa cấu hình |
| POST | `/api/openviking/disable` | — | Dừng service + gỡ `OPENVIKING_ENDPOINT` + khởi động lại gateway (giữ nguyên bản cài) |
| POST | `/api/openviking/restart` | — | Khởi động lại `hermes-openviking.service` (phục hồi server bị treo) |
| POST | `/api/openviking/upgrade` | — | `pip install --upgrade openviking` (nền) + khởi động lại. `202` |
| GET | `/api/openviking/stats` | — | `service_active`, `active_since`, `data_dir`, `data_size_mb`, `server_stats` trực tiếp (best-effort) |
| POST | `/api/openviking/uninstall` | `{purge?: bool}` | Ngắt kết nối + dừng + chạy trình gỡ cài ở nền. `purge=true` còn xóa cấu hình + dữ liệu |
| GET | `/api/openviking/logs` | `lines` (query, mặc định 100) | journal tail của `hermes-openviking.service` |

Luồng trên dashboard:

```
[Bật Memory nâng cao]
  → POST /api/openviking/install        (poll /status until installed=true)
  → POST /api/openviking/config {api_key}   (or rely on the reused OPENAI_API_KEY)
  → POST /api/openviking/enable         (poll /status until healthy=true)
[Tắt]      → POST /api/openviking/disable
[Gỡ]       → POST /api/openviking/uninstall {"purge": true}
```

```bash
# Install (background) then check
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" \
  http://localhost:9997/api/openviking/install
curl -s -H "Authorization: Bearer $MGMT_KEY" \
  http://localhost:9997/api/openviking/status
# { "ok": true, "data": {"installed": true, "config_ready": true,
#     "service_active": false, "healthy": false, "wired_into_hermes": false,
#     "endpoint": "http://127.0.0.1:1933"}, "error": null }

# Configure (only if no usable OPENAI_API_KEY was reused) + enable
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"api_key":"sk-..."}' http://localhost:9997/api/openviking/config
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" \
  http://localhost:9997/api/openviking/enable
```

#### 12) OpenAI Codex OAuth (4)

Đăng nhập bot vào **OpenAI Codex** (nhà cung cấp `openai-codex`) mà không cần
API key, ngay từ dashboard. Codex dùng luồng **device-code**: API khởi chạy
`hermes auth add openai-codex` ở chế độ headless, trả về một URL + mã ngắn;
người dùng mở URL, nhập mã, và tiến trình nền ghi token vào
`~/.hermes/auth.json`. Khi thành công bot được tự động chuyển sang nhà cung cấp
`codex`.

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| POST | `/api/codex/auth/start` | — | Bắt đầu đăng nhập device-code. Trả về `{status:"pending", url, code}` — hiển thị cả hai cho người dùng. Tiến trình tiếp tục polling ở nền |
| GET | `/api/codex/auth/status` | — | `disconnected` / `pending` (kèm `url`+`code`) / `connected`. Lần `connected` đầu tiên, đặt model.provider=codex trong `config.yaml` + khởi động lại gateway |
| POST | `/api/codex/auth/import` | `{auth_json}` | Phương án dự phòng — dán một `auth.json` từ Codex CLI / máy khác thay cho luồng device. Kiểm tra có mục codex, sau đó đặt model + khởi động lại |
| POST | `/api/codex/auth/disable` | `{to_provider?}` | Ngắt Codex: `hermes auth remove openai-codex`, xóa codex khỏi `auth.json` + `active_provider`, trỏ lại model.provider trong `config.yaml` (sang `to_provider` hoặc không có), khởi động lại gateway. Cần thiết vì `active_provider` của Codex ghi đè cấu hình — nếu không gỡ thì dashboard không thể đổi nhà cung cấp |

Luồng trên dashboard:

```
[Đăng nhập Codex]
  → POST /api/codex/auth/start          → show url + code
  → user opens url, enters code in browser
  → poll GET /api/codex/auth/status     → connected (bot now uses Codex)
```

```bash
# 1. Start — show the url + code to the user
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" \
  http://localhost:9997/api/codex/auth/start
# { "ok": true, "data": {"status": "pending",
#     "url": "https://auth.openai.com/codex/device", "code": "41R1-F6HEA"}, "error": null }

# 2. Poll until the user finishes in the browser
curl -s -H "Authorization: Bearer $MGMT_KEY" \
  http://localhost:9997/api/codex/auth/status
# { "ok": true, "data": {"status": "connected", "model_set": true}, "error": null }
```

#### 13) Vai trò agent & chính sách quy tắc (8)

Gán cho agent một **vai trò** (CSKH, kinh doanh, marketing, lễ tân, hoặc vai
trò tự tạo) ngay từ dashboard. Mỗi vai trò = persona + giọng điệu + một tập
**nhóm quy tắc**. Nhóm quy tắc là các tệp markdown (`config/rules/*.md`, 8
nhóm A–H); vai trò là yaml (`config/roles/*.yaml` preset,
`HERMES_HOME/roles/*.yaml` tự tạo). Áp dụng một vai trò sẽ lắp ráp system
prompt (persona + nội dung mọi quy tắc được bật), ghi vào
`HERMES_HOME/persona.md`, lưu `active_role.json`, và khởi động lại gateway.

Các nhóm quy tắc (bật/tắt theo vai trò): `a-identity`, `b-account-safety`,
`c-anti-spam-content`, `d-security-privacy`, `e-marketing-sales`,
`f-conversation-quality`, `g-tools-actions`, `h-operations-escalation`.

| Phương thức | Đường dẫn | Body | Mô tả |
|---|---|---|---|
| GET | `/api/rules` | — | Liệt kê mọi nhóm quy tắc (`id`, `title`, `body` markdown đầy đủ) |
| GET | `/api/rules/{group_id}` | — | Markdown của một nhóm quy tắc |
| GET | `/api/roles` | — | Liệt kê vai trò (preset + tự tạo) + id vai trò đang dùng |
| GET | `/api/roles/active` | — | Vai trò đang được áp dụng (`id`, `rules`, `applied_at`) |
| GET | `/api/roles/{role_id}` | — | Chi tiết vai trò (persona, giọng điệu, rules, nguồn) |
| POST | `/api/roles` | `{id, label?, description?, emoji?, tone?, persona, rules:[group_id...]}` | Tạo/cập nhật vai trò **tự tạo**. Rule id không xác định bị bỏ qua; không được đè lên id preset |
| DELETE | `/api/roles/{role_id}` | — | Xóa vai trò tự tạo (preset chỉ đọc → 403) |
| POST | `/api/roles/{role_id}/apply` | — | Lắp ráp persona + rules → ghi `persona.md` → khởi động lại gateway. Trả về `persona_preview` |

Luồng trên dashboard:

```
GET /api/roles                       → render role cards (active highlighted)
GET /api/rules                        → render the 8 rule-group toggles
[Tạo role]   → POST /api/roles {id, persona, rules:[...]}
[Áp dụng]    → POST /api/roles/{id}/apply   → bot adopts the role
```

```bash
# List roles + rule groups (for the GUI)
curl -s -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/roles
curl -s -H "Authorization: Bearer $MGMT_KEY" http://localhost:9997/api/rules

# Create a custom role picking which rule groups to enforce
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"id":"spa","label":"Lễ tân Spa","persona":"Bạn là lễ tân spa...",
       "rules":["a-identity","d-security-privacy","f-conversation-quality"]}' \
  http://localhost:9997/api/roles

# Apply it (assembles persona+rules, restarts gateway)
curl -s -X POST -H "Authorization: Bearer $MGMT_KEY" \
  http://localhost:9997/api/roles/spa/apply
```

### Kết quả kiểm thử API

Đã smoke-test trên một VPS cài thật ngày **2026-05-11**:

```
PASS: 34/34 tested endpoints
FAIL: 0
SKIP: 8  (destructive control + SSE stream — schema validated only)
```

| Hạng mục | Kết quả |
|---|---|
| Health / info (6 GET) | ✅ tất cả 200, cấu trúc JSON đã xác minh |
| Xác thực (5 endpoint) | ✅ login từ chối sai mật khẩu (401), body rỗng → 422, logout idempotent |
| Cấu hình (6 endpoint) | ✅ liệt kê 15 nhà cung cấp; `PUT /api/config/provider` idempotent với cả chuỗi model trần và có tiền tố (lỗi hồi quy đã sửa trong commit `64fd29f`) |
| Kênh (2 endpoint) | ✅ 404 với kênh không tồn tại; body PUT rỗng → 422 |
| Cron (3 endpoint) | ✅ list + status; body POST rỗng → 422 |
| Nhật ký (2 endpoint) | ✅ tail + files |
| Env (3 endpoint) | ✅ vòng PUT + DELETE tạm thời |
| CLI (1 endpoint) | ✅ passthrough `hermes version` |
| 404 theo path-param (6) | ✅ delete/pause với ID `__nonexistent__` được xử lý gọn |

Script smoke test: [`scripts/test-mgmt-api.sh`](scripts/test-mgmt-api.sh)
(bản sao tại `/tmp/test-mgmt-api.sh` khi triển khai).

## Bảo mật

- **Cổng:** UFW cho phép 22 (giới hạn tốc độ), 80, 443, 9997 — mọi cổng khác bị chặn
- **Token:** hex 64 ký tự tạo bằng `openssl rand -hex 32` (`HERMES_GATEWAY_TOKEN`, `HERMES_MGMT_API_KEY`, `HERMES_MGMT_SESSION_SECRET`)
- **Băm mật khẩu:** bcrypt (cost factor 12) cho mật khẩu `/login`
- **Giới hạn tốc độ:** 10 lần đăng nhập thất bại mỗi IP / 15 phút → 429
- **Che API key:** mọi phản hồi GET trả về `sk-****<last4>`
- **HSTS + CORS:** allowlist tường minh (không dùng wildcard), header nghiêm ngặt
- **fail2ban:** chống brute-force SSH

## Xử lý sự cố

### Dashboard / gateway không khởi động

```bash
journalctl -u hermes-dashboard --no-pager -n 50
journalctl -u hermes-gateway --no-pager -n 50

# First-time setup (if no provider configured):
hermes gateway setup
hermes model
hermes config show
```

### SSL thất bại

```bash
journalctl -u caddy --no-pager -n 50
dig +short $(grep ^DOMAIN /opt/hermes/.env | cut -d= -f2)
# Ensure DNS A record points to VPS IP, then:
systemctl restart caddy
```

### Rollback nâng cấp

```bash
# Hermes rollback to previous version
cd /opt/hermes/hermes-agent
git log -n 5 --oneline
git checkout <previous-sha>
/opt/hermes/hermes-agent/.venv/bin/uv pip install -e '.[web,messaging,cron,voice,mcp,honcho]'
systemctl restart hermes-gateway hermes-dashboard
```

### Đưa về trạng thái sạch

```bash
curl -X POST -H "Authorization: Bearer $MGMT_KEY" -H "Content-Type: application/json" \
  -d '{"confirm":"RESET"}' \
  http://localhost:9997/api/reset
```

## Phát triển

```bash
cd management-api
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e '.[dev]'
pytest -q tests/        # 63 tests
```

## Giấy phép

MIT. Xem `LICENSE`.

Không liên kết với Nous Research. Bản thân `hermes-agent` được Nous Research
phát hành theo giấy phép MIT.
